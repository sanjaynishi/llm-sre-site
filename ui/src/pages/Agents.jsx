import React, { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../api/client";

/**
 * Simple inline theme (no external CSS needed).
 * NOTE: Keep styles defined once (don’t re-declare selectStyle inside the component).
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

  const current = result?.weather?.current;
  const units = result?.weather?.current_units;

  return (
    <div style={{ padding: 16, maxWidth: 900 }}>
      <h2>Agentic AI</h2>
      <p style={{ marginTop: 4, opacity: 0.8 }}>
        Pre-defined agents & locations (cost-controlled). Powered by Lambda + Open-Meteo.
      </p>

      {/* ✅ ERROR VISIBILITY */}
      {err && <p style={{ color: "crimson" }}>Error: {err}</p>}

      {/* ✅ DEBUG VISIBILITY */}
      <p style={{ fontSize: 12, opacity: 0.6 }}>
        Debug → loading: {String(loading)} | agents: {catalog?.agents?.length ?? 0} | agentId:{" "}
        {agentId || "(empty)"} | location: {location || "(empty)"}
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
              Run
            </button>
          </div>

          {result && (
            <div style={cardStyle}>
              <h3 style={{ marginTop: 0 }}>{result.title}</h3>

              {current ? (
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
              )}

              <details style={{ marginTop: 12 }}>
                <summary>View raw JSON</summary>
                <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(result, null, 2)}</pre>
              </details>
            </div>
          )}
        </>
      )}
    </div>
  );
}