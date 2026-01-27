// ui/src/layouts/MainLayout.jsx
import React from "react";
import AppHeader from "../components/AppHeader";

export default function MainLayout({ children }) {
  return (
    <div style={styles.page}>
      <div style={styles.shell}>
        <AppHeader />

        {/* CENTERING FIX */}
        <main style={styles.main}>
          <section style={styles.centerWrap}>
            {children}
          </section>
        </main>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "#f3f4f6",
    display: "flex",
    justifyContent: "center",
  },

  shell: {
    width: "100%",
    maxWidth: 1100,
    padding: "18px 16px 30px",
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif',
    color: "#111827",
  },

  main: {
    marginTop: 16,
    display: "flex",
    justifyContent: "center",   // ⬅️ key
  },

  centerWrap: {
    width: "100%",
    maxWidth: 980,              // ⬅️ visual center
    background: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: 18,
    padding: 16,
    boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",
  },
};