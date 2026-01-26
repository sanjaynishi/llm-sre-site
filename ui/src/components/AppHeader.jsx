import React, { useEffect, useMemo, useState } from "react";

function formatLocalTimestamp(d = new Date()) {
  // Example: "Mon Jan 26, 2026"
  const dateStr = d
    .toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "2-digit",
      year: "numeric",
    })
    .replace(",", "");

  // Example: "8:23:04 PM"
  const timeStr = d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });

  return `🕒 ${dateStr} · ${timeStr} (Local)`;
}

function getDeployEnv() {
  // Determines where you deployed (dev vs prod) based on hostname
  // dev.aimlsre.com -> dev
  // aimlsre.com / www.aimlsre.com -> production
  try {
    const host = window?.location?.hostname || "";
    if (host.startsWith("dev.")) return "dev";
    return "production";
  } catch {
    return ""; // SSR / non-browser safety
  }
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

  const env = useMemo(() => getDeployEnv(), []);
  const ts = formatLocalTimestamp(now);

  const envStyle =
    env === "dev"
      ? styles.badgeDev
      : env === "production"
      ? styles.badgeProd
      : styles.badgeNeutral;

  return (
    <header className="app-header" style={styles.header}>
      <div style={styles.left}>
        <div style={styles.titleRow}>
          <h1 style={styles.title}>{title}</h1>

          {env ? (
            <span style={{ ...styles.badgeBase, ...envStyle }} title="Deployed environment">
              {env}
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
  badgeBase: {
    display: "inline-flex",
    alignItems: "center",
    padding: "4px 10px",
    borderRadius: 999,
    fontSize: 12,
    fontWeight: 800,
    border: "1px solid #e5e7eb",
    textTransform: "lowercase",
    lineHeight: 1,
    userSelect: "none",
  },
  badgeDev: {
    background: "#eff6ff",
    color: "#1d4ed8",
    border: "1px solid #bfdbfe",
  },
  badgeProd: {
    background: "#ecfdf5",
    color: "#047857",
    border: "1px solid #a7f3d0",
  },
  badgeNeutral: {
    background: "#f9fafb",
    color: "#374151",
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