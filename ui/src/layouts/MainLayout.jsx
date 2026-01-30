// ui/src/layouts/MainLayout.jsx
import React from "react";
import AppHeader from "../components/AppHeader";
import WarmupPing from "../components/WarmupPing"; // ✅ ADD

export default function MainLayout({ children }) {
  return (
    <div style={styles.page}>
      <div style={styles.shell}>
        {/* 🔥 Warm backend once on initial load */}
        <WarmupPing />

        <AppHeader />

        {/* CONTENT */}
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

    /* ✅ iPhone-safe: do NOT flex-center the whole page */
    width: "100%",
    overflowX: "hidden",
  },

  shell: {
    /* ✅ Always fit viewport */
    width: "100%",
    maxWidth: 1100,
    margin: "0 auto",

    /* ✅ Notch-safe padding on iPhone + normal padding everywhere */
    paddingLeft: "calc(16px + env(safe-area-inset-left))",
    paddingRight: "calc(16px + env(safe-area-inset-right))",
    paddingTop: "calc(18px + env(safe-area-inset-top))",
    paddingBottom: "calc(30px + env(safe-area-inset-bottom))",

    boxSizing: "border-box",

    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif',
    color: "#111827",
  },

  main: {
    marginTop: 16,

    /* ✅ Keep layout simple & mobile-safe */
    width: "100%",
  },

  centerWrap: {
    width: "100%",
    maxWidth: 980,
    margin: "0 auto",

    /* ✅ Prevent child overflow from cropping the page */
    overflowX: "hidden",
    boxSizing: "border-box",

    background: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: 18,
    padding: 16,
    boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",
  },
};