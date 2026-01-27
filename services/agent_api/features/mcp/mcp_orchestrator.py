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


# -----------------------
# Data model for UI trace
# -----------------------

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
    """
    Best-effort extraction if model wraps JSON with extra text.
    """
    if not text:
        return None
    # 1) direct parse
    j = _safe_json_loads(text)
    if isinstance(j, dict):
        return j

    # 2) try to find first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        j2 = _safe_json_loads(text[start : end + 1])
        if isinstance(j2, dict):
            return j2
    return None


# -----------------------
# Safe HTTP tool executor
# -----------------------

def _http_request(method: str, url: str, body: Optional[dict] = None, timeout_sec: int = 12) -> Dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
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
    if body.lstrip().lower().startswith("<!doctype html") or body.lstrip().lower().startswith("<html"):
        return True
    return False


# -----------------------
# LLM helpers (ONE model)
# -----------------------

def _openai_client() -> OpenAI:
    # Uses OPENAI_API_KEY by default. If you use Azure/OpenAI-compatible gateway,
    # you can set OPENAI_BASE_URL and OPENAI_API_KEY accordingly.
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    api_key = os.environ.get("OPENAI_API_KEY", "").strip() or None
    if base_url:
        return OpenAI(base_url=base_url, api_key=api_key)
    return OpenAI(api_key=api_key)


def _mcp_model() -> str:
    # One standard model for BOTH scenarios
    # Set this in Lambda env: MCP_MODEL="gpt-4.1-mini" (example) or whatever you prefer
    return os.environ.get("MCP_MODEL", "").strip() or "gpt-4.1-mini"


def _llm_json(client: OpenAI, model: str, system: str, user: str, timeout_sec: int = 25) -> Tuple[Optional[dict], str]:
    """
    Calls model and returns (json_dict_or_none, raw_text).
    """
    # Responses API keeps you future-proof on OpenAI SDK v2.x
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_output_tokens=1200,
        timeout=timeout_sec,
    )

    # SDK returns a structured response; easiest is output_text helper
    raw = getattr(resp, "output_text", None)
    if raw is None:
        # fallback: try to build text from output blocks
        raw = ""
        try:
            for item in resp.output:
                for c in getattr(item, "content", []) or []:
                    if getattr(c, "type", "") in ("output_text", "text"):
                        raw += getattr(c, "text", "") or ""
        except Exception:
            raw = ""

    raw = (raw or "").strip()
    j = _extract_json_object(raw)
    return j, raw


# -----------------------
# Scenario specs
# -----------------------

def _scenario_spec(scenario: str) -> Dict[str, Any]:
    """
    Keep scenario spec simple. LLM generates the plan + explanations.
    Tools are still constrained by whitelist.
    """
    if scenario == "quantum-sre-10":
        return {
            "scenario": "quantum-sre-10",
            "goal": "Explain quantum computing in practical SRE terms and produce a realistic, safe 10-step learning + experimentation plan.",
            "must_steps": 10,
            "allowed_tools": [
                {"method": "GET", "path": "/api/health"},
                # (optional later) {"method":"GET","path":"/api/news/latest"}
            ],
            "notes": [
                "No hype. Clarify what quantum is NOT.",
                "Use practical analogies (queuing, probabilistic failure, optimization).",
                "Avoid claiming speedups unless you qualify assumptions.",
            ],
        }

    # default
    return {
        "scenario": "first-call-html",
        "goal": "Diagnose why first API call sometimes returns HTML/504 instead of JSON and prove retry behavior, then recommend mitigations.",
        "must_steps": 7,
        "allowed_tools": [
            {"method": "GET", "path": "/api/health"},
            {"method": "POST", "path": "/api/runbooks/ask"},
        ],
        "notes": [
            "Detect HTML error pages (CloudFront) vs JSON.",
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

    # body limits
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
    base_url = (base_url or "").strip().rstrip("/")
    if not base_url:
        base_url = "https://dev.aimlsre.com"  # safe fallback

    spec = _scenario_spec(scenario)

    client = _openai_client()
    model = _mcp_model()

    # ---------------
    # Step 1: PLAN (LLM)
    # ---------------
    t0 = time.time()
    system = (
        "You are an SRE orchestration planner. "
        "Return STRICT JSON only. No markdown. No extra text."
    )
    user = json.dumps(
        {
            "task": "Create an MCP execution plan as JSON.",
            "spec": spec,
            "output_contract": {
                "goal": "string",
                "why_agentic": "string",
                "steps": [
                    {
                        "name": "string",
                        "type": "plan|tool|retry|reason|recommend|note",
                        "tool": {"method": "GET|POST", "path": "/api/...", "body": {"any": "json"}}  # only when type=tool
                    }
                ],
                "constraints": {
                    "max_steps": 12,
                    "allowed_tools": spec["allowed_tools"],
                },
            },
            "rules": [
                "If you include any tool steps, they MUST be from allowed_tools exactly.",
                "For first-call-html: include a tool call to GET /api/health and POST /api/runbooks/ask, then a retry step and a second POST retry.",
                "For quantum-sre-10: produce exactly 10 steps, mostly explanation steps; only optional tool is GET /api/health.",
                "Keep steps short and readable for UI.",
            ],
        },
        ensure_ascii=False,
    )

    plan_json, plan_raw = _llm_json(client, model, system=system, user=user)
    if not plan_json:
        # hard fallback if model fails: keep site working
        fallback = {
            "goal": spec["goal"],
            "why_agentic": "Fallback plan used because planner LLM returned invalid JSON; still executing safely.",
            "steps": [{"name": "Note: Planner fallback", "type": "note"}],
        }
        add_step("Create execution plan", "plan", "warn", {"plan": fallback, "llm_raw_head": plan_raw[:400]}, t0)
        plan = fallback
    else:
        add_step("Create execution plan", "plan", "ok", {"plan": plan_json}, t0)
        plan = plan_json

    # normalize steps
    plan_steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(plan_steps, list):
        plan_steps = []

    # ---------------
    # Execute steps (only tool steps actually call network)
    # ---------------
    allowed_tools = spec.get("allowed_tools", [])
    max_steps = 12
    executed_tools = 0

    for s in plan_steps[:max_steps]:
        name = (s.get("name") or "").strip() or "Step"
        type_ = (s.get("type") or "note").strip()

        # tool
        if type_ == "tool":
            t0 = time.time()
            ok, why = _validate_tool_call(s.get("tool") or {}, allowed_tools)
            if not ok:
                add_step(
                    name,
                    "tool",
                    "error",
                    {"error": "Tool validation failed", "why": why, "tool": s.get("tool")},
                    t0,
                )
                continue

            tool = s["tool"]
            method = tool.get("method", tool.get("tool", "GET")).upper()
            path = tool["path"]
            body = tool.get("body")
            url = f"{base_url}{path}"

            resp = _http_request(method, url, body=body, timeout_sec=20)
            executed_tools += 1

            add_step(
                name,
                "tool",
                "ok" if resp["ok"] and not _looks_like_html(resp) else "warn",
                {
                    "request": {"method": method, "url": url, "body": body},
                    "response": {
                        "status": resp.get("status"),
                        "content_type": resp.get("content_type"),
                        "body_head": (resp.get("body") or "")[:260],
                    },
                    "interpretation": (
                        "Looks like HTML error page (CloudFront/timeout)"
                        if _looks_like_html(resp)
                        else "OK"
                    ),
                },
                t0,
            )
            continue

        # retry step (no-op, just trace + tiny backoff)
        if type_ == "retry":
            t0 = time.time()
            time.sleep(0.25)
            add_step(name, "retry", "ok", {"backoff_ms": 250}, t0)
            continue

        # any other step = trace only
        t0 = time.time()
        add_step(name, type_, "ok", {"note": "Non-tool step (explanation/analysis)."}, t0)

    # ---------------
    # Final summary (LLM) – same model
    # ---------------
    t0 = time.time()
    trace = {
        "scenario": scenario,
        "base_url": base_url,
        "spec": spec,
        "steps_executed": [asdict(x) for x in steps],
    }

    system2 = "You are an SRE analyst. Return STRICT JSON only. No markdown."
    user2 = json.dumps(
        {
            "task": "Summarize the run into root-cause + recommended mitigations, grounded ONLY in the observed trace.",
            "trace": trace,
            "output_contract": {
                "likely_root_cause": "string",
                "confidence": "low|medium|high",
                "recommended_actions": ["string"],
            },
            "rules": [
                "Do NOT invent tool outputs. Use only what is in trace.",
                "If first-call-html: mention cold start / timeout / CloudFront HTML error pages and client retry mitigation.",
                "If quantum-sre-10: provide a safe 10-step learning plan and clarify limitations.",
            ],
        },
        ensure_ascii=False,
    )

    summary_json, summary_raw = _llm_json(client, model, system=system2, user=user2, timeout_sec=25)
    if not summary_json:
        add_step(
            "LLM summary",
            "reason",
            "warn",
            {"error": "LLM returned invalid JSON", "llm_raw_head": summary_raw[:500]},
            t0,
        )
    else:
        # add as two steps so UI looks nice
        add_step(
            "Root-cause reasoning",
            "reason",
            "ok",
            {
                "likely_root_cause": summary_json.get("likely_root_cause"),
                "confidence": summary_json.get("confidence"),
            },
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