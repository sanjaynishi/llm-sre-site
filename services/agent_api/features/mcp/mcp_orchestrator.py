# services/agent_api/features/mcp/mcp_orchestrator.py

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import urllib.request
import urllib.error


@dataclass
class McpStep:
    step: int
    name: str
    type: str                 # "plan" | "tool" | "observe" | "retry" | "reason" | "recommend"
    status: str               # "ok" | "warn" | "error"
    started_at: str
    finished_at: str
    detail: Dict[str, Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_request(method: str, url: str, body: Optional[dict] = None, timeout_sec: int = 12) -> Dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        import json
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            return {
                "ok": True,
                "status": resp.status,
                "content_type": ct,
                "body": raw.decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": int(getattr(e, "code", 0) or 0),
            "content_type": e.headers.get("Content-Type", ""),
            "body": raw,
        }
    except Exception as e:
        return {
            "ok": False,
            "status": 0,
            "content_type": "",
            "body": str(e),
        }


def run_mcp_scenario(scenario: str, base_url: str) -> Dict[str, Any]:
    """
    MCP MVP: one-shot run, returns a full trace.
    This is intentionally synchronous to keep it simple in Lambda.
    """
    run_id = f"mcp-{uuid.uuid4().hex[:10]}"
    started_at = _now_iso()
    steps: List[McpStep] = []
    step_no = 0

    def add_step(name: str, type_: str, status: str, detail: Dict[str, Any], t0: float) -> None:
        nonlocal step_no
        step_no += 1
        steps.append(
            McpStep(
                step=step_no,
                name=name,
                type=type_,
                status=status,
                started_at=datetime.fromtimestamp(t0, tz=timezone.utc).isoformat(),
                finished_at=_now_iso(),
                detail=detail,
            )
        )

    # -------------------------
    # Step 1: Planner (LLM-like)
    # -------------------------
    t0 = time.time()
    plan = {
        "goal": "Diagnose first-call HTML/504 issue and prove retry behavior",
        "steps": [
            {"tool": "GET", "path": "/api/health"},
            {"tool": "POST", "path": "/api/runbooks/ask", "body": {"question": "hello", "top_k": 5}},
            {"tool": "POST", "path": "/api/runbooks/ask", "body": {"question": "hello", "top_k": 5}, "retry": True},
        ],
        "why_agentic": "We create a plan, execute tools, observe anomalies, retry with strategy, then recommend fixes.",
    }
    add_step("Create execution plan", "plan", "ok", {"plan": plan}, t0)

    # Scenario routing (only one scenario for now)
    if scenario not in ("first-call-html", "first-call-504", "first-call-timeout"):
        scenario = "first-call-html"

    # -------------------------
    # Step 2: Tool - GET /health
    # -------------------------
    t0 = time.time()
    health = _http_request("GET", f"{base_url}/api/health", timeout_sec=10)
    add_step(
        "Probe health endpoint",
        "tool",
        "ok" if health["ok"] else "warn",
        {
            "request": {"method": "GET", "url": f"{base_url}/api/health"},
            "response": {"status": health["status"], "content_type": health["content_type"]},
        },
        t0,
    )

    # -------------------------
    # Step 3: Tool - POST /runbooks/ask (first attempt)
    # -------------------------
    t0 = time.time()
    first = _http_request(
        "POST",
        f"{base_url}/api/runbooks/ask",
        body={"question": "hello", "top_k": 5},
        timeout_sec=15,
    )
    first_is_html = "text/html" in (first.get("content_type") or "").lower()
    first_failed = (not first["ok"]) or first_is_html

    add_step(
        "Runbooks ask (first attempt)",
        "tool",
        "warn" if first_failed else "ok",
        {
            "request": {"method": "POST", "url": f"{base_url}/api/runbooks/ask"},
            "response": {
                "status": first["status"],
                "content_type": first["content_type"],
                "body_head": (first.get("body") or "")[:240],
            },
            "interpretation": (
                "Non-JSON (text/html) indicates CloudFront error page or upstream timeout"
                if first_is_html
                else "OK"
            ),
        },
        t0,
    )

    # -------------------------
    # Step 4: Retry strategy
    # -------------------------
    t0 = time.time()
    retry_note = {
        "why_retry": "First call can fail due to cold start / heavy init; retry should succeed if backend is healthy.",
        "backoff_ms": 250,
    }
    time.sleep(0.25)
    add_step("Apply retry strategy", "retry", "ok", retry_note, t0)

    # -------------------------
    # Step 5: Tool - POST /runbooks/ask (retry)
    # -------------------------
    t0 = time.time()
    second = _http_request(
        "POST",
        f"{base_url}/api/runbooks/ask",
        body={"question": "hello", "top_k": 5},
        timeout_sec=20,
    )
    second_is_html = "text/html" in (second.get("content_type") or "").lower()
    second_ok = second["ok"] and (not second_is_html)

    add_step(
        "Runbooks ask (retry)",
        "tool",
        "ok" if second_ok else "error",
        {
            "response": {
                "status": second["status"],
                "content_type": second["content_type"],
                "body_head": (second.get("body") or "")[:240],
            }
        },
        t0,
    )

    # -------------------------
    # Step 6: Reason + Recommend
    # -------------------------
    t0 = time.time()
    root_cause = {
        "likely_root_cause": "Cold start / initialization latency causing CloudFront to return HTML error page on first call.",
        "signals": [
            "First attempt sometimes returns text/html CloudFront error page (504) then retry returns JSON 200.",
            "Health endpoint is consistently JSON.",
        ],
        "confidence": "high" if second_ok and first_failed else "medium",
    }
    add_step("Root-cause reasoning", "reason", "ok", root_cause, t0)

    t0 = time.time()
    recommendations = {
        "recommended_actions": [
            "Add client-side retry when response content-type is not JSON (1 quick retry with small backoff).",
            "Lazy-load heavy components (Chroma download/init) only when /runbooks/ask is called (you already do, but ensure no eager init).",
            "Optional: scheduled warm-up ping to /api/health (or /api/runbooks/ask with trivial question) every 5–10 min in dev.",
            "If needed: increase API Gateway/Lambda timeout or reduce first-call init size.",
        ]
    }
    add_step("Recommended fixes", "recommend", "ok", recommendations, t0)

    finished_at = _now_iso()
    return {
        "ok": True,
        "run_id": run_id,
        "scenario": scenario,
        "base_url": base_url,
        "started_at": started_at,
        "finished_at": finished_at,
        "steps": [asdict(s) for s in steps],
    }