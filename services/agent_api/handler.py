import os
import json
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from openai import OpenAI

# -------- OpenAI setup (secure via env vars) --------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.1-mini")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}

# -------- Small HTTP helper (stdlib) --------
def http_get_json(url: str, timeout: int = 10) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "aimlsre-agent/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


# -------- Open-Meteo Weather (Geocode + Forecast) --------
def geocode_location(name: str) -> Dict[str, Any]:
    """
    Uses Open-Meteo Geocoding API to resolve a location string to lat/lon.
    """
    q = urllib.parse.quote(name)
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=en&format=json"
    data = http_get_json(url)
    results = data.get("results") or []
    if not results:
        raise ValueError(f"Could not geocode location: {name}")
    r = results[0]
    return {
        "name": r.get("name"),
        "country": r.get("country"),
        "admin1": r.get("admin1"),
        "latitude": r.get("latitude"),
        "longitude": r.get("longitude"),
        "timezone": r.get("timezone") or "auto",
    }


def get_weather_full(location: str) -> Dict[str, Any]:
    """
    Returns a UI-friendly structure:
    {
      "title": "...",
      "weather": {
         "location": {...},
         "current": {...},
         "current_units": {...},
         "daily": {...},
         "daily_units": {...}
      }
    }
    """
    loc = geocode_location(location)
    lat = loc["latitude"]
    lon = loc["longitude"]
    tz = urllib.parse.quote(loc.get("timezone") or "auto")

    # Keep the payload useful but not huge
    # current: temperature, feels-like, humidity, wind, precipitation
    # daily: max/min temp + precip probability + sunshine duration (optional)
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&timezone={tz}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,precipitation"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&forecast_days=7"
    )

    data = http_get_json(url)

    # Normalize keys for the UI page you already have
    current = data.get("current") or {}
    current_units = data.get("current_units") or {}
    daily = data.get("daily") or {}
    daily_units = data.get("daily_units") or {}

    title_loc = ", ".join(
        [p for p in [loc.get("name"), loc.get("admin1"), loc.get("country")] if p]
    )

    return {
        "title": f"Weather for {title_loc}",
        "weather": {
            "location": loc,
            "current": current,
            "current_units": current_units,
            "daily": daily,
            "daily_units": daily_units,
        },
    }


# -------- Travel Agent Logic --------
def get_travel_info(city: str) -> dict:
    if not client:
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
- Costs should be approximate, not exact
- total must equal the sum of all cost fields
- No markdown, no explanations, JSON only
"""

    resp = client.responses.create(
        model=MODEL,
        input=prompt,
        max_output_tokens=650,
    )

    # Safe extraction across SDK versions:
    raw_text = getattr(resp, "output_text", None)
    if raw_text is None:
        raw_text = ""
        for item in getattr(resp, "output", []) or []:
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        raw_text += content.get("text", "")
    raw_text = (raw_text or "").strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON from model", "raw_output": raw_text[:1200]}

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


# -------- Lambda Router --------
def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("rawPath", "") or ""
    qs = event.get("queryStringParameters") or {}

    # CORS preflight
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": json.dumps({"ok": True})}

    # ---- Catalog endpoint ----
    if method == "GET" and path == "/api/agents":
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(
                {
                    "agents": [
                        {
                            "id": "agent-weather",
                            "category": "Weather",
                            "label": "Weather information (full details)",
                            "mode": "tool_weather",
                            "allowed_locations": [
                                "Delhi, India",
                                "London, UK",
                                "New York, NY",
                                "San Francisco, CA",
                                "Seattle, WA",
                                "Tokyo, Japan",
                            ],
                        },
                        {
                            "id": "agent-travel",
                            "category": "Travel",
                            "label": "Travel planner (AI-powered)",
                            "mode": "tool_travel",
                            "allowed_locations": ["Paris", "London", "New York", "Tokyo", "Rome"],
                        },
                    ]
                }
            ),
        }

    # ---- Run endpoint ----
    if method == "POST" and path == "/api/agent/run":
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Invalid JSON body"}),
            }

        agent_id = body.get("agent_id")
        location = body.get("location")  # for travel, treat as city
        if not agent_id or not location:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "agent_id and location are required"}),
            }

        try:
            if agent_id == "agent-weather":
                result = get_weather_full(location)
                return {"statusCode": 200, "headers": CORS_HEADERS, "body": json.dumps({"result": result})}

            if agent_id == "agent-travel":
                result = get_travel_info(location)
                return {"statusCode": 200, "headers": CORS_HEADERS, "body": json.dumps({"result": result})}

            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": f"Unknown agent_id: {agent_id}"}),
            }
        except Exception as e:
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Agent execution failed", "details": str(e)}),
            }

    return {"statusCode": 404, "headers": CORS_HEADERS, "body": json.dumps({"error": "Not found"})}