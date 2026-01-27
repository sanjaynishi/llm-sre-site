# services/agent_api/features/mcp/mcp_orchestrator.py

from __future__ import annotations

import json
import os
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# -------------------------
# Data model
# -------------------------
@dataclass
class McpStep:
    step: int
    name: str
    type: str                 # "plan" | "tool" | "note" | "retry" | "reason" | "recommend"
    status: str               # "ok" | "warn" | "error"
    started_at: str
    finished_at: str
    detail: Dict[str, Any]
    generated_by: Dict[str, Any] = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_loads(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except Exception:
        return None


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


# -------------------------
# LLM helper
# -------------------------
def _openai_client():
    """
    Uses openai>=1.x. If not available or key missing, returns None.
    """
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    return OpenAI(api_key=api_key)


def _llm_json(
    prompt: str,
    model: str,
    temperature: float = 0.2,
    max_output_tokens: int = 900,
) -> Tuple[Optional[dict], Optional[str]]:
    """
    Returns (json_obj, raw_text). Attempts to force JSON output.
    """
    client = _openai_client()
    if client is None:
        return None, "LLM not configured (missing openai lib or OPENAI_API_KEY)."

    # Prefer Responses API (openai>=1.0)
    try:
        resp = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are an orchestration planner for an AI SRE demo. "
                        "Return ONLY valid JSON that matches the requested schema. "
                        "No markdown. No extra keys beyond schema unless asked."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        text = (resp.output_text or "").strip()
        return _safe_json_loads(text), text
    except Exception as e:
        # Fallback: Chat Completions (if Responses not supported in runtime)
        try:
            cc = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an orchestration planner for an AI SRE demo. "
                            "Return ONLY valid JSON that matches the requested schema. "
                            "No markdown."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_output_tokens,
            )
            text = (cc.choices[0].message.content or "").strip()
            return _safe_json_loads(text), text
        except Exception as e2:
            return None, f"LLM call failed: {type(e).__name__}: {e}; fallback failed: {type(e2).__name__}: {e2}"


# -------------------------
# Scenario inputs
# -------------------------
def _scenario_prompt(scenario: str) -> Dict[str, Any]:
    """
    Defines scenario goal + constraints. LLM will generate the step plan.
    """
    if scenario == "first-call-html":
        return {
            "scenario": scenario,
            "goal": "Diagnose why the first click sometimes returns HTML/504 instead of JSON, and show a retry path + mitigations.",
            "constraints": {
                "max_steps": 12,
                "allowed_tools": [
                    {"method": "GET", "path": "/api/health"},
                    {"method": "POST", "path": "/api/runbooks/ask"},
                ],
                "must_include_retry": True,
            },
        }

    if scenario == "quantum-sre-10":
        return {
            "scenario": scenario,
            "goal": "Explain quantum computing in practical SRE terms and produce a realistic, safe 10-step learning/experimentation plan.",
            "constraints": {
                "max_steps": 12,
                "allowed_tools": [
                    {"method": "GET", "path": "/api/health"},
                ],
                "must_include_retry": False,
            },
        }

    # default
    return {
        "scenario": scenario,
        "goal": "Run an MCP orchestration scenario.",
        "constraints": {"max_steps": 12, "allowed_tools": [{"method": "GET", "path": "/api/health"}]},
    }


def _build_planner_prompt(scenario_spec: Dict[str, Any], base_url: str) -> str:
    """
    LLM must return a PLAN JSON in this schema:

    {
      "goal": "...",
      "why_agentic": "...",
      "steps": [
        {
          "name": "...",
          "type": "tool" | "note" | "recommend" | "retry",
          "tool": {"method":"GET|POST","path":"/api/...","body":{...}} | null,
          "content": "..." | null,
          "retry": true|false
        }
      ]
    }
    """
    return json.dumps(
        {
            "task": "Create an MCP plan.",
            "base_url": base_url,
            "scenario": scenario_spec.get("scenario"),
            "goal": scenario_spec.get("goal"),
            "constraints": scenario_spec.get("constraints"),
            "schema": {
                "goal": "string",
                "why_agentic": "string",
                "steps": [
                    {
                        "name": "string",
                        "type": "tool|note|recommend|retry",
                        "tool": {"method": "GET|POST", "path": "/api/...", "body": {}},
                        "content": "string",
                        "retry": "boolean",
                    }
                ],
            },
            "guidance": [
                "For first-call-html: include POST /api/runbooks/ask twice, second marked retry=true with small backoff.",
                "For quantum-sre-10: produce 10 steps; keep it safe and practical; use SRE analogies; minimize tool use.",
                "Return ONLY JSON. No markdown.",
            ],
        },
        indent=2,
    )


def _looks_like_html(content_type: str, body: str) -> bool:
    ct = (content_type or "").lower()
    if "text/html" in ct:
        return True
    head = (body or "").lstrip()[:64].lower()
    return head.startswith("<!doctype html") or head.startswith("<html")


# -------------------------
# Main entry
# -------------------------
def run_mcp_scenario(
    scenario: str,
    base_url: str,
    audience: Optional[str] = None,
    intent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    MCP runner:
    - Step 1: LLM generates a plan (JSON)
    - Step 2+: execute tool steps, emit non-tool steps, then LLM reason+recommend
    """

    scenario = (scenario or "").strip() or "first-call-html"
    base_url = (base_url or "").strip().rstrip("/")

    model = os.environ.get("MCP_MODEL", "gpt-4.1-mini").strip()
    temperature = float(os.environ.get("MCP_TEMPERATURE", "0.2"))

    run_id = f"mcp-{uuid.uuid4().hex[:10]}"
    started_at = _now_iso()

    steps: List[McpStep] = []
    step_no = 0

    def add_step(
        name: str,
        type_: str,
        status: str,
        detail: Dict[str, Any],
        t0: float,
        generated_by: Dict[str, Any],
    ) -> None:
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
                generated_by=generated_by,
            )
        )

    # -------------------------
    # Step 1: LLM plan
    # -------------------------
    t0 = time.time()
    scenario_spec = _scenario_prompt(scenario)
    planner_prompt = _build_planner_prompt(scenario_spec, base_url)

    plan_json, plan_raw = _llm_json(
        prompt=planner_prompt,
        model=model,
        temperature=temperature,
        max_output_tokens=1000,
    )

    # If LLM unavailable, fallback to minimal plan
    if not plan_json:
        plan_json = {
            "goal": scenario_spec.get("goal", "Run MCP scenario"),
            "why_agentic": "Fallback plan used because LLM was unavailable; still executes tools and records outputs.",
            "steps": [
                {"name": "Probe health endpoint", "type": "tool", "tool": {"method": "GET", "path": "/api/health", "body": {}}, "content": None, "retry": False}
            ],
        }

    add_step(
        "Create execution plan",
        "plan",
        "ok",
        {"plan": plan_json, "llm_raw_preview": (plan_raw or "")[:600] if plan_raw else None},
        t0,
        generated_by={"type": "llm", "model": model, "purpose": "planning"},
    )

    # -------------------------
    # Execute steps
    # -------------------------
    observations: List[dict] = []

    for s in plan_json.get("steps", [])[: int(scenario_spec.get("constraints", {}).get("max_steps", 12))]:
        name = str(s.get("name") or "Step").strip()
        stype = str(s.get("type") or "note").strip()
        tool = s.get("tool") or None
        content = s.get("content")
        is_retry = bool(s.get("retry"))

        # Retry steps: just backoff marker (optional)
        if stype == "retry":
            t0 = time.time()
            backoff_ms = 250
            time.sleep(backoff_ms / 1000.0)
            add_step(
                name,
                "retry",
                "ok",
                {"backoff_ms": backoff_ms, "why": "Backoff before retry tool call."},
                t0,
                generated_by={"type": "engine"},
            )
            continue

        # Tool step
        if stype == "tool" and isinstance(tool, dict):
            method = (tool.get("method") or "GET").upper()
            path = (tool.get("path") or "/api/health").strip()
            body = tool.get("body") if isinstance(tool.get("body"), dict) else {}

            url = f"{base_url}{path}" if path.startswith("/api/") else f"{base_url}/api{path if path.startswith('/') else '/' + path}"

            t0 = time.time()
            out = _http_request(method, url, body=body if method == "POST" else None, timeout_sec=20)

            is_html = _looks_like_html(out.get("content_type", ""), out.get("body", ""))
            status = "ok" if out.get("ok") and not is_html else ("warn" if out.get("status") else "error")

            detail = {
                "request": {"method": method, "url": url, "body": body if method == "POST" else {}},
                "response": {
                    "status": out.get("status"),
                    "content_type": out.get("content_type"),
                    "body_head": (out.get("body") or "")[:260],
                },
                "interpretation": "Looks like HTML error page (CloudFront/timeout)" if is_html else "OK",
                "retry": is_retry,
            }

            add_step(
                name,
                "tool",
                status,
                detail,
                t0,
                generated_by={"type": "tool", "tool": {"method": method, "path": path}},
            )
            observations.append({"name": name, "type": "tool", "detail": detail})
            continue

        # Non-tool steps: note/recommend
        t0 = time.time()
        add_step(
            name,
            stype if stype in ("note", "recommend") else "note",
            "ok",
            {"content": content} if content else {"note": "Non-tool step (explanation/analysis)."},
            t0,
            generated_by={"type": "llm", "model": model, "purpose": "content"} if content else {"type": "engine"},
        )
        observations.append({"name": name, "type": stype, "content": content})

    # -------------------------
    # LLM Reason + Recommend (optional but recommended)
    # -------------------------
    t0 = time.time()

    reason_prompt = json.dumps(
        {
            "task": "Produce root-cause reasoning and recommended fixes based on the run observations.",
            "scenario": scenario,
            "goal": plan_json.get("goal"),
            "observations": observations[-10:],  # keep it compact
            "return_schema": {
                "likely_root_cause": "string|null",
                "confidence": "low|medium|high|null",
                "recommended_actions": ["string"],
            },
            "rules": [
                "Return ONLY JSON.",
                "If scenario is educational (quantum), you may return null root cause and focus on actionable next steps.",
            ],
        },
        indent=2,
    )

    rr_json, rr_raw = _llm_json(
        prompt=reason_prompt,
        model=model,
        temperature=temperature,
        max_output_tokens=700,
    )

    if not rr_json:
        rr_json = {"likely_root_cause": None, "confidence": None, "recommended_actions": []}

    add_step(
        "Root-cause reasoning",
        "reason",
        "ok",
        {
            "likely_root_cause": rr_json.get("likely_root_cause"),
            "confidence": rr_json.get("confidence"),
            "llm_raw_preview": (rr_raw or "")[:600] if rr_raw else None,
        },
        t0,
        generated_by={"type": "llm", "model": model, "purpose": "reasoning"},
    )

    t0 = time.time()
    add_step(
        "Recommended fixes",
        "recommend",
        "ok",
        {"recommended_actions": rr_json.get("recommended_actions", [])},
        t0,
        generated_by={"type": "llm", "model": model, "purpose": "recommendations"},
    )

    finished_at = _now_iso()

    return {
        "ok": True,
        "run_id": run_id,
        "scenario": scenario,
        "base_url": base_url,
        "model": model,
        "llm": {
            "provider": "openai",
            "planner_model": model,
            "reasoning_model": model,
            "temperature": temperature,
        },
        "started_at": started_at,
        "finished_at": finished_at,
        "steps": [asdict(s) for s in steps],
    }