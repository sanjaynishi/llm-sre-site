import React, { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../api/client";

/**
 * Simple inline theme (no external CSS needed).
 */
const selectStyle = {
  minWidth: 320,
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid #444",
  background: "#111",
  color: "#fff",
  outline: "none",
};

const buttonStyle = {
  padding: "10px 14px",
  borderRadius: 10,
  border: "1px solid #444",
  background: "#1f6feb",
  color: "#fff",
  cursor: "pointer",
};

const labelStyle = {
  display: "block",
  marginBottom: 6,
  fontSize: 13,
  opacity: 0.85,
};

const cardStyle = {
  marginTop: 16,
  padding: 12,
  border: "1px solid #ddd",
  borderRadius: 8,
};

const sectionTitle = {
  margin: "14px 0 8px",
  fontSize: 14,
};

export default function Agents() {
  const [loading, setLoading] = useState(true);
  const [catalog, setCatalog] = useState(null);
  const [agentId, setAgentId] = useState("agent-weather");
  const [location, setLocation] = useState("");
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");

  // Load agent catalog
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

  // Current selected agent object
  const agent = useMemo(() => {
    return catalog?.agents?.find((a) => a.id === agentId);
  }, [catalog, agentId]);

  // When agent changes, reset location to that agent's first allowed location
  useEffect(() => {
    const a = catalog?.agents?.find((x) => x.id === agentId);
    const firstLoc = a?.allowed_locations?.[0] || "";
    setLocation(firstLoc);
    setResult(null);
    setErr("");
  }, [agentId, catalog]);

  async function runAgent() {
    setErr("");
    setResult(null);
    try {
      const data = await apiPost("/api/agent/run", {
        agent_id: agentId,
        location,
      });

      // Normalized: backend returns { result: {...} }
      setResult(data?.result ?? data);
    } catch (e) {
      setErr(String(e?.message || e));
    }
  }

  // Normalize shape (in case backend changes)
  const normalized = result?.result ? result.result : result;

  const isTravel =
    agentId === "agent-travel" || Boolean(normalized?.travel_plan);
  const isWeather =
    agentId === "agent-weather" || Boolean(normalized?.weather);

  const current = normalized?.weather?.current;
  const units = normalized?.weather?.current_units;

  const travelPlan = normalized?.travel_plan;
  const cost = travelPlan?.estimated_cost_usd;

  return (
    <div style={{ padding: 16, maxWidth: 900 }}>
      <h2>Agentic AI</h2>
      <p style={{ marginTop: 4, opacity: 0.8 }}>
        Pre-defined agents & locations (cost-controlled). Powered by Lambda.
      </p>

      {/* ERROR */}
      {err && <p style={{ color: "crimson" }}>Error: {err}</p>}

      {/* DEBUG LINE */}
      <p style={{ fontSize: 12, opacity: 0.6 }}>
        Debug → loading: {String(loading)} | agents:{" "}
        {catalog?.agents?.length ?? 0} | agentId: {agentId || "(empty)"} |
        location: {location || "(empty)"}
      </p>

      {loading ? (
        <p>Loading agents…</p>
      ) : (
        <>
          <div
            style={{
              display: "flex",
              gap: 12,
              flexWrap: "wrap",
              alignItems: "end",
            }}
          >
            <div>
              <label style={labelStyle}>Agent</label>
              <select
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                style={selectStyle}
              >
                {(catalog?.agents || []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={labelStyle}>Location</label>
              <select
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                style={selectStyle}
              >
                {(agent?.allowed_locations || []).map((loc) => (
                  <option key={loc} value={loc}>
                    {loc}
                  </option>
                ))}
              </select>
            </div>

            <button onClick={runAgent} disabled={!location || !agentId} style={buttonStyle}>
              {agentId === "agent-travel" ? "Generate Travel Plan" : "Run Weather"}
            </button>
          </div>

          {result && (
            <div style={cardStyle}>
              <h3 style={{ marginTop: 0 }}>
                {normalized?.title || "Agent Result"}
              </h3>

              {/* TRAVEL VIEW */}
              {isTravel ? (
                <>
                  {travelPlan?.error ? (
                    <p style={{ color: "crimson" }}>
                      Travel error: {String(travelPlan.error)}
                    </p>
                  ) : (
                    <>
                      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                        <div>
                          <b>Next 2 days:</b>{" "}
                          {travelPlan?.weather_outlook?.next_2_days || "-"}
                        </div>
                        <div>
                          <b>Next 5 days:</b>{" "}
                          {travelPlan?.weather_outlook?.next_5_days || "-"}
                        </div>
                      </div>

                      <h4 style={sectionTitle}>2-day itinerary</h4>
                      <ul style={{ marginTop: 6 }}>
                        {(travelPlan?.itinerary_2_days || []).map((x, i) => (
                          <li key={i}>{x}</li>
                        ))}
                      </ul>

                      <h4 style={sectionTitle}>5-day itinerary</h4>
                      <ul style={{ marginTop: 6 }}>
                        {(travelPlan?.itinerary_5_days || []).map((x, i) => (
                          <li key={i}>{x}</li>
                        ))}
                      </ul>

                      <h4 style={sectionTitle}>Estimated cost (USD)</h4>
                      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                        <div>
                          <b>Flights (2):</b> {cost?.flights_for_2 ?? "-"}
                        </div>
                        <div>
                          <b>Hotel (4★, 5 nights):</b> {cost?.hotel_4_star_5_nights ?? "-"}
                        </div>
                        <div>
                          <b>Local + food:</b> {cost?.local_transport_food ?? "-"}
                        </div>
                        <div>
                          <b>Total:</b> {cost?.total ?? "-"}
                        </div>
                      </div>

                      <h4 style={sectionTitle}>Travel tips</h4>
                      <ul style={{ marginTop: 6 }}>
                        {(travelPlan?.travel_tips || []).map((x, i) => (
                          <li key={i}>{x}</li>
                        ))}
                      </ul>
                    </>
                  )}
                </>
              ) : null}

              {/* WEATHER VIEW */}
              {isWeather && !isTravel ? (
                current ? (
                  <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                    <div>
                      <b>Temp:</b> {current.temperature_2m}
                      {units?.temperature_2m}
                    </div>
                    <div>
                      <b>Feels like:</b> {current.apparent_temperature}
                      {units?.apparent_temperature}
                    </div>
                    <div>
                      <b>Humidity:</b> {current.relative_humidity_2m}
                      {units?.relative_humidity_2m}
                    </div>
                    <div>
                      <b>Wind:</b> {current.wind_speed_10m}
                      {units?.wind_speed_10m}
                    </div>
                  </div>
                ) : (
                  <p>No current weather in response.</p>
                )
              ) : null}

              <details style={{ marginTop: 12 }}>
                <summary>View raw JSON</summary>
                <pre style={{ whiteSpace: "pre-wrap" }}>
                  {JSON.stringify(result, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </>
      )}
    </div>
  );
}