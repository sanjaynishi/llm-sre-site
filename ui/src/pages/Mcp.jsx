// ui/src/pages/Mcp.jsx
import React, { useMemo, useRef, useState } from "react";
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
  const resultsRef = useRef(null);

  const [active, setActive] = useState(null);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [showResultsNudge, setShowResultsNudge] = useState(false);

  async function runScenario(s) {
    setActive(s.key);
    setRunning(true);
    setStatus("Running MCP…");
    setError("");
    setResult(null);
    setShowResultsNudge(false);

    try {
      const res = await apiPost("/api/mcp/run", s.request(baseUrl));
      setResult(res);
      setStatus("Done. Results are below ↓");
      setShowResultsNudge(true);

      // Auto-scroll to results (after React paints)
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 50);
    } catch (e) {
      setError(String(e?.message || e));
      setStatus("Failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <h2>MCP — Agentic Orchestration</h2>
      <p>
        These scenarios demonstrate <b>plan → tool use → observation → retry → reasoning</b>,
        with full step-by-step visibility.
      </p>

      {status ? <div style={statusRow}>{status}</div> : null}

      {MCP_SCENARIOS.map((s) => (
        <div key={s.key} style={card}>
          <h3 style={{ marginTop: 0 }}>{s.title}</h3>
          <p style={{ marginTop: 6 }}>{s.description}</p>

          <details style={{ marginTop: 8 }}>
            <summary>
              <b>Question</b>
            </summary>
            <p style={{ marginTop: 8 }}>{s.question}</p>
          </details>

          <details style={{ marginTop: 8 }}>
            <summary>
              <b>Expected steps</b>
            </summary>
            <ul style={{ marginTop: 8 }}>
              {s.expectedSteps.map((x, i) => (
                <li key={i} style={{ marginBottom: 6 }}>
                  {x}
                </li>
              ))}
            </ul>
          </details>

          <button onClick={() => runScenario(s)} disabled={running} style={button}>
            {running && active === s.key ? "Running…" : "Execute MCP"}
          </button>
        </div>
      ))}

      {error ? <pre style={errorBox}>{error}</pre> : null}

      {/* Results */}
      {result ? (
        <div ref={resultsRef} style={{ marginTop: 16 }}>
          <h3 style={{ margin: "0 0 8px 0" }}>Results</h3>
          <pre style={output}>{pretty(result)}</pre>
        </div>
      ) : null}

      {/* Sticky nudge so user doesn't miss results */}
      {showResultsNudge && result ? (
        <div style={nudge}>
          <span>✅ MCP finished — results are below</span>
          <button
            type="button"
            style={nudgeBtn}
            onClick={() => {
              resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
              setShowResultsNudge(false);
            }}
          >
            Jump to results ↓
          </button>
        </div>
      ) : null}
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

const statusRow = {
  marginTop: 10,
  padding: "10px 12px",
  borderRadius: 12,
  background: "#f3f4f6",
  border: "1px solid #e5e7eb",
  fontWeight: 800,
  color: "#111827",
};

const output = {
  marginTop: 8,
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

const nudge = {
  position: "sticky",
  bottom: 12,
  marginTop: 12,
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 12,
  padding: "10px 12px",
  borderRadius: 14,
  border: "1px solid #e5e7eb",
  background: "#ffffff",
  boxShadow: "0 10px 22px rgba(17, 24, 39, 0.10)",
};

const nudgeBtn = {
  padding: "8px 10px",
  borderRadius: 12,
  border: "1px solid #111827",
  background: "#111827",
  color: "#ffffff",
  fontWeight: 800,
  cursor: "pointer",
  whiteSpace: "nowrap",
};