// ui/src/components/NavTabs.jsx
import React from "react";

/**
 * Mobile-friendly NavTabs:
 * - Uses horizontal scroll on small screens (prevents LHS cut / overflow)
 * - Wraps nicely on larger screens
 * - Keeps your existing look & feel (gradients, active styling)
 */

const wrapStyle = {
  marginTop: 16,

  /* ✅ Mobile: allow horizontal scroll instead of layout overflow */
  overflowX: "auto",
  overflowY: "hidden",
  WebkitOverflowScrolling: "touch",

  /* A little breathing room so scrollbars (if any) don't overlap */
  paddingBottom: 6,
};

const rowStyle = {
  display: "flex",
  justifyContent: "center",
  gap: 10,
  alignItems: "center",

  /* ✅ Prevent tabs from forcing page wider than viewport */
  flexWrap: "nowrap",
  minWidth: "max-content",

  /* Small padding so first/last tab isn't flush to edges */
  paddingLeft: 10,
  paddingRight: 10,
};

const tabBase = {
  padding: "10px 14px",
  borderRadius: 14,
  border: "1px solid #e5e7eb",
  background: "linear-gradient(180deg, #ffffff 0%, #f3f4f6 100%)",
  color: "#111827",
  fontWeight: 800,
  cursor: "pointer",
  whiteSpace: "nowrap", // ✅ keep labels on one line
  flex: "0 0 auto",     // ✅ never shrink, never wrap
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