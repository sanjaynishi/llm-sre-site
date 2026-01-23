"""
LLM SRE Agent API (Lambda)

Endpoints (behind CloudFront /api/*):
  GET  /api/health
  GET  /api/agents
  POST /api/agent/run
  POST /api/runbooks/ask   body: { "question": "...", "top_k": 5 }
  OPTIONS *                CORS preflight

RAG:
  - Downloads Chroma persistent store from S3 into /tmp on first use
  - Uses OpenAI embeddings via HTTPS (no openai SDK)
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, List, Dict, Tuple

try:
    import boto3
    from botocore.exceptions import ClientError
except Exception:
    boto3 = None
    ClientError = Exception


# ---------------- Config ----------------

ALLOWED_ORIGINS = {
    "https://dev.aimlsre.com",
    "https://aimlsre.com",
    "https://www.aimlsre.com",
}

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2").strip()

# Bucket that holds config + runbooks + vectors (you’re using agent-config bucket)
S3_BUCKET = os.environ.get("S3_BUCKET", "").strip()
S3_PREFIX = os.environ.get("S3_PREFIX", "knowledge/").strip()

# RAG vectors location (within S3_BUCKET)
VECTORS_PREFIX = os.environ.get("VECTORS_PREFIX", "knowledge/vectors/dev/chroma/").strip()
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "runbooks_dev").strip()
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small").strip()

# Local ephemeral storage
CHROMA_LOCAL_DIR = "/tmp/chroma_store"

# Agent catalog defaults (simple, you can replace with S3 later)
DEFAULT_AGENTS = {
    "agents": [
        {"id": "agent-runbooks", "category": "Runbooks", "label": "Ask runbooks (RAG)", "mode": "rag_runbooks"},
        {"id": "agent-travel", "category": "Demo", "label": "Travel plan (OpenAI via HTTPS)", "mode": "tool_travel"},
    ]
}

# Warm caches
_s3 = None
_chroma_collection = None


# ---------------- Basic helpers ----------------

def _s3_client():
    global _s3
    if boto3 is None:
        raise RuntimeError("boto3 not available in runtime")
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
    # Normalize CloudFront /api/* -> API routes /...
    if path.startswith("/api/"):
        path = path[4:]  # remove "/api"
    return path


def _get_body_json(event: dict) -> dict:
    body = event.get("body") or ""
    if not body:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON body: {e}") from e


# ---------------- OpenAI HTTPS helpers (NO SDK) ----------------

def _http_post_json(url: str, payload: dict, headers: dict | None = None, timeout_sec: int = 25) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json", "User-Agent": "llm-sre-agent/1.0"}
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        detail = (detail[:800] + "...") if len(detail) > 800 else detail
        raise RuntimeError(f"HTTP {e.code} POST {url} :: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error POST {url} :: {e}") from e


def _openai_headers() -> dict:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")
    return {"Authorization": f"Bearer {OPENAI_API_KEY}"}


def _openai_embed(text: str) -> List[float]:
    """
    Calls OpenAI embeddings endpoint via HTTPS.
    """
    url = "https://api.openai.com/v1/embeddings"
    payload = {"model": EMBED_MODEL, "input": [text]}
    resp = _http_post_json(url, payload, headers=_openai_headers(), timeout_sec=25)

    # Expected: {"data":[{"embedding":[...]}], ...}
    data = resp.get("data") or []
    if not data or not isinstance(data, list) or not data[0].get("embedding"):
        raise RuntimeError(f"Embeddings API returned unexpected payload: {str(resp)[:400]}")
    return data[0]["embedding"]


def _openai_answer(prompt: str) -> str:
    """
    Calls OpenAI Responses endpoint via HTTPS.
    """
    url = "https://api.openai.com/v1/responses"
    payload = {"model": OPENAI_MODEL, "input": prompt, "max_output_tokens": 700}
    resp = _http_post_json(url, payload, headers=_openai_headers(), timeout_sec=25)

    # Extract output text
    out_text = ""
    for item in resp.get("output", []) or []:
        if item.get("type") == "message":
            for c in item.get("content", []) or []:
                if c.get("type") in ("output_text", "text"):
                    out_text += c.get("text", "")
    out_text = (out_text or "").strip() or (resp.get("output_text") or "").strip()
    return out_text or "No answer returned."


# ---------------- S3 download helpers ----------------

def _s3_list_keys(bucket: str, prefix: str) -> List[str]:
    s3 = _s3_client()
    keys: List[str] = []
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


# ---------------- Chroma init/query (LAZY IMPORT) ----------------

def _ensure_chroma_collection():
    """
    Cold-start: download vector store from S3 -> /tmp, then open Chroma.
    Warm-start: reuse globals.
    """
    global _chroma_collection

    if _chroma_collection is not None:
        return _chroma_collection

    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET env var missing")
    if not VECTORS_PREFIX:
        raise RuntimeError("VECTORS_PREFIX env var missing")

    # Lazy import so Lambda ZIP doesn’t crash if chromadb isn't packaged
    try:
        import chromadb
        from chromadb.config import Settings
    except Exception as e:
        raise RuntimeError(
            "chromadb not available in this Lambda package. "
            "Either (a) switch to container-image Lambda, or (b) remove RAG imports."
        ) from e

    _s3_download_prefix(S3_BUCKET, VECTORS_PREFIX, CHROMA_LOCAL_DIR)

    client = chromadb.PersistentClient(
        path=CHROMA_LOCAL_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    _chroma_collection = client.get_collection(CHROMA_COLLECTION)

    # sanity check
    _ = _chroma_collection.count()
    return _chroma_collection


def _retrieve_chunks(question: str, top_k: int = 5) -> List[Dict[str, Any]]:
    col = _ensure_chroma_collection()
    q_emb = _openai_embed(question)

    res = col.query(
        query_embeddings=[q_emb],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    out: List[Dict[str, Any]] = []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    for doc, meta, dist in zip(docs, metas, dists):
        out.append({"text": doc, "meta": meta, "distance": dist})
    return out


def _answer_with_llm(question: str, contexts: List[Dict[str, Any]]) -> str:
    # Build context block with citations
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

    return _openai_answer(prompt)


# ---------------- Endpoint handlers ----------------

def _handle_get_health(event: dict) -> dict:
    return _json_response(event, 200, {"ok": True})


def _handle_get_agents(event: dict) -> dict:
    # Later you can load agents.json from S3. For now return defaults.
    return _json_response(event, 200, DEFAULT_AGENTS)


def _handle_post_agent_run(event: dict) -> dict:
    """
    Demo placeholder: keeps existing endpoint alive.
    You can extend this to run tools/agents.
    """
    req = _get_body_json(event)
    agent_id = (req.get("agent_id") or "").strip()
    location = (req.get("location") or "").strip()

    if not agent_id:
        return _json_response(event, 400, {"error": {"code": "MISSING_AGENT", "message": "agent_id is required"}})

    # Minimal demo: travel agent via OpenAI HTTPS
    if agent_id == "agent-travel":
        if not location:
            return _json_response(event, 400, {"error": {"code": "MISSING_LOCATION", "message": "location is required"}})

        prompt = f"Give a concise 2-day travel plan for {location}. Return plain text."
        answer = _openai_answer(prompt)
        return _json_response(event, 200, {"result": {"title": f"Travel plan: {location}", "text": answer}})

    return _json_response(event, 400, {"error": {"code": "INVALID_AGENT", "message": f"Unknown agent_id: {agent_id}"}})


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

    return _json_response(
        event,
        200,
        {
            "question": question,
            "top_k": top_k,
            "sources": [
                {
                    "file": (c["meta"] or {}).get("file"),
                    "s3_key": (c["meta"] or {}).get("s3_key"),
                    "chunk": (c["meta"] or {}).get("chunk"),
                }
                for c in contexts
            ],
            "answer": answer,
        },
    )


# ---------------- Lambda entry ----------------

def lambda_handler(event: dict, context: Any) -> dict:
    method = _get_method(event)
    path = _get_path(event)

    # CORS preflight
    if method == "OPTIONS":
        return _json_response(event, 200, {"ok": True})

    # Health (always cheap, no deps)
    if method == "GET" and (path == "/health" or path.endswith("/health")):
        return _handle_get_health(event)

    # Agents catalog
    if method == "GET" and (path == "/agents" or path.endswith("/agents")):
        return _handle_get_agents(event)

    # Run selected agent
    if method == "POST" and (path == "/agent/run" or path.endswith("/agent/run")):
        try:
            return _handle_post_agent_run(event)
        except Exception as e:
            return _json_response(event, 500, {"error": {"code": "AGENT_FAILED", "message": str(e)}})

    # RAG runbooks Q&A
    if method == "POST" and (path == "/runbooks/ask" or path.endswith("/runbooks/ask")):
        try:
            return _handle_post_runbooks_ask(event)
        except Exception as e:
            return _json_response(event, 500, {"error": {"code": "RAG_FAILED", "message": str(e)}})

    return _json_response(event, 404, {"error": {"code": "NOT_FOUND", "message": f"Route not found: {path}"}})