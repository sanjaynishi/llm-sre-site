"""
LLM SRE Agent API (Lambda)

Existing endpoints:
  GET  /api/agents
  POST /api/agent/run
  OPTIONS *

New RAG endpoint:
  POST /api/runbooks/ask
    body: { "question": "...", "top_k": 5 }

Vectors:
  Downloads Chroma persistent store from S3 into /tmp on cold start.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Tuple, List, Dict

try:
    import boto3
    from botocore.exceptions import ClientError
except Exception:
    boto3 = None
    ClientError = Exception

from openai import OpenAI

# Chroma deps are present because we're using container image
import chromadb
from chromadb.config import Settings


# ---------------- Config ----------------

ALLOWED_ORIGINS = {
    "https://dev.aimlsre.com",
    "https://aimlsre.com",
    "https://www.aimlsre.com",
}

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2").strip()

S3_BUCKET = os.environ.get("S3_BUCKET", "").strip()  # your config bucket
S3_PREFIX = os.environ.get("S3_PREFIX", "knowledge/").strip()

# RAG
VECTORS_PREFIX = os.environ.get("VECTORS_PREFIX", "knowledge/vectors/dev/chroma/").strip()
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "runbooks_dev").strip()
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small").strip()

# Local path in Lambda ephemeral storage
CHROMA_LOCAL_DIR = "/tmp/chroma_store"

# Warm caches
_s3 = None
_chroma_client = None
_chroma_collection = None
_openai_client = None


# ---------------- Helpers ----------------

def _s3_client():
    global _s3
    if boto3 is None:
        raise RuntimeError("boto3 not available")
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _pick_cors_origin(event: dict) -> str:
    headers = event.get("headers") or {}
    origin = headers.get("origin") or headers.get("Origin")
    return origin if origin in ALLOWED_ORIGINS else "*"


def _json_response(event: dict, status_code: int, body: dict, extra_headers: dict | None = None) -> dict:
    cors_origin = _pick_cors_origin(event)
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": cors_origin,
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }
    if extra_headers:
        headers.update(extra_headers)
    return {"statusCode": status_code, "headers": headers, "body": json.dumps(body)}


def _get_method(event: dict) -> str:
    return (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or ""
    ).upper()


def _get_path(event: dict) -> str:
    # HTTP API v2: rawPath; REST: path
    path = event.get("rawPath") or event.get("path") or "/"
    # If CloudFront forwards /api/* but API Gateway route expects /...,
    # you can normalize here if needed.
    if path.startswith("/api/"):
        path = path[4:]  # remove "/api"
    return path


def _get_body_json(event: dict) -> dict:
    body = event.get("body") or ""
    if not body:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return json.loads(body)


def _ensure_openai():
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


# ---------------- S3 download folder ----------------

def _s3_list_keys(bucket: str, prefix: str) -> List[str]:
    s3 = _s3_client()
    keys = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []) or []:
            k = obj["Key"]
            if not k.endswith("/"):
                keys.append(k)
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return keys


def _s3_download_prefix(bucket: str, prefix: str, local_dir: str) -> int:
    """
    Downloads all objects under prefix into local_dir (preserving relative paths).
    Returns number of files downloaded.
    """
    s3 = _s3_client()
    keys = _s3_list_keys(bucket, prefix)
    if not keys:
        raise RuntimeError(f"No objects found at s3://{bucket}/{prefix}")

    # clean target dir
    if os.path.isdir(local_dir):
        shutil.rmtree(local_dir, ignore_errors=True)
    os.makedirs(local_dir, exist_ok=True)

    count = 0
    for key in keys:
        rel = key[len(prefix):].lstrip("/")
        dest = os.path.join(local_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        s3.download_file(bucket, key, dest)
        count += 1
    return count


# ---------------- Chroma init/query ----------------

def _ensure_chroma():
    """
    Cold-start: download vector store from S3 -> /tmp, then open Chroma.
    Warm-start: reuse globals.
    """
    global _chroma_client, _chroma_collection

    if _chroma_collection is not None:
        return _chroma_collection

    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET env var missing")
    if not VECTORS_PREFIX:
        raise RuntimeError("VECTORS_PREFIX env var missing")

    # Download store on first use
    downloaded = _s3_download_prefix(S3_BUCKET, VECTORS_PREFIX, CHROMA_LOCAL_DIR)

    _chroma_client = chromadb.PersistentClient(
        path=CHROMA_LOCAL_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    _chroma_collection = _chroma_client.get_collection(CHROMA_COLLECTION)

    # simple sanity check
    _ = _chroma_collection.count()
    return _chroma_collection


def _embed_text(text: str) -> List[float]:
    client = _ensure_openai()
    emb = client.embeddings.create(model=EMBED_MODEL, input=[text])
    return emb.data[0].embedding


def _retrieve_chunks(question: str, top_k: int = 5) -> List[Dict[str, Any]]:
    col = _ensure_chroma()
    q_emb = _embed_text(question)

    res = col.query(
        query_embeddings=[q_emb],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    out = []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    for doc, meta, dist in zip(docs, metas, dists):
        out.append({
            "text": doc,
            "meta": meta,
            "distance": dist,
        })
    return out


def _answer_with_llm(question: str, contexts: List[Dict[str, Any]]) -> str:
    client = _ensure_openai()

    # Build context block with light citations
    ctx_lines = []
    for i, c in enumerate(contexts, start=1):
        meta = c.get("meta") or {}
        src = meta.get("file") or meta.get("s3_key") or "runbook"
        chunk = meta.get("chunk")
        label = f"[{i}] {src} (chunk {chunk})"
        ctx_lines.append(f"{label}\n{c.get('text','')}\n")

    context_block = "\n".join(ctx_lines)[:14000]  # keep prompt bounded

    prompt = f"""
You are an SRE runbook assistant. Answer the user's question using ONLY the provided runbook excerpts.
If the excerpts do not contain the answer, say what is missing and what to check next.

Write like a calm human SRE:
- Start with a 1-2 sentence summary
- Then give step-by-step actions
- Include commands/snippets when helpful
- End with "If still failing" next checks
- Cite sources using [1], [2], etc.

User question:
{question}

Runbook excerpts:
{context_block}
""".strip()

    resp = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
        max_output_tokens=700,
    )

    # Extract output text
    out_text = ""
    for item in resp.output or []:
        if getattr(item, "type", None) == "message":
            for c in item.content or []:
                if getattr(c, "type", None) in ("output_text", "text"):
                    out_text += c.text or ""
    out_text = (out_text or "").strip() or (getattr(resp, "output_text", "") or "").strip()
    return out_text or "No answer returned."


# ---------------- Handlers ----------------

def _handle_post_runbooks_ask(event: dict) -> dict:
    req = _get_body_json(event)
    question = (req.get("question") or "").strip()
    top_k = int(req.get("top_k") or 5)

    if not question:
        return _json_response(event, 400, {"error": {"code": "MISSING_QUESTION", "message": "question is required"}})

    if top_k < 1 or top_k > 10:
        top_k = 5

    contexts = _retrieve_chunks(question, top_k=top_k)
    answer = _answer_with_llm(question, contexts)

    return _json_response(event, 200, {
        "question": question,
        "top_k": top_k,
        "sources": [
            {"file": (c["meta"] or {}).get("file"), "s3_key": (c["meta"] or {}).get("s3_key"), "chunk": (c["meta"] or {}).get("chunk")}
            for c in contexts
        ],
        "answer": answer
    })


# ---------------- Lambda entry ----------------

def lambda_handler(event: dict, context: Any) -> dict:
    method = _get_method(event)
    path = _get_path(event)

    if method == "OPTIONS":
        return _json_response(event, 200, {"ok": True})

    if method == "POST" and path == "/runbooks/ask":
        try:
            return _handle_post_runbooks_ask(event)
        except Exception as e:
            return _json_response(event, 500, {"error": {"code": "RAG_FAILED", "message": str(e)}})

    return _json_response(event, 404, {"error": {"code": "NOT_FOUND", "message": f"Route not found: {path}"}})