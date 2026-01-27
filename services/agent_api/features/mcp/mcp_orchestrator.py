# services/agent_api/features/mcp/mcp_orchestrator.py

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import urllib.request
import urllib.error

from openai import OpenAI


@dataclass
class McpStep:
    step: int
    name: str
    type: str            # "plan" | "tool" | "retry" | "reason" | "recommend" | "note"
    status: str          # "ok" | "warn" | "error"
    started_at: str
    finished_at: str
    detail: Dict[str, Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_loads(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except Exception:
        return None


def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    j = _safe_json_loads(text)
    if isinstance(j, dict):
        return j
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        j2 = _safe_json_loads(text[start : end + 1])
        if isinstance(j2, dict):
            return j2
    return None


# -----------------------
# HTTP tool executor
# -----------------------

def _http_request(method: str, url: str, body: Optional[dict] = None, timeout_sec: int = 12) -> Dict[str, Any]:
    data = None
    headers = {
        "Accept": "application/json",
        # IMPORTANT: avoid CloudFront/WAF blocking Python urllib UA
        "User-Agent": "Mozilla/5.0 (compatible; aimlsre-mcp/1.0; +https://aimlsre.com)"
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            return {
                "ok": True,
                "status": int(getattr(resp, "status", 200) or 200),
                "content_type": ct,
                "body": raw.decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": int(getattr(e, "code", 0) or 0),
            "content_type": (e.headers.get("Content-Type", "") if e.headers else ""),
            "body": raw,
        }
    except Exception as e:
        return {"ok": False, "status": 0, "content_type": "", "body": str(e)}


def _looks_like_html(resp: Dict[str, Any]) -> bool:
    ct = (resp.get("content_type") or "").lower()
    body = (resp.get("body") or "")
    if "text/html" in ct:
        return True
    b = body.lstrip().lower()
    return b.startswith("<!doctype html") or b.startswith("<html")


# -----------------------
# OpenAI helpers (one model)
# -----------------------

def _openai_client() -> OpenAI:
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    api_key = os.environ.get("OPENAI_API_KEY", "").strip() or None
    if base_url:
        return OpenAI(base_url=base_url, api_key=api_key)
    return OpenAI(api_key=api_key)


def _mcp_model() -> str:
    return os.environ.get("MCP_MODEL", "").strip() or "gpt-4.1-mini"


def _llm_json(client: OpenAI, model: str, system: str, user: str, timeout_sec: int = 25) -> Tuple[Optional[dict], str]:
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_output_tokens=1400,
        timeout=timeout_sec,
    )
    raw = getattr(resp, "output_text", "") or ""
    raw = raw.strip()
    return _extract_json_object(raw), raw


# -----------------------
# Scenario specs
# -----------------------

def _scenario_spec(scenario: str) -> Dict[str, Any]:
    # QUANTUM: no tools (education flow), so it never triggers CF/WAF issues
    if scenario == "quantum-sre-10":
        return {
            "scenario": "quantum-sre-10",
            "goal": "Explain quantum computing in practical SRE terms and produce a realistic, safe 10-step learning and experimentation plan.",
            "must_steps": 10,
            "allowed_tools": [],
            "notes": [
                "No hype. Clarify what quantum is NOT.",
                "Use SRE analogies (queues, retries, probabilistic outcomes, optimization).",
                "Give a safe roadmap using simulators (no paid hardware required).",
            ],
        }

    # DEFAULT: first-call-html (this can use tools)
    return {
        "scenario": "first-call-html",
        "goal": "Diagnose why the first API call sometimes returns HTML/504 instead of JSON and prove retry behavior, then recommend mitigations.",
        "must_steps": 7,
        "allowed_tools": [
            {"method": "GET", "path": "/api/health"},
            {"method": "POST", "path": "/api/runbooks/ask"},
        ],
        "notes": [
            "Detect HTML error pages vs JSON.",
            "Show a retry with small backoff.",
        ],
    }


def _validate_tool_call(tool: Dict[str, Any], allowed: List[Dict[str, str]]) -> Tuple[bool, str]:
    method = (tool.get("method") or tool.get("tool") or "").upper().strip()
    path = (tool.get("path") or "").strip()
    if not method or not path:
        return False, "Missing method/path"
    if not path.startswith("/api/"):
        return False, "Path must start with /api/"
    ok = any(a["method"] == method and a["path"] == path for a in allowed)
    if not ok:
        return False, f"Tool not allowed: {method} {path}"
    body = tool.get("body")
    if body is not None:
        try:
            bs = json.dumps(body)
            if len(bs) > 6000:
                return False, "Tool body too large"
        except Exception:
            return False, "Invalid tool body"
    return True, ""


# -----------------------
# Main orchestrator
# -----------------------

def run_mcp_scenario(scenario: str, base_url: str) -> Dict[str, Any]:
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

    scenario = (scenario or "").strip() or "first-call-html"
    base_url = (base_url or "").strip().rstrip("/") or "https://dev.aimlsre.com"

    spec = _scenario_spec(scenario)
    allowed_tools = spec.get("allowed_tools", [])

    client = _openai_client()
    model = _mcp_model()

    # ----------------
    # Step 1: PLAN (LLM)
    # ----------------
    t0 = time.time()
    system = "You are an SRE orchestration planner. Return STRICT JSON only. No markdown, no extra text."
    user = json.dumps(
        {
            "task": "Create an MCP execution plan.",
            "spec": spec,
            "output_contract": {
                "goal": "string",
                "why_agentic": "string",
                "steps": [
                    {
                        "name": "string",
                        "type": "note|tool|retry|reason|recommend",
                        "content": "string (required for non-tool steps)",
                        "tool": {"method": "GET|POST", "path": "/api/...", "body": {"any": "json"}}  # only when type=tool
                    }
                ]
            },
            "rules": [
                "Return valid JSON object only.",
                "For quantum-sre-10: produce EXACTLY 10 steps, ALL non-tool (no tool calls).",
                "For first-call-html: include /api/health, /api/runbooks/ask, then retry, then ask retry, plus reasoning and mitigations.",
                "Keep each step content short but useful (2-5 lines).",
                "Never use tools outside allowed_tools.",
            ],
        },
        ensure_ascii=False,
    )

    plan_json, plan_raw = _llm_json(client, model, system=system, user=user)
    if not plan_json:
        fallback = {
            "goal": spec["goal"],
            "why_agentic": "Fallback plan used because planner returned invalid JSON.",
            "steps": [
                {
                    "name": "Fallback note",
                    "type": "note",
                    "content": "Planner failed to return JSON. Please retry.",
                    "tool": None,
                }
            ],
        }
        add_step("Create execution plan", "plan", "warn", {"plan": fallback, "llm_raw_head": plan_raw[:500]}, t0)
        plan = fallback
    else:
        add_step("Create execution plan", "plan", "ok", {"plan": plan_json}, t0)
        plan = plan_json

    plan_steps = plan.get("steps") if isinstance(plan, dict) else []
    if not isinstance(plan_steps, list):
        plan_steps = []

    # ----------------
    # Execute plan steps
    # ----------------
    max_steps = 14

    for s in plan_steps[:max_steps]:
        name = (s.get("name") or "").strip() or "Step"
        type_ = (s.get("type") or "note").strip()
        content = (s.get("content") or "").strip()

        if type_ == "tool":
            t0 = time.time()
            ok, why = _validate_tool_call(s.get("tool") or {}, allowed_tools)
            if not ok:
                add_step(name, "tool", "error", {"error": "Tool validation failed", "why": why, "tool": s.get("tool")}, t0)
                continue

            tool = s["tool"]
            method = tool.get("method", tool.get("tool", "GET")).upper()
            path = tool["path"]
            body = tool.get("body")
            url = f"{base_url}{path}"

            resp = _http_request(method, url, body=body, timeout_sec=20)
            htmlish = _looks_like_html(resp)

            add_step(
                name,
                "tool",
                "ok" if resp["ok"] and not htmlish else "warn",
                {
                    "request": {"method": method, "url": url, "body": body},
                    "response": {
                        "status": resp.get("status"),
                        "content_type": resp.get("content_type"),
                        "body_head": (resp.get("body") or "")[:260],
                    },
                    "interpretation": "Looks like HTML error page (CloudFront/WAF/timeout)" if htmlish else "OK",
                },
                t0,
            )
            continue

        if type_ == "retry":
            t0 = time.time()
            time.sleep(0.25)
            add_step(name, "retry", "ok", {"content": content or "Backoff 250ms then retry." , "backoff_ms": 250}, t0)
            continue

        # Non-tool steps: show actual content from LLM plan
        t0 = time.time()
        add_step(
            name,
            type_,
            "ok",
            {"content": content or "(No content provided by planner.)"},
            t0,
        )

    # ----------------
    # Final summary (LLM)
    # ----------------
    t0 = time.time()
    trace = {
        "scenario": scenario,
        "base_url": base_url,
        "spec": spec,
        "steps": [asdict(x) for x in steps],
    }

    system2 = "You are an SRE analyst. Return STRICT JSON only. No markdown."
    user2 = json.dumps(
        {
            "task": "Summarize the run grounded ONLY in the trace.",
            "trace": trace,
            "output_contract": {
                "likely_root_cause": "string",
                "confidence": "low|medium|high",
                "recommended_actions": ["string"],
            },
            "rules": [
                "Do not invent tool outputs.",
                "If quantum: provide a clean 10-step learning summary and safe next actions.",
                "If first-call-html: mention cold start/timeouts/HTML pages and mitigations.",
            ],
        },
        ensure_ascii=False,
    )

    summary_json, summary_raw = _llm_json(client, model, system=system2, user=user2, timeout_sec=25)
    if not summary_json:
        add_step("LLM summary", "reason", "warn", {"error": "LLM returned invalid JSON", "llm_raw_head": summary_raw[:600]}, t0)
    else:
        add_step(
            "Root-cause reasoning",
            "reason",
            "ok",
            {"likely_root_cause": summary_json.get("likely_root_cause"), "confidence": summary_json.get("confidence")},
            t0,
        )
        t0 = time.time()
        add_step(
            "Recommended fixes",
            "recommend",
            "ok",
            {"recommended_actions": summary_json.get("recommended_actions") or []},
            t0,
        )

    finished_at = _now_iso()
    return {
        "ok": True,
        "run_id": run_id,
        "scenario": scenario,
        "base_url": base_url,
        "model": model,
        "started_at": started_at,
        "finished_at": finished_at,
        "steps": [asdict(s) for s in steps],
    }