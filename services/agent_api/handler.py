import os
import json
from openai import OpenAI

# -------- OpenAI setup (secure via env vars) --------
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.1-mini")


# -------- Core Travel Agent Logic --------
def get_travel_info(city: str) -> dict:
    """
    Returns compact, UI-friendly travel info as JSON.
    """

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

    response = client.responses.create(
        model=MODEL,
        input=prompt,
        max_output_tokens=600
    )

    # -------- Safe JSON extraction --------
    raw_text = ""
    for item in response.output:
        if item["type"] == "message":
            for content in item["content"]:
                if content["type"] == "output_text":
                    raw_text += content["text"]

    raw_text = raw_text.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Failsafe if model output drifts
        return {
            "error": "Failed to parse travel info",
            "raw_output": raw_text
        }


# -------- Lambda Router --------
def handler(event, context):
    """
    GET /api/agents?city=Paris
    """

    city = ((event.get("queryStringParameters") or {}).get("city") or "").strip()

    if not city:
        return {
            "statusCode": 400,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Query parameter 'city' is required"})
        }

    try:
        travel_info = get_travel_info(city)

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({
                "city": city,
                "travel_plan": travel_info
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({
                "error": "Internal server error",
                "details": str(e)
            })
        }