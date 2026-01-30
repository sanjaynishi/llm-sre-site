// ui/src/layouts/MainLayout.jsx
import React from "react";
import AppHeader from "../components/AppHeader";
import WarmupPing from "../components/WarmupPing";

export default function MainLayout({ children }) {
  return (
    <div style={styles.page}>
      <WarmupPing />

      <div style={styles.shell}>
        {/* ✅ Header card uses SAME width + SAME frame style as main content */}
        <header style={styles.frame}>
          <AppHeader />
        </header>

        {/* ✅ Main content uses SAME width + SAME frame style */}
        <main style={{ marginTop: 12 }}>
          <section style={styles.frame}>{children}</section>
        </main>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "#f3f4f6",
    width: "100%",
  },

  shell: {
    width: "100%",
    maxWidth: 1100,
    margin: "0 auto",

    // ✅ iPhone notch safe-area + consistent padding
    paddingLeft: "calc(16px + env(safe-area-inset-left))",
    paddingRight: "calc(16px + env(safe-area-inset-right))",
    paddingTop: "calc(14px + env(safe-area-inset-top))",
    paddingBottom: "calc(26px + env(safe-area-inset-bottom))",

    boxSizing: "border-box",
    color: "#111827",
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif',
  },

  // ✅ ONE shared frame style for BOTH header and content (same width)
  frame: {
    width: "100%",
    maxWidth: 980,
    margin: "0 auto",
    boxSizing: "border-box",

    background: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: 18,
    padding: 16,
    boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",

    // ✅ do not clip children (important for tabs / header wrap)
    overflow: "visible",
  },
};