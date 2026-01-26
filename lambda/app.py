"""
lambda/app.py

Minimal Lambda API for:
  GET  /api/health
  GET  /api/runbooks
  GET  /api/doc?name=FILE.pdf   (or ?key=full/s3/key.pdf)  -> returns a presigned URL
  GET  /api/agents
  GET  /api/news/latest
  POST /api/runbooks/ask        (Chroma RAG; requires chromadb + pysqlite3-binary + OpenAI)

Notes:
- CloudFront routes /api/* to API Gateway; this handler normalizes "/api" away.
- Includes sqlite shim for Chroma (Lambda base sqlite is too old).
- AI News uses free sources (RSS + HN Algolia). No registration/API keys.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError

# --- sqlite shim for Chroma (Lambda has old sqlite3) ---
# IMPORTANT: keep this before any potential chromadb/sqlite import.
try:
    import pysqlite3.dbapi2 as sqlite3  # provided by pysqlite3-binary

    sys.modules["sqlite3"] = sqlite3
except Exception:
    # If this fails, Chroma may fail later with sqlite version error.
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
# AI News config (free)
# =====================
NEWS_ENABLED = os.environ.get("NEWS_ENABLED", "true").strip().lower() in ("1", "true", "yes", "y")
NEWS_MAX_ITEMS = int(os.environ.get("NEWS_MAX_ITEMS", "18"))
NEWS_DAYS_BACK = int(os.environ.get("NEWS_DAYS_BACK", "7"))
NEWS_CACHE_TTL_SEC = int(os.environ.get("NEWS_CACHE_TTL_SEC", str(6 * 60 * 60)))

RSS_SOURCES = [
    ("OpenAI", "https://openai.com/news/rss.xml", "Official"),
    ("DeepMind", "https://deepmind.google/blog/feed/basic", "Research"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml", "Open Source"),
    ("AWS ML Blog", "https://aws.amazon.com/blogs/machine-learning/feed/", "MLOps"),
    ("Microsoft Foundry", "https://devblogs.microsoft.com/foundry/feed/", "Enterprise"),
    ("Anthropic", "https://www.anthropic.com/news/rss.xml", "Official"),
]
HN_ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date?query={q}&tags=story&hitsPerPage=25"

AI_KEYWORDS = [
    "ai", "llm", "openai", "gpt", "claude", "anthropic", "gemini", "deepmind",
    "mistral", "hugging face", "transformer", "rag", "agentic", "multimodal",
    "inference", "alignment", "safety", "eval", "evals", "rlhf", "prompt",
]

# Calm guardrails: drop overly-hype phrasing
DROP_PATTERNS = [
    r"\bdoom\b", r"\bpanic\b", r"\bdestroy\b", r"\bapocalypse\b", r"\bterrifying\b",
    r"\breplaces all jobs\b", r"\bend of\b", r"\bsingularity\b",
]

_news_cache: Dict[str, Any] = {"ts": 0.0, "payload": None}

# =====================
# Helpers
# =====================

def _s3_key(path: str) -> str:
    """Build full S3 key using S3_PREFIX."""
    path = (path or "").lstrip("/")
    if not S3_PREFIX:
        return path
    return f"{S3_PREFIX.rstrip('/')}/{path}"

def _response(event: dict, status: int, body: dict) -> dict:
    # Always valid JSON response (avoid API GW generic 500)
    return {
        "statusCode": int(status),
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",  # tighten later with allowlist if desired
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Vary": "Origin",
        },
        "body": json.dumps(body, default=str),
    }

def _get_method(event: dict) -> str:
    return (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or "GET"
    ).upper()

def _get_path(event: dict) -> str:
    path = event.get("rawPath") or event.get("path") or "/"
    # Normalize CloudFront /api/* -> strip "/api"
    if path.startswith("/api/"):
        path = path[4:]
    return path

def _get_qs(event: dict) -> dict:
    return event.get("queryStringParameters") or {}

def _get_body_json(event: dict) -> dict:
    body = event.get("body") or ""
    if not body:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except Exception as e:
        raise ValueError(f"Invalid JSON body: {e}") from e

def _get_object_json(bucket: str, key: str) -> dict:
    obj = s3.get_object(Bucket=bucket, Key=key)
    raw = obj["Body"].read().decode("utf-8", errors="replace")
    return json.loads(raw)

def _list_prefix(bucket: str, prefix: str) -> List[dict]:
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

def _presign(bucket: str, key: str, expires: int = 300) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=int(expires),
    )

def _safe_name(name: str) -> str:
    # prevent path traversal and weird keys when using ?name=
    name = (name or "").strip()
    if not name or "/" in name or "\\" in name or ".." in name:
        return ""
    return name

# =====================
# AI News helpers
# =====================

_DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 aimlsre-news/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "close",
}

def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()

def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]*>", "", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _relevant(text: str) -> bool:
    t = (text or "").lower()
    if not any(k in t for k in AI_KEYWORDS):
        return False
    if any(re.search(p, t) for p in DROP_PATTERNS):
        return False
    return True

def _http_get_text(url: str, timeout_sec: int = 12) -> str:
    req = urllib.request.Request(url, headers=_DEFAULT_HTTP_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        detail = (detail[:600] + "...") if len(detail) > 600 else detail
        raise RuntimeError(f"HTTP {e.code} GET {url} :: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error GET {url} :: {e}") from e

def _http_get_json(url: str, timeout_sec: int = 10) -> dict:
    return json.loads(_http_get_text(url, timeout_sec=timeout_sec))

def _parse_rss(xml_text: str, source: str, tag: str) -> List[dict]:
    items: List[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_DAYS_BACK)

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return items

    for it in root.findall(".//item"):
        title = _strip_html((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        desc = _strip_html((it.findtext("description") or "").strip())

        if not title or not link:
            continue

        blob = f"{title} {desc}"
        if not _relevant(blob):
            continue

        published_at = None
        pub = (it.findtext("pubDate") or "").strip()
        if pub:
            parsed = None
            for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
                try:
                    parsed = datetime.strptime(pub, fmt)
                    break
                except Exception:
                    continue
            if parsed:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                dt = parsed.astimezone(timezone.utc)
                if dt < cutoff:
                    continue
                published_at = dt.astimezone().isoformat()

        items.append({
            "id": link[-16:] if len(link) > 16 else link,
            "title": title[:180],
            "url": link,
            "summary": desc[:260],
            "source": source,
            "tag": tag,
            "publishedAt": published_at,
        })

    return items

def _dedupe_sort(items: List[dict]) -> List[dict]:
    seen = set()
    uniq: List[dict] = []
    for it in items:
        u = (it.get("url") or "").strip().lower()
        if not u or u in seen:
            continue
        seen.add(u)
        uniq.append(it)
    uniq.sort(key=lambda x: x.get("publishedAt") or "", reverse=True)
    return uniq[:NEWS_MAX_ITEMS]

def _get_ai_news_payload() -> dict:
    if not NEWS_ENABLED:
        return {"updatedAt": _now_iso(), "items": [], "disabled": True}

    now = time.time()
    if _news_cache["payload"] is not None and (now - _news_cache["ts"] < NEWS_CACHE_TTL_SEC):
        return _news_cache["payload"]

    items: List[dict] = []
    errors: List[dict] = []

    for name, url, tag in RSS_SOURCES:
        try:
            xml_text = _http_get_text(url, timeout_sec=12)
            items.extend(_parse_rss(xml_text, name, tag))
        except Exception as e:
            errors.append({"source": name, "url": url, "error": str(e)[:300]})

    try:
        q = urllib.parse.quote(
            "AI OR LLM OR OpenAI OR Anthropic OR Claude OR Gemini OR DeepMind OR Mistral OR RAG OR agentic"
        )
        data = _http_get_json(HN_ALGOLIA.format(q=q), timeout_sec=10)
        cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_DAYS_BACK)

        for h in (data.get("hits") or [])[:25]:
            title = (h.get("title") or "").strip()
            link = (h.get("url") or "").strip()
            created = (h.get("created_at") or "").strip()
            if not title or not link:
                continue
            if not _relevant(title):
                continue

            published_at = None
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if dt < cutoff:
                        continue
                    published_at = dt.astimezone().isoformat()
                except Exception:
                    pass

            items.append({
                "id": link[-16:] if len(link) > 16 else link,
                "title": title[:180],
                "url": link,
                "summary": "",
                "source": "Hacker News",
                "tag": "Community Signal",
                "publishedAt": published_at,
            })
    except Exception as e:
        errors.append({"source": "Hacker News", "url": "hn.algolia.com", "error": str(e)[:300]})

    payload = {"updatedAt": _now_iso(), "items": _dedupe_sort(items), "errors": errors[:20]}
    _news_cache["ts"] = now
    _news_cache["payload"] = payload
    return payload

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
    _chroma_collection = client.get_or_create_collection(CHROMA_COLLECTION)
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

    out: List[dict] = []
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

    # Robust text extraction across SDK variants
    out_text = ""
    try:
        ot = getattr(resp, "output_text", None)
        if isinstance(ot, str) and ot.strip():
            return ot.strip()
    except Exception:
        pass

    try:
        for item in (getattr(resp, "output", None) or []):
            if getattr(item, "type", None) == "message":
                for c in (getattr(item, "content", None) or []):
                    if getattr(c, "type", None) in ("output_text", "text"):
                        out_text += (getattr(c, "text", None) or "")
    except Exception:
        pass

    return (out_text or "").strip() or "No answer returned."

# =====================
# Lambda handler
# =====================

def lambda_handler(event: dict, context: Any) -> dict:
    try:
        method = _get_method(event)
        path = _get_path(event)

        # Log minimal routing info (shows in CloudWatch)
        print(f"REQ method={method} path={path} rawPath={event.get('rawPath')}")

        if method == "OPTIONS":
            return _response(event, 200, {"ok": True})

        # -----------------
        # Health check
        # GET /api/health -> normalized "/health"
        # -----------------
        if method == "GET" and (path == "/health" or path.endswith("/health")):
            try:
                import sqlite3 as _s
                sqlite_ver = getattr(_s, "sqlite_version", "unknown")
            except Exception:
                sqlite_ver = "unknown"

            return _response(event, 200, {
                "ok": True,
                "sqlite_version": sqlite_ver,
                "bucket": S3_BUCKET,
                "prefix": S3_PREFIX,
                "runbooks_prefix": _s3_key(RUNBOOKS_PREFIX),
                "vectors_prefix": _s3_key(VECTORS_PREFIX),
                "chroma_collection": CHROMA_COLLECTION,
                "embed_model": EMBED_MODEL,
                "news_enabled": NEWS_ENABLED,
            })

        # -----------------
        # AI News
        # GET /api/news/latest -> normalized "/news/latest"
        # -----------------
        if method == "GET" and (path == "/news/latest" or path.endswith("/news/latest")):
            return _response(event, 200, _get_ai_news_payload())

        # -----------------
        # List runbooks
        # GET /api/runbooks -> normalized "/runbooks"
        # -----------------
        if method == "GET" and (path == "/runbooks" or path.endswith("/runbooks")):
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
                        "last_modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
                    })

            runbooks.sort(key=lambda x: (x.get("name") or "").lower())
            return _response(event, 200, {"bucket": S3_BUCKET, "prefix": prefix, "runbooks": runbooks})

        # -----------------
        # Get runbook doc (presigned URL)
        # GET /api/doc?name=FILE.pdf  OR /api/doc?key=full/s3/key.pdf
        # normalized path "/doc"
        # -----------------
        if method == "GET" and (path == "/doc" or path.endswith("/doc")):
            if not S3_BUCKET:
                return _response(event, 500, {"error": "S3_BUCKET not set"})

            qs = _get_qs(event)
            key = (qs.get("key") or "").strip()
            name = _safe_name(qs.get("name") or "")

            if key:
                url = _presign(S3_BUCKET, key, expires=300)
                return _response(event, 200, {"key": key, "url": url})

            if name:
                prefix = _s3_key(RUNBOOKS_PREFIX)
                objs = _list_prefix(S3_BUCKET, prefix)
                for obj in objs:
                    k = obj.get("Key", "")
                    if k.endswith("/" + name) or k.endswith(name):
                        url = _presign(S3_BUCKET, k, expires=300)
                        return _response(event, 200, {"key": k, "url": url})
                return _response(event, 404, {"error": f"Runbook not found: {name}"})

            return _response(event, 400, {"error": "Provide ?name=<file.pdf> or ?key=<s3-key>"})

        # -----------------
        # Agents
        # GET /api/agents -> normalized "/agents"
        # -----------------
        if method == "GET" and (path == "/agents" or path.endswith("/agents")):
            if not S3_BUCKET:
                return _response(event, 500, {"error": "S3_BUCKET not set"})
            key = _s3_key(AGENTS_KEY)
            data = _get_object_json(S3_BUCKET, key)
            return _response(event, 200, data)

        # -----------------
        # RAG ask
        # POST /api/runbooks/ask -> normalized "/runbooks/ask"
        # -----------------
        if method == "POST" and (path == "/runbooks/ask" or path.endswith("/runbooks/ask")):
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

        return _response(event, 404, {"error": {"code": "NOT_FOUND", "message": f"Route not found: {method} {path}"}})

    except ValueError as e:
        return _response(event, 400, {"error": {"code": "BAD_REQUEST", "message": str(e)}})
    except ClientError as e:
        return _response(event, 500, {"error": {"code": "AWS_ERROR", "message": str(e)}})
    except Exception as e:
        return _response(event, 500, {"error": {"code": "UNHANDLED", "message": str(e)}})

# Backward-compatible alias if anything is still configured as "app.handler"
handler = lambda_handler