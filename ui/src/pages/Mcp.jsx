import React, { useMemo, useState } from "react";
import { apiPost } from "../api/client";
import { MCP_SCENARIOS } from "../data/mcpScenarios";

function pretty(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

export default function Mcp() {
  const baseUrl = useMemo(() => window.location.origin, []);
  const [active, setActive] = useState(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function runScenario(s) {
    setActive(s.key);
    setRunning(true);
    setError("");
    setResult(null);

    try {
      const res = await apiPost("/api/mcp/run", s.request(baseUrl));
      setResult(res);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <h2>MCP — Agentic Orchestration</h2>
      <p>
        These scenarios demonstrate <b>plan → tool use → observation → retry →
        reasoning</b>, with full step-by-step visibility.
      </p>

      {MCP_SCENARIOS.map((s) => (
        <div key={s.key} style={card}>
          <h3>{s.title}</h3>
          <p>{s.description}</p>

          <details>
            <summary><b>Question</b></summary>
            <p>{s.question}</p>
          </details>

          <details>
            <summary><b>Expected steps</b></summary>
            <ul>
              {s.expectedSteps.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </details>

          <button
            onClick={() => runScenario(s)}
            disabled={running}
            style={button}
          >
            {running && active === s.key ? "Running…" : "Execute MCP"}
          </button>
        </div>
      ))}

      {error && (
        <pre style={errorBox}>{error}</pre>
      )}

      {result && (
        <pre style={output}>{pretty(result)}</pre>
      )}
    </div>
  );
}

const card = {
  marginTop: 16,
  padding: 14,
  background: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: 14,
};

const button = {
  marginTop: 10,
  padding: "8px 14px",
  fontWeight: 800,
  borderRadius: 10,
  border: "1px solid #1d4ed8",
  background: "#2563eb",
  color: "#fff",
  cursor: "pointer",
};

const output = {
  marginTop: 16,
  padding: 12,
  background: "#0f172a",
  color: "#e5e7eb",
  borderRadius: 10,
  maxHeight: 420,
  overflow: "auto",
  fontSize: 12,
};

const errorBox = {
  marginTop: 16,
  padding: 12,
  background: "#fee2e2",
  color: "#7f1d1d",
  borderRadius: 10,
};