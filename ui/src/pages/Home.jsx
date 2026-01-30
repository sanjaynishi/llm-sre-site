// ui/src/pages/Home.jsx
import React from "react";

const page = {
  padding: 18,
  maxWidth: 1100,
  margin: "0 auto",
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif',
  color: "#0f172a",
};

const card = {
  background: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: 18,
  padding: 16,
  boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",
};

const muted = { color: "#475569" };

const pill = {
  display: "inline-flex",
  alignItems: "center",
  gap: 8,
  padding: "6px 10px",
  borderRadius: 999,
  border: "1px solid #e2e8f0",
  background: "#f8fafc",
  fontSize: 12,
  fontWeight: 800,
  color: "#0f172a",
};

const btn = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "10px 14px",
  borderRadius: 12,
  border: "1px solid #e2e8f0",
  background: "#0f172a",
  color: "#fff",
  fontWeight: 900,
  textDecoration: "none",
  cursor: "pointer",
};

const btnGhost = {
  ...btn,
  background: "#ffffff",
  color: "#0f172a",
};

function SmallCard({ title, desc }) {
  return (
    <div style={card}>
      <div style={{ fontWeight: 950 }}>{title}</div>
      <div style={{ marginTop: 6, fontSize: 13, lineHeight: 1.4, ...muted }}>
        {desc}
      </div>
    </div>
  );
}

export default function Home({ onNavigate }) {
  const go = (key) => onNavigate?.(key);

  return (
    <div style={page}>
      {/* HERO */}
      <div style={{ ...card, padding: 20 }}>
        <div style={pill}>🤖 AI + SRE • funny, practical, professional</div>

        <h1
          style={{
            margin: "10px 0 0",
            fontSize: 34,
            fontWeight: 950,
            letterSpacing: "-0.03em",
          }}
        >
          {window.location.hostname}
        </h1>

        <div style={{ marginTop: 8, fontSize: 16, ...muted, lineHeight: 1.5 }}>
          My personal lab for running GenAI platforms like real production systems —
          with automation-first thinking, safe patterns, and reusable runbooks.
        </div>

        {/* ✅ Fun but professional line (new) */}
        <div style={{ marginTop: 6, fontSize: 14, ...muted }}>
          Built with React (Vite) and Python, using AI as a co-pilot — because even engineers
          appreciate a smart second brain.
        </div>

        <div
          style={{
            marginTop: 14,
            display: "flex",
            gap: 10,
            flexWrap: "wrap",
          }}
        >
          <button style={btn} onClick={() => go("runbooks")}>
            Open Runbooks
          </button>
          <button style={btnGhost} onClick={() => go("rag")}>
            RAG Chat
          </button>
          <button style={btnGhost} onClick={() => go("mcp")}>
            MCP Workflow
          </button>
        </div>
      </div>

      {/* WHAT IS SRE / AI-ML / LLMs */}
      <div style={{ marginTop: 16, ...card }}>
        <div style={{ fontSize: 18, fontWeight: 950 }}>What this site is about</div>

        <div style={{ marginTop: 10, fontSize: 14, lineHeight: 1.55, ...muted }}>
          <strong>SRE (Site Reliability Engineering)</strong> is the art of keeping systems
          boring — in a good way. We reduce surprises with guardrails, automation, and
          calm dashboards so nobody has to “hero” at 2 AM.
        </div>

        <div style={{ marginTop: 10, fontSize: 14, lineHeight: 1.55, ...muted }}>
          <strong>AI/ML</strong> adds a twist: the system learns from data, behavior changes,
          and results can be probabilistic. So production discipline matters more, not less.
        </div>

        <div style={{ marginTop: 10, fontSize: 14, lineHeight: 1.55, ...muted }}>
          <strong>LLMs (Large Language Models)</strong> are powerful reasoning engines —
          not databases, not truth machines, and not magic. Think “brilliant intern”:
          useful, fast, occasionally confident… and still needs supervision.
        </div>

        <div style={{ marginTop: 12, fontSize: 14, lineHeight: 1.55, ...muted }}>
          This site is where I combine all three into practical demos you can actually use:
          patterns, runbooks, and automation for real GenAI operations.
        </div>
      </div>

      {/* SIMPLE VALUE */}
      <div
        style={{
          marginTop: 16,
          display: "grid",
          gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
          gap: 12,
        }}
      >
        <SmallCard
          title="⚙️ Automation"
          desc="Repeatable, zero-touch style workflows: reduce manual steps, speed up triage, and standardize operations."
        />
        <SmallCard
          title="📘 Runbook thinking"
          desc="Clear playbooks you can hand to any engineer: what to check, what to collect, and what to do next."
        />
        <SmallCard
          title="🛡️ Safe patterns"
          desc="Secure-by-default ideas for GenAI workloads: access boundaries, data handling, and operational guardrails."
        />
      </div>

      {/* QUICK LINKS */}
      <div style={{ marginTop: 16, ...card }}>
        <div style={{ fontSize: 16, fontWeight: 950 }}>Jump to</div>
        <div style={{ marginTop: 6, fontSize: 13, ...muted }}>
          Pick a section. Each one is a working area on the site.
        </div>

        <div
          style={{
            marginTop: 12,
            display: "flex",
            gap: 10,
            flexWrap: "wrap",
          }}
        >
          <button style={btnGhost} onClick={() => go("runbooks")}>
            Runbooks
          </button>
          <button style={btnGhost} onClick={() => go("rag")}>
            RAG Chat
          </button>
          <button style={btnGhost} onClick={() => go("agents")}>
            Agentic AI
          </button>
          <button style={btnGhost} onClick={() => go("aiNews")}>
            AI News
          </button>
          <button style={btnGhost} onClick={() => go("mcp")}>
            MCP Workflow
          </button>
        </div>
      </div>

      <div style={{ marginTop: 14, textAlign: "center", fontSize: 12, ...muted }}>
        Less fluff. More working demos.
      </div>
    </div>
  );
}