# services/agent_api/features/mcp/mcp_orchestrator.py

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import urllib.request
import urllib.error


@dataclass
class McpStep:
    step: int
    name: str
    type: str                 # "plan" | "tool" | "note" | "retry" | "reason" | "recommend"
    status: str               # "ok" | "warn" | "error"
    started_at: str
    finished_at: str
    detail: Dict[str, Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_request(
    method: str,
    url: str,
    body: Optional[dict] = None,
    timeout_sec: int = 12,
    headers: Optional[dict] = None,
) -> Dict[str, Any]:
    data = None
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)

    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=h, method=method)
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


def _looks_like_html(content_type: str, body: str) -> bool:
    ct = (content_type or "").lower()
    if "text/html" in ct:
        return True
    head = (body or "").lstrip()[:40].lower()
    return head.startswith("<!doctype html") or head.startswith("<html")


def _normalize_scenario(s: Optional[str]) -> str:
    s = (s or "").strip()
    allowed = {"first-call-html", "quantum-sre-10"}
    # ✅ IMPORTANT: default to first-call scenario (never default to quantum)
    if s not in allowed:
        return "first-call-html"
    return s


def _add_step(steps: List[McpStep], name: str, type_: str, status: str, detail: Dict[str, Any], t0: float) -> None:
    step_no = len(steps) + 1
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


def run_mcp_scenario(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    MCP run: scenario-driven orchestration.
    payload must include:
      - scenario
      - base_url
    """
    run_id = f"mcp-{uuid.uuid4().hex[:10]}"
    started_at = _now_iso()

    scenario = _normalize_scenario(payload.get("scenario"))
    base_url = (payload.get("base_url") or "").rstrip("/")
    if not base_url:
        # fail fast: base_url is required for consistent behavior
        return {
            "ok": False,
            "run_id": run_id,
            "error": {"code": "BAD_REQUEST", "message": "base_url is required"},
        }

    steps: List[McpStep] = []

    # -------------------------
    # Scenario: FIRST-CALL HTML
    # -------------------------
    if scenario == "first-call-html":
        # Step 1: plan (keep it deterministic / cheap)
        t0 = time.time()
        plan = {
            "goal": "Diagnose first-call HTML/504 issue and prove retry behavior",
            "why_agentic": "We plan, execute tools, observe anomalies (HTML/504), apply retry strategy, then recommend mitigations.",
            "steps": [
                {"tool": "GET", "path": "/api/health"},
                {"tool": "POST", "path": "/api/runbooks/ask", "body": {"question": "hello", "top_k": 5}},
                {"tool": "POST", "path": "/api/runbooks/ask", "body": {"question": "hello", "top_k": 5}, "retry": True},
            ],
        }
        _add_step(steps, "Create execution plan", "plan", "ok", {"plan": plan}, t0)

        # Step 2: GET /api/health
        t0 = time.time()
        health = _http_request("GET", f"{base_url}/api/health", timeout_sec=10)
        _add_step(
            steps,
            "Probe health endpoint",
            "tool",
            "ok" if health["ok"] and not _looks_like_html(health["content_type"], health["body"]) else "warn",
            {
                "request": {"method": "GET", "url": f"{base_url}/api/health"},
                "response": {
                    "status": health["status"],
                    "content_type": health["content_type"],
                    "body_head": (health.get("body") or "")[:180],
                },
            },
            t0,
        )

        # Step 3: POST /api/runbooks/ask (first attempt)
        t0 = time.time()
        first = _http_request(
            "POST",
            f"{base_url}/api/runbooks/ask",
            body={"question": "hello", "top_k": 5},
            timeout_sec=20,
        )
        first_is_html = _looks_like_html(first.get("content_type", ""), first.get("body", ""))
        first_failed = (not first["ok"]) or first_is_html

        _add_step(
            steps,
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
                "interpretation": "HTML/timeout indicates CloudFront/origin issue (cold start, timeout, or routing)"
                if first_is_html or not first["ok"]
                else "OK",
            },
            t0,
        )

        # Step 4: retry strategy (only if needed)
        if first_failed:
            t0 = time.time()
            backoff_ms = 350
            time.sleep(backoff_ms / 1000.0)
            _add_step(
                steps,
                "Apply retry strategy",
                "retry",
                "ok",
                {"why_retry": "First call can fail due to cold start / init latency; retry often succeeds.", "backoff_ms": backoff_ms},
                t0,
            )

            # Step 5: retry POST
            t0 = time.time()
            second = _http_request(
                "POST",
                f"{base_url}/api/runbooks/ask",
                body={"question": "hello", "top_k": 5},
                timeout_sec=25,
            )
            second_is_html = _looks_like_html(second.get("content_type", ""), second.get("body", ""))
            second_ok = second["ok"] and (not second_is_html)

            _add_step(
                steps,
                "Runbooks ask (retry)",
                "tool",
                "ok" if second_ok else "error",
                {
                    "response": {
                        "status": second["status"],
                        "content_type": second["content_type"],
                        "body_head": (second.get("body") or "")[:240],
                    },
                    "interpretation": "Retry succeeded" if second_ok else "Retry still failing (origin timeout/routing/security).",
                },
                t0,
            )

        # Step 6: reasoning
        t0 = time.time()
        _add_step(
            steps,
            "Root-cause reasoning",
            "reason",
            "ok",
            {
                "likely_root_cause": "Cold start / init latency or origin timeout causing CloudFront to return HTML error on first call.",
                "confidence": "medium",
                "signals": [
                    "HTML error page or 5xx seen on first call (intermittent).",
                    "/api/health often returns JSON even when /api/runbooks/ask is slow.",
                ],
            },
            t0,
        )

        # Step 7: recommendations
        t0 = time.time()
        _add_step(
            steps,
            "Recommended fixes",
            "recommend",
            "ok",
            {
                "recommended_actions": [
                    "Client-side soft retry when response is non-JSON or 502/503/504.",
                    "Warm-up ping (or scheduled invoke) to reduce cold starts in dev.",
                    "Increase origin/API timeout where applicable; reduce first-call init (lazy-load heavy components).",
                    "Confirm CloudFront behavior for /api/* routes to API Gateway (not S3).",
                ]
            },
            t0,
        )

        return {
            "ok": True,
            "run_id": run_id,
            "scenario": scenario,
            "base_url": base_url,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "steps": [asdict(s) for s in steps],
        }

    # -------------------------
    # Scenario: QUANTUM (still LLM-driven in your setup)
    # -------------------------
    # Keep your existing quantum LLM-based flow here.
    # IMPORTANT: ensure it is only reached when scenario == "quantum-sre-10".
    return {
        "ok": False,
        "run_id": run_id,
        "scenario": scenario,
        "error": {"code": "NOT_IMPLEMENTED", "message": "quantum-sre-10 handler not included in this patch snippet"},
    }