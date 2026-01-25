import React, { useMemo, useState } from "react";
import Runbook from "./pages/Runbooks";
import Rag from "./pages/Rag";
import Agents from "./pages/Agents";
import AiNews from "./pages/AiNews"; // ✅ ADD

const appWrap = { minHeight: "100vh", background: "#f3f4f6" };

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
  justifyContent: "center",
  alignItems: "center",
  textAlign: "center",
  marginTop: 6,
};

const title = {
  margin: 0,
  fontSize: 30,
  fontWeight: 900,
  letterSpacing: "-0.02em",
};

const subtitle = {
  marginTop: 8,
  marginBottom: 0,
  color: "#4b5563",
  lineHeight: 1.35,
  maxWidth: 820,
};

const tabsRow = {
  marginTop: 16,
  display: "flex",
  justifyContent: "center",
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
  transition: "transform 120ms ease, box-shadow 120ms ease, border 120ms ease",
};

const tabActive = {
  border: "2px solid #1d4ed8",
  background: "linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%)",
  color: "#ffffff",
  boxShadow: "0 14px 28px rgba(37, 99, 235, 0.26)",
  transform: "translateY(-1px)",
};

const contentCard = {
  marginTop: 16,
  background: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: 18,
  padding: 14,
  boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",
};

export default function App() {
  const tabs = useMemo(
    () => [
      { key: "runbook", label: "Runbooks" },   // predefined dropdown
      { key: "rag", label: "RAG Chat" },       // ✅ renamed already
      { key: "agents", label: "Agentic AI" },
      { key: "aiNews", label: "AI News" },     // ✅ ADD
    ],
    []
  );

  const [active, setActive] = useState("runbook");

  return (
    <div style={appWrap}>
      <div style={shell}>
        <div style={titleRow}>
          <div>
            <h1 style={title}>AIML LLM SRE / DevOps</h1>
            <p style={subtitle}>
              Runbooks (predefined), RAG Chat (ask anything), Agentic AI utilities, and curated AI News.
            </p>
          </div>
        </div>

        <div style={tabsRow}>
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setActive(t.key)}
              style={{ ...tabBase, ...(active === t.key ? tabActive : {}) }}
              aria-pressed={active === t.key}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div style={contentCard}>
          {active === "runbook" && <Runbook />}
          {active === "rag" && <Rag />}
          {active === "agents" && <Agents />}
          {active === "aiNews" && <AiNews />} {/* ✅ ADD */}
        </div>
      </div>
    </div>
  );
}