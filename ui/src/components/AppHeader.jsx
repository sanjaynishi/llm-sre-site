import React, { useEffect, useMemo, useState } from "react";

function formatLocalTimestamp(d = new Date()) {
  // Date like: "Mon Jan 26, 2026"
  const dateStr = d
    .toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "2-digit",
      year: "numeric",
    })
    .replace(",", ""); // "Mon, Jan..." -> "Mon Jan..."

  // Time like: "8:23:04 PM"
  const timeStr = d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });

  return `🕒 ${dateStr} · ${timeStr} (Local)`;
}

export default function AppHeader({
  title = "AIML LLM SRE / DevOps",
  subtitle = "Runbooks (predefined), RAG Chat (ask anything), Agentic AI utilities, and curated AI News.",
}) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const mode = useMemo(() => {
    // Vite: import.meta.env.MODE is usually "development" / "production"
    try {
      return (import.meta?.env?.MODE || "").toString();
    } catch {
      return "";
    }
  }, []);

  const ts = formatLocalTimestamp(now);

  return (
    <header className="app-header" style={styles.header}>
      <div style={styles.left}>
        <div style={styles.titleRow}>
          <h1 style={styles.title}>{title}</h1>
          {mode ? (
            <span style={styles.badge} title="Build mode">
              {mode}
            </span>
          ) : null}
        </div>
        <p style={styles.subtitle}>{subtitle}</p>
      </div>

      <div style={styles.right} aria-label="Local time">
        <span style={styles.time}>{ts}</span>
      </div>
    </header>
  );
}

const styles = {
  header: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 16,
    padding: "14px 16px",
    background: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: 18,
    boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",
  },
  left: {
    minWidth: 0,
    flex: 1,
  },
  titleRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    minWidth: 0,
  },
  title: {
    margin: 0,
    fontSize: 26,
    fontWeight: 900,
    letterSpacing: "-0.02em",
    color: "#111827",
    lineHeight: 1.1,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  badge: {
    display: "inline-flex",
    alignItems: "center",
    padding: "4px 10px",
    borderRadius: 999,
    fontSize: 12,
    fontWeight: 800,
    border: "1px solid #e5e7eb",
    background: "#f9fafb",
    color: "#374151",
    textTransform: "lowercase",
  },
  subtitle: {
    margin: "6px 0 0 0",
    color: "#4b5563",
    lineHeight: 1.35,
    fontSize: 14,
    maxWidth: 860,
  },
  right: {
    flexShrink: 0,
    textAlign: "right",
    paddingTop: 2,
  },
  time: {
    display: "inline-block",
    fontSize: 13,
    fontWeight: 800,
    color: "#111827",
    background: "#f3f4f6",
    border: "1px solid #e5e7eb",
    borderRadius: 999,
    padding: "6px 10px",
    whiteSpace: "nowrap",
  },
};