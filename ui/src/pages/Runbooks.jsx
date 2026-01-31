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

const btnSecondary = {
  padding: "10px 14px",
  borderRadius: 12,
  border: "1px solid #e5e7eb",
  background: "#fff",
  color: "#111827",
  fontWeight: 900,
  cursor: "pointer",
};

const btnDanger = {
  padding: "10px 14px",
  borderRadius: 12,
  border: "1px solid #fecaca",
  background: "#fff",
  color: "#991b1b",
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

// ✅ pretty retry panel styles
const retryCard = {
  marginTop: 12,
  borderRadius: 14,
  border: "1px solid #fee2e2",
  background: "#fff7f7",
  padding: 12,
  display: "flex",
  gap: 12,
  alignItems: "flex-start",
};

const retryIcon = {
  width: 34,
  height: 34,
  borderRadius: 12,
  background: "#fee2e2",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: "#991b1b",
  fontWeight: 1000,
  flex: "0 0 auto",
};

const retryTitle = { fontWeight: 950, color: "#991b1b", marginBottom: 4 };
const retryText = { color: "#7f1d1d", lineHeight: 1.35, fontSize: 13 };

const retryActions = {
  marginTop: 10,
  display: "flex",
  gap: 10,
  flexWrap: "wrap",
};

function safeJsonParse(text) {
  try {
    return { ok: true, data: JSON.parse(text) };
  } catch (e) {
    return { ok: false, error: e };
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function firstChars(str, n = 200) {
  const s = String(str || "");
  return s.length > n ? s.slice(0, n) + "…" : s;
}

export default function Runbooks() {
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

      // --- Quantum ---
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

  // ✅ retry system
  const [lastPayload, setLastPayload] = useState(null);
  const [retryCount, setRetryCount] = useState(0);

  // ✅ pretty retry message state (only shown on failures)
  const [retryUi, setRetryUi] = useState({
    show: false,
    title: "",
    detail: "",
    hint: "",
  });

  const selected = QUESTIONS.find((q) => q.id === qid) || QUESTIONS[0];

  function hideRetryUi() {
    setRetryUi({ show: false, title: "", detail: "", hint: "" });
  }

  function showRetryUi({ title, detail, hint }) {
    setRetryUi({
      show: true,
      title: title || "Temporary issue reaching the API",
      detail: detail || "",
      hint:
        hint ||
        "Try Retry. If it keeps happening, it’s usually CloudFront routing to S3 (HTML) instead of the API, or a Lambda-side error.",
    });
  }

  async function postJsonWithRetry(url, payload, opts = {}) {
    const attempts = Math.min(6, Math.max(1, Number(opts.attempts || 4)));
    const baseDelayMs = Math.min(4000, Math.max(150, Number(opts.baseDelayMs || 450)));
    const timeoutMs = Math.min(60000, Math.max(5000, Number(opts.timeoutMs || 25000)));

    let lastErr = null;

    for (let attempt = 1; attempt <= attempts; attempt++) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);

      try {
        setRetryCount(attempt - 1);

        if (attempt > 1) {
          setStatus(`Retrying… (attempt ${attempt}/${attempts})`);
        }

        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
          body: JSON.stringify(payload),
          signal: controller.signal,
        });

        const contentType = res.headers.get("content-type") || "";
        const text = await res.text();

        if (!contentType.includes("application/json")) {
          const msg =
            `Expected JSON but got "${contentType || "unknown"}". ` +
            `Preview: ${firstChars(text, 200)}`;
          const err = new Error(msg);
          err._retryable = true;
          err._status = res.status;
          throw err;
        }

        const parsed = safeJsonParse(text);
        if (!parsed.ok) {
          const err = new Error(`Response not valid JSON. Preview: ${firstChars(text, 200)}`);
          err._retryable = true;
          err._status = res.status;
          throw err;
        }

        const data = parsed.data;

        if (!res.ok || data?.error) {
          const apiMsg = data?.error?.message || `HTTP ${res.status}`;
          const err = new Error(apiMsg);

          const retryableStatus = [408, 429, 500, 502, 503, 504];
          err._retryable = retryableStatus.includes(res.status);
          err._status = res.status;
          err._data = data;
          throw err;
        }

        clearTimeout(timer);
        return { ok: true, data, res };
      } catch (e) {
        clearTimeout(timer);
        lastErr = e;

        const aborted = e?.name === "AbortError";
        const retryable = aborted || e?._retryable === true;

        if (attempt < attempts && retryable) {
          const jitter = Math.floor(Math.random() * 180);
          const delay = Math.min(6000, baseDelayMs * Math.pow(2, attempt - 1)) + jitter;
          await sleep(delay);
          continue;
        }

        break;
      }
    }

    return { ok: false, error: lastErr };
  }

  async function runAsk(payload, modeLabel = "Asking…") {
    setLastPayload(payload);

    setLoading(true);
    setRetryCount(0);
    setStatus(modeLabel);

    setAnswer("");
    setSources([]);

    // start clean
    hideRetryUi();

    const result = await postJsonWithRetry("/api/runbooks/ask", payload, {
      attempts: 4,
      baseDelayMs: 450,
      timeoutMs: 25000,
    });

    try {
      if (!result.ok) {
        const msg = result?.error?.message || String(result?.error || "Unknown error");
        setStatus("Error");

        showRetryUi({
          title: "Couldn’t reach the Runbooks API cleanly",
          detail: msg,
          hint:
            "Retry usually works if CloudFront is warming up. If it keeps returning HTML, check CloudFront behavior for /api/*.",
        });
        return;
      }

      const data = result.data;

      // ✅ Success: hide retry UI automatically
      hideRetryUi();

      setAnswer(data?.answer || "");
      setSources(Array.isArray(data?.sources) ? data.sources : []);
      setStatus("Done.");
    } finally {
      setLoading(false);
    }
  }

  async function onAsk() {
    if (!selected?.question) {
      setStatus("Pick a question.");
      return;
    }
    const k = Math.min(10, Math.max(1, Number(topK) || 5));
    await runAsk({ question: selected.question, top_k: k }, "Asking…");
  }

  async function onRetryNow() {
    if (!lastPayload) {
      setStatus("Nothing to retry yet. Click Ask first.");
      return;
    }
    await runAsk(lastPayload, "Retrying…");
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

        <div style={{ alignSelf: "flex-end", display: "flex", gap: 10 }}>
          <button
            onClick={onAsk}
            style={{ ...btn, ...(loading ? btnDisabled : {}) }}
            disabled={loading}
            title="Ask the selected runbook question"
          >
            {loading ? "Asking…" : "Ask"}
          </button>

          <button
            onClick={onRetryNow}
            style={{ ...btnSecondary, ...(loading ? btnDisabled : {}) }}
            disabled={loading || !lastPayload}
            title="Retry the last request"
          >
            Retry
          </button>
        </div>
      </div>

      {/* Status line */}
      {status ? (
        <div style={{ marginTop: 10, color: "#374151" }}>
          {status}
          {loading ? null : retryCount > 0 ? (
            <span style={{ marginLeft: 8, color: "#6b7280" }}>
              (retries attempted: {retryCount})
            </span>
          ) : null}
        </div>
      ) : null}

      {/* ✅ Pretty retry panel (auto-hides on success) */}
      {retryUi.show ? (
        <div style={retryCard}>
          <div style={retryIcon}>!</div>
          <div style={{ flex: 1 }}>
            <div style={retryTitle}>{retryUi.title}</div>
            {retryUi.detail ? <div style={retryText}>{retryUi.detail}</div> : null}
            {retryUi.hint ? (
              <div style={{ ...retryText, marginTop: 6, color: "#6b7280" }}>{retryUi.hint}</div>
            ) : null}

            <div style={retryActions}>
              <button
                onClick={onRetryNow}
                style={{ ...btn, ...(loading ? btnDisabled : {}) }}
                disabled={loading || !lastPayload}
              >
                {loading ? "Retrying…" : "Retry now"}
              </button>

              <button onClick={hideRetryUi} style={btnDanger} disabled={loading}>
                Dismiss
              </button>
            </div>
          </div>
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