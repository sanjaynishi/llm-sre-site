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
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [banner, setBanner] = useState(""); // small “results are below” message

  function scrollToResults() {
    // Give React time to render the results block
    setTimeout(() => {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  }

  async function runScenario(s) {
    setActive(s.key);
    setRunning(true);
    setError("");
    setResult(null);
    setBanner("");

    try {
      const res = await apiPost("/api/mcp/run", s.request(baseUrl));
      setResult(res);

      // Friendly banner + auto-scroll so you don’t miss it
      setBanner("✅ MCP finished — results are below (auto-scrolled).");
      scrollToResults();
    } catch (e) {
      setError(String(e?.message || e));
      setBanner("");
      scrollToResults();
    } finally {
      setRunning(false);
    }
  }

  const plannerModel =
    result?.llm?.planner_model || result?.model || "unknown";
  const reasonModel =
    result?.llm?.reasoning_model || result?.model || "unknown";
  const provider = result?.llm?.provider || (result?.model ? "openai" : "—");
  const temp =
    typeof result?.llm?.temperature === "number" ? result.llm.temperature : null;

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>MCP — Agentic Orchestration</h2>
      <p style={{ marginTop: 6, opacity: 0.9 }}>
        These scenarios demonstrate <b>plan → tool use → observation → retry → reasoning</b>,
        with step-by-step visibility.
      </p>

      {MCP_SCENARIOS.map((s) => (
        <div key={s.key} style={card}>
          <h3 style={{ margin: "0 0 6px" }}>{s.title}</h3>
          <p style={{ margin: "0 0 10px", opacity: 0.9 }}>{s.description}</p>

          <details>
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
                <li key={i}>{x}</li>
              ))}
            </ul>
          </details>

          <button
            onClick={() => runScenario(s)}
            disabled={running}
            style={{
              ...button,
              opacity: running ? 0.7 : 1,
              cursor: running ? "not-allowed" : "pointer",
            }}
            type="button"
          >
            {running && active === s.key ? "Running…" : "Execute MCP"}
          </button>
        </div>
      ))}

      {/* Anchor for auto-scroll */}
      <div ref={resultsRef} />

      {(banner || error || result) && (
        <div style={{ marginTop: 18 }}>
          {banner && <div style={bannerStyle}>{banner}</div>}

          {/* Model attribution box */}
          {result && (
            <div style={metaBox}>
              <div style={{ fontWeight: 900, marginBottom: 6 }}>
                Run metadata
              </div>
              <div style={metaRow}>
                <span style={metaKey}>Scenario:</span>
                <span style={metaVal}>{result.scenario || "—"}</span>
              </div>
              <div style={metaRow}>
                <span style={metaKey}>Run ID:</span>
                <span style={metaVal}>{result.run_id || "—"}</span>
              </div>
              <div style={metaRow}>
                <span style={metaKey}>LLM provider:</span>
                <span style={metaVal}>{provider}</span>
              </div>
              <div style={metaRow}>
                <span style={metaKey}>Planner model:</span>
                <span style={metaVal}>{plannerModel}</span>
              </div>
              <div style={metaRow}>
                <span style={metaKey}>Reasoner model:</span>
                <span style={metaVal}>{reasonModel}</span>
              </div>
              <div style={metaRow}>
                <span style={metaKey}>Temperature:</span>
                <span style={metaVal}>{temp === null ? "—" : String(temp)}</span>
              </div>
            </div>
          )}

          {error && <pre style={errorBox}>{error}</pre>}

          {result && (
            <>
              <div style={{ marginTop: 10, display: "flex", gap: 10 }}>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard
                      ?.writeText(pretty(result))
                      .then(() => setBanner("✅ Copied results JSON to clipboard."))
                      .catch(() =>
                        setBanner("⚠️ Could not copy automatically. Please copy manually.")
                      );
                  }}
                  style={copyBtn}
                >
                  Copy results JSON
                </button>

                <button
                  type="button"
                  onClick={scrollToResults}
                  style={copyBtn}
                >
                  Scroll to results
                </button>
              </div>

              <pre style={output}>{pretty(result)}</pre>
            </>
          )}
        </div>
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
  fontWeight: 900,
  borderRadius: 10,
  border: "1px solid #1d4ed8",
  background: "#2563eb",
  color: "#fff",
};

const bannerStyle = {
  marginTop: 10,
  padding: "10px 12px",
  borderRadius: 12,
  background: "#ecfdf5",
  border: "1px solid #a7f3d0",
  color: "#065f46",
  fontWeight: 800,
};

const metaBox = {
  marginTop: 12,
  padding: 12,
  borderRadius: 14,
  background: "#ffffff",
  border: "1px solid #e5e7eb",
};

const metaRow = {
  display: "flex",
  gap: 10,
  alignItems: "baseline",
  marginTop: 6,
};

const metaKey = {
  width: 140,
  fontWeight: 800,
  color: "#374151",
};

const metaVal = {
  color: "#111827",
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif',
};

const copyBtn = {
  padding: "8px 12px",
  fontWeight: 900,
  borderRadius: 10,
  border: "1px solid #d1d5db",
  background: "#ffffff",
  cursor: "pointer",
};

const output = {
  marginTop: 12,
  padding: 12,
  background: "#0f172a",
  color: "#e5e7eb",
  borderRadius: 10,
  maxHeight: 520,
  overflow: "auto",
  fontSize: 12,
};

const errorBox = {
  marginTop: 12,
  padding: 12,
  background: "#fee2e2",
  color: "#7f1d1d",
  borderRadius: 10,
};