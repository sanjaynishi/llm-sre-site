import React, { useMemo, useState } from "react";
import Runbook from "./pages/Runbooks";   // adjust paths if yours differ
import Rag from "./pages/Rag";           // adjust paths if yours differ
import Agents from "./pages/Agents";     // adjust paths if yours differ

const appWrap = {
  minHeight: "100vh",
  background: "#f3f4f6",
};

const shell = {
  maxWidth: 1100,
  margin: "0 auto",
  padding: "18px 16px 30px",
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif',
  color: "#111827",
};

const titleRow = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "end",
  flexWrap: "wrap",
  gap: 10,
};

const title = { margin: 0, fontSize: 28, fontWeight: 900, letterSpacing: "-0.02em" };
const subtitle = { marginTop: 6, marginBottom: 0, color: "#4b5563", lineHeight: 1.35 };

const tabsRow = {
  marginTop: 14,
  display: "flex",
  gap: 10,
  flexWrap: "wrap",
  alignItems: "center",
};

const tabBase = {
  padding: "10px 14px",
  borderRadius: 14,
  border: "1px solid #e5e7eb",
  background: "linear-gradient(180deg, #ffffff 0%, #f3f4f6 100%)",
  color: "#111827",
  fontWeight: 900,
  cursor: "pointer",
  boxShadow: "0 6px 14px rgba(17, 24, 39, 0.06)",
};

const tabActive = {
  border: "1px solid #1d4ed8",
  background: "linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%)",
  color: "#ffffff",
  boxShadow: "0 10px 22px rgba(37, 99, 235, 0.22)",
};

const contentCard = {
  marginTop: 14,
  background: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: 18,
  padding: 14,
  boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",
};

export default function App() {
  const tabs = useMemo(
    () => [
      { key: "runbook", label: "Runbook" },
      { key: "rag", label: "RAG" },
      { key: "agents", label: "Agentic AI" },
    ],
    []
  );

  const [active, setActive] = useState("runbook");

  return (
    <div style={appWrap}>
      <div style={shell}>
        <div style={titleRow}>
          <div>
            <h1 style={title}>SRE / DevOps</h1>
            <p style={subtitle}>
              Runbooks, RAG tools, and Agentic AI utilities — all inline (no popups).
            </p>
          </div>
        </div>

        <div style={tabsRow}>
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setActive(t.key)}
              style={{ ...tabBase, ...(active === t.key ? tabActive : {}) }}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div style={contentCard}>
          {active === "runbook" && <Runbook />}
          {active === "rag" && <Rag />}
          {active === "agents" && <Agents />}
        </div>
      </div>
    </div>
  );
}