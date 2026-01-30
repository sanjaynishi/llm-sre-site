import React, { useEffect, useMemo, useState } from "react";

function formatLocalTimestamp(d = new Date()) {
  const dateStr = d
    .toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "2-digit",
      year: "numeric",
    })
    .replace(",", "");

  const timeStr = d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });

  return `🕒 ${dateStr} · ${timeStr} (Local)`;
}

function getDeployEnv() {
  try {
    const host = window?.location?.hostname || "";
    if (host.startsWith("dev.")) return "dev";
    return "production";
  } catch {
    return "";
  }
}

function useIsNarrow(breakpointPx = 720) {
  const [isNarrow, setIsNarrow] = useState(() => {
    try {
      return window.innerWidth < breakpointPx;
    } catch {
      return false;
    }
  });

  useEffect(() => {
    function onResize() {
      setIsNarrow(window.innerWidth < breakpointPx);
    }
    window.addEventListener("resize", onResize, { passive: true });
    return () => window.removeEventListener("resize", onResize);
  }, [breakpointPx]);

  return isNarrow;
}

export default function AppHeader({
  title = "AIML LLM SRE / DevOps",
  subtitle = "Runbooks (predefined), RAG Chat (ask anything), Agentic AI utilities, and curated AI News.",
}) {
  const [now, setNow] = useState(() => new Date());
  const isNarrow = useIsNarrow(720);

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
    <header className="app-header" style={styles.header(isNarrow)}>
      <div style={styles.left}>
        <div style={styles.titleRow(isNarrow)}>
          <h1 style={styles.title(isNarrow)}>{title}</h1>

          {env ? (
            <span
              style={{ ...styles.badgeBase, ...envStyle }}
              title="Deployed environment"
            >
              {env}
            </span>
          ) : null}
        </div>

        <p style={styles.subtitle}>{subtitle}</p>
      </div>

      <div style={styles.right(isNarrow)} aria-label="Local time">
        <span style={styles.time(isNarrow)}>{ts}</span>
      </div>
    </header>
  );
}

const styles = {
  // ✅ IMPORTANT: No “card” styling here.
  // MainLayout provides the frame so widths match perfectly.
  header: (isNarrow) => ({
    display: "flex",
    alignItems: isNarrow ? "flex-start" : "center",
    justifyContent: "space-between",
    gap: 12,
    flexWrap: "wrap",

    width: "100%",
    boxSizing: "border-box",

    padding: 0,
    margin: 0,
    background: "transparent",
    border: "none",
    boxShadow: "none",
  }),

  left: {
    minWidth: 0,
    flex: 1,
  },

  titleRow: (isNarrow) => ({
    display: "flex",
    alignItems: "baseline",
    gap: 10,
    minWidth: 0,
    flexWrap: "wrap",
  }),

  // ✅ Let title wrap on iPhone (no nowrap)
  title: (isNarrow) => ({
    margin: 0,
    fontSize: isNarrow ? 20 : 26,
    fontWeight: 900,
    letterSpacing: "-0.02em",
    color: "#111827",
    lineHeight: 1.15,
    whiteSpace: "normal",
    wordBreak: "break-word",
  }),

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
    whiteSpace: "nowrap",
    flex: "0 0 auto",
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
    maxWidth: "100%",
  },

  // ✅ On narrow screens, time goes under (full width)
  right: (isNarrow) => ({
    flexShrink: 0,
    width: isNarrow ? "100%" : "auto",
    textAlign: isNarrow ? "left" : "right",
  }),

  // ✅ Allow time pill to wrap on small screens
  time: (isNarrow) => ({
    display: "inline-block",
    fontSize: 13,
    fontWeight: 800,
    color: "#111827",
    background: "#f3f4f6",
    border: "1px solid #e5e7eb",
    borderRadius: 999,
    padding: "6px 10px",
    whiteSpace: isNarrow ? "normal" : "nowrap",
    wordBreak: "break-word",
    maxWidth: "100%",
  }),
};