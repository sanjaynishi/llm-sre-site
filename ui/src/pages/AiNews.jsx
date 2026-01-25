import React, { useEffect, useMemo, useState } from "react";
import { apiGet } from "../api/client";

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
  lineHeight: 1.4,
};

const gridStyle = {
  display: "grid",
  gap: 12,
  marginTop: 16,
};

const cardStyle = {
  background: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: 14,
  padding: 14,
  boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
};

const rowStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 10,
  marginTop: 8,
  color: "#6b7280",
  fontSize: 13,
};

const chipStyle = {
  display: "inline-flex",
  alignItems: "center",
  padding: "2px 10px",
  borderRadius: 999,
  background: "#f3f4f6",
  border: "1px solid #e5e7eb",
  color: "#374151",
  fontSize: 12,
  fontWeight: 600,
  whiteSpace: "nowrap",
};

const linkStyle = {
  color: "#111827",
  fontWeight: 700,
  textDecoration: "none",
};

const readMoreStyle = {
  color: "#111827",
  fontWeight: 700,
  textDecoration: "none",
  borderBottom: "1px solid #e5e7eb",
  paddingBottom: 1,
};

const muted = { color: "#6b7280" };

function formatDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export default function AiNews() {
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [data, setData] = useState(null);

  const items = useMemo(() => data?.items || [], [data]);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setErr("");
      try {
        const res = await apiGet("/news/latest"); // backend should serve /api/news/latest or proxy accordingly
        if (!alive) return;
        setData(res);
      } catch (e) {
        if (!alive) return;
        setErr(e?.message || "Failed to load AI news.");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div style={pageStyle}>
      <h1 style={headerStyle}>AI News</h1>
      <div style={subStyle}>
        Curated AI updates focused on progress, responsibility, and real-world impact.
        <div style={{ marginTop: 6, ...muted }}>
          {data?.updatedAt ? (
            <>Last updated: <b>{formatDate(data.updatedAt)}</b></>
          ) : (
            <>Updates are cached to keep things calm and low-cost.</>
          )}
        </div>
      </div>

      {loading && (
        <div style={{ marginTop: 14, ...muted }}>Loading curated news…</div>
      )}

      {err && (
        <div style={{ marginTop: 14, color: "#b91c1c" }}>{err}</div>
      )}

      {!loading && !err && items.length === 0 && (
        <div style={{ marginTop: 14, ...muted }}>
          No items yet. (If this is your first run, the backend feed cache may be warming up.)
        </div>
      )}

      <div style={gridStyle}>
        {items.map((it) => (
          <div key={it.id || it.url} style={cardStyle}>
            <a
              href={it.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ ...linkStyle, fontSize: 16, lineHeight: 1.35 }}
              title="Open in a new tab"
            >
              {it.title}
            </a>

            {it.summary && (
              <div style={{ marginTop: 8, color: "#374151", lineHeight: 1.45 }}>
                {it.summary}
              </div>
            )}

            <div style={rowStyle}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                {it.source && <span style={chipStyle}>{it.source}</span>}
                {it.tag && <span style={chipStyle}>{it.tag}</span>}
                {it.publishedAt && <span style={muted}>{formatDate(it.publishedAt)}</span>}
              </div>

              <a
                href={it.url}
                target="_blank"
                rel="noopener noreferrer"
                style={readMoreStyle}
              >
                Read more →
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}