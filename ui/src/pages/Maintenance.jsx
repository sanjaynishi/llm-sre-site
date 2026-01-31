import React from "react";

export default function Maintenance() {
  const page = {
    minHeight: "70vh",
    display: "grid",
    placeItems: "center",
    padding: 18,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif',
    color: "#0f172a",
  };

  const card = {
    maxWidth: 720,
    width: "100%",
    background: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: 18,
    padding: 18,
    boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",
  };

  const pill = {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    padding: "6px 10px",
    borderRadius: 999,
    border: "1px solid #e2e8f0",
    background: "#f8fafc",
    fontSize: 12,
    fontWeight: 700,
  };

  return (
    <div style={page}>
      <div style={card}>
        <div style={pill}>🛠️ Maintenance Mode</div>
        <h1 style={{ margin: "12px 0 6px", fontSize: 26, fontWeight: 900 }}>
          We’re deploying an upgrade
        </h1>
        <p style={{ margin: 0, color: "#475569", lineHeight: 1.5 }}>
          The AIML SRE site is temporarily in maintenance while we promote changes to
          production and refresh the RAG runbook index.
        </p>

        <div style={{ marginTop: 14, color: "#0f172a", fontSize: 13 }}>
          <div>✅ UI deployment: in progress</div>
          <div>⏳ Runbook vector store (RAG): pending upload + indexing</div>
          <div style={{ marginTop: 10, color: "#475569" }}>
            Please check back soon.
          </div>
        </div>
      </div>
    </div>
  );
}