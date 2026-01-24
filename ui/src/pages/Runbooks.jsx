import React, { useMemo, useState } from "react";

const card = {
  padding: 14,
  border: "1px solid #e5e7eb",
  borderRadius: 16,
  background: "#fff",
};

const row = { display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" };

const label = { fontWeight: 800, fontSize: 13, color: "#111827" };

const selectStyle = {
  padding: "10px 12px",
  borderRadius: 12,
  border: "1px solid #e5e7eb",
  minWidth: 360,
};

const inputStyle = {
  padding: "10px 12px",
  borderRadius: 12,
  border: "1px solid #e5e7eb",
  width: 90,
};

const btn = {
  padding: "10px 14px",
  borderRadius: 12,
  border: "1px solid #1d4ed8",
  background: "#1d4ed8",
  color: "#fff",
  fontWeight: 900,
  cursor: "pointer",
};

const pre = {
  marginTop: 12,
  whiteSpace: "pre-wrap",
  background: "#0b1220",
  color: "#e5e7eb",
  padding: 12,
  borderRadius: 12,
  overflowX: "auto",
  fontSize: 13,
  lineHeight: 1.35,
};

export default function Runbooks() {
  // ✅ Put ALL your predefined questions here
  const QUESTIONS = useMemo(
    () => [
      {
        id: "invalidate_cf",
        label: "Invalidate CloudFront cache after deploying UI",
        question: "How do I invalidate CloudFront cache after deploying the UI?",
      },
      {
        id: "behaviors_api_spa",
        label: "CloudFront behaviors for /api/* vs SPA routes",
        question: "What are the CloudFront behaviors for /api/* vs SPA routes?",
      },
      {
        id: "cors_apigw",
        label: "Fix CORS issues for API Gateway behind CloudFront",
        question: "How do I fix CORS issues for API Gateway behind CloudFront?",
      },
      {
        id: "lambda_logs",
        label: "Check Lambda logs for API 500 errors",
        question: "How do I check Lambda logs to debug API 500 errors?",
      },
      // add more here…
    ],
    []
  );

  const [qid, setQid] = useState(QUESTIONS[0]?.id || "");
  const [topK, setTopK] = useState(5);
  const [status, setStatus] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(false);

  const selected = QUESTIONS.find((q) => q.id === qid) || QUESTIONS[0];

  async function onAsk() {
    if (!selected?.question) {
      setStatus("Pick a question.");
      return;
    }

    setLoading(true);
    setStatus("Asking…");
    setAnswer("");
    setSources([]);

    try {
      const res = await fetch("/api/runbooks/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: selected.question, top_k: Number(topK) || 5 }),
      });

      const data = await res.json();

      if (!res.ok || data?.error) {
        const msg = data?.error?.message || `HTTP ${res.status}`;
        setStatus(`Error: ${msg}`);
        setLoading(false);
        return;
      }

      setAnswer(data.answer || "");
      setSources(Array.isArray(data.sources) ? data.sources : []);
      setStatus("Done.");
    } catch (e) {
      setStatus(`Network error: ${String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={card}>
      <h2 style={{ marginTop: 0, marginBottom: 6 }}>Runbooks</h2>
      <div style={{ color: "#4b5563", marginBottom: 12 }}>
        Predefined questions (cost-controlled). Powered by RAG.
      </div>

      <div style={row}>
        <div>
          <div style={label}>Pick a question</div>
          <select
            value={qid}
            onChange={(e) => setQid(e.target.value)}
            style={selectStyle}
          >
            {QUESTIONS.map((q) => (
              <option key={q.id} value={q.id}>
                {q.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <div style={label}>top_k</div>
          <input
            type="number"
            min={1}
            max={10}
            value={topK}
            onChange={(e) => setTopK(e.target.value)}
            style={inputStyle}
          />
        </div>

        <div style={{ alignSelf: "flex-end" }}>
          <button onClick={onAsk} style={btn} disabled={loading}>
            {loading ? "Asking…" : "Ask"}
          </button>
        </div>
      </div>

      {status ? (
        <div style={{ marginTop: 10, color: status.startsWith("Error") ? "#b91c1c" : "#374151" }}>
          {status}
        </div>
      ) : null}

      {answer ? (
        <>
          <div style={pre}>{answer}</div>

          {sources?.length ? (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontWeight: 900, marginBottom: 6 }}>Sources</div>
              <ul style={{ marginTop: 0 }}>
                {sources.map((s, idx) => (
                  <li key={idx}>
                    {s.file || s.s3_key || "source"}{s.chunk !== undefined ? ` (chunk ${s.chunk})` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}