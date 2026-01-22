"""
LLM SRE Agent API (Lambda)

Endpoints (behind CloudFront /api/*):
  GET  /api/agents        -> returns agent catalog (S3-backed + fallback)
  POST /api/agent/run     -> runs a selected agent:
       - agent-weather (Open-Meteo)
       - agent-travel  (OpenAI over HTTPS, no SDK required)
  OPTIONS *               -> CORS preflight
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Tuple

try:
    import boto3
    from botocore.exceptions import ClientError
except Exception:
    boto3 = None
    ClientError = Exception


# --- Config / Guardrails ------------------------------------------------------

ALLOWED_ORIGINS = {
    "https://dev.aimlsre.com",
    "https://aimlsre.com",
    "https://www.aimlsre.com",
    "https://dev.snrcs.com",
    "https://dev.sanjaynishi.com",
    "https://snrcs.com",
    "https://www.snrcs.com",
    "https://sanjaynishi.com",
    "https://www.sanjaynishi.com",
}

# Fallback allowlists if S3 config missing/unreadable
DEFAULT_ALLOWED_LOCATIONS = {
    "New York, NY",
    "San Francisco, CA",
    "Seattle, WA",
    "London, UK",
    "Delhi, India",
    "Tokyo, Japan",
}

DEFAULT_TRAVEL_CITIES = {"Paris", "London", "New York", "Tokyo", "Rome"}

AGENT_ID_WEATHER = "agent-weather"
AGENT_ID_TRAVEL = "agent-travel"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.1-mini").strip()

AGENT_CONFIG_BUCKET = os.environ.get("AGENT_CONFIG_BUCKET", "").strip()
AGENT_CONFIG_PREFIX = os.environ.get("AGENT_CONFIG_PREFIX", "agent-config").strip()


# --- S3 Config Cache (ETag-aware) --------------------------------------------

_s3 = None
_config_cache = {
    "agents": None,
    "allowlists": None,
    "etag_agents": None,
    "etag_allow": None,
    "last_check_ts": 0.0,
}

# How often we check ETags (seconds). Small + safe.
CONFIG_ETAG_CHECK_INTERVAL_SEC = 10


def _s3_client():
    global _s3
    if boto3 is None:
        raise RuntimeError("boto3 not available (local lint). Lambda runtime includes boto3.")
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _s3_head_etag(bucket: str, key: str) -> str | None:
    try:
        resp = _s3_client().head_object(Bucket=bucket, Key=key)
        etag = resp.get("ETag")
        return etag.strip('"') if isinstance(etag, str) else None
    except Exception:
        return None


def _s3_get_json(bucket: str, key: str) -> dict:
    resp = _s3_client().get_object(Bucket=bucket, Key=key)
    raw = resp["Body"].read().decode("utf-8")
    return json.loads(raw)


def _load_agent_config() -> Tuple[dict, dict]:
    """
    Returns (agents_json, allowlists_json).
    - If env vars not set or boto3 missing: returns ({}, {})
    - Uses ETag-aware cache so updates in S3 are picked up quickly.
    """
    if not AGENT_CONFIG_BUCKET or boto3 is None:
        return {}, {}

    agents_key = f"{AGENT_CONFIG_PREFIX}/agents.json"
    allow_key = f"{AGENT_CONFIG_PREFIX}/allowlists.json"

    now = time.time()

    # If we have cached values, only check ETags every N seconds.
    if (
        _config_cache["agents"] is not None
        and _config_cache["allowlists"] is not None
        and (now - float(_config_cache["last_check_ts"] or 0.0)) < CONFIG_ETAG_CHECK_INTERVAL_SEC
    ):
        return _config_cache["agents"], _config_cache["allowlists"]

    _config_cache["last_check_ts"] = now

    # Read current ETags
    etag_agents = _s3_head_etag(AGENT_CONFIG_BUCKET, agents_key)
    etag_allow = _s3_head_etag(AGENT_CONFIG_BUCKET, allow_key)

    # If nothing changed and we already have cached content, return cache.
    if (
        _config_cache["agents"] is not None
        and _config_cache["allowlists"] is not None
        and etag_agents
        and etag_allow
        and etag_agents == _config_cache["etag_agents"]
        and etag_allow == _config_cache["etag_allow"]
    ):
        return _config_cache["agents"], _config_cache["allowlists"]

    # Otherwise reload (best-effort)
    agents = {}
    allow = {}
    try:
        agents = _s3_get_json(AGENT_CONFIG_BUCKET, agents_key)
    except Exception:
        agents = {}
    try:
        allow = _s3_get_json(AGENT_CONFIG_BUCKET, allow_key)
    except Exception:
        allow = {}

    _config_cache["agents"] = agents
    _config_cache["allowlists"] = allow
    _config_cache["etag_agents"] = etag_agents
    _config_cache["etag_allow"] = etag_allow

    return agents, allow


def _normalize_str_list(v) -> list[str]:
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for x in v:
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def _effective_allowlists() -> Tuple[set[str], set[str]]:
    """
    Returns (allowed_weather_locations, allowed_travel_cities)
    based on allowlists.json if present; else falls back to defaults.
    allowlists.json format:
      {
        "weather_locations": ["Delhi, India", ...],
        "travel_cities": ["Delhi", "Paris", ...]
      }
    """
    _, allow_cfg = _load_agent_config()
    weather_locations = _normalize_str_list((allow_cfg or {}).get("weather_locations"))
    travel_cities = _normalize_str_list((allow_cfg or {}).get("travel_cities"))

    allow_weather = set(weather_locations) if weather_locations else set(DEFAULT_ALLOWED_LOCATIONS)
    allow_travel = set(travel_cities) if travel_cities else set(DEFAULT_TRAVEL_CITIES)

    return allow_weather, allow_travel


# --- HTTP Helpers -------------------------------------------------------------

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
    return event.get("rawPath") or event.get("path") or "/"


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


def _extract_json_object(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


# --- Open-Meteo ---------------------------------------------------------------

def geocode_location(location: str) -> dict:
    base = "https://geocoding-api.open-meteo.com/v1/search"
    safe_location = location.strip()

    def _query(name: str) -> list[dict]:
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
        "hourly": ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "precipitation_probability",
                "precipitation",
                "rain",
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
                "wind_direction_10m_dominant",
            ]
        ),
    }
    url = f"{base}?{urllib.parse.urlencode(params)}"
    return _http_get_json(url)


# --- OpenAI Travel (HTTPS, no SDK) --------------------------------------------

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

    url = "https://api.openai.com/v1/responses"
    payload = {"model": OPENAI_MODEL, "input": prompt, "max_output_tokens": 650}
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

    try:
        resp = _http_post_json(url, payload, headers=headers, timeout_sec=25)
    except Exception as e:
        return {"error": f"OpenAI call failed: {str(e)}"}

    if isinstance(resp, dict) and resp.get("error"):
        return {"error": f"OpenAI API error: {resp.get('error')}"}

    output_text = ""
    for item in resp.get("output", []) or []:
        if item.get("type") == "message":
            for c in item.get("content", []) or []:
                if c.get("type") in ("output_text", "text"):
                    output_text += c.get("text", "")

    output_text = (output_text or "").strip() or (resp.get("output_text") or "").strip()

    candidate = _extract_json_object(output_text)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON from model", "raw_output": output_text[:1200]}

    # sanity-check total
    try:
        c = data.get("estimated_cost_usd", {})
        parts = float(c.get("flights_for_2", 0)) + float(c.get("hotel_4_star_5_nights", 0)) + float(
            c.get("local_transport_food", 0)
        )
        c["total"] = round(parts, 0)
        data["estimated_cost_usd"] = c
    except Exception:
        pass

    return data


# --- API Routes ---------------------------------------------------------------

def _handle_get_agents(event: dict) -> dict:
    # Always derive allowlists (S3-backed if available)
    allow_weather, allow_travel = _effective_allowlists()

    default_agents = {
        "agents": [
            {
                "id": AGENT_ID_WEATHER,
                "category": "Weather",
                "label": "Weather information (full details)",
                "mode": "tool_weather",
                "allowed_locations": sorted(allow_weather),
            },
            {
                "id": AGENT_ID_TRAVEL,
                "category": "Travel",
                "label": "Travel planner (AI-powered)",
                "mode": "tool_travel",
                "allowed_locations": sorted(allow_travel),
            },
        ]
    }

    # Try to use agents.json for labels/categories/modes (but never trust it for allowlists)
    agents_cfg, _ = _load_agent_config()
    merged = {"agents": []}

    if isinstance(agents_cfg, dict) and isinstance(agents_cfg.get("agents"), list):
        for a in agents_cfg["agents"]:
            if not isinstance(a, dict) or not a.get("id"):
                continue
            a2 = dict(a)
            if a2["id"] == AGENT_ID_WEATHER:
                a2["allowed_locations"] = sorted(allow_weather)
            elif a2["id"] == AGENT_ID_TRAVEL:
                a2["allowed_locations"] = sorted(allow_travel)
            merged["agents"].append(a2)

    body = merged if merged["agents"] else default_agents

    # Prevent CloudFront/browser caching of catalog
    return _json_response(
        event,
        200,
        body,
        extra_headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


def _handle_post_agent_run(event: dict) -> dict:
    req = _get_body_json(event)
    agent_id = req.get("agent_id")
    location = req.get("location")

    if not agent_id:
        return _json_response(event, 400, {"error": {"code": "MISSING_AGENT", "message": "agent_id is required"}})
    if not location:
        return _json_response(event, 400, {"error": {"code": "MISSING_LOCATION", "message": "location is required"}})

    allow_weather, allow_travel = _effective_allowlists()

    if agent_id == AGENT_ID_WEATHER:
        if location not in allow_weather:
            return _json_response(event, 400, {"error": {"code": "LOCATION_NOT_ALLOWED", "message": "Choose a location from dropdown"}})

        geo = geocode_location(location)
        if geo.get("lat") is None or geo.get("lon") is None:
            return _json_response(event, 500, {"error": {"code": "GEOCODE_FAILED", "message": "No coordinates returned"}})

        weather = fetch_weather(float(geo["lat"]), float(geo["lon"]))
        return _json_response(event, 200, {"result": {"title": f"Weather: {location}", "geocoding": geo, "weather": weather}})

    if agent_id == AGENT_ID_TRAVEL:
        city = str(location).strip()
        if city not in allow_travel:
            return _json_response(event, 400, {"error": {"code": "CITY_NOT_ALLOWED", "message": "Choose a city from dropdown"}})

        travel = get_travel_info(city)
        return _json_response(event, 200, {"result": {"title": f"Travel plan: {city}", "city": city, "travel_plan": travel}})

    return _json_response(event, 400, {"error": {"code": "INVALID_AGENT", "message": "Unknown agent_id"}})


# --- Lambda entrypoint --------------------------------------------------------

def lambda_handler(event: dict, context: Any) -> dict:
    method = _get_method(event)
    path = _get_path(event)

    if method == "OPTIONS":
        return _json_response(event, 200, {"ok": True})

    if method == "GET" and path.endswith("/agents"):
        return _handle_get_agents(event)

    if method == "POST" and path.endswith("/agent/run"):
        try:
            return _handle_post_agent_run(event)
        except ValueError as e:
            return _json_response(event, 400, {"error": {"code": "BAD_REQUEST", "message": str(e)}})
        except Exception as e:
            return _json_response(event, 500, {"error": {"code": "AGENT_FAILED", "message": str(e)}})

    return _json_response(event, 404, {"error": {"code": "NOT_FOUND", "message": "Route not found"}})