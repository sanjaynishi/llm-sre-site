import React, { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../api/client";

/**
 * Agents page (inline UI, no popups)
 * - Better readability (light background card layout)
 * - Weather shown as clean stats + optional raw JSON toggle
 * - Travel shown as formatted sections + colored itineraries
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
  fontWeight: 800,
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
  borderRadius: 16,
  padding: 16,
  boxShadow: "0 8px 20px rgba(17, 24, 39, 0.06)",
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
  fontWeight: 600,
};

const selectStyle = {
  minWidth: 320,
  padding: "10px 12px",
  borderRadius: 12,
  border: "1px solid #d1d5db",
  background: "#f9fafb",
  color: "#111827",
  outline: "none",
};

const buttonStyle = {
  padding: "10px 14px",
  borderRadius: 12,
  border: "1px solid #1d4ed8",
  background: "#2563eb",
  color: "#ffffff",
  cursor: "pointer",
  fontWeight: 700,
};

const disabledButtonStyle = {
  ...buttonStyle,
  opacity: 0.6,
  cursor: "not-allowed",
};

const errorStyle = {
  marginTop: 10,
  padding: 10,
  borderRadius: 12,
  border: "1px solid #fecaca",
  background: "#fff1f2",
  color: "#9f1239",
  fontWeight: 600,
};

const badgeStyle = (bg, fg) => ({
  display: "inline-block",
  padding: "4px 10px",
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 700,
  background: bg,
  color: fg,
  border: `1px solid ${fg}33`,
});

const sectionTitle = {
  marginTop: 0,
  marginBottom: 10,
  fontSize: 18,
  fontWeight: 800,
  color: "#111827",
};

const grid2 = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  gap: 12,
};

const statCard = {
  background: "#f9fafb",
  border: "1px solid #e5e7eb",
  borderRadius: 14,
  padding: 12,
};

const statLabel = {
  fontSize: 12,
  color: "#6b7280",
  fontWeight: 700,
  marginBottom: 4,
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const statValue = {
  fontSize: 18,
  fontWeight: 800,
  color: "#111827",
};

const listCard = (bg) => ({
  background: bg,
  border: "1px solid #e5e7eb",
  borderRadius: 14,
  padding: 12,
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

export default function Agents() {
  const [loading, setLoading] = useState(true);
  const [catalog, setCatalog] = useState(null);
  const [agentId, setAgentId] = useState("agent-weather");
  const [location, setLocation] = useState("");
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const [showRaw, setShowRaw] = useState(false);

  // 1) Auto-select valid location when agent changes
  useEffect(() => {
    if (!agent) return;

    const firstLocation = agent.allowed_locations?.[0] || "";
    if (firstLocation && firstLocation !== location) {
      setLocation(firstLocation);
    }
  }, [agentId, agent]); // (optionally add `location` if you want)


  // 2) Load catalog once
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

  async function runAgent() {
    setErr("");
    setResult(null);
    setShowRaw(false);
    try {
      const data = await apiPost("/api/agent/run", {
        agent_id: agentId,
        location,
      });
      setResult(data?.result || data);
    } catch (e) {
      setErr(String(e?.message || e));
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

  return (
    <div style={pageStyle}>
      <h2 style={headerStyle}>Agentic AI</h2>
      <p style={subStyle}>
        Select an agent and run it. Output is displayed inline (no popups). Weather uses Open-Meteo;
        Travel uses OpenAI (gpt-5.1-mini).
      </p>

      {err && <div style={errorStyle}>Error: {err}</div>}

      <div style={panelStyle}>
        <div style={rowStyle}>
          <div>
            <label style={labelStyle}>Agent</label>
            <select value={agentId} onChange={(e) => setAgentId(e.target.value)} style={selectStyle}>
              {(catalog?.agents || []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={labelStyle}>{agentId === "agent-travel" ? "City" : "Location"}</label>
            <select value={location} onChange={(e) => setLocation(e.target.value)} style={selectStyle}>
              {(agent?.allowed_locations || []).map((loc) => (
                <option key={loc} value={loc}>
                  {loc}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={runAgent}
            disabled={!location || !agentId}
            style={!location || !agentId ? disabledButtonStyle : buttonStyle}
          >
            Run
          </button>

          <button
            onClick={() => setShowRaw((s) => !s)}
            disabled={!result}
            style={!result ? disabledButtonStyle : { ...buttonStyle, background: "#111827", borderColor: "#111827" }}
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
              <h3 style={{ margin: 0, fontSize: 18, fontWeight: 900 }}>{result.title || "Result"}</h3>
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
                {/* Weather outlook */}
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <span style={badgeStyle("#eef2ff", "#3730a3")}>
                    Next 2 days: {travelPlan?.weather_outlook?.next_2_days || "—"}
                  </span>
                  <span style={badgeStyle("#eff6ff", "#1d4ed8")}>
                    Next 5 days: {travelPlan?.weather_outlook?.next_5_days || "—"}
                  </span>
                </div>

                {/* Itineraries in different colors */}
                <div style={{ marginTop: 12, display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
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

                {/* Costs */}
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

                {/* Tips */}
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

                {/* If travel_plan returned an error */}
                {travelPlan?.error && (
                  <div style={{ ...errorStyle, marginTop: 12 }}>
                    Travel agent error: {String(travelPlan.error)}
                  </div>
                )}
              </div>
            )}

            {/* Raw JSON toggle (inline) */}
            {showRaw && (
              <div style={{ marginTop: 12 }}>
                <div style={{ ...sectionTitle, marginBottom: 8 }}>Raw JSON</div>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    background: "#0b1020",
                    color: "#e5e7eb",
                    padding: 12,
                    borderRadius: 14,
                    border: "1px solid #111827",
                    overflowX: "auto",
                    fontSize: 12,
                    lineHeight: 1.4,
                  }}
                >
                  {JSON.stringify(result, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>

      {/* footer note */}
      <p style={{ marginTop: 14, color: "#6b7280", fontSize: 12 }}>
        Tip: Select <b>Travel planner</b> from the Agent dropdown to see travel output.
      </p>
    </div>
  );
}