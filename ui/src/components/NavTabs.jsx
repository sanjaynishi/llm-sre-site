// ui/src/components/NavTabs.jsx
import React from "react";

/**
 * iPhone-friendly tabs:
 * - horizontal scroll (pan-x)
 * - starts from left (not centered) so you can reach all buttons
 * - still looks same (your gradients/active styles)
 */

const wrapStyle = {
  marginTop: 16,
  width: "100%",

  overflowX: "auto",
  overflowY: "hidden",
  WebkitOverflowScrolling: "touch",

  // iOS scrolling reliability
  touchAction: "pan-x",
};

const rowStyle = {
  display: "flex",
  gap: 10,
  alignItems: "center",

  // ✅ Start from left so user can scroll to the right
  justifyContent: "flex-start",

  // ✅ Keep on one line (scroll instead of wrapping)
  flexWrap: "nowrap",
  width: "max-content",

  paddingLeft: 6,
  paddingRight: 6,
};

const tabBase = {
  padding: "10px 14px",
  borderRadius: 14,
  border: "1px solid #e5e7eb",
  background: "linear-gradient(180deg, #ffffff 0%, #f3f4f6 100%)",
  color: "#111827",
  fontWeight: 800,
  cursor: "pointer",
  whiteSpace: "nowrap",
  flex: "0 0 auto",
};

const tabActive = {
  border: "2px solid #1d4ed8",
  background: "linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%)",
  color: "#ffffff",
};

export default function NavTabs({ tabs = [], active, onChange }) {
  return (
    <div style={wrapStyle}>
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
    </div>
  );
}