"""
LLM SRE Agent API (Lambda)

Endpoints (behind CloudFront /api/*):
  GET  /api/agents        -> returns agent catalog (from S3 if configured; fallback otherwise)
  POST /api/agent/run     -> runs a selected agent:
       - agent-weather (Open-Meteo)
       - agent-travel  (OpenAI over HTTPS, no SDK required)
  OPTIONS *               -> CORS preflight
"""

from __future__ import annotations

import base64
import json
import os
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

# Hard-coded fallbacks (used if S3 config missing/unreadable)
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
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2").strip()

# Optional: comma-separated fallback models (try in order if model_not_found)
# Example: "gpt-5.2,gpt-5"
OPENAI_FALLBACK_MODELS = [
    m.strip() for m in os.environ.get("OPENAI_FALLBACK_MODELS", "").split(",") if m.strip()
]

AGENT_CONFIG_BUCKET = os.environ.get("AGENT_CONFIG_BUCKET", "").strip()
AGENT_CONFIG_PREFIX = os.environ.get("AGENT_CONFIG_PREFIX", "agent-config").strip()


# --- S3 helpers (config) ------------------------------------------------------

_s3 = None
_config_cache = {"agents": None, "allowlists": None}


def _s3_client():
    global _s3
    if boto3 is None:
        raise RuntimeError("boto3 not available")
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _s3_get_json(bucket: str, key: str) -> dict:
    try:
        resp = _s3_client().get_object(Bucket=bucket, Key=key)
        raw = resp["Body"].read().decode("utf-8")
        return json.loads(raw)
    except ClientError as e:
        raise RuntimeError(f"S3 get_object failed for s3://{bucket}/{key}: {e}") from e


def _load_agent_config() -> Tuple[dict, dict]:
    """
    Returns (agents_json, allowlists_json).
    If S3 config missing/unavailable, returns ({}, {}) and caller falls back.
    Uses simple warm-start cache (Lambda).
    """
    if not AGENT_CONFIG_BUCKET:
        return {}, {}

    if _config_cache["agents"] is not None and _config_cache["allowlists"] is not None:
        return _config_cache["agents"], _config_cache["allowlists"]

    agents_key = f"{AGENT_CONFIG_PREFIX}/agents.json"
    allow_key = f"{AGENT_CONFIG_PREFIX}/allowlists.json"

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
    return agents, allow


def _normalize_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for x in value:
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def _effective_allowlists() -> Tuple[list[str], list[str]]:
    """
    Returns (weather_locations, travel_cities) using allowlists.json if present,
    else fall back to hard-coded defaults.
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
        weather_locations = sorted(DEFAULT_ALLOWED_LOCATIONS)
    if not travel_cities:
        travel_cities = sorted(DEFAULT_TRAVEL_CITIES)

    return weather_locations, travel_cities


# --- HTTP helpers -------------------------------------------------------------

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


# --- OpenAI Travel (stdlib-only HTTPS) ----------------------------------------

def _openai_call(model: str, prompt: str) -> dict:
    url = "https://api.openai.com/v1/responses"
    payload = {
        "model": model,
        "input": prompt,
        "max_output_tokens": 650,
    }
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    return _http_post_json(url, payload, headers=headers, timeout_sec=25)


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

    # Try primary model, then fallback models if model_not_found happens.
    models_to_try = [OPENAI_MODEL] + [m for m in OPENAI_FALLBACK_MODELS if m != OPENAI_MODEL]

    last_err = None
    resp = None

    for m in models_to_try:
        try:
            resp = _openai_call(m, prompt)
        except Exception as e:
            last_err = f"OpenAI call failed (model={m}): {e}"
            continue

        # OpenAI error payloads are usually like: {"error": {...}}
        if isinstance(resp, dict) and resp.get("error"):
            err_obj = resp.get("error") or {}
            code = err_obj.get("code") or ""
            msg = err_obj.get("message") or str(err_obj)
            last_err = f"OpenAI API error (model={m}): {code} {msg}"

            # Retry only if model not found
            if code == "model_not_found" or "does not exist" in str(msg).lower():
                continue

            return {"error": last_err}

        # Success
        break

    if not isinstance(resp, dict) or resp.get("error"):
        return {"error": last_err or "OpenAI call failed"}

    # Extract output text
    output_text = ""
    for item in resp.get("output", []) or []:
        if item.get("type") == "message":
            for c in item.get("content", []) or []:
                if c.get("type") in ("output_text", "text"):
                    output_text += c.get("text", "")

    output_text = (output_text or "").strip() or (resp.get("output_text") or "").strip()
    if not output_text:
        return {"error": "OpenAI returned empty output"}

    candidate = _extract_json_object(output_text)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON from model", "raw_output": output_text[:1200]}

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


# --- API Routes ---------------------------------------------------------------

def _handle_get_agents(event: dict) -> dict:
    # fallback catalog if S3 is missing/unreadable
    default_agents = {
        "agents": [
            {
                "id": AGENT_ID_WEATHER,
                "category": "Weather",
                "label": "Weather information (full details)",
                "mode": "tool_weather",
                "allowed_locations": sorted(DEFAULT_ALLOWED_LOCATIONS),
            },
            {
                "id": AGENT_ID_TRAVEL,
                "category": "Travel",
                "label": "Travel planner (AI-powered)",
                "mode": "tool_travel",
                "allowed_locations": sorted(DEFAULT_TRAVEL_CITIES),
            },
        ]
    }

    try:
        agents_cfg, _ = _load_agent_config()
        weather_locations, travel_cities = _effective_allowlists()

        # agents.json structure: { "agents": [ {id,category,label,mode}, ... ] }
        if isinstance(agents_cfg, dict) and isinstance(agents_cfg.get("agents"), list):
            merged = {"agents": []}
            for a in agents_cfg["agents"]:
                if not isinstance(a, dict) or not a.get("id"):
                    continue
                a2 = dict(a)
                if a2["id"] == AGENT_ID_WEATHER:
                    a2["allowed_locations"] = weather_locations
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