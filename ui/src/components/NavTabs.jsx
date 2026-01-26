// ui/src/components/NavTabs.jsx
import React from "react";

const rowStyle = {
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
  fontWeight: 800,
  cursor: "pointer",
};

const tabActive = {
  border: "2px solid #1d4ed8",
  background: "linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%)",
  color: "#ffffff",
};

export default function NavTabs({ tabs = [], active, onChange }) {
  return (
    <div style={rowStyle}>
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange?.(t.key)}
          style={{ ...tabBase, ...(active === t.key ? tabActive : {}) }}
          aria-pressed={active === t.key}
          type="button"
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}