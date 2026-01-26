# core/request.py
from __future__ import annotations

import base64
import json
from typing import Any, Dict


def get_method(event: dict) -> str:
    """Return HTTP method for both HTTP API v2 and REST API v1 shapes."""
    return (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or ""
    ).upper()


def get_path(event: dict) -> str:
    """Return normalized path. CloudFront forwards /api/* -> APIGW; we strip '/api'."""
    path = event.get("rawPath") or event.get("path") or "/"
    if path.startswith("/api/"):
        path = path[4:]  # remove "/api"
    return path


def get_body_json(event: dict) -> Dict[str, Any]:
    """Parse JSON body; supports base64 encoding from API Gateway."""
    body = event.get("body") or ""
    if not body:
        return {}

    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", errors="replace")

    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON body: {e}") from e