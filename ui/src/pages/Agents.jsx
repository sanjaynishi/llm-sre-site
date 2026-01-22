import React, { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../api/client";

/**
 * Agents page (inline UI, no popups)
 * - Improved readability (light background card layout)
 * - Better dropdown styling (pretty background, focus ring)
 * - Clear "selected" tab styling (prominent active state)
 * - Weather shown as clean stats + optional raw JSON toggle
 * - Travel shown as formatted sections + colored itineraries
 * - Spinner on Run
 */

const pageStyle = {
  padding: 18,
  maxWidth: 980,
  margin: "0 auto",
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif',
  color: "#111827",
};

const headerStyle = {
  margin: 0,
  fontSize: 26,
  fontWeight: 900,
  letterSpacing: "-0.02em",
};

const subStyle = {
  marginTop: 6,
  color: "#4b5563",
  lineHeight: 1.35,
};

const panelStyle = {
  marginTop: 16,
  background: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: 18,
  padding: 16,
  boxShadow: "0 10px 26px rgba(17, 24, 39, 0.08)",
};

const rowStyle = {
  display: "flex",
  gap: 12,
  flexWrap: "wrap",
  alignItems: "end",
};

const labelStyle = {
  display: "block",
  marginBottom: 6,
  fontSize: 13,
  color: "#374151",
  fontWeight: 700,
};

const fieldWrap = {
  display: "flex",
  flexDirection: "column",
  gap: 6,
};

const selectStyle = {
  minWidth: 320,
  padding: "10px 12px",
  borderRadius: 14,
  border: "1px solid #d1d5db",
  background: "linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)",
  color: "#111827",
  outline: "none",
  boxShadow: "0 2px 10px rgba(15, 23, 42, 0.06)",
  appearance: "none",
};

const selectFocusStyle = {
  border: "1px solid #2563eb",
  boxShadow: "0 0 0 4px rgba(37, 99, 235, 0.18), 0 2px 10px rgba(15, 23, 42, 0.06)",
};

const buttonStyle = {
  padding: "10px 14px",
  borderRadius: 14,
  border: "1px solid #1d4ed8",
  background: "#2563eb",
  color: "#ffffff",
  cursor: "pointer",
  fontWeight: 800,
  boxShadow: "0 8px 18px rgba(37, 99, 235, 0.18)",
};

const disabledButtonStyle = {
  ...buttonStyle,
  opacity: 0.55,
  cursor: "not-allowed",
  boxShadow: "none",
};

const secondaryBtn = {
  ...buttonStyle,
  background: "#111827",
  borderColor: "#111827",
  boxShadow: "0 8px 18px rgba(17, 24, 39, 0.12)",
};

const errorStyle = {
  marginTop: 10,
  padding: 10,
  borderRadius: 14,
  border: "1px solid #fecaca",
  background: "#fff1f2",
  color: "#9f1239",
  fontWeight: 700,
};

const badgeStyle = (bg, fg) => ({
  display: "inline-block",
  padding: "4px 10px",
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 800,
  background: bg,
  color: fg,
  border: `1px solid ${fg}33`,
});

const sectionTitle = {
  marginTop: 0,
  marginBottom: 10,
  fontSize: 18,
  fontWeight: 900,
  color: "#111827",
};

const grid2 = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  gap: 12,
};

const statCard = {
  background: "linear-gradient(180deg, #ffffff 0%, #f9fafb 100%)",
  border: "1px solid #e5e7eb",
  borderRadius: 16,
  padding: 12,
  boxShadow: "0 6px 14px rgba(17, 24, 39, 0.06)",
};

const statLabel = {
  fontSize: 12,
  color: "#6b7280",
  fontWeight: 800,
  marginBottom: 4,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
};

const statValue = {
  fontSize: 18,
  fontWeight: 900,
  color: "#111827",
};

const listCard = (bg) => ({
  background: bg,
  border: "1px solid #e5e7eb",
  borderRadius: 16,
  padding: 12,
  boxShadow: "0 6px 14px rgba(17, 24, 39, 0.06)",
});

const liStyle = {
  marginBottom: 8,
  lineHeight: 1.35,
};

function safeNumber(v) {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

// --- Mini spinner (no dependencies) ---
function Spinner({ size = 16 }) {
  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: "999px",
        border: "2px solid rgba(255,255,255,0.45)",
        borderTopColor: "#ffffff",
        display: "inline-block",
        animation: "spin 0.8s linear infinite",
      }}
    />
  );
}

export default function Agents() {
  const [loading, setLoading] = useState(true);
  const [catalog, setCatalog] = useState(null);
  const [agentId, setAgentId] = useState("agent-weather");
  const [location, setLocation] = useState("");
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const [showRaw, setShowRaw] = useState(false);
  const [running, setRunning] = useState(false);

  // For select focus styling
  const [focusAgent, setFocusAgent] = useState(false);
  const [focusLoc, setFocusLoc] = useState(false);

  // Optional local tabs (if you want Runbook to look selected on this page)
  // If your real tab bar is elsewhere, ignore/remove this.
  const tabs = ["Runbook", "Agentic AI"];
  const [activeTab, setActiveTab] = useState("Agentic AI"); // mark selected

  // 1) Load catalog once
  useEffect(() => {
    let mounted = true;

    (async () => {
      try {
        setErr("");
        setLoading(true);

        const data = await apiGet("/api/agents");
        if (!mounted) return;

        setCatalog(data);

        const first = data?.agents?.[0];
        const initialAgentId = first?.id || "agent-weather";
        const initialLocation = first?.allowed_locations?.[0] || "";

        setAgentId(initialAgentId);
        setLocation(initialLocation);
      } catch (e) {
        if (!mounted) return;
        setErr(String(e?.message || e));
      } finally {
        if (mounted) setLoading(false);
      }
    })();

    return () => {
      mounted = false;
    };
  }, []);

  const agent = useMemo(() => {
    return catalog?.agents?.find((a) => a.id === agentId);
  }, [catalog, agentId]);

  // 2) Auto-select valid location when agent changes
  useEffect(() => {
    if (!agent) return;
    const firstLocation = agent.allowed_locations?.[0] || "";
    if (firstLocation && firstLocation !== location) {
      setLocation(firstLocation);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, agent]);

  async function runAgent() {
    setErr("");
    setResult(null);
    setShowRaw(false);
    setRunning(true);
    try {
      const data = await apiPost("/api/agent/run", {
        agent_id: agentId,
        location,
      });
      setResult(data?.result || data);
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setRunning(false);
    }
  }

  // --- Weather view helpers ---
  const current = result?.weather?.current;
  const units = result?.weather?.current_units;

  // --- Travel view helpers ---
  const travelPlan = result?.travel_plan;
  const isTravel = !!travelPlan && (result?.title || "").toLowerCase().includes("travel");
  const isWeather = !!current && (result?.title || "").toLowerCase().includes("weather");

  const tripCost = travelPlan?.estimated_cost_usd || {};
  const flights = safeNumber(tripCost?.flights_for_2);
  const hotel = safeNumber(tripCost?.hotel_4_star_5_nights);
  const local = safeNumber(tripCost?.local_transport_food);
  const total = safeNumber(tripCost?.total);

  // Tab styles
  const tabBar = {
    display: "flex",
    gap: 10,
    marginTop: 12,
    flexWrap: "wrap",
  };

  const tabStyle = (active) => ({
    padding: "10px 14px",
    borderRadius: 14,
    border: active ? "1px solid #1d4ed8" : "1px solid #e5e7eb",
    background: active
      ? "linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%)"
      : "linear-gradient(180deg, #ffffff 0%, #f3f4f6 100%)",
    color: active ? "#ffffff" : "#111827",
    fontWeight: 900,
    cursor: "pointer",
    boxShadow: active ? "0 10px 22px rgba(37, 99, 235, 0.22)" : "0 6px 14px rgba(17, 24, 39, 0.06)",
  });

  return (
    <div style={pageStyle}>
      {/* keyframes for spinner */}
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>

      <h2 style={headerStyle}>Agentic AI</h2>
      <p style={subStyle}>
        Select an agent and run it. Output is displayed inline (no popups). Weather uses Open-Meteo; Travel uses OpenAI.
      </p>

      {/* Optional: Local tabs so "selected" looks prominent */}
      <div style={tabBar}>
        {tabs.map((t) => (
          <button key={t} onClick={() => setActiveTab(t)} style={tabStyle(activeTab === t)}>
            {t}
          </button>
        ))}
      </div>

      {err && <div style={errorStyle}>Error: {err}</div>}

      <div style={panelStyle}>
        <div style={rowStyle}>
          <div style={fieldWrap}>
            <label style={labelStyle}>Agent</label>
            <select
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              onFocus={() => setFocusAgent(true)}
              onBlur={() => setFocusAgent(false)}
              style={focusAgent ? { ...selectStyle, ...selectFocusStyle } : selectStyle}
            >
              {(catalog?.agents || []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>

          <div style={fieldWrap}>
            <label style={labelStyle}>{agentId === "agent-travel" ? "City" : "Location"}</label>
            <select
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              onFocus={() => setFocusLoc(true)}
              onBlur={() => setFocusLoc(false)}
              style={focusLoc ? { ...selectStyle, ...selectFocusStyle } : selectStyle}
            >
              {(agent?.allowed_locations || []).map((loc) => (
                <option key={loc} value={loc}>
                  {loc}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={runAgent}
            disabled={!location || !agentId || running}
            style={!location || !agentId || running ? disabledButtonStyle : buttonStyle}
          >
            {running ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
                <Spinner size={16} /> Running…
              </span>
            ) : (
              "Run"
            )}
          </button>

          <button
            onClick={() => setShowRaw((s) => !s)}
            disabled={!result}
            style={!result ? disabledButtonStyle : secondaryBtn}
            title="Show/hide raw JSON (inline)"
          >
            {showRaw ? "Hide raw JSON" : "Show raw JSON"}
          </button>
        </div>

        {loading && <p style={{ marginTop: 14, color: "#374151" }}>Loading agents…</p>}

        {/* ----------------- RESULT VIEW ----------------- */}
        {result && (
          <div style={{ marginTop: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <h3 style={{ margin: 0, fontSize: 18, fontWeight: 950 }}>{result.title || "Result"}</h3>
              {isWeather && <span style={badgeStyle("#ecfeff", "#0e7490")}>WEATHER</span>}
              {isTravel && <span style={badgeStyle("#f5f3ff", "#5b21b6")}>TRAVEL</span>}
            </div>

            {/* -------- Pretty Weather -------- */}
            {isWeather && (
              <div style={{ marginTop: 12 }}>
                <div style={grid2}>
                  <div style={statCard}>
                    <div style={statLabel}>Temperature</div>
                    <div style={statValue}>
                      {current.temperature_2m}
                      {units?.temperature_2m}
                    </div>
                  </div>
                  <div style={statCard}>
                    <div style={statLabel}>Feels like</div>
                    <div style={statValue}>
                      {current.apparent_temperature}
                      {units?.apparent_temperature}
                    </div>
                  </div>
                  <div style={statCard}>
                    <div style={statLabel}>Humidity</div>
                    <div style={statValue}>
                      {current.relative_humidity_2m}
                      {units?.relative_humidity_2m}
                    </div>
                  </div>
                  <div style={statCard}>
                    <div style={statLabel}>Cloud cover</div>
                    <div style={statValue}>
                      {current.cloud_cover}
                      {units?.cloud_cover}
                    </div>
                  </div>
                  <div style={statCard}>
                    <div style={statLabel}>Wind</div>
                    <div style={statValue}>
                      {current.wind_speed_10m}
                      {units?.wind_speed_10m}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* -------- Pretty Travel -------- */}
            {isTravel && (
              <div style={{ marginTop: 12 }}>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <span style={badgeStyle("#eef2ff", "#3730a3")}>
                    Next 2 days: {travelPlan?.weather_outlook?.next_2_days || "—"}
                  </span>
                  <span style={badgeStyle("#eff6ff", "#1d4ed8")}>
                    Next 5 days: {travelPlan?.weather_outlook?.next_5_days || "—"}
                  </span>
                </div>

                <div
                  style={{
                    marginTop: 12,
                    display: "grid",
                    gap: 12,
                    gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
                  }}
                >
                  <div style={listCard("#f0fdf4")}>
                    <div style={{ ...sectionTitle, color: "#166534" }}>2-Day Itinerary</div>
                    <ol style={{ margin: 0, paddingLeft: 18 }}>
                      {(travelPlan?.itinerary_2_days || []).map((x, i) => (
                        <li key={i} style={liStyle}>
                          {x}
                        </li>
                      ))}
                    </ol>
                  </div>

                  <div style={listCard("#eff6ff")}>
                    <div style={{ ...sectionTitle, color: "#1d4ed8" }}>5-Day Itinerary</div>
                    <ol style={{ margin: 0, paddingLeft: 18 }}>
                      {(travelPlan?.itinerary_5_days || []).map((x, i) => (
                        <li key={i} style={liStyle}>
                          {x}
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>

                <div style={{ marginTop: 12 }}>
                  <div style={{ ...sectionTitle, marginBottom: 8 }}>Estimated Cost (USD)</div>
                  <div style={grid2}>
                    <div style={statCard}>
                      <div style={statLabel}>Flights (2)</div>
                      <div style={statValue}>{flights ?? "—"}</div>
                    </div>
                    <div style={statCard}>
                      <div style={statLabel}>Hotel (4-star, 5 nights)</div>
                      <div style={statValue}>{hotel ?? "—"}</div>
                    </div>
                    <div style={statCard}>
                      <div style={statLabel}>Local transport + food</div>
                      <div style={statValue}>{local ?? "—"}</div>
                    </div>
                    <div style={{ ...statCard, border: "1px solid #111827", background: "#111827" }}>
                      <div style={{ ...statLabel, color: "#e5e7eb" }}>Total</div>
                      <div style={{ ...statValue, color: "#ffffff" }}>{total ?? "—"}</div>
                    </div>
                  </div>
                </div>

                <div style={{ marginTop: 12, ...listCard("#fff7ed") }}>
                  <div style={{ ...sectionTitle, color: "#9a3412" }}>Travel Tips</div>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {(travelPlan?.travel_tips || []).map((x, i) => (
                      <li key={i} style={liStyle}>
                        {x}
                      </li>
                    ))}
                  </ul>
                </div>

                {travelPlan?.error && (
                  <div style={{ ...errorStyle, marginTop: 12 }}>
                    Travel agent error: {String(travelPlan.error)}
                  </div>
                )}
              </div>
            )}

            {showRaw && (
              <div style={{ marginTop: 12 }}>
                <div style={{ ...sectionTitle, marginBottom: 8 }}>Raw JSON</div>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    background: "#0b1020",
                    color: "#e5e7eb",
                    padding: 12,
                    borderRadius: 16,
                    border: "1px solid #111827",
                    overflowX: "auto",
                    fontSize: 12,
                    lineHeight: 1.5,
                    boxShadow: "0 10px 22px rgba(0,0,0,0.20)",
                  }}
                >
                  {JSON.stringify(result, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>

      <p style={{ marginTop: 14, color: "#6b7280", fontSize: 12 }}>
        Tip: Select <b>Travel planner</b> from the Agent dropdown to see travel output.
      </p>
    </div>
  );
}