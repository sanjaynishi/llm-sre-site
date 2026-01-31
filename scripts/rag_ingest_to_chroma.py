#!/usr/bin/env python3
"""
Build a persistent Chroma vector store from runbook PDFs.

Modes:
  1) Local mode (recommended for DEV): ingest from DOCS/runbooks/**
  2) S3 mode (recommended for PROD artifact ingestion): ingest from s3://bucket/prefix

Outputs:
  A persistent Chroma folder (local) at --persist-dir

Examples:

DEV (local):
  export OPENAI_API_KEY="..."
  python scripts/rag_ingest_to_chroma.py \
    --local-dir DOCS/runbooks \
    --persist-dir rag_store_dev \
    --collection runbooks_dev

PROD (s3):
  export OPENAI_API_KEY="..."
  python scripts/rag_ingest_to_chroma.py \
    --bucket llm-sre-agent-config-prod-XXXXXXXXXXXX \
    --pdf-prefix knowledge/runbooks/ \
    --persist-dir rag_store_prod \
    --collection runbooks_prod
"""

from __future__ import annotations

import argparse, os, re, hashlib, time
from typing import List, Tuple, Optional

import boto3
from pypdf import PdfReader
import chromadb
from openai import OpenAI


# -------------------------
# Discovery helpers
# -------------------------

def s3_list_pdfs(bucket: str, prefix: str) -> List[str]:
    s3 = boto3.client("s3")
    keys, token = [], None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in (resp.get("Contents") or []):
            k = obj["Key"]
            if k.lower().endswith(".pdf"):
                keys.append(k)
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return sorted(keys)


def local_list_pdfs(root_dir: str) -> List[str]:
    pdfs = []
    for base, _, files in os.walk(root_dir):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdfs.append(os.path.join(base, f))
    return sorted(pdfs)


def s3_download(bucket: str, key: str, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    boto3.client("s3").download_file(bucket, key, out_path)


# -------------------------
# PDF + text processing
# -------------------------

def extract_pdf_text(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    parts = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        parts.append(f"\n\n--- Page {i+1} ---\n{text}")
    return "\n".join(parts)


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, max_chars: int = 2200, overlap: int = 250) -> List[str]:
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks


def stable_id(*parts: str) -> str:
    return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()


def safe_tmp_name(unique_key: str, filename: str) -> str:
    # Prevent collisions if filenames repeat across folders
    short = hashlib.sha1(unique_key.encode("utf-8")).hexdigest()[:10]
    return f"{short}-{filename}"


# -------------------------
# OpenAI embeddings (retry)
# -------------------------

def embed_with_retry(client: OpenAI, model: str, inputs: List[str], max_retries: int = 6) -> List[List[float]]:
    delay = 1.0
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.embeddings.create(model=model, input=inputs)
            return [e.embedding for e in resp.data]
        except Exception as e:
            if attempt == max_retries:
                raise
            # Basic exponential backoff
            time.sleep(delay)
            delay = min(delay * 2, 20.0)


# -------------------------
# Main
# -------------------------

def main():
    ap = argparse.ArgumentParser()
    # One of these modes must be used:
    ap.add_argument("--local-dir", help="Local folder to recursively ingest PDFs (e.g., DOCS/runbooks)")
    ap.add_argument("--bucket", help="S3 bucket containing PDFs")
    ap.add_argument("--pdf-prefix", help="S3 prefix containing PDFs")

    ap.add_argument("--persist-dir", required=True, help="Local folder to persist Chroma store")
    ap.add_argument("--collection", required=True, help="Chroma collection name")
    ap.add_argument("--embed-model", default="text-embedding-3-small")
    ap.add_argument("--tmp-dir", default=".rag_tmp")
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--reset-collection", action="store_true", help="Delete and rebuild the collection")

    args = ap.parse_args()

    # Validate mode
    local_mode = bool(args.local_dir)
    s3_mode = bool(args.bucket and args.pdf_prefix)
    if not (local_mode or s3_mode):
        raise SystemExit("Provide either --local-dir OR (--bucket AND --pdf-prefix).")

    os.makedirs(args.tmp_dir, exist_ok=True)

    # OpenAI client (reads OPENAI_API_KEY from env)
    client = OpenAI()

    # Chroma persistent store
    chroma = chromadb.PersistentClient(path=args.persist_dir)
    if args.reset_collection:
        try:
            chroma.delete_collection(name=args.collection)
        except Exception:
            pass
    col = chroma.get_or_create_collection(name=args.collection)

    # Discover PDFs
    items: List[Tuple[str, str]] = []
    # items = list of (source_key, local_path_to_pdf)

    if local_mode:
        root = args.local_dir
        pdf_paths = local_list_pdfs(root)
        if not pdf_paths:
            raise SystemExit(f"No PDFs found under: {root}")
        print(f"Found {len(pdf_paths)} PDFs (local): {root}")
        for p in pdf_paths:
            # source_key should be stable across machines: relative path from local-dir
            rel = os.path.relpath(p, root).replace("\\", "/")
            items.append((f"local::{rel}", p))

    if s3_mode:
        pdf_keys = s3_list_pdfs(args.bucket, args.pdf_prefix)
        if not pdf_keys:
            raise SystemExit(f"No PDFs at s3://{args.bucket}/{args.pdf_prefix}")
        print(f"Found {len(pdf_keys)} PDFs (s3): s3://{args.bucket}/{args.pdf_prefix}")
        for key in pdf_keys:
            filename = os.path.basename(key)
            tmp_name = safe_tmp_name(f"{args.bucket}/{key}", filename)
            local_pdf = os.path.join(args.tmp_dir, tmp_name)
            s3_download(args.bucket, key, local_pdf)
            items.append((f"s3://{args.bucket}/{key}", local_pdf))

    # Ingest
    for source_key, pdf_path in items:
        filename = os.path.basename(pdf_path)
        print(f"\n==> {source_key}")

        raw = extract_pdf_text(pdf_path)
        text = clean_text(raw)
        chunks = chunk_text(text)

        if not chunks:
            print("  (no text extracted; skipping)")
            continue

        ids, docs, metas = [], [], []
        for idx, chunk in enumerate(chunks):
            ids.append(stable_id(source_key, str(idx)))
            docs.append(chunk)
            metas.append({
                "source": source_key,
                "file": filename,
                "chunk": idx,
            })

        batch = max(1, args.batch)
        for i in range(0, len(docs), batch):
            d = docs[i:i + batch]
            vectors = embed_with_retry(client, args.embed_model, d)
            col.upsert(
                ids=ids[i:i + batch],
                documents=d,
                metadatas=metas[i:i + batch],
                embeddings=vectors,
            )

        print(f"  stored chunks: {len(chunks)}")

    print("\n✅ Done building Chroma store.")
    print(f"Persist dir: {args.persist_dir}")
    print(f"Collection: {args.collection}")
    print(f"Count: {col.count()}")


if __name__ == "__main__":
    main()