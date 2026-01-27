# services/agent_api/features/mcp/mcp_orchestrator.py

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import urllib.request
import urllib.error


# -----------------------------
# Models / Data Structures
# -----------------------------

@dataclass
class McpStep:
    step: int
    name: str
    type: str                 # "plan" | "tool" | "note" | "retry" | "reason" | "recommend"
    status: str               # "ok" | "warn" | "error"
    started_at: str
    finished_at: str
    detail: Dict[str, Any]
    generated_by: Optional[Dict[str, Any]] = None


# -----------------------------
# Time / Parsing Helpers
# -----------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_json_object(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


def _looks_like_html(content_type: str, body: str) -> bool:
    ct = (content_type or "").lower()
    if "text/html" in ct:
        return True
    b = (body or "").lstrip().lower()
    return b.startswith("<!doctype html") or b.startswith("<html")


# -----------------------------
# HTTP (tool execution)
# -----------------------------

def _http_request(
    method: str,
    url: str,
    body: Optional[dict] = None,
    timeout_sec: int = 12,
) -> Dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            text = raw.decode("utf-8", errors="replace")
            return {"ok": True, "status": resp.status, "content_type": ct, "body": text}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": int(getattr(e, "code", 0) or 0),
            "content_type": e.headers.get("Content-Type", ""),
            "body": raw,
        }
    except Exception as e:
        return {"ok": False, "status": 0, "content_type": "", "body": str(e)}


def _add_step(
    steps: List[McpStep],
    step_no: int,
    *,
    name: str,
    type_: str,
    status: str,
    detail: Dict[str, Any],
    t0: float,
    generated_by: Optional[Dict[str, Any]] = None,
) -> int:
    steps.append(
        McpStep(
            step=step_no,
            name=name,
            type=type_,
            status=status,
            started_at=datetime.fromtimestamp(t0, tz=timezone.utc).isoformat(),
            finished_at=_now_iso(),
            detail=detail,
            generated_by=generated_by,
        )
    )
    return step_no + 1


# -----------------------------
# LLM: OpenAI Responses API (HTTP-only)
# -----------------------------

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()

# One standard model for MCP planning + reasoning
MCP_MODEL = os.environ.get("MCP_MODEL", "gpt-4.1-mini").strip()
MCP_TEMPERATURE = float(os.environ.get("MCP_TEMPERATURE", "0.2"))
MCP_MAX_TOKENS_PLAN = int(os.environ.get("MCP_MAX_TOKENS_PLAN", "650"))
MCP_MAX_TOKENS_REASON = int(os.environ.get("MCP_MAX_TOKENS_REASON", "650"))


def _openai_post_json(payload: dict, timeout_sec: int = 25) -> dict:
    if not OPENAI_API_KEY:
        return {"error": {"message": "OPENAI_API_KEY not configured"}}

    url = "https://api.openai.com/v1/responses"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        detail = (detail[:900] + "...") if len(detail) > 900 else detail
        return {"error": {"message": f"OpenAI HTTP {e.code}", "detail": detail}}
    except Exception as e:
        return {"error": {"message": f"OpenAI call failed: {e}"}}


def _openai_output_text(resp: dict) -> str:
    # Prefer output_text if present
    ot = resp.get("output_text")
    if isinstance(ot, str) and ot.strip():
        return ot.strip()

    text = ""
    for item in resp.get("output", []) or []:
        if item.get("type") == "message":
            for c in item.get("content", []) or []:
                if c.get("type") in ("output_text", "text"):
                    text += c.get("text", "")
    return (text or "").strip()


def _llm_json(prompt: str, *, model: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
    payload = {
        "model": model,
        "input": prompt,
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    resp = _openai_post_json(payload, timeout_sec=30)
    if resp.get("error"):
        return {"error": resp.get("error"), "raw": resp}

    out_text = _openai_output_text(resp)
    candidate = _extract_json_object(out_text)
    try:
        return json.loads(candidate)
    except Exception:
        return {
            "error": {"message": "LLM returned non-JSON or invalid JSON"},
            "raw_output_preview": (out_text or "")[:1200],
        }


# -----------------------------
# Prompts
# -----------------------------

def _plan_prompt(*, scenario: str, base_url: str, kwargs: Dict[str, Any]) -> str:
    # Keep prompt strict + cheap: return JSON ONLY.
    # For first-call-html scenario: ensure tool steps include runbooks ask + retry.
    audience = (kwargs.get("audience") or "sre").strip()
    intent = (kwargs.get("intent") or "").strip()

    return f"""
You are an orchestration planner for an MCP workflow.

Return VALID JSON ONLY (no markdown) with this schema:

{{
  "goal": "string",
  "why_agentic": "string",
  "steps": [
    {{
      "name": "string",
      "type": "tool|note|retry|reason|recommend",
      "content": "string optional for note/recommend",
      "retry": false,
      "tool": {{
        "method": "GET|POST",
        "path": "/api/health OR /api/runbooks/ask",
        "body": {{ }}
      }} | null
    }}
  ],
  "constraints": {{
    "max_steps": 14,
    "allowed_tools": [
      {{ "method":"GET", "path":"/api/health" }},
      {{ "method":"POST", "path":"/api/runbooks/ask" }}
    ]
  }}
}}

Rules:
- Use at most 12 steps.
- If scenario is "first-call-html", your plan MUST include:
  1) tool GET /api/health
  2) tool POST /api/runbooks/ask with a tiny question (e.g. "hello") and top_k 5
  3) a retry step (type "retry") with small backoff (put in content)
  4) tool POST /api/runbooks/ask again (retry attempt)
  5) reason step and recommend step
- If scenario is "quantum-sre-10", produce a safe learning plan in SRE terms.
  - Tool calls are optional, but if you include tools, only use GET /api/health.
  - Keep it realistic (simulators, no hype).
- base_url is "{base_url}" (used only for context; tools are executed by server).

Inputs:
- scenario: "{scenario}"
- audience: "{audience}"
- intent: "{intent}"
""".strip()


def _reason_prompt(*, scenario: str, plan: Dict[str, Any], observations: List[Dict[str, Any]], kwargs: Dict[str, Any]) -> str:
    # One reasoning call that returns the final "likely_root_cause" + "recommended_actions".
    audience = (kwargs.get("audience") or "sre").strip()
    return f"""
You are an MCP reasoning engine.

Return VALID JSON ONLY (no markdown) with this schema:

{{
  "likely_root_cause": "string or null",
  "confidence": "low|medium|high",
  "recommended_actions": ["string", "..."]
}}

Context:
- scenario: "{scenario}"
- audience: "{audience}"

Plan (JSON):
{json.dumps(plan, indent=2)[:5000]}

Observations (JSON array, each contains status/content_type/body_head):
{json.dumps(observations, indent=2)[:5000]}

Guidance:
- If scenario is "first-call-html": focus on CloudFront/API GW/Lambda cold start, timeouts, origin routing, content-type mismatches.
- If scenario is "quantum-sre-10": likely_root_cause can be null; focus on safe next steps and learning plan actions.
""".strip()


# -----------------------------
# Runner
# -----------------------------

def run_mcp_scenario(
    scenario: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Robust signature:
    - Works with positional OR keyword calls
    - Accepts scenario=, base_url=, plus extra payload fields (audience, intent, etc.)
    """

    run_id = f"mcp-{uuid.uuid4().hex[:10]}"
    started_at = _now_iso()

    scenario = (scenario or kwargs.get("scenario") or "first-call-html").strip() or "first-call-html"
    base_url = (base_url or kwargs.get("base_url") or "").strip().rstrip("/")

    # Normalize scenario
    if scenario not in ("first-call-html", "first-call-504", "first-call-timeout", "quantum-sre-10"):
        scenario = "first-call-html"

    # LLM metadata (shown in output)
    llm_meta = {
        "provider": "openai",
        "planner_model": MCP_MODEL,
        "reasoning_model": MCP_MODEL,
        "temperature": MCP_TEMPERATURE,
    }

    steps: List[McpStep] = []
    step_no = 1

    # -------------------------
    # Step 1: LLM Planner
    # -------------------------
    t0 = time.time()
    plan_prompt = _plan_prompt(scenario=scenario, base_url=base_url, kwargs=kwargs)
    plan_json = _llm_json(
        plan_prompt,
        model=MCP_MODEL,
        temperature=MCP_TEMPERATURE,
        max_tokens=MCP_MAX_TOKENS_PLAN,
    )

    if plan_json.get("error"):
        # Fallback if LLM fails
        fallback_plan = {
            "goal": f"MCP scenario: {scenario}",
            "why_agentic": "Planner LLM failed; fallback minimal plan used.",
            "steps": [{"name": "Probe /api/health", "type": "tool", "tool": {"method": "GET", "path": "/api/health", "body": {}}}],
            "constraints": {"max_steps": 6, "allowed_tools": [{"method": "GET", "path": "/api/health"}]},
        }
        plan = fallback_plan
        detail = {"plan": plan, "llm_error": plan_json.get("error"), "llm_raw_preview": str(plan_json)[:900]}
        gen = {"type": "llm", "model": MCP_MODEL, "purpose": "planning", "status": "error"}
    else:
        plan = plan_json
        detail = {"plan": plan}
        gen = {"type": "llm", "model": MCP_MODEL, "purpose": "planning"}

    step_no = _add_step(
        steps,
        step_no,
        name="Create execution plan",
        type_="plan",
        status="ok" if not plan_json.get("error") else "warn",
        detail=detail,
        t0=t0,
        generated_by=gen,
    )

    plan_steps = plan.get("steps") if isinstance(plan, dict) else []
    if not isinstance(plan_steps, list):
        plan_steps = []

    # Execute up to 12 steps from plan (excluding the plan step itself)
    plan_steps = plan_steps[:12]

    # Collect observations for reasoning
    observations: List[Dict[str, Any]] = []

    # -------------------------
    # Step 2..N: Execute plan steps
    # -------------------------
    for s in plan_steps:
        t0 = time.time()
        name = str((s or {}).get("name") or "Step").strip()
        stype = str((s or {}).get("type") or "note").strip().lower()
        tool = (s or {}).get("tool", None)
        content = (s or {}).get("content", None)

        if stype == "tool" and isinstance(tool, dict):
            method = str(tool.get("method") or "GET").upper()
            path = str(tool.get("path") or "/api/health").strip()
            body = tool.get("body") if isinstance(tool.get("body"), dict) else {}

            # Only allow these tools
            if not (method in ("GET", "POST") and path in ("/api/health", "/api/runbooks/ask")):
                step_no = _add_step(
                    steps,
                    step_no,
                    name=name,
                    type_="tool",
                    status="error",
                    detail={"error": f"Tool not allowed: {method} {path}"},
                    t0=t0,
                    generated_by={"type": "llm", "model": MCP_MODEL, "purpose": "plan_step"},
                )
                observations.append({"name": name, "type": "tool", "status": "error", "content_type": "", "http_status": 0})
                continue

            url = f"{base_url}{path}"
            resp = _http_request(method, url, body=body if method == "POST" else None, timeout_sec=22)
            is_html = _looks_like_html(resp.get("content_type", ""), resp.get("body", ""))
            ok_jsonish = resp.get("ok") and not is_html

            status = "ok" if ok_jsonish else ("warn" if resp.get("ok") else "error")

            body_head = (resp.get("body") or "")[:260]
            observations.append(
                {
                    "name": name,
                    "type": "tool",
                    "http_status": resp.get("status"),
                    "content_type": resp.get("content_type"),
                    "body_head": body_head,
                    "status": status,
                    "url": url,
                }
            )

            step_no = _add_step(
                steps,
                step_no,
                name=name,
                type_="tool",
                status=status,
                detail={
                    "request": {"method": method, "url": url, "body": body},
                    "response": {
                        "status": resp.get("status"),
                        "content_type": resp.get("content_type"),
                        "body_head": body_head,
                    },
                    "interpretation": "Looks like HTML error page (CloudFront/origin/timeout)" if is_html else "OK",
                },
                t0=t0,
                generated_by={"type": "llm", "model": MCP_MODEL, "purpose": "plan_step"},
            )
            continue

        if stype == "retry":
            # Let the plan specify backoff in content like "backoff_ms: 350"
            backoff_ms = 350
            try:
                if isinstance(content, str) and "backoff" in content.lower():
                    # super light parse
                    digits = "".join([ch if ch.isdigit() else " " for ch in content])
                    nums = [int(x) for x in digits.split() if x.isdigit()]
                    if nums:
                        backoff_ms = max(50, min(2000, nums[0]))
            except Exception:
                pass

            time.sleep(backoff_ms / 1000.0)
            observations.append({"name": name, "type": "retry", "status": "ok", "backoff_ms": backoff_ms})

            step_no = _add_step(
                steps,
                step_no,
                name=name,
                type_="retry",
                status="ok",
                detail={"backoff_ms": backoff_ms, "note": content or "Retry backoff"},
                t0=t0,
                generated_by={"type": "llm", "model": MCP_MODEL, "purpose": "plan_step"},
            )
            continue

        # note / recommend / reason placeholders from plan: store content (no extra LLM call per step)
        if stype not in ("note", "recommend", "reason"):
            stype = "note"

        observations.append({"name": name, "type": stype, "status": "ok", "content_head": (content or "")[:220]})

        step_no = _add_step(
            steps,
            step_no,
            name=name,
            type_=stype,
            status="ok",
            detail={"content": content or "Non-tool step (explanation/analysis)."},
            t0=t0,
            generated_by={"type": "llm", "model": MCP_MODEL, "purpose": "plan_step"},
        )

    # -------------------------
    # Final: LLM Reason + Recommend (single call)
    # -------------------------
    t0 = time.time()
    reason_prompt = _reason_prompt(scenario=scenario, plan=plan, observations=observations, kwargs=kwargs)
    rr = _llm_json(
        reason_prompt,
        model=MCP_MODEL,
        temperature=MCP_TEMPERATURE,
        max_tokens=MCP_MAX_TOKENS_REASON,
    )

    if rr.get("error"):
        reason_detail = {
            "likely_root_cause": None if scenario == "quantum-sre-10" else "Unable to determine (LLM reasoning failed).",
            "confidence": "low",
            "llm_error": rr.get("error"),
            "recommended_actions": [
                "Check Lambda logs (/aws/lambda/...) for timeouts and init duration",
                "Verify CloudFront origin path + API Gateway route mappings",
                "Add a client-side soft retry on first-call HTML/non-JSON",
            ],
        }
        step_no = _add_step(
            steps,
            step_no,
            name="Root-cause reasoning",
            type_="reason",
            status="warn",
            detail=reason_detail,
            t0=t0,
            generated_by={"type": "llm", "model": MCP_MODEL, "purpose": "reasoning", "status": "error"},
        )
        # recommendations step
        t0 = time.time()
        step_no = _add_step(
            steps,
            step_no,
            name="Recommended fixes",
            type_="recommend",
            status="ok",
            detail={"recommended_actions": reason_detail.get("recommended_actions", [])},
            t0=t0,
            generated_by={"type": "llm", "model": MCP_MODEL, "purpose": "recommendations", "status": "fallback"},
        )
    else:
        # Add reasoning step
        step_no = _add_step(
            steps,
            step_no,
            name="Root-cause reasoning",
            type_="reason",
            status="ok",
            detail={
                "likely_root_cause": rr.get("likely_root_cause"),
                "confidence": rr.get("confidence"),
                "llm_raw_preview": json.dumps(rr, indent=2)[:900],
            },
            t0=t0,
            generated_by={"type": "llm", "model": MCP_MODEL, "purpose": "reasoning"},
        )
        # Add recommendations step
        t0 = time.time()
        recs = rr.get("recommended_actions") if isinstance(rr.get("recommended_actions"), list) else []
        step_no = _add_step(
            steps,
            step_no,
            name="Recommended fixes",
            type_="recommend",
            status="ok",
            detail={"recommended_actions": recs},
            t0=t0,
            generated_by={"type": "llm", "model": MCP_MODEL, "purpose": "recommendations"},
        )

    finished_at = _now_iso()

    # Echo model usage at the top (helps you see where LLM ran)
    return {
        "ok": True,
        "run_id": run_id,
        "scenario": scenario,
        "base_url": base_url,
        "model": MCP_MODEL,
        "llm": llm_meta,
        "started_at": started_at,
        "finished_at": finished_at,
        "steps": [asdict(s) for s in steps],
    }