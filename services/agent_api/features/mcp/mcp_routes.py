# services/agent_api/features/mcp/mcp_routes.py

from __future__ import annotations

from typing import Any, Dict

from core.response import json_response
from core.request import get_body_json

from .mcp_orchestrator import run_mcp_scenario


_ALLOWED_BASE_URLS = {
    "https://dev.aimlsre.com",
    "https://aimlsre.com",
    "https://www.aimlsre.com",
}


def handle_post_mcp_run(event: Dict[str, Any]) -> Dict[str, Any]:
    req = get_body_json(event)
    scenario = (req.get("scenario") or "first-call-html").strip()

    base_url = (req.get("base_url") or "https://dev.aimlsre.com").strip().rstrip("/")

    if base_url not in _ALLOWED_BASE_URLS:
        return json_response(
            event,
            400,
            {
                "error": {
                    "code": "INVALID_BASE_URL",
                    "message": "base_url not allowed",
                    "allowed": sorted(_ALLOWED_BASE_URLS),
                }
            },
        )

    trace = run_mcp_scenario(scenario=scenario, base_url=base_url)
    return json_response(event, 200, trace)