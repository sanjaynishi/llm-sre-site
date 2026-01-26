import React from "react";
import AppHeader from "../components/AppHeader";

export default function MainLayout({ children }) {
  return (
    <div style={styles.page}>
      <div style={styles.shell}>
        <AppHeader />
        <main style={styles.main}>{children}</main>
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
};