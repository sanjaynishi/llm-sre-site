// ui/src/layouts/MainLayout.jsx
import React from "react";
import AppHeader from "../components/AppHeader";

export default function MainLayout({ children }) {
  return (
    <div style={styles.page}>
      <div style={styles.shell}>
        <AppHeader />

        {/* This restores the centered white card in the middle */}
        <main style={styles.main}>
          <div style={styles.contentCard}>{children}</div>
        </main>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "#f3f4f6",
  },
  shell: {
    maxWidth: 1100,
    margin: "0 auto",
    padding: "18px 16px 30px",
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif',
    color: "#111827",
  },
  main: {
    marginTop: 14,
  },
  contentCard: {
    // Center the actual page content
    maxWidth: 980,
    margin: "0 auto",
    background: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: 18,
    padding: 14,
    boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",
  },
};