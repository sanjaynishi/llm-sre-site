// ui/src/components/AskRunbooks.jsx
import React, { useMemo, useState } from "react";

/**
 * POST JSON with a single "soft retry" when the first response is likely
 * a CloudFront/Origin HTML error page (504/502/etc) or otherwise non-JSON.
 *
 * ✅ UX fix:
 * - If first attempt looks like HTML / non-JSON warmup, do NOT show scary error.
 * - Show "Warming up… retrying once" and only error if retry also fails.
 */
async function postJsonWithSoftRetry(
  url,
  body,
  {
    retryDelayMs = 900,
    retryOnStatuses = [502, 503, 504],
    retryOnNonJson = true,
    onWarmup, // optional callback for UI status updates
  } = {}
) {
  async function attempt() {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body ?? {}),
    });

    const text = await res.text();

    // Best-effort JSON parse
    let json = null;
    try {
      json = JSON.parse(text);
    } catch {
      json = null;
    }

    const contentType = (res.headers.get("content-type") || "").toLowerCase();
    const looksLikeHtml =
      contentType.includes("text/html") ||
      /^\s*<!doctype html/i.test(text) ||
      /^\s*<html[\s>]/i.test(text);

    const isNonJson = !json && (retryOnNonJson || looksLikeHtml);
    const shouldRetry =
      (!res.ok && retryOnStatuses.includes(res.status)) || isNonJson;

    return {
      res,
      json,
      rawText: text,
      meta: {
        contentType,
        looksLikeHtml,
        isNonJson,
        shouldRetry,
      },
    };
  }

  // Attempt #1
  const first = await attempt();
  if (first.res.ok && first.json) return { ...first, meta: { ...first.meta, retried: false } };

  // Soft retry once if it looks like warmup / HTML / non-JSON / 5xx
  if (first.meta.shouldRetry) {
    if (typeof onWarmup === "function") {
      onWarmup(first); // let UI update status before waiting
    }

    await new Promise((r) => setTimeout(r, retryDelayMs));

    const second = await attempt();
    if (second.res.ok && second.json) {
      return { ...second, meta: { ...second.meta, retried: true, firstAttempt: first.meta } };
    }

    return { ...second, meta: { ...second.meta, retried: true, firstAttempt: first.meta } };
  }

  // No retry performed
  return { ...first, meta: { ...first.meta, retried: false } };
}

export default function AskRunbooks() {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState([]);
  const [raw, setRaw] = useState(null);
  const [showRaw, setShowRaw] = useState(false);

  const canAsk = useMemo(
    () => question.trim().length > 0 && !loading,
    [question, loading]
  );

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
    setShowRaw(false);

    try {
      const payload = { question: q, top_k: Number(topK) || 5 };

      const { res, json, rawText, meta } = await postJsonWithSoftRetry(
        "/api/runbooks/ask",
        payload,
        {
          retryDelayMs: 900,
          onWarmup: (firstAttempt) => {
            // ✅ key UX change: don't show scary HTML error on first attempt
            const code = firstAttempt?.res?.status;
            setStatus(`Warming up backend… Retrying${code ? ` (HTTP ${code})` : ""}`);
          },
        }
      );

      // If still not OK or not JSON after retry, show a friendly error
      if (!res.ok || !json) {
        const contentType = meta?.contentType || "";
        const looksHtml = meta?.looksLikeHtml || contentType.includes("text/html");

        const msg =
          (json?.error?.message || json?.message) ??
          (looksHtml
            ? `Backend still warming up: expected JSON but got HTML. Please try again. (HTTP ${res.status})`
            : `Request failed (HTTP ${res.status}).`);

        setStatus(msg);

        // Store raw info for debugging
        setRaw(
          json || {
            error: {
              code: "NON_JSON_RESPONSE",
              message: msg,
              httpStatus: res.status,
              contentType: meta?.contentType || null,
              retried: !!meta?.retried,
              rawPreview: (rawText || "").slice(0, 800),
              firstAttempt: meta?.firstAttempt || null,
            },
          }
        );
        return;
      }

      // API supports either success or {error:{...}}
      if (json?.error) {
        setStatus(json.error.message || "RAG failed.");
        setRaw(json);
        return;
      }

      setStatus(meta?.retried ? "Done (after warmup retry)." : "Done.");
      setAnswer(json?.answer || "");
      setSources(Array.isArray(json?.sources) ? json.sources : []);
      setRaw(json);
    } catch (e) {
      const msg = String(e?.message || e);
      setStatus(msg);
      setRaw({ error: { code: "CLIENT_EXCEPTION", message: msg } });
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

      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          marginTop: 12,
        }}
      >
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
          type="button"
        >
          {loading ? "Asking…" : "Ask"}
        </button>

        <span style={{ marginLeft: 6, opacity: 0.85 }}>{status}</span>
      </div>

      {(answer || raw) && (
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
          {answer ? (
            <>
              <h3 style={{ marginTop: 0 }}>Answer</h3>
              <div>{answer}</div>
            </>
          ) : (
            <h3 style={{ marginTop: 0 }}>Response</h3>
          )}

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
                    {s.s3_key ? (
                      <span style={{ opacity: 0.7 }}> — {s.s3_key}</span>
                    ) : null}
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
              type="button"
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