import React, { useMemo, useState } from "react";

export default function AskRunbooks() {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState([]);
  const [raw, setRaw] = useState(null);
  const [showRaw, setShowRaw] = useState(false);

  const canAsk = useMemo(() => question.trim().length > 0 && !loading, [question, loading]);

  async function onAsk() {
    const q = question.trim();
    if (!q) {
      setStatus("Please type a question.");
      return;
    }

    setLoading(true);
    setStatus("Asking…");
    setAnswer("");
    setSources([]);
    setRaw(null);

    try {
      const res = await fetch("/api/runbooks/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, top_k: Number(topK) || 5 }),
      });

      const data = await res.json().catch(() => null);

      if (!res.ok) {
        const msg =
          data?.error?.message ||
          data?.message ||
          `Request failed (${res.status})`;
        setStatus(msg);
        setRaw(data);
        return;
      }

      // API supports either success or {error:{...}}
      if (data?.error) {
        setStatus(data.error.message || "RAG failed.");
        setRaw(data);
        return;
      }

      setStatus("Done.");
      setAnswer(data?.answer || "");
      setSources(Array.isArray(data?.sources) ? data.sources : []);
      setRaw(data);
    } catch (e) {
      setStatus(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      onAsk();
    }
  }

  return (
    <section style={{ maxWidth: 900, margin: "2rem auto", padding: "1rem" }}>
      <h2 style={{ marginBottom: "0.5rem" }}>Ask Runbooks (RAG)</h2>
      <div style={{ marginBottom: "0.75rem", opacity: 0.8 }}>
        Tip: press <b>Ctrl/⌘ + Enter</b> to ask.
      </div>

      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={onKeyDown}
        rows={5}
        placeholder="Ask something like: How do I invalidate CloudFront cache after deploying the UI?"
        style={{
          width: "100%",
          padding: "0.75rem",
          borderRadius: 10,
          border: "1px solid #ddd",
          fontSize: 15,
          lineHeight: 1.4,
        }}
      />

      <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 12 }}>
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          Top K:
          <input
            type="number"
            min={1}
            max={10}
            value={topK}
            onChange={(e) => setTopK(e.target.value)}
            style={{ width: 70, padding: "0.3rem 0.4rem" }}
          />
        </label>

        <button
          onClick={onAsk}
          disabled={!canAsk}
          style={{
            padding: "0.55rem 0.9rem",
            borderRadius: 10,
            border: "1px solid #222",
            background: loading ? "#ddd" : "#111",
            color: loading ? "#333" : "#fff",
            cursor: canAsk ? "pointer" : "not-allowed",
          }}
        >
          {loading ? "Asking…" : "Ask"}
        </button>

        <span style={{ marginLeft: 6, opacity: 0.85 }}>{status}</span>
      </div>

      {answer && (
        <div
          style={{
            marginTop: 18,
            padding: 16,
            borderRadius: 12,
            border: "1px solid #eee",
            background: "#fafafa",
            whiteSpace: "pre-wrap",
          }}
        >
          <h3 style={{ marginTop: 0 }}>Answer</h3>
          <div>{answer}</div>

          {sources?.length > 0 && (
            <>
              <h3 style={{ marginTop: 18 }}>Sources</h3>
              <ul style={{ marginTop: 8 }}>
                {sources.map((s, i) => (
                  <li key={i} style={{ marginBottom: 6 }}>
                    <code>{s.file || "runbook"}</code>
                    {typeof s.chunk !== "undefined" && s.chunk !== null ? (
                      <span style={{ opacity: 0.8 }}> (chunk {s.chunk})</span>
                    ) : null}
                    {s.s3_key ? <span style={{ opacity: 0.7 }}> — {s.s3_key}</span> : null}
                  </li>
                ))}
              </ul>
            </>
          )}

          <div style={{ marginTop: 14 }}>
            <button
              onClick={() => setShowRaw((v) => !v)}
              style={{
                padding: "0.4rem 0.7rem",
                borderRadius: 10,
                border: "1px solid #aaa",
                background: "#fff",
                cursor: "pointer",
              }}
            >
              {showRaw ? "Hide raw JSON" : "Show raw JSON"}
            </button>

            {showRaw && raw && (
              <pre style={{ marginTop: 10, whiteSpace: "pre-wrap" }}>
                {JSON.stringify(raw, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}
    </section>
  );
}