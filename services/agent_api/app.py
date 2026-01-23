"""
LLM SRE Agent API (Lambda)

Endpoints (behind CloudFront /api/*):
  GET  /api/health         -> basic health
  GET  /api/agents         -> returns agent catalog (Weather + Travel) with allowed_locations
  POST /api/agent/run      -> runs selected agent (weather/travel)
  POST /api/runbooks/ask   -> RAG Q&A over runbooks (question-based, no location)
  OPTIONS *                -> CORS preflight

Notes:
- /api/agents MUST return only location-based agents used by /api/agent/run.
  Do NOT include the RAG agent here (it breaks the UI dropdown by making "location" null).
- RAG uses /api/runbooks/ask and expects {"question": "...", "top_k": 5}.

RAG storage:
- Downloads Chroma persistent store from S3 into /tmp on first query (cold start).
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

# OpenAI SDK is required ONLY if you're using container image or you packaged it.
# If you are running ZIP Lambda without dependencies, remove this and use stdlib HTTPS calls instead.
from openai import OpenAI

# Chroma deps are present only if you're using container image
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

# Existing S3 config (agents.json / allowlists.json)
AGENT_CONFIG_BUCKET = os.environ.get("AGENT_CONFIG_BUCKET", "").strip()
AGENT_CONFIG_PREFIX = os.environ.get("AGENT_CONFIG_PREFIX", "agent-config").strip()

# Runbooks + vectors storage (can be same bucket)
S3_BUCKET = os.environ.get("S3_BUCKET", "").strip()
S3_PREFIX = os.environ.get("S3_PREFIX", "knowledge/").strip()

# RAG / vectors
VECTORS_PREFIX = os.environ.get("VECTORS_PREFIX", "knowledge/vectors/dev/chroma/").strip()
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "runbooks_dev").strip()
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small").strip()

CHROMA_LOCAL_DIR = "/tmp/chroma_store"

# Defaults (fallback if S3 config missing)
DEFAULT_ALLOWED_LOCATIONS = sorted([
    "New York, NY",
    "San Francisco, CA",
    "Seattle, WA",
    "London, UK",
    "Delhi, India",
    "Tokyo, Japan",
])

DEFAULT_TRAVEL_CITIES = sorted([
    "Paris",
    "London",
    "New York",
    "Tokyo",
    "Rome",
])

AGENT_ID_WEATHER = "agent-weather"
AGENT_ID_TRAVEL = "agent-travel"

# Warm caches / globals
_s3 = None
_config_cache = {"agents": None, "allowlists": None}

_openai_client = None
_chroma_client = None
_chroma_collection = None


# ---------------- Basic helpers ----------------

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
    # CloudFront forwards /api/*, but API Gateway routes are /...
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


def _ensure_openai():
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


# ---------------- S3 config (agents/allowlists) ----------------

def _s3_get_json(bucket: str, key: str) -> dict:
    try:
        resp = _s3_client().get_object(Bucket=bucket, Key=key)
        raw = resp["Body"].read().decode("utf-8")
        return json.loads(raw)
    except Exception:
        return {}


def _load_agent_config() -> Tuple[dict, dict]:
    """
    Returns (agents_json, allowlists_json) from S3 if configured.
    Uses warm Lambda cache; falls back to ({},{}) if missing.
    """
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
    """
    allowlists.json format:
      {
        "weather_locations": [...],
        "travel_cities": [...]
      }
    """
    _, allow_cfg = _load_agent_config()

    weather_locations = _normalize_str_list(allow_cfg.get("weather_locations")) if isinstance(allow_cfg, dict) else []
    travel_cities = _normalize_str_list(allow_cfg.get("travel_cities")) if isinstance(allow_cfg, dict) else []

    if not weather_locations:
        weather_locations = DEFAULT_ALLOWED_LOCATIONS
    if not travel_cities:
        travel_cities = DEFAULT_TRAVEL_CITIES

    return weather_locations, travel_cities


# ---------------- HTTP helpers (stdlib) ----------------

def _http_get_json(url: str, timeout_sec: int = 10) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "llm-sre-agent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        detail = (detail[:500] + "...") if len(detail) > 500 else detail
        raise RuntimeError(f"HTTP {e.code} calling upstream: {url} :: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error calling upstream: {url} :: {e}") from e


# ---------------- Weather (Open-Meteo) ----------------

def geocode_location(location: str) -> dict:
    base = "https://geocoding-api.open-meteo.com/v1/search"
    safe_location = location.strip()

    def _query(name: str) -> List[dict]:
        qs = urllib.parse.urlencode({"name": name, "count": 1, "language": "en", "format": "json"})
        data = _http_get_json(f"{base}?{qs}")
        return data.get("results") or []

    results = _query(safe_location)
    if not results and "," in safe_location:
        fallback = safe_location.split(",", 1)[0].strip()
        results = _query(fallback)

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
    return _http_get_json(url)


# ---------------- Travel (OpenAI) ----------------

def get_travel_info(city: str) -> dict:
    if not OPENAI_API_KEY:
        return {"error": "OPENAI_API_KEY not configured"}

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

Rules:
- Keep concise and realistic
- Assume travel from a major US city
- Costs approximate; total = sum of parts
- No markdown; JSON only
""".strip()

    client = _ensure_openai()
    resp = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
        max_output_tokens=650,
    )

    # Extract output text
    out_text = ""
    for item in resp.output or []:
        if getattr(item, "type", None) == "message":
            for c in item.content or []:
                if getattr(c, "type", None) in ("output_text", "text"):
                    out_text += c.text or ""
    out_text = (out_text or "").strip() or (getattr(resp, "output_text", "") or "").strip()

    if not out_text:
        return {"error": "OpenAI returned empty output"}

    # Try parse JSON (best effort)
    try:
        data = json.loads(out_text)
    except Exception:
        # fallback: attempt to extract first {...}
        start = out_text.find("{")
        end = out_text.rfind("}")
        candidate = out_text[start:end + 1] if start != -1 and end != -1 and end > start else out_text
        try:
            data = json.loads(candidate)
        except Exception:
            return {"error": "Failed to parse JSON from model", "raw_output": out_text[:1200]}

    # Sanity-check total
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


# ---------------- RAG helpers (Chroma in /tmp) ----------------

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

    _s3_download_prefix(S3_BUCKET, VECTORS_PREFIX, CHROMA_LOCAL_DIR)

    _chroma_client = chromadb.PersistentClient(
        path=CHROMA_LOCAL_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    _chroma_collection = _chroma_client.get_collection(CHROMA_COLLECTION)
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

    out: List[Dict[str, Any]] = []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    for doc, meta, dist in zip(docs, metas, dists):
        out.append({"text": doc, "meta": meta, "distance": dist})
    return out


def _answer_with_llm(question: str, contexts: List[Dict[str, Any]]) -> str:
    client = _ensure_openai()

    ctx_lines: List[str] = []
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


# ---------------- Handlers ----------------

def _handle_get_health(event: dict) -> dict:
    return _json_response(event, 200, {"ok": True})


def _handle_get_agents(event: dict) -> dict:
    """
    Returns the agent catalog for the UI dropdown.
    IMPORTANT: Only include agents that use /api/agent/run (location dropdown flow).
    Do NOT include the RAG agent here (it uses /api/runbooks/ask and a question input).
    """
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

        if isinstance(agents_cfg, dict) and isinstance(agents_cfg.get("agents"), list):
            merged = {"agents": []}
            for a in agents_cfg["agents"]:
                if not isinstance(a, dict) or not a.get("id"):
                    continue

                a2 = dict(a)

                # Only include supported dropdown agents
                if a2["id"] == AGENT_ID_WEATHER:
                    a2["allowed_locations"] = weather_locations
                    merged["agents"].append(a2)
                elif a2["id"] == AGENT_ID_TRAVEL:
                    a2["allowed_locations"] = travel_cities
                    merged["agents"].append(a2)

            if merged["agents"]:
                return _json_response(event, 200, merged)

        return _json_response(event, 200, default_agents)
    except Exception:
        return _json_response(event, 200, default_agents)


def _handle_post_agent_run(event: dict) -> dict:
    req = _get_body_json(event)
    agent_id = req.get("agent_id")
    location = req.get("location")

    if not agent_id:
        return _json_response(event, 400, {"error": {"code": "MISSING_AGENT", "message": "agent_id is required"}})
    if not location:
        return _json_response(event, 400, {"error": {"code": "MISSING_LOCATION", "message": "location is required"}})

    weather_locations, travel_cities = _effective_allowlists()
    allow_weather = set(weather_locations)
    allow_travel = set(travel_cities)

    if agent_id == AGENT_ID_WEATHER:
        if location not in allow_weather:
            return _json_response(event, 400, {"error": {"code": "LOCATION_NOT_ALLOWED", "message": "Choose a location from dropdown"}})

        geo = geocode_location(location)
        if geo.get("lat") is None or geo.get("lon") is None:
            return _json_response(event, 500, {"error": {"code": "GEOCODE_FAILED", "message": "No coordinates returned"}})

        weather = fetch_weather(float(geo["lat"]), float(geo["lon"]))
        return _json_response(event, 200, {"result": {"title": f"Weather: {location}", "geocoding": geo, "weather": weather}})

    if agent_id == AGENT_ID_TRAVEL:
        city = location.strip()
        if city not in allow_travel:
            return _json_response(event, 400, {"error": {"code": "CITY_NOT_ALLOWED", "message": "Choose a city from dropdown"}})

        travel = get_travel_info(city)
        return _json_response(event, 200, {"result": {"title": f"Travel plan: {city}", "city": city, "travel_plan": travel}})

    return _json_response(event, 400, {"error": {"code": "INVALID_AGENT", "message": "Unknown agent_id"}})


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
            {
                "file": (c["meta"] or {}).get("file"),
                "s3_key": (c["meta"] or {}).get("s3_key"),
                "chunk": (c["meta"] or {}).get("chunk"),
            }
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

    # Health
    if method == "GET" and (path == "/health" or path.endswith("/health")):
        return _handle_get_health(event)

    # Agents catalog (Weather + Travel only)
    if method == "GET" and (path == "/agents" or path.endswith("/agents")):
        return _handle_get_agents(event)

    # Agent run (location-based)
    if method == "POST" and (path == "/agent/run" or path.endswith("/agent/run")):
        try:
            return _handle_post_agent_run(event)
        except ValueError as e:
            return _json_response(event, 400, {"error": {"code": "BAD_REQUEST", "message": str(e)}})
        except Exception as e:
            return _json_response(event, 500, {"error": {"code": "AGENT_FAILED", "message": str(e)}})

    # RAG endpoint (question-based)
    if method == "POST" and (path == "/runbooks/ask" or path.endswith("/runbooks/ask")):
        try:
            return _handle_post_runbooks_ask(event)
        except Exception as e:
            return _json_response(event, 500, {"error": {"code": "RAG_FAILED", "message": str(e)}})

    return _json_response(event, 404, {"error": {"code": "NOT_FOUND", "message": f"Route not found: {path}"}})