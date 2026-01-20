import React, { useEffect, useMemo, useState } from "react";
import { apiGet } from "../api/client";

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
  padding: 16,
  border: "1px solid #333",
  borderRadius: 12,
  background: "#0d1117",
};

export default function Agents() {
  const [loading, setLoading] = useState(true);
  const [catalog, setCatalog] = useState(null);
  const [agentId, setAgentId] = useState("agent-weather");
  const [city, setCity] = useState("");
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
        setAgentId(first?.id || "agent-weather");
        setCity(first?.allowed_locations?.[0] || "");
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

  const agent = useMemo(
    () => catalog?.agents?.find((a) => a.id === agentId),
    [catalog, agentId]
  );

  async function runAgent() {
    setErr("");
    setResult(null);

    try {
      const data = await apiGet(`/api/agents?city=${encodeURIComponent(city)}`);
      setResult(data);
    } catch (e) {
      setErr(String(e?.message || e));
    }
  }

  const travel = result?.travel_plan;

  return (
    <div style={{ padding: 16, maxWidth: 900 }}>
      <h2>Agentic AI – Travel Planner</h2>
      <p style={{ marginTop: 4, opacity: 0.8 }}>
        AI-generated travel plans powered by OpenAI (cost-controlled, server-side).
      </p>

      {err && <p style={{ color: "crimson" }}>Error: {err}</p>}

      <p style={{ fontSize: 12, opacity: 0.6 }}>
        Debug → loading: {String(loading)} | agent: {agentId} | city: {city || "(empty)"}
      </p>

      {loading ? (
        <p>Loading agents…</p>
      ) : (
        <>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
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
              <label style={labelStyle}>City</label>
              <select
                value={city}
                onChange={(e) => setCity(e.target.value)}
                style={selectStyle}
              >
                {(agent?.allowed_locations || []).map((loc) => (
                  <option key={loc} value={loc}>
                    {loc}
                  </option>
                ))}
              </select>
            </div>

            <button onClick={runAgent} disabled={!city} style={buttonStyle}>
              Generate Travel Plan
            </button>
          </div>

          {travel && (
            <div style={cardStyle}>
              <h3 style={{ marginTop: 0 }}>📍 {result.city}</h3>

              <p>
                <b>Weather outlook:</b>{" "}
                {travel.weather_outlook?.next_2_days} (2 days),{" "}
                {travel.weather_outlook?.next_5_days} (5 days)
              </p>

              <h4>🗓 2-Day Itinerary</h4>
              <ul>
                {travel.itinerary_2_days?.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>

              <h4>🗓 5-Day Itinerary</h4>
              <ul>
                {travel.itinerary_5_days?.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>

              <h4>💰 Estimated Cost (USD)</h4>
              <ul>
                <li>Flights (2): ${travel.estimated_cost_usd?.flights_for_2}</li>
                <li>Hotel (4★, 5 nights): ${travel.estimated_cost_usd?.hotel_4_star_5_nights}</li>
                <li>Local transport & food: ${travel.estimated_cost_usd?.local_transport_food}</li>
                <li>
                  <b>Total: ${travel.estimated_cost_usd?.total}</b>
                </li>
              </ul>

              <h4>✈ Travel Tips</h4>
              <ul>
                {travel.travel_tips?.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>

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