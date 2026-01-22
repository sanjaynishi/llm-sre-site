import React from "react";
import { NavLink } from "react-router-dom";

const navWrap = {
  display: "flex",
  gap: 10,
  flexWrap: "wrap",
  alignItems: "center",
};

const baseTab = {
  padding: "10px 14px",
  borderRadius: 14,
  border: "1px solid #e5e7eb",
  background: "linear-gradient(180deg, #ffffff 0%, #f3f4f6 100%)",
  color: "#111827",
  fontWeight: 900,
  cursor: "pointer",
  boxShadow: "0 6px 14px rgba(17, 24, 39, 0.06)",
  textDecoration: "none",
  display: "inline-flex",
  alignItems: "center",
};

const activeTab = {
  border: "1px solid #1d4ed8",
  background: "linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%)",
  color: "#ffffff",
  boxShadow: "0 10px 22px rgba(37, 99, 235, 0.22)",
};

const tabClass = ({ isActive }) => ({
  ...baseTab,
  ...(isActive ? activeTab : {}),
});

export default function NavTabs({ items }) {
  // items example:
  // [{ label: "Runbook", to: "/runbook" }, { label: "RAG", to: "/rag" }, { label: "Agentic AI", to: "/agents" }]
  return (
    <div style={navWrap}>
      {items.map((it) => (
        <NavLink key={it.to} to={it.to} style={tabClass}>
          {it.label}
        </NavLink>
      ))}
    </div>
  );
}