"""
services/agent_api/app.py

LLM SRE Agent API (Lambda)

Endpoints (behind CloudFront /api/*):
  GET  /api/health
  GET  /api/agents
  GET  /api/news/latest
  POST /api/agent/run
  POST /api/runbooks/ask
  POST /api/mcp/run
  GET  /api/_routes          (debug)
  GET  /api/_debug/news      (debug)
  OPTIONS *                  (CORS)

Important:
- CloudFront calls /api/* but we normalize by stripping '/api' to match routes like:
    /health, /agents, /news/latest, ...
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from typing import Any, Dict, List, Tuple

from core.request import get_method, get_path, get_body_json
from core.response import json_response

from news_service import handle_get_debug_news, handle_get_news_latest
from features.mcp.mcp_routes import handle_post_mcp_run  # ✅ MCP handler lives here

# ---- sqlite shim (must be BEFORE any chromadb import) ----
# IMPORTANT: chromadb checks sqlite3 version at import time.
try:
    import pysqlite3.dbapi2 as sqlite3  # type: ignore

    sys.modules["sqlite3"] = sqlite3
except Exception:
    # If shim isn't available, chromadb import may fail later (surface a clear error).
    pass

# ---- disable Chroma telemetry ----
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY", "False")
os.environ.setdefault("CHROMA_ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("POSTHOG_DISABLED", "true")

try:
    import boto3
except Exception:
    boto3 = None


# ---------------- Config ----------------

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2").strip()

AGENT_CONFIG_BUCKET = os.environ.get("AGENT_CONFIG_BUCKET", "").strip()
AGENT_CONFIG_PREFIX = os.environ.get("AGENT_CONFIG_PREFIX", "agent-config").strip().strip("/")

# RAG storage
S3_BUCKET = os.environ.get("S3_BUCKET", "").strip()
VECTORS_PREFIX = os.environ.get("VECTORS_PREFIX", "knowledge/vectors/dev/chroma/").strip().lstrip("/")
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "runbooks_dev").strip()
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small").strip()

CHROMA_LOCAL_DIR = "/tmp/chroma_store"

DEFAULT_ALLOWED_LOCATIONS = sorted(
    ["New York, NY", "San Francisco, CA", "Seattle, WA", "London, UK", "Delhi, India", "Tokyo, Japan"]
)
DEFAULT_TRAVEL_CITIES = sorted(["Paris", "London", "New York", "Tokyo", "Rome", "Delhi"])

AGENT_ID_WEATHER = "agent-weather"
AGENT_ID_TRAVEL = "agent-travel"

_s3 = None
_config_cache: Dict[str, Any] = {"agents": None, "allowlists": None}

_openai_client = None
_chroma_client = None
_chroma_collection = None


# ---------------- Basic helpers ----------------

def _log(msg: str) -> None:
    print(msg)


def _s3_client():
    global _s3
    if boto3 is None:
        raise RuntimeError("boto3 not available in this Lambda runtime")
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _normalize_path(p: str) -> str:
    """
    Safety normalization in case core.request.get_path ever returns raw '/api/...'
    """
    p = p or "/"
    if p.startswith("/api/"):
        p = p[4:]
    return p


# ---------------- S3 config (agents/allowlists) ----------------

def _s3_get_json(bucket: str, key: str) -> dict:
    try:
        resp = _s3_client().get_object(Bucket=bucket, Key=key)
        raw = resp["Body"].read().decode("utf-8", errors="replace")
        return json.loads(raw)
    except Exception as e:
        _log(f"S3 read failed: s3://{bucket}/{key} :: {e}")
        return {}


def _load_agent_config() -> Tuple[dict, dict]:
    if not AGENT_CONFIG_BUCKET:
        return {}, {}

    if _config_cache["agents"] is not None and _config_cache["allowlists"] is not None:
        return _config_cache["agents"], _config_cache["allowlists"]

    agents_key = f"{AGENT_CONFIG_PREFIX}/agents.json"
    allow_key = f"{AGENT_CONFIG_PREFIX}/allowlists.json"

    agents = _s3_get_json(AGENT_CONFIG_BUCKET, agents_key) or {}
    allow = _s3_get_json(AGENT_CONFIG_BUCKET, allow_key) or {}

    _config_cache["agents"] = agents
    _config_cache["allowlists"] = allow
    return agents, allow


def _normalize_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for x in value:
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def _effective_allowlists() -> Tuple[List[str], List[str]]:
    _, allow_cfg = _load_agent_config()

    weather_locations = _normalize_str_list(allow_cfg.get("weather_locations")) if isinstance(allow_cfg, dict) else []
    travel_cities = _normalize_str_list(allow_cfg.get("travel_cities")) if isinstance(allow_cfg, dict) else []

    if not weather_locations:
        weather_locations = DEFAULT_ALLOWED_LOCATIONS
    if not travel_cities:
        travel_cities = DEFAULT_TRAVEL_CITIES

    return weather_locations, travel_cities


# ---------------- Weather + Travel ----------------
# (kept inline for now; you can modularize next)

import urllib.parse
import urllib.request
import urllib.error


def _http_get_json(url: str, timeout_sec: int = 8) -> dict:
    with urllib.request.urlopen(url, timeout=timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def geocode_location(location: str) -> dict:
    base = "https://geocoding-api.open-meteo.com/v1/search"
    safe_location = location.strip()

    def _query(name: str) -> List[dict]:
        qs = urllib.parse.urlencode({"name": name, "count": 1, "language": "en", "format": "json"})
        data = _http_get_json(f"{base}?{qs}", timeout_sec=8)
        return data.get("results") or []

    results = _query(safe_location)
    if not results and "," in safe_location:
        results = _query(safe_location.split(",", 1)[0].strip())

    if not results:
        raise ValueError(f"Location not found: {location}")

    r = results[0]
    return {
        "name": r.get("name"),
        "country": r.get("country"),
        "admin1": r.get("admin1"),
        "lat": r.get("latitude"),
        "lon": r.get("longitude"),
        "timezone": r.get("timezone"),
    }


def fetch_weather(lat: float, lon: float) -> dict:
    base = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "auto",
        "forecast_days": 7,
        "current": ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "precipitation",
                "rain",
                "showers",
                "snowfall",
                "cloud_cover",
                "wind_speed_10m",
                "wind_direction_10m",
                "weather_code",
            ]
        ),
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "rain_sum",
                "snowfall_sum",
                "precipitation_probability_max",
                "wind_speed_10m_max",
            ]
        ),
    }
    url = f"{base}?{urllib.parse.urlencode(params)}"
    return _http_get_json(url, timeout_sec=8)


# ---------------- OpenAI (Travel via HTTP) ----------------

def _http_post_json(url: str, payload: dict, headers: dict | None = None, timeout_sec: int = 25) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        detail = (detail[:900] + "...") if len(detail) > 900 else detail
        raise RuntimeError(f"HTTP {e.code} POST {url} :: {detail}") from e


def _extract_json_object(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


def _openai_call(prompt: str) -> dict:
    if not OPENAI_API_KEY:
        return {"error": {"message": "OPENAI_API_KEY not configured"}}

    url = "https://api.openai.com/v1/responses"
    payload = {"model": OPENAI_MODEL, "input": prompt, "max_output_tokens": 650}
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    return _http_post_json(url, payload, headers=headers, timeout_sec=25)


def get_travel_info(city: str) -> dict:
    prompt = f"""
You are a travel planning assistant.

City: {city}

Return VALID JSON ONLY with this exact structure:

{{
  "weather_outlook": {{
    "next_2_days": "sunny | partly cloudy | cloudy | rainy",
    "next_5_days": "sunny | partly cloudy | cloudy | rainy"
  }},
  "itinerary_2_days": ["Day 1: ...", "Day 2: ..."],
  "itinerary_5_days": ["Day 1: ...", "Day 2: ...", "Day 3: ...", "Day 4: ...", "Day 5: ..."],
  "estimated_cost_usd": {{
    "flights_for_2": number,
    "hotel_4_star_5_nights": number,
    "local_transport_food": number,
    "total": number
  }},
  "travel_tips": ["...", "...", "..."]
}}
""".strip()

    resp = _openai_call(prompt)
    if isinstance(resp, dict) and resp.get("error"):
        return {"error": resp.get("error")}

    output_text = ""
    for item in resp.get("output", []) or []:
        if item.get("type") == "message":
            for c in item.get("content", []) or []:
                if c.get("type") in ("output_text", "text"):
                    output_text += c.get("text", "")

    output_text = (output_text or "").strip() or (resp.get("output_text") or "").strip()
    if not output_text:
        return {"error": {"message": "OpenAI returned empty output"}}

    candidate = _extract_json_object(output_text)
    try:
        data = json.loads(candidate)
    except Exception:
        return {"error": {"message": "Failed to parse JSON from model", "raw_output": output_text[:1200]}}

    # total sanity
    try:
        c = data.get("estimated_cost_usd", {})
        parts = (
            float(c.get("flights_for_2", 0))
            + float(c.get("hotel_4_star_5_nights", 0))
            + float(c.get("local_transport_food", 0))
        )
        c["total"] = round(parts, 0)
        data["estimated_cost_usd"] = c
    except Exception:
        pass

    return data


# ---------------- RAG: Chroma + OpenAI embeddings ----------------

def _ensure_openai_sdk():
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
    s3 = _s3_client()
    keys = _s3_list_keys(bucket, prefix)
    if not keys:
        raise RuntimeError(f"No objects found at s3://{bucket}/{prefix}")

    if os.path.isdir(local_dir):
        shutil.rmtree(local_dir, ignore_errors=True)
    os.makedirs(local_dir, exist_ok=True)

    count = 0
    for key in keys:
        rel = key[len(prefix) :].lstrip("/")
        dest = os.path.join(local_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        s3.download_file(bucket, key, dest)
        count += 1
    return count


def _ensure_chroma():
    global _chroma_client, _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection

    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET env var missing")
    if not VECTORS_PREFIX:
        raise RuntimeError("VECTORS_PREFIX env var missing")

    _s3_download_prefix(S3_BUCKET, VECTORS_PREFIX, CHROMA_LOCAL_DIR)

    try:
        import chromadb  # type: ignore
        from chromadb.config import Settings  # type: ignore
    except Exception as e:
        raise RuntimeError(f"chromadb not installed in this Lambda image. Import error: {e}") from e

    _chroma_client = chromadb.PersistentClient(
        path=CHROMA_LOCAL_DIR,
        settings=Settings(anonymized_telemetry=False, allow_reset=False),
    )

    _chroma_collection = _chroma_client.get_or_create_collection(CHROMA_COLLECTION)
    _ = _chroma_collection.count()
    return _chroma_collection


def _embed_text(text: str) -> List[float]:
    client = _ensure_openai_sdk()
    emb = client.embeddings.create(model=EMBED_MODEL, input=[text])
    return emb.data[0].embedding


def _response_text_from_openai_response(resp: Any) -> str:
    try:
        ot = getattr(resp, "output_text", None)
        if isinstance(ot, str) and ot.strip():
            return ot.strip()
    except Exception:
        pass

    text = ""
    try:
        output = getattr(resp, "output", None) or []
        for item in output:
            if getattr(item, "type", None) == "message":
                for c in getattr(item, "content", None) or []:
                    ctype = getattr(c, "type", None)
                    if ctype in ("output_text", "text"):
                        t = getattr(c, "text", None)
                        if t:
                            text += t
    except Exception:
        pass

    return (text or "").strip()


def _retrieve_chunks(question: str, top_k: int) -> List[Dict[str, Any]]:
    col = _ensure_chroma()
    q_emb = _embed_text(question)

    res = col.query(
        query_embeddings=[q_emb],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    out: List[Dict[str, Any]] = []
    for doc, meta, dist in zip(docs, metas, dists):
        out.append({"text": doc, "meta": meta, "distance": dist})
    return out


def _answer_with_llm(question: str, contexts: List[Dict[str, Any]]) -> str:
    client = _ensure_openai_sdk()

    ctx_lines: List[str] = []
    for i, c in enumerate(contexts, start=1):
        meta = c.get("meta") or {}
        src = meta.get("file") or meta.get("s3_key") or "runbook"
        chunk = meta.get("chunk")
        label = f"[{i}] {src}" + (f" (chunk {chunk})" if chunk is not None else "")
        ctx_lines.append(f"{label}\n{c.get('text','')}\n")

    context_block = "\n".join(ctx_lines)[:14000]

    prompt = f"""
You are an SRE runbook assistant. Answer ONLY using the provided excerpts.
If the excerpts don’t contain the answer, say what is missing and what to check next.

Format:
- 1–2 sentence summary
- Steps (commands/snippets OK)
- "If still failing" checks
- Cite sources like [1], [2]

Question:
{question}

Excerpts:
{context_block}
""".strip()

    resp = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
        max_output_tokens=700,
    )

    out_text = _response_text_from_openai_response(resp)
    return out_text or "No answer returned."


# ---------------- Handlers ----------------

def _handle_get_health(event: dict) -> dict:
    try:
        import sqlite3 as _s  # uses our shim if present
        sqlite_ver = getattr(_s, "sqlite_version", "unknown")
    except Exception:
        sqlite_ver = "unknown"

    return json_response(event, 200, {"ok": True, "sqlite_version": sqlite_ver})


def _handle_get_routes(event: dict, method: str, path: str) -> dict:
    # Show *normalized* routes (after "/api" is stripped)
    return json_response(
        event,
        200,
        {
            "ok": True,
            "rawPath": event.get("rawPath"),
            "normalizedPath": path,
            "method": method,
            "routes": [
                "GET /health",
                "GET /agents",
                "GET /news/latest",
                "GET /_routes",
                "GET /_debug/news",
                "POST /agent/run",
                "POST /runbooks/ask",
                "POST /mcp/run",
            ],
            "note": "CloudFront calls these as /api/*; handler normalizes by stripping '/api/'.",
        },
    )


def _handle_get_agents(event: dict) -> dict:
    default_agents = {
        "agents": [
            {
                "id": AGENT_ID_WEATHER,
                "category": "Weather",
                "label": "Weather information (full details)",
                "mode": "tool_weather",
                "allowed_locations": DEFAULT_ALLOWED_LOCATIONS,
            },
            {
                "id": AGENT_ID_TRAVEL,
                "category": "Travel",
                "label": "Travel planner (AI-powered)",
                "mode": "tool_travel",
                "allowed_locations": DEFAULT_TRAVEL_CITIES,
            },
        ]
    }

    try:
        agents_cfg, _ = _load_agent_config()
        weather_locations, travel_cities = _effective_allowlists()
        merged = {"agents": []}

        if isinstance(agents_cfg, dict) and isinstance(agents_cfg.get("agents"), list):
            for a in agents_cfg["agents"]:
                if not isinstance(a, dict) or not a.get("id"):
                    continue
                aid = a.get("id")

                if aid == AGENT_ID_WEATHER:
                    a2 = dict(a)
                    a2["allowed_locations"] = weather_locations
                    merged["agents"].append(a2)
                elif aid == AGENT_ID_TRAVEL:
                    a2 = dict(a)
                    a2["allowed_locations"] = travel_cities
                    merged["agents"].append(a2)

        if not merged["agents"]:
            return json_response(event, 200, default_agents)

        return json_response(event, 200, merged)

    except Exception as e:
        _log(f"/agents fallback due to error: {e}")
        return json_response(event, 200, default_agents)


def _handle_post_agent_run(event: dict) -> dict:
    req = get_body_json(event)
    agent_id = req.get("agent_id")
    location = req.get("location")

    if not agent_id:
        return json_response(event, 400, {"error": {"code": "MISSING_AGENT", "message": "agent_id is required"}})
    if not location:
        return json_response(event, 400, {"error": {"code": "MISSING_LOCATION", "message": "location is required"}})

    weather_locations, travel_cities = _effective_allowlists()

    if agent_id == AGENT_ID_WEATHER:
        if location not in set(weather_locations):
            return json_response(
                event, 400, {"error": {"code": "LOCATION_NOT_ALLOWED", "message": "Choose a location from dropdown"}}
            )

        geo = geocode_location(location)
        if geo.get("lat") is None or geo.get("lon") is None:
            return json_response(event, 500, {"error": {"code": "GEOCODE_FAILED", "message": "No coordinates returned"}})

        weather = fetch_weather(float(geo["lat"]), float(geo["lon"]))
        return json_response(
            event,
            200,
            {"result": {"title": f"Weather: {location}", "geocoding": geo, "weather": weather}},
        )

    if agent_id == AGENT_ID_TRAVEL:
        city = location.strip()
        if city not in set(travel_cities):
            return json_response(
                event, 400, {"error": {"code": "CITY_NOT_ALLOWED", "message": "Choose a city from dropdown"}}
            )

        travel = get_travel_info(city)
        return json_response(event, 200, {"result": {"title": f"Travel plan: {city}", "city": city, "travel_plan": travel}})

    return json_response(event, 400, {"error": {"code": "INVALID_AGENT", "message": "Unknown agent_id"}})


def _handle_post_runbooks_ask(event: dict) -> dict:
    req = get_body_json(event)
    question = (req.get("question") or "").strip()
    top_k = int(req.get("top_k") or 5)

    if not question:
        return json_response(event, 400, {"error": {"code": "MISSING_QUESTION", "message": "question is required"}})
    if top_k < 1 or top_k > 10:
        top_k = 5

    contexts = _retrieve_chunks(question, top_k=top_k)
    answer = _answer_with_llm(question, contexts)

    return json_response(
        event,
        200,
        {
            "question": question,
            "top_k": top_k,
            "sources": [
                {
                    "file": (c.get("meta") or {}).get("file"),
                    "s3_key": (c.get("meta") or {}).get("s3_key"),
                    "chunk": (c.get("meta") or {}).get("chunk"),
                }
                for c in contexts
            ],
            "answer": answer,
        },
    )


# ---------------- Lambda entry ----------------

def lambda_handler(event: dict, context: Any) -> dict:
    try:
        method = get_method(event)
        path = _normalize_path(get_path(event))

        _log(f"REQ method={method} path={path} rawPath={event.get('rawPath')}")

        if method == "OPTIONS":
            return json_response(event, 200, {"ok": True})

        if method == "GET" and (path == "/_routes" or path.endswith("/_routes")):
            return _handle_get_routes(event, method, path)

        if method == "GET" and (path == "/health" or path.endswith("/health")):
            return _handle_get_health(event)

        if method == "GET" and (path == "/agents" or path.endswith("/agents")):
            return _handle_get_agents(event)

        if method == "GET" and (path == "/_debug/news" or path.endswith("/_debug/news")):
            return handle_get_debug_news(event)

        # ✅ after normalization, this MUST be "/news/latest"
        if method == "GET" and (path == "/news/latest" or path.endswith("/news/latest")):
            return handle_get_news_latest(event)

        if method == "POST" and (path == "/agent/run" or path.endswith("/agent/run")):
            return _handle_post_agent_run(event)

        if method == "POST" and (path == "/runbooks/ask" or path.endswith("/runbooks/ask")):
            return _handle_post_runbooks_ask(event)

        # ✅ MCP route (delegates to features/mcp/mcp_routes.py)
        if method == "POST" and (path == "/mcp/run" or path.endswith("/mcp/run")):
            return handle_post_mcp_run(event)

        return json_response(event, 404, {"error": {"code": "NOT_FOUND", "message": f"Route not found: {path}"}})

    except ValueError as e:
        return json_response(event, 400, {"error": {"code": "BAD_REQUEST", "message": str(e)}})
    except Exception as e:
        return json_response(event, 500, {"error": {"code": "UNHANDLED", "message": str(e)}})


# Backward-compatible alias if anything is still configured as "app.handler"
handler = lambda_handler