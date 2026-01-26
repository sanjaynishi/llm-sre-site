from __future__ import annotations

import json

ALLOWED_ORIGINS = {
    "https://dev.aimlsre.com",
    "https://aimlsre.com",
    "https://www.aimlsre.com",
}


def pick_cors_origin(event: dict) -> str:
    headers = event.get("headers") or {}
    origin = headers.get("origin") or headers.get("Origin")
    return origin if origin in ALLOWED_ORIGINS else "*"


def json_response(event: dict, status_code: int, body: dict, extra_headers: dict | None = None) -> dict:
    cors_origin = pick_cors_origin(event)
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": str(cors_origin),
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": (
            "Content-Type,Authorization,X-Requested-With,X-Amz-Date,X-Api-Key,X-Amz-Security-Token"
        ),
        "Vary": "Origin",
    }
    if extra_headers:
        for k, v in extra_headers.items():
            headers[str(k)] = str(v)

    return {
        "statusCode": int(status_code),
        "headers": headers,
        "body": json.dumps(body, default=str),
    }