#!/usr/bin/env python3
"""
Incremental Chroma index builder for Runbooks (S3 -> Chroma -> S3)

What it does:
1) Lists PDFs under s3://S3_BUCKET/(S3_PREFIX/RUNBOOKS_PREFIX)
2) Loads a manifest JSON from S3 that stores last-seen metadata (etag/size/last_modified)
3) Computes diffs:
   - NEW PDFs -> index
   - CHANGED PDFs -> delete prior vectors for that pdf, re-index
   - REMOVED PDFs -> delete vectors for that pdf
4) Downloads existing Chroma store from S3 (VECTORS_PREFIX) unless --rebuild
5) Updates local Chroma store
6) Uploads updated Chroma store back to S3 (VECTORS_PREFIX) unless --dry-run
7) Writes updated manifest back to S3 unless --dry-run

Dry run:
  python scripts/build_chroma_index.py --dry-run

Rebuild:
  python scripts/build_chroma_index.py --rebuild

Create the following environment variables before running:
export S3_BUCKET="llm-sre-agent-config-dev-830330555687"
export S3_PREFIX="knowledge"
export RUNBOOKS_PREFIX="runbooks/"
export VECTORS_PREFIX="knowledge/vectors/dev/chroma/"
export CHROMA_COLLECTION="runbooks_dev"
export EMBED_MODEL="text-embedding-3-small"
export OPENAI_API_KEY="sk-...."   # not required for dry-run but ok

python scripts/build_chroma_index.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError
from pypdf import PdfReader

# --- sqlite shim (only needed in Lambda; safe locally) ---
try:
    import pysqlite3  # type: ignore
    sys.modules["sqlite3"] = pysqlite3
except Exception:
    pass

import chromadb
from chromadb.config import Settings
from openai import OpenAI


# ---------------------------
# Config (env vars)
# ---------------------------
S3_BUCKET = os.environ.get("S3_BUCKET", "").strip()
S3_PREFIX = os.environ.get("S3_PREFIX", "").lstrip("/").strip()              # e.g. "knowledge"
RUNBOOKS_PREFIX = os.environ.get("RUNBOOKS_PREFIX", "runbooks/").lstrip("/").strip()  # "runbooks/"
VECTORS_PREFIX = os.environ.get("VECTORS_PREFIX", "knowledge/vectors/dev/chroma_v2/").lstrip("/").strip()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small").strip()
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "runbooks_dev").strip()

LOCAL_CHROMA_DIR = os.environ.get("LOCAL_CHROMA_DIR", "./chroma_store").strip()
LOCAL_TMP_RUNBOOK_DIR = os.environ.get("LOCAL_TMP_RUNBOOK_DIR", "./.tmp_runbooks").strip()

CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "200"))
EMBED_BATCH_SIZE = int(os.environ.get("EMBED_BATCH_SIZE", "64"))

# Manifest location (recommended to keep INSIDE vectors prefix)
# Default: s3://bucket/<VECTORS_PREFIX>/manifest.json
MANIFEST_KEY = os.environ.get("MANIFEST_KEY", f"{VECTORS_PREFIX.rstrip('/')}/manifest.json").lstrip("/").strip()


# ---------------------------
# Data structures
# ---------------------------
@dataclass(frozen=True)
class S3PdfMeta:
    key: str
    etag: str
    size: int
    last_modified: str  # isoformat

    @staticmethod
    def from_head_or_list_obj(obj: Dict[str, Any]) -> "S3PdfMeta":
        # list_objects_v2 "Contents" has ETag only via head_object, but many people want to avoid head calls.
        # We'll do HEAD to get stable etag for diffing.
        raise NotImplementedError


# ---------------------------
# Helpers: S3 key join
# ---------------------------
def s3_join(prefix: str, path: str) -> str:
    prefix = (prefix or "").strip().strip("/")
    path = (path or "").strip().lstrip("/")
    if not prefix:
        return path
    if not path:
        return prefix
    return f"{prefix}/{path}"


def runbooks_prefix_full() -> str:
    # e.g. knowledge/runbooks/
    p = s3_join(S3_PREFIX, RUNBOOKS_PREFIX)
    return p.rstrip("/") + "/"


def vectors_prefix_full() -> str:
    return VECTORS_PREFIX.rstrip("/") + "/"


# ---------------------------
# Helpers: PDF parsing + chunking
# ---------------------------
def pdf_to_text(path: str) -> str:
    reader = PdfReader(path)
    parts: List[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks: List[str] = []
    i = 0
    step = max(1, chunk_size - overlap)
    while i < len(text):
        chunks.append(text[i : i + chunk_size])
        i += step
    return chunks


def stable_chunk_id(s3_key: str, chunk_index: int) -> str:
    # Stable per file/chunk position; we DELETE all chunks for a file before re-adding on changes,
    # so stable IDs are enough (no stale chunks remain).
    raw = f"{s3_key}::chunk::{chunk_index}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


# ---------------------------
# Helpers: S3 operations
# ---------------------------
def s3_client():
    return boto3.client("s3")


def s3_list_pdfs(bucket: str, prefix: str) -> List[str]:
    s3 = s3_client()
    keys: List[str] = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []) or []:
            k = obj.get("Key") or ""
            if k.lower().endswith(".pdf"):
                keys.append(k)
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return sorted(keys)


def s3_head_pdf_meta(bucket: str, key: str) -> Dict[str, Any]:
    s3 = s3_client()
    resp = s3.head_object(Bucket=bucket, Key=key)
    etag = (resp.get("ETag") or "").replace('"', "")
    size = int(resp.get("ContentLength") or 0)
    lm = resp.get("LastModified")
    lm_iso = lm.isoformat() if lm else ""
    return {"key": key, "etag": etag, "size": size, "last_modified": lm_iso}


def s3_get_json(bucket: str, key: str) -> Dict[str, Any]:
    s3 = s3_client()
    try:
        resp = s3.get_object(Bucket=bucket, Key=key)
        raw = resp["Body"].read().decode("utf-8")
        return json.loads(raw)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return {}
        raise


def s3_put_json(bucket: str, key: str, data: Dict[str, Any]) -> None:
    s3 = s3_client()
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def s3_download_prefix(bucket: str, prefix: str, local_dir: str) -> int:
    s3 = s3_client()
    prefix = prefix.rstrip("/") + "/"
    token = None
    keys: List[str] = []
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []) or []:
            k = obj.get("Key") or ""
            if k.endswith("/"):
                continue
            keys.append(k)
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break

    if not keys:
        return 0

    if os.path.isdir(local_dir):
        shutil.rmtree(local_dir, ignore_errors=True)
    os.makedirs(local_dir, exist_ok=True)

    count = 0
    for k in keys:
        rel = k[len(prefix):].lstrip("/")
        dest = os.path.join(local_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        s3.download_file(bucket, k, dest)
        count += 1
    return count


def s3_upload_dir(bucket: str, prefix: str, local_dir: str) -> int:
    s3 = s3_client()
    prefix = prefix.rstrip("/") + "/"
    count = 0
    for root, _, files in os.walk(local_dir):
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, local_dir).replace("\\", "/")
            key = prefix + rel
            s3.upload_file(full, bucket, key)
            count += 1
    return count


# ---------------------------
# Diff logic
# ---------------------------
def build_current_state(bucket: str, pdf_keys: List[str]) -> Dict[str, Dict[str, Any]]:
    current: Dict[str, Dict[str, Any]] = {}
    for k in pdf_keys:
        meta = s3_head_pdf_meta(bucket, k)
        current[k] = meta
    return current


def compute_diff(
    previous: Dict[str, Dict[str, Any]],
    current: Dict[str, Dict[str, Any]],
) -> Tuple[List[str], List[str], List[str]]:
    prev_keys = set(previous.keys())
    cur_keys = set(current.keys())

    added = sorted(cur_keys - prev_keys)
    removed = sorted(prev_keys - cur_keys)

    changed: List[str] = []
    for k in sorted(cur_keys & prev_keys):
        p = previous.get(k, {})
        c = current.get(k, {})
        # Prefer ETag; fallback to size/last_modified
        if (p.get("etag") and c.get("etag") and p.get("etag") != c.get("etag")):
            changed.append(k)
        else:
            if (p.get("size") != c.get("size")) or (p.get("last_modified") != c.get("last_modified")):
                changed.append(k)

    return added, changed, removed


# ---------------------------
# Chroma operations
# ---------------------------
def open_chroma(local_dir: str):
    os.makedirs(local_dir, exist_ok=True)
    client = chromadb.PersistentClient(
        path=local_dir,
        settings=Settings(anonymized_telemetry=False),
    )
    col = client.get_or_create_collection(CHROMA_COLLECTION)
    return client, col


def chroma_delete_pdf(collection, s3_key: str, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY-RUN: would delete vectors where s3_key == {s3_key}")
        return
    # chroma supports where filtering on metadata
    collection.delete(where={"s3_key": s3_key})


def chroma_index_pdf(
    collection,
    openai_client: OpenAI,
    bucket: str,
    s3_key: str,
    dry_run: bool,
) -> Tuple[int, int]:
    """
    Returns (chunks_added, embed_calls_batches)
    """
    filename = s3_key.split("/")[-1]
    os.makedirs(LOCAL_TMP_RUNBOOK_DIR, exist_ok=True)
    local_pdf = os.path.join(LOCAL_TMP_RUNBOOK_DIR, f"{uuid.uuid4()}__{filename}")

    # Download
    if dry_run:
        print(f"DRY-RUN: would download s3://{bucket}/{s3_key} -> {local_pdf}")
    else:
        s3_client().download_file(bucket, s3_key, local_pdf)

    # Parse + chunk
    text = "" if dry_run else pdf_to_text(local_pdf)
    chunks = [] if dry_run else chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)

    if not chunks and not dry_run:
        print(f"Skip (no text extracted): {s3_key}")
        return 0, 0

    if dry_run:
        # Estimate chunk count without reading PDF (we can’t safely estimate); print intent only.
        print(f"DRY-RUN: would extract text + chunk + embed + add to Chroma for: {s3_key}")
        return 0, 0

    # Embed + upsert (after delete, add is fine too; upsert is safer)
    total_added = 0
    batches = 0

    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start : start + EMBED_BATCH_SIZE]
        emb = openai_client.embeddings.create(model=EMBED_MODEL, input=batch)
        vectors = [d.embedding for d in emb.data]
        batches += 1

        ids = [stable_chunk_id(s3_key, start + i) for i in range(len(batch))]
        metas = [{"s3_key": s3_key, "file": filename, "chunk": start + i} for i in range(len(batch))]

        # In chromadb, upsert exists in newer versions; add may fail if IDs exist.
        # Since we delete first for changed files, add should be OK. Upsert is extra-safe.
        if hasattr(collection, "upsert"):
            collection.upsert(ids=ids, documents=batch, metadatas=metas, embeddings=vectors)
        else:
            collection.add(ids=ids, documents=batch, metadatas=metas, embeddings=vectors)

        total_added += len(batch)

    # Cleanup PDF
    try:
        os.remove(local_pdf)
    except Exception:
        pass

    return total_added, batches


# ---------------------------
# Main
# ---------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Print actions only; do not modify Chroma or S3")
    ap.add_argument("--rebuild", action="store_true", help="Ignore existing Chroma store; rebuild local store from scratch")
    ap.add_argument("--max-pdfs", type=int, default=0, help="Limit number of PDFs processed (0 = no limit)")
    args = ap.parse_args()

    if not S3_BUCKET:
        raise SystemExit("S3_BUCKET env var is required")
    if not OPENAI_API_KEY and not args.dry_run:
        raise SystemExit("OPENAI_API_KEY env var is required (or use --dry-run)")
    if not VECTORS_PREFIX:
        raise SystemExit("VECTORS_PREFIX env var is required")

    run_prefix = runbooks_prefix_full()
    vec_prefix = vectors_prefix_full()

    print(f"Runbooks prefix : s3://{S3_BUCKET}/{run_prefix}")
    print(f"Vectors prefix  : s3://{S3_BUCKET}/{vec_prefix}")
    print(f"Manifest key    : s3://{S3_BUCKET}/{MANIFEST_KEY}")
    print(f"Local Chroma dir: {LOCAL_CHROMA_DIR}")
    print(f"Dry run         : {args.dry_run}")
    print(f"Rebuild         : {args.rebuild}")
    print("----")

    # Load manifest (previous state)
    manifest = s3_get_json(S3_BUCKET, MANIFEST_KEY)
    previous_files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}

    # Current runbooks list
    pdf_keys = s3_list_pdfs(S3_BUCKET, run_prefix)
    if args.max_pdfs and args.max_pdfs > 0:
        pdf_keys = pdf_keys[: args.max_pdfs]

    if not pdf_keys:
        raise SystemExit(f"No PDFs found under s3://{S3_BUCKET}/{run_prefix}")

    # Build current metadata state (HEAD calls)
    print(f"Listing {len(pdf_keys)} PDFs and fetching HEAD metadata...")
    current_files = build_current_state(S3_BUCKET, pdf_keys)

    added, changed, removed = compute_diff(previous_files, current_files)

    print(f"Diff results: added={len(added)} changed={len(changed)} removed={len(removed)}")
    if added:
        print("  Added:")
        for k in added[:20]:
            print(f"    + {k}")
        if len(added) > 20:
            print(f"    ... +{len(added)-20} more")
    if changed:
        print("  Changed:")
        for k in changed[:20]:
            print(f"    ~ {k}")
        if len(changed) > 20:
            print(f"    ... +{len(changed)-20} more")
    if removed:
        print("  Removed:")
        for k in removed[:20]:
            print(f"    - {k}")
        if len(removed) > 20:
            print(f"    ... +{len(removed)-20} more")

    # If nothing changed, exit early (still can validate store exists)
    if not (added or changed or removed):
        print("No changes detected. Nothing to index.")
        return

    # Prepare local chroma store
    if args.rebuild:
        if os.path.isdir(LOCAL_CHROMA_DIR):
            shutil.rmtree(LOCAL_CHROMA_DIR, ignore_errors=True)
        os.makedirs(LOCAL_CHROMA_DIR, exist_ok=True)
        print("Rebuild requested: local Chroma store cleared.")
    else:
        # Download existing store from S3 if present
        if args.dry_run:
            print(f"DRY-RUN: would download existing Chroma store from s3://{S3_BUCKET}/{vec_prefix} -> {LOCAL_CHROMA_DIR}")
        else:
            downloaded = s3_download_prefix(S3_BUCKET, vec_prefix, LOCAL_CHROMA_DIR)
            print(f"Downloaded {downloaded} objects from existing Chroma store (0 means new store).")

    # Open chroma
    _, collection = open_chroma(LOCAL_CHROMA_DIR)

    # OpenAI client (unless dry-run)
    openai_client = OpenAI(api_key=OPENAI_API_KEY) if not args.dry_run else None

    # Apply removals
    for k in removed:
        chroma_delete_pdf(collection, k, args.dry_run)

    # Apply changes + additions
    to_process = changed + added
    total_chunks = 0
    total_batches = 0

    for k in to_process:
        # delete old chunks first (safe for both added/changed)
        chroma_delete_pdf(collection, k, args.dry_run)

        chunks_added, batches = (0, 0)
        if not args.dry_run:
            assert openai_client is not None
            chunks_added, batches = chroma_index_pdf(collection, openai_client, S3_BUCKET, k, args.dry_run)

        total_chunks += chunks_added
        total_batches += batches
        print(f"Indexed: {k}  chunks={chunks_added}  embed_batches={batches}")

    # Save updated manifest
    new_manifest = {
        "schema": 1,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bucket": S3_BUCKET,
        "runbooks_prefix": run_prefix,
        "vectors_prefix": vec_prefix,
        "collection": CHROMA_COLLECTION,
        "embed_model": EMBED_MODEL,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "files": current_files,  # only current PDFs
    }

    # Upload store + manifest
    if args.dry_run:
        print(f"DRY-RUN: would upload local Chroma store -> s3://{S3_BUCKET}/{vec_prefix}")
        print(f"DRY-RUN: would write manifest -> s3://{S3_BUCKET}/{MANIFEST_KEY}")
    else:
        # Upload store
        uploaded = s3_upload_dir(S3_BUCKET, vec_prefix, LOCAL_CHROMA_DIR)
        print(f"Uploaded {uploaded} objects to s3://{S3_BUCKET}/{vec_prefix}")

        # Write manifest
        s3_put_json(S3_BUCKET, MANIFEST_KEY, new_manifest)
        print(f"Wrote manifest: s3://{S3_BUCKET}/{MANIFEST_KEY}")

    try:
        print(f"Collection count now: {collection.count()}")
    except Exception:
        pass

    print("Done.")
    if not args.dry_run:
        print(f"Embedded chunks: {total_chunks} across {total_batches} embedding batch calls")


if __name__ == "__main__":
    main()