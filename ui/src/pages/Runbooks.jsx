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

const btnDisabled = {
  opacity: 0.6,
  cursor: "not-allowed",
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

function safeJsonParse(text) {
  try {
    return { ok: true, data: JSON.parse(text) };
  } catch (e) {
    return { ok: false, error: e };
  }
}

export default function Runbooks() {
  // ✅ Add as many predefined questions as you want here
  const QUESTIONS = useMemo(
    () => [
      // --- CloudFront / UI ---
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
        id: "headers_cache",
        label: "Check caching headers (x-cache, age, etag)",
        question: "What headers should I check to confirm caching (x-cache, age, etag)?",
      },
      {
        id: "assets_policy",
        label: "Cache policy for SPA assets vs index.html",
        question: "What’s the recommended cache policy for SPA assets vs index.html?",
      },

      // --- API Gateway / Lambda ---
      {
        id: "apigw_500",
        label: "Troubleshoot API Gateway 500s behind CloudFront",
        question: "How do I troubleshoot API Gateway 500 errors behind CloudFront?",
      },
      {
        id: "lambda_invoke_perm",
        label: "Fix Lambda invoke permissions for API Gateway",
        question: "How do I validate/fix Lambda permissions for API Gateway invoke?",
      },
      {
        id: "lambda_logs",
        label: "Check Lambda logs for API errors",
        question: "How do I check Lambda logs to debug API errors (500/502)?",
      },

      // --- RAG / Chroma ---
      {
        id: "rag_topk",
        label: "What is top_k and how to tune it?",
        question: "What is top_k and how does it affect retrieval accuracy and cost?",
      },
      {
        id: "chroma_s3",
        label: "Where are Chroma vectors stored and loaded from?",
        question: "Where are Chroma vectors stored in S3 and how are they loaded in Lambda?",
      },
      {
        id: "sqlite_chroma",
        label: "Fix sqlite/chroma issues in Lambda",
        question: "How do I handle sqlite3 version issues for Chroma in Lambda?",
      },
      {
        id: "incremental_indexing",
        label: "Incremental indexing for changed PDFs",
        question: "How do I re-index only changed runbook PDFs (incremental indexing)?",
      },

      // --- Security / Threat model ---
      {
        id: "cors_restrict",
        label: "Restrict CORS origins for dev vs prod",
        question: "How do I restrict CORS origins properly for dev vs prod?",
      },
      {
        id: "secrets_handling",
        label: "Prevent secrets exposure in env vars/logs",
        question: "How do I prevent secrets exposure in Lambda env vars and logs?",
      },

      // --- Quantum (answered only if your runbooks contain this info) ---
      {
        id: "quantum_qubit",
        label: "Quantum: What is a qubit vs a classical bit?",
        question: "What is a qubit and how is it different from a classical bit?",
      },
      {
        id: "quantum_superposition",
        label: "Quantum: Explain superposition and measurement",
        question: "Explain superposition and measurement in practical terms.",
      },
      {
        id: "quantum_entanglement",
        label: "Quantum: What is entanglement used for?",
        question: "What is entanglement and how is it used in algorithms?",
      },
      {
        id: "quantum_qaoa",
        label: "Quantum: What is QAOA and when to use it?",
        question: "Explain QAOA and where it fits in optimization problems.",
      },
      {
        id: "quantum_qubo",
        label: "Quantum: What is QUBO and how to map problems?",
        question: "What is a QUBO formulation and how do we map a problem to QUBO?",
      },
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

    const k = Math.min(10, Math.max(1, Number(topK) || 5));

    setLoading(true);
    setStatus("Asking…");
    setAnswer("");
    setSources([]);

    try {
      const res = await fetch("/api/runbooks/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: selected.question, top_k: k }),
      });

      // IMPORTANT: avoid "Unexpected token '<'" by NOT blindly calling res.json()
      const contentType = res.headers.get("content-type") || "";
      const text = await res.text();

      if (!contentType.includes("application/json")) {
        setStatus(
          `Error: Expected JSON but got "${contentType || "unknown"}". ` +
            `This usually means CloudFront/S3 returned HTML. (First 200 chars): ` +
            text.slice(0, 200)
        );
        return;
      }

      const parsed = safeJsonParse(text);
      if (!parsed.ok) {
        setStatus(
          `Error: Response was not valid JSON. (First 200 chars): ${text.slice(0, 200)}`
        );
        return;
      }

      const data = parsed.data;

      if (!res.ok || data?.error) {
        const msg = data?.error?.message || `HTTP ${res.status}`;
        setStatus(`Error: ${msg}`);
        return;
      }

      setAnswer(data?.answer || "");
      setSources(Array.isArray(data?.sources) ? data.sources : []);
      setStatus("Done.");
    } catch (e) {
      setStatus(`Network error: ${e?.message || String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={card}>
      <h2 style={{ marginTop: 0, marginBottom: 6 }}>Runbooks</h2>
      <div style={{ color: "#4b5563", marginBottom: 12 }}>
        Predefined questions (cost-controlled). Powered by RAG/LLM.
      </div>

      <div style={row}>
        <div>
          <div style={label}>Pick a question</div>
          <select value={qid} onChange={(e) => setQid(e.target.value)} style={selectStyle}>
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
          <button
            onClick={onAsk}
            style={{ ...btn, ...(loading ? btnDisabled : {}) }}
            disabled={loading}
          >
            {loading ? "Asking…" : "Ask"}
          </button>
        </div>
      </div>

      {status ? (
        <div
          style={{
            marginTop: 10,
            color: status.startsWith("Error") ? "#b91c1c" : "#374151",
          }}
        >
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
                    {s.file || s.s3_key || "source"}
                    {s.chunk !== undefined ? ` (chunk ${s.chunk})` : ""}
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