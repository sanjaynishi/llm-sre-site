"""
lambda/app.py

Minimal Lambda API for:
  GET  /api/health
  GET  /api/runbooks
  GET  /api/doc?name=FILE.pdf   (or ?key=full/s3/key.pdf)
  GET  /api/agents
  POST /api/runbooks/ask        (Chroma RAG; requires chromadb + pysqlite3-binary + OpenAI)

Notes:
- CloudFront routes /api/* to API Gateway; this handler normalizes "/api" away.
- Includes sqlite shim for Chroma (Lambda base sqlite is too old).
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError

# --- sqlite shim for Chroma (Lambda has old sqlite3) ---
# IMPORTANT: keep this before any potential chromadb/sqlite import.
try:
    import pysqlite3  # provided by pysqlite3-binary
    sys.modules["sqlite3"] = pysqlite3
except Exception:
    # If this fails, Chroma may fail later with sqlite version error
    pass

s3 = boto3.client("s3")

# =====================
# Environment variables
# =====================
S3_BUCKET = os.environ.get("S3_BUCKET", "").strip()
S3_PREFIX = os.environ.get("S3_PREFIX", "").lstrip("/")  # e.g. "knowledge/"
RUNBOOKS_PREFIX = os.environ.get("RUNBOOKS_PREFIX", "runbooks/").lstrip("/")
AGENTS_KEY = os.environ.get("AGENTS_KEY", "agents.json").lstrip("/")

# RAG / Chroma
VECTORS_PREFIX = os.environ.get("VECTORS_PREFIX", "knowledge/vectors/dev/chroma/").lstrip("/")
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "runbooks_dev").strip()
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small").strip()

# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2").strip()

CHROMA_LOCAL_DIR = "/tmp/chroma_store"

# =====================
# Helpers
# =====================

def _s3_key(path: str) -> str:
    """Build full S3 key using S3_PREFIX."""
    if not S3_PREFIX:
        return path.lstrip("/")
    return f"{S3_PREFIX.rstrip('/')}/{path.lstrip('/')}"


def _pick_origin(event: dict) -> str:
    # Keep it permissive for now (your CloudFront already controls origins).
    # If you want strict allowlist later, plug it in here.
    headers = event.get("headers") or {}
    return headers.get("origin") or headers.get("Origin") or "*"


def _response(event: dict, status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": "*",  # or _pick_origin(event)
            "access-control-allow-methods": "GET,POST,OPTIONS",
            "access-control-allow-headers": "Content-Type,Authorization",
            "vary": "Origin",
        },
        "body": json.dumps(body),
    }


def _get_method(event: dict) -> str:
    return (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or "GET"
    ).upper()


def _get_path(event: dict) -> str:
    # HTTP API v2 uses rawPath. CloudFront sends /api/* to API GW.
    path = event.get("rawPath") or event.get("path") or "/"
    if path.startswith("/api/"):
        path = path[4:]  # remove "/api"
    return path


def _get_qs(event: dict) -> dict:
    return event.get("queryStringParameters") or {}


def _get_body_json(event: dict) -> dict:
    body = event.get("body") or ""
    if not body:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", errors="replace")
    return json.loads(body)


def _get_object_text(bucket: str, key: str) -> str:
    obj = s3.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read().decode("utf-8", errors="replace")


def _get_object_json(bucket: str, key: str) -> dict:
    return json.loads(_get_object_text(bucket, key))


def _list_prefix(bucket: str, prefix: str) -> List[dict]:
    """List all objects under prefix (handles pagination)."""
    out: List[dict] = []
    token = None
    while True:
        kwargs: Dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        out.extend(resp.get("Contents", []) or [])
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return out


def _download_prefix(bucket: str, prefix: str, local_dir: str) -> int:
    """Download all objects under s3://bucket/prefix -> local_dir."""
    objs = _list_prefix(bucket, prefix)
    keys = [o["Key"] for o in objs if o.get("Key") and not o["Key"].endswith("/")]
    if not keys:
        raise RuntimeError(f"No objects found at s3://{bucket}/{prefix}")

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


# =====================
# RAG (Chroma + OpenAI)
# =====================

_chroma_collection = None
_openai_client = None


def _ensure_openai():
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")

    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError(f"OpenAI SDK not installed. Import error: {e}") from e

    _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def _ensure_chroma():
    global _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection

    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET env var missing")
    if not VECTORS_PREFIX:
        raise RuntimeError("VECTORS_PREFIX env var missing")

    vectors_prefix = _s3_key(VECTORS_PREFIX)

    # Download persisted Chroma store from S3 -> /tmp
    _download_prefix(S3_BUCKET, vectors_prefix, CHROMA_LOCAL_DIR)

    try:
        import chromadb  # type: ignore
        from chromadb.config import Settings  # type: ignore
    except Exception as e:
        raise RuntimeError(f"chromadb not installed in this Lambda image. Import error: {e}") from e

    client = chromadb.PersistentClient(
        path=CHROMA_LOCAL_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    _chroma_collection = client.get_collection(CHROMA_COLLECTION)
    _ = _chroma_collection.count()
    return _chroma_collection


def _embed(text: str) -> List[float]:
    client = _ensure_openai()
    emb = client.embeddings.create(model=EMBED_MODEL, input=[text])
    return emb.data[0].embedding


def _retrieve(question: str, top_k: int) -> List[dict]:
    col = _ensure_chroma()
    q = _embed(question)

    res = col.query(
        query_embeddings=[q],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        out.append({"text": doc, "meta": meta or {}, "distance": dist})
    return out


def _answer(question: str, contexts: List[dict]) -> str:
    client = _ensure_openai()

    ctx_lines = []
    for i, c in enumerate(contexts, start=1):
        meta = c.get("meta") or {}
        src = meta.get("file") or meta.get("s3_key") or "runbook"
        chunk = meta.get("chunk")
        label = f"[{i}] {src}" + (f" (chunk {chunk})" if chunk is not None else "")
        ctx_lines.append(f"{label}\n{c.get('text','')}\n")

    context_block = "\n".join(ctx_lines)[:14000]

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

    out_text = ""
    for item in resp.output or []:
        if getattr(item, "type", None) == "message":
            for c in item.content or []:
                if getattr(c, "type", None) in ("output_text", "text"):
                    out_text += c.text or ""
    out_text = (out_text or "").strip() or (getattr(resp, "output_text", "") or "").strip()
    return out_text or "No answer returned."


# =====================
# Lambda handler
# =====================

def lambda_handler(event, context):
    # Handle CORS preflight
    if _get_method(event) == "OPTIONS":
        return _response(event, 200, {"ok": True})

    method = _get_method(event)
    path = _get_path(event)

    try:
        # -----------------
        # Health check
        # -----------------
        if path == "/health" and method == "GET":
            return _response(event, 200, {
                "ok": True,
                "bucket": S3_BUCKET,
                "prefix": S3_PREFIX,
                "runbooks_prefix": _s3_key(RUNBOOKS_PREFIX),
                "vectors_prefix": _s3_key(VECTORS_PREFIX),
                "chroma_collection": CHROMA_COLLECTION,
                "embed_model": EMBED_MODEL,
            })

        # -----------------
        # List runbooks
        # GET /runbooks
        # -----------------
        if path == "/runbooks" and method == "GET":
            if not S3_BUCKET:
                return _response(event, 500, {"error": "S3_BUCKET not set"})

            prefix = _s3_key(RUNBOOKS_PREFIX)
            objs = _list_prefix(S3_BUCKET, prefix)

            runbooks = []
            for obj in objs:
                key = obj.get("Key", "")
                if key.lower().endswith(".pdf"):
                    runbooks.append({
                        "name": key.split("/")[-1],
                        "key": key,
                        "size": obj.get("Size", 0),
                        "last_modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None
                    })

            runbooks.sort(key=lambda x: (x["name"] or "").lower())
            return _response(event, 200, {
                "bucket": S3_BUCKET,
                "prefix": prefix,
                "runbooks": runbooks
            })

        # -----------------
        # Get runbook content (text only)
        # GET /doc?name=FILE.pdf  OR /doc?key=full/s3/key.pdf
        # -----------------
        if path == "/doc" and method == "GET":
            if not S3_BUCKET:
                return _response(event, 500, {"error": "S3_BUCKET not set"})

            qs = _get_qs(event)

            # Option 1: full key provided
            if "key" in qs and qs["key"]:
                key = qs["key"]
                content = _get_object_text(S3_BUCKET, key)
                return _response(event, 200, {"key": key, "content": content})

            # Option 2: filename provided
            if "name" in qs and qs["name"]:
                filename = qs["name"]
                prefix = _s3_key(RUNBOOKS_PREFIX)
                objs = _list_prefix(S3_BUCKET, prefix)

                for obj in objs:
                    key = obj.get("Key", "")
                    if key.endswith("/" + filename) or key.endswith(filename):
                        content = _get_object_text(S3_BUCKET, key)
                        return _response(event, 200, {"key": key, "content": content})

                return _response(event, 404, {"error": f"Runbook not found: {filename}"})

            return _response(event, 400, {"error": "Provide ?name=<file.pdf> or ?key=<s3-key>"})

        # -----------------
        # Agents
        # GET /agents
        # -----------------
        if path == "/agents" and method == "GET":
            if not S3_BUCKET:
                return _response(event, 500, {"error": "S3_BUCKET not set"})
            key = _s3_key(AGENTS_KEY)
            data = _get_object_json(S3_BUCKET, key)
            return _response(event, 200, data)

        # -----------------
        # RAG ask
        # POST /runbooks/ask
        # -----------------
        if path == "/runbooks/ask" and method == "POST":
            req = _get_body_json(event)
            question = (req.get("question") or "").strip()
            top_k = int(req.get("top_k") or 5)

            if not question:
                return _response(event, 400, {"error": {"code": "MISSING_QUESTION", "message": "question is required"}})
            if top_k < 1 or top_k > 10:
                top_k = 5

            ctx = _retrieve(question, top_k)
            ans = _answer(question, ctx)

            return _response(event, 200, {
                "question": question,
                "top_k": top_k,
                "sources": [
                    {
                        "file": (c.get("meta") or {}).get("file"),
                        "s3_key": (c.get("meta") or {}).get("s3_key"),
                        "chunk": (c.get("meta") or {}).get("chunk"),
                        "distance": c.get("distance"),
                    }
                    for c in ctx
                ],
                "answer": ans,
            })

        return _response(event, 404, {"error": f"Route not found: {method} {path}"})

    except ClientError as e:
        return _response(event, 500, {"error": "AWS error", "detail": str(e)})
    except Exception as e:
        return _response(event, 500, {"error": "Unhandled error", "detail": str(e)})

# Backward-compatible alias if anything is still configured as "app.handler"
handler = lambda_handler