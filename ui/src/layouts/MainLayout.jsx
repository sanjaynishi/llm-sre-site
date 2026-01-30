// ui/src/layouts/MainLayout.jsx
import React from "react";
import AppHeader from "../components/AppHeader";
import WarmupPing from "../components/WarmupPing";

export default function MainLayout({ children }) {
  return (
    <div style={styles.page}>
      <WarmupPing />

      <div style={styles.shell}>
        {/* Header should always be visible on iPhone */}
        <header style={styles.headerWrap}>
          <AppHeader />
        </header>

        <main style={styles.main}>
          <section style={styles.centerWrap}>{children}</section>
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

    // ✅ keep layout stable on mobile
    display: "flex",
    justifyContent: "center",
  },

  shell: {
    width: "100%",
    maxWidth: 1100,
    margin: "0 auto",

    // ✅ iPhone notch safe-area
    paddingLeft: "calc(16px + env(safe-area-inset-left))",
    paddingRight: "calc(16px + env(safe-area-inset-right))",
    paddingTop: "calc(14px + env(safe-area-inset-top))",
    paddingBottom: "calc(26px + env(safe-area-inset-bottom))",

    boxSizing: "border-box",
    color: "#111827",
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif',
  },

  headerWrap: {
    width: "100%",
    // ✅ prevent header getting clipped by any nested overflow rules
    overflow: "visible",
  },

  main: {
    marginTop: 12,
    width: "100%",
  },

  centerWrap: {
    width: "100%",
    maxWidth: 980,
    margin: "0 auto",
    boxSizing: "border-box",

    background: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: 18,
    padding: 16,
    boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",

    // ✅ CRITICAL: do NOT hide overflow here (it breaks tab scrolling + some layouts)
    overflow: "visible",
  },
};