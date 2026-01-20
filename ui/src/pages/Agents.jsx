import React, { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../api/client";

const selectStyle = {
  minWidth: 320,
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid #2b2b2b",
  background: "#0b0f17",
  color: "#e6edf3",
  outline: "none",
};

const buttonStyle = {
  padding: "10px 14px",
  borderRadius: 10,
  border: "1px solid #2b2b2b",
  background: "#1f6feb",
  color: "#fff",
  cursor: "pointer",
};

const labelStyle = {
  display: "block",
  marginBottom: 6,
  fontSize: 13,
  opacity: 0.8,
  color: "#c9d1d9",
};

const card = {
  marginTop: 16,
  padding: 16,
  border: "1px solid #2b2b2b",
  borderRadius: 14,
  background: "#0b0f17",
  color: "#e6edf3",
};

const pill = {
  display: "inline-block",
  padding: "4px 10px",
  borderRadius: 999,
  border: "1px solid #2b2b2b",
  background: "#0f1623",
  fontSize: 12,
  opacity: 0.9,
};

const grid = {
  marginTop: 12,
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  gap: 12,
};

const stat = {
  padding: 12,
  border: "1px solid #2b2b2b",
  borderRadius: 12,
  background: "#0f1623",
};

function toTitleCase(s) {
  return String(s || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function safeNum(x) {
  if (x === null || x === undefined) return null;
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
}

function formatMoney(x) {
  const n = safeNum(x);
  if (n === null) return "-";
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

// Small helper: turn Open-Meteo daily arrays into friendly outlook
function buildDailyOutlook(weather) {
  const daily = weather?.daily;
  if (!daily?.time?.length) return [];

  const times = daily.time;
  const maxT = daily.temperature_2m_max || [];
  const minT = daily.temperature_2m_min || [];
  const pop = daily.precipitation_probability_max || [];

  // show next 3 days
  const out = [];
  for (let i = 0; i < Math.min(3, times.length); i++) {
    out.push({
      day: times[i],
      max: safeNum(maxT[i]),
      min: safeNum(minT[i]),
      pop: safeNum(pop[i]),
    });
  }
  return out;
}

export default function Agents() {
  const [loading, setLoading] = useState(true);
  const [catalog, setCatalog] = useState(null);
  const [agentId, setAgentId] = useState("agent-weather");
  const [location, setLocation] = useState("");
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");

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

  // When user changes agent, auto-pick first allowed location for that agent
  useEffect(() => {
    const firstLoc = agent?.allowed_locations?.[0] || "";
    if (firstLoc) setLocation(firstLoc);
  }, [agentId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function runAgent() {
    setErr("");
    setResult(null);
    try {
      const data = await apiPost("/api/agent/run", { agent_id: agentId, location });
      setResult(data?.result || data);
    } catch (e) {
      setErr(String(e?.message || e));
    }
  }

  const isTravel = agentId === "agent-travel";

  // ---- Weather extraction ----
  const current = result?.weather?.current;
  const units = result?.weather?.current_units;
  const dailyOutlook = buildDailyOutlook(result?.weather);

  // ---- Travel extraction ----
  const travelPlan = result?.travel_plan;
  const cost = travelPlan?.estimated_cost_usd;

  return (
    <div style={{ padding: 16, maxWidth: 980, color: "#e6edf3" }}>
      <h2 style={{ marginBottom: 6 }}>Agentic AI</h2>
      <p style={{ marginTop: 0, opacity: 0.75 }}>
        Choose an agent and location. Results render inline in a readable format (no popups).
      </p>

      {err && (
        <div style={{ ...card, borderColor: "#8b2d2d", background: "#1a0f12" }}>
          <b style={{ color: "#ff7b7b" }}>Error:</b> {err}
        </div>
      )}

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
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
          <label style={labelStyle}>{isTravel ? "City" : "Location"}</label>
          <select value={location} onChange={(e) => setLocation(e.target.value)} style={selectStyle}>
            {(agent?.allowed_locations || []).map((loc) => (
              <option key={loc} value={loc}>
                {loc}
              </option>
            ))}
          </select>
        </div>

        <button onClick={runAgent} disabled={!location || !agentId || loading} style={buttonStyle}>
          {loading ? "Loading…" : isTravel ? "Generate travel plan" : "Run weather"}
        </button>

        <span style={pill}>{toTitleCase(agentId)}</span>
      </div>

      {result && (
        <div style={card}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
            <div>
              <h3 style={{ margin: 0 }}>{result?.title || (isTravel ? "Travel plan" : "Weather")}</h3>
              <div style={{ marginTop: 6, fontSize: 13, opacity: 0.8 }}>
                {isTravel ? (
                  <>
                    City: <b>{result?.city || location}</b>
                  </>
                ) : (
                  <>
                    Location: <b>{location}</b>
                  </>
                )}
              </div>
            </div>
            <div style={{ ...pill, height: "fit-content" }}>
              {isTravel ? "Travel" : "Weather"}
            </div>
          </div>

          {/* ---- WEATHER VIEW ---- */}
          {!isTravel && (
            <>
              <div style={grid}>
                <div style={stat}>
                  <div style={{ fontSize: 12, opacity: 0.7 }}>Temperature</div>
                  <div style={{ fontSize: 20, marginTop: 6 }}>
                    {current?.temperature_2m ?? "-"}
                    {units?.temperature_2m || ""}
                  </div>
                </div>

                <div style={stat}>
                  <div style={{ fontSize: 12, opacity: 0.7 }}>Feels like</div>
                  <div style={{ fontSize: 20, marginTop: 6 }}>
                    {current?.apparent_temperature ?? "-"}
                    {units?.apparent_temperature || ""}
                  </div>
                </div>

                <div style={stat}>
                  <div style={{ fontSize: 12, opacity: 0.7 }}>Humidity</div>
                  <div style={{ fontSize: 20, marginTop: 6 }}>
                    {current?.relative_humidity_2m ?? "-"}
                    {units?.relative_humidity_2m || ""}
                  </div>
                </div>

                <div style={stat}>
                  <div style={{ fontSize: 12, opacity: 0.7 }}>Cloud cover</div>
                  <div style={{ fontSize: 20, marginTop: 6 }}>
                    {current?.cloud_cover ?? "-"}
                    {units?.cloud_cover || "%"}
                  </div>
                </div>
              </div>

              <h4 style={{ margin: "18px 0 10px" }}>Next 3 days outlook</h4>
              {dailyOutlook.length ? (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
                  {dailyOutlook.map((d) => (
                    <div key={d.day} style={stat}>
                      <div style={{ fontSize: 12, opacity: 0.7 }}>{d.day}</div>
                      <div style={{ marginTop: 8, lineHeight: 1.5 }}>
                        <div>
                          <b>High:</b> {d.max ?? "-"}°C
                        </div>
                        <div>
                          <b>Low:</b> {d.min ?? "-"}°C
                        </div>
                        <div>
                          <b>Rain chance:</b> {d.pop ?? "-"}%
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ opacity: 0.8 }}>No daily outlook available.</p>
              )}
            </>
          )}

          {/* ---- TRAVEL VIEW ---- */}
          {isTravel && (
            <>
              {travelPlan?.error ? (
                <div style={{ ...stat, borderColor: "#8b2d2d", background: "#1a0f12", marginTop: 12 }}>
                  <b style={{ color: "#ff7b7b" }}>Travel error:</b> {String(travelPlan.error)}
                </div>
              ) : (
                <>
                  <div style={grid}>
                    <div style={stat}>
                      <div style={{ fontSize: 12, opacity: 0.7 }}>Weather outlook (2 days)</div>
                      <div style={{ fontSize: 16, marginTop: 6 }}>
                        {travelPlan?.weather_outlook?.next_2_days || "-"}
                      </div>
                    </div>

                    <div style={stat}>
                      <div style={{ fontSize: 12, opacity: 0.7 }}>Weather outlook (5 days)</div>
                      <div style={{ fontSize: 16, marginTop: 6 }}>
                        {travelPlan?.weather_outlook?.next_5_days || "-"}
                      </div>
                    </div>

                    <div style={stat}>
                      <div style={{ fontSize: 12, opacity: 0.7 }}>Estimated cost (USD)</div>
                      <div style={{ fontSize: 20, marginTop: 6 }}>${formatMoney(cost?.total)}</div>
                      <div style={{ fontSize: 12, opacity: 0.75, marginTop: 8, lineHeight: 1.5 }}>
                        Flights for 2: <b>${formatMoney(cost?.flights_for_2)}</b>
                        <br />
                        4★ hotel (5 nights): <b>${formatMoney(cost?.hotel_4_star_5_nights)}</b>
                        <br />
                        Local + food: <b>${formatMoney(cost?.local_transport_food)}</b>
                      </div>
                    </div>
                  </div>

                  <h4 style={{ margin: "18px 0 10px" }}>2-day itinerary</h4>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12 }}>
                    {(travelPlan?.itinerary_2_days || []).map((x, i) => (
                      <div key={i} style={stat}>
                        <div style={{ fontSize: 12, opacity: 0.7 }}>Day {i + 1}</div>
                        <div style={{ marginTop: 8, lineHeight: 1.5 }}>{x}</div>
                      </div>
                    ))}
                  </div>

                  <h4 style={{ margin: "18px 0 10px" }}>5-day itinerary</h4>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12 }}>
                    {(travelPlan?.itinerary_5_days || []).map((x, i) => (
                      <div key={i} style={stat}>
                        <div style={{ fontSize: 12, opacity: 0.7 }}>Day {i + 1}</div>
                        <div style={{ marginTop: 8, lineHeight: 1.5 }}>{x}</div>
                      </div>
                    ))}
                  </div>

                  <h4 style={{ margin: "18px 0 10px" }}>Travel tips</h4>
                  <ul style={{ marginTop: 0, lineHeight: 1.6, opacity: 0.95 }}>
                    {(travelPlan?.travel_tips || []).map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}

          {/* Inline debug only (no popup) */}
          <details style={{ marginTop: 16 }}>
            <summary style={{ cursor: "pointer", opacity: 0.85 }}>Advanced: view raw JSON</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, marginTop: 10 }}>
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}