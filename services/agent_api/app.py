"""
LLM SRE Agent API (Lambda)

Endpoints (behind CloudFront /api/*):
  GET  /api/agents        -> returns agent catalog (weather + travel)
  POST /api/agent/run     -> runs a selected agent (weather or travel)
  OPTIONS *               -> CORS preflight

Weather:
- Uses Open-Meteo Geocoding + Forecast APIs.
- Returns current + hourly + daily (full JSON).

Travel:
- Uses OpenAI Responses API to generate compact travel JSON.
- Cost-controlled allow-list of cities.
- Uses env vars: OPENAI_API_KEY (required for travel), OPENAI_MODEL (optional).

Python 3.11 compatible.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from openai import OpenAI


# --- Config / Guardrails ------------------------------------------------------

# Allowed origins for CORS (tighten as you want).
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

# Hard-coded allow-list (next step: load from S3 agents.json)
ALLOWED_LOCATIONS = {
    "New York, NY",
    "San Francisco, CA",
    "Seattle, WA",
    "London, UK",
    "Delhi, India",
    "Tokyo, Japan",
}

# Travel allow-list (keep small for cost control)
ALLOWED_CITIES = {
    "Paris",
    "London",
    "New York",
    "Tokyo",
    "Rome",
}

AGENT_ID_WEATHER = "agent-weather"
AGENT_ID_TRAVEL = "agent-travel"


# --- Helpers ------------------------------------------------------------------

def _pick_cors_origin(event: dict) -> str:
    """Return a safe Access-Control-Allow-Origin value."""
    headers = event.get("headers") or {}
    origin = headers.get("origin") or headers.get("Origin")
    if origin and origin in ALLOWED_ORIGINS:
        return origin
    return "*"  # safe default for your current use-case


def _json_response(event: dict, status_code: int, body: dict, extra_headers: dict | None = None) -> dict:
    cors_origin = _pick_cors_origin(event)
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": cors_origin,
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
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


def _http_get_json(url: str, timeout_sec: int = 8) -> dict:
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


# --- Open-Meteo Calls ---------------------------------------------------------

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


# --- OpenAI Travel ------------------------------------------------------------

def _openai_client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    return OpenAI(api_key=key)


def _extract_output_text(resp: Any) -> str:
    # Works across newer SDK variants
    txt = getattr(resp, "output_text", None)
    if isinstance(txt, str) and txt.strip():
        return txt.strip()

    acc = ""
    for item in getattr(resp, "output", []) or []:
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    acc += content.get("text", "")
    return (acc or "").strip()


def generate_travel_plan(city: str) -> dict:
    client = _openai_client()
    model = os.environ.get("OPENAI_MODEL", "gpt-5.1-mini")

    prompt = f"""
You are a travel planning assistant.

City: {city}

Return VALID JSON ONLY with this exact structure:

{{
  "weather_outlook": {{
    "next_2_days": "sunny | partly cloudy | cloudy | rainy",
    "next_5_days": "sunny | partly cloudy | cloudy | rainy"
  }},
  "itinerary_2_days": [
    "Day 1: ...",
    "Day 2: ..."
  ],
  "itinerary_5_days": [
    "Day 1: ...",
    "Day 2: ...",
    "Day 3: ...",
    "Day 4: ...",
    "Day 5: ..."
  ],
  "estimated_cost_usd": {{
    "flights_for_2": number,
    "hotel_4_star_5_nights": number,
    "local_transport_food": number,
    "total": number
  }},
  "travel_tips": [
    "...",
    "...",
    "..."
  ]
}}

Rules:
- Keep responses concise and realistic
- Assume travel from a major US city
- Costs approximate, not exact
- total must equal the sum of all cost fields
- No markdown, no explanations, JSON only
"""

    resp = client.responses.create(
        model=model,
        input=prompt,
        max_output_tokens=650,
    )

    raw = _extract_output_text(resp)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON from model", "raw_output": raw[:1200]}

    # enforce total correctness
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
    agents = {
        "agents": [
            {
                "id": AGENT_ID_WEATHER,
                "category": "Weather",
                "label": "Weather information (full details)",
                "mode": "tool_weather",
                "allowed_locations": sorted(ALLOWED_LOCATIONS),
            },
            {
                "id": AGENT_ID_TRAVEL,
                "category": "Travel",
                "label": "Travel planner (AI-powered)",
                "mode": "tool_travel",
                "allowed_locations": sorted(ALLOWED_CITIES),
            },
        ]
    }
    return _json_response(event, 200, agents)


def _handle_post_agent_run(event: dict) -> dict:
    req = _get_body_json(event)
    agent_id = req.get("agent_id")
    location = req.get("location")

    if not agent_id:
        return _json_response(event, 400, {"error": {"code": "MISSING_AGENT", "message": "agent_id is required"}})

    if not location:
        return _json_response(event, 400, {"error": {"code": "MISSING_LOCATION", "message": "location is required"}})

    # --- WEATHER ---
    if agent_id == AGENT_ID_WEATHER:
        if location not in ALLOWED_LOCATIONS:
            return _json_response(
                event,
                400,
                {"error": {"code": "LOCATION_NOT_ALLOWED", "message": "Choose a location from dropdown"}},
            )

        geo = geocode_location(location)
        if geo.get("lat") is None or geo.get("lon") is None:
            return _json_response(
                event,
                500,
                {"error": {"code": "GEOCODE_FAILED", "message": "Geocoding did not return coordinates"}},
            )

        weather = fetch_weather(float(geo["lat"]), float(geo["lon"]))

        return _json_response(
            event,
            200,
            {
                "result": {
                    "title": f"Weather: {location}",
                    "geocoding": geo,
                    "weather": weather,
                }
            },
        )

    # --- TRAVEL ---
    if agent_id == AGENT_ID_TRAVEL:
        city = location.strip()
        if city not in ALLOWED_CITIES:
            return _json_response(
                event,
                400,
                {"error": {"code": "CITY_NOT_ALLOWED", "message": "Choose a city from dropdown"}},
            )

        try:
            travel = generate_travel_plan(city)
        except Exception as e:
            return _json_response(event, 500, {"error": {"code": "TRAVEL_FAILED", "message": str(e)}})

        return _json_response(
            event,
            200,
            {"result": {"title": f"Travel plan: {city}", "city": city, "travel_plan": travel}},
        )

    return _json_response(event, 400, {"error": {"code": "INVALID_AGENT", "message": "Unknown agent_id"}})


# --- Lambda entrypoint --------------------------------------------------------

def lambda_handler(event: dict, context: Any) -> dict:
    method = _get_method(event)
    path = _get_path(event)

    if method == "OPTIONS":
        return _json_response(event, 200, {"ok": True})

    # route by suffix so it works behind /api/* on CloudFront
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