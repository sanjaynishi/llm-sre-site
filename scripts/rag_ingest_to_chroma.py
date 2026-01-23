#!/usr/bin/env python3
"""
Build a Chroma vector store from runbook PDFs stored in S3.

Outputs a persistent Chroma folder (local) that you will upload to S3.

Usage:
  export OPENAI_API_KEY="..."
  python scripts/rag_ingest_to_chroma.py \
    --bucket llm-sre-agent-config-dev-830330555687 \
    --pdf-prefix knowledge/runbooks/ \
    --persist-dir rag_store_dev \
    --collection runbooks_dev
"""

from __future__ import annotations
import argparse, os, json, re, hashlib
from typing import List
import boto3
from pypdf import PdfReader
import chromadb
from chromadb.config import Settings
from openai import OpenAI


def s3_list_pdfs(bucket: str, prefix: str) -> List[str]:
    s3 = boto3.client("s3")
    keys, token = [], None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []) or []:
            k = obj["Key"]
            if k.lower().endswith(".pdf"):
                keys.append(k)
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return sorted(keys)


def s3_download(bucket: str, key: str, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    boto3.client("s3").download_file(bucket, key, out_path)


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
    h = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--pdf-prefix", required=True)
    ap.add_argument("--persist-dir", required=True)
    ap.add_argument("--collection", required=True)
    ap.add_argument("--embed-model", default="text-embedding-3-small")
    ap.add_argument("--tmp-dir", default=".rag_tmp")
    args = ap.parse_args()

    os.makedirs(args.tmp_dir, exist_ok=True)

    client = OpenAI()

    chroma = chromadb.PersistentClient(
        path=args.persist_dir,
        settings=Settings(anonymized_telemetry=False),
    )
    col = chroma.get_or_create_collection(name=args.collection)

    pdf_keys = s3_list_pdfs(args.bucket, args.pdf_prefix)
    if not pdf_keys:
        raise SystemExit(f"No PDFs at s3://{args.bucket}/{args.pdf_prefix}")

    print(f"Found {len(pdf_keys)} PDFs")

    for key in pdf_keys:
        filename = os.path.basename(key)
        local_pdf = os.path.join(args.tmp_dir, filename)

        print(f"\n==> {key}")
        s3_download(args.bucket, key, local_pdf)

        raw = extract_pdf_text(local_pdf)
        text = clean_text(raw)
        chunks = chunk_text(text)

        if not chunks:
            print("  (no text extracted; skipping)")
            continue

        ids, docs, metas = [], [], []
        for idx, chunk in enumerate(chunks):
            ids.append(stable_id(args.bucket, key, str(idx)))
            docs.append(chunk)
            metas.append({"s3_bucket": args.bucket, "s3_key": key, "file": filename, "chunk": idx})

        batch = 64
        for i in range(0, len(docs), batch):
            d = docs[i:i+batch]
            emb = client.embeddings.create(model=args.embed_model, input=d)
            vectors = [e.embedding for e in emb.data]
            col.upsert(
                ids=ids[i:i+batch],
                documents=d,
                metadatas=metas[i:i+batch],
                embeddings=vectors,
            )

        print(f"  stored chunks: {len(chunks)}")

    print("\n✅ Done building Chroma store.")
    print(f"Persist dir: {args.persist_dir}")
    print(f"Collection: {args.collection}")
    print(f"Count: {col.count()}")


if __name__ == "__main__":
    main()