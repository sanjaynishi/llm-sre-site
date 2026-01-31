import React, { useMemo, useState } from "react";

import Home from "./pages/Home";
import MainLayout from "./layouts/MainLayout";
import NavTabs from "./components/NavTabs";

import Runbooks from "./pages/Runbooks";
import Rag from "./pages/Rag";
import Agents from "./pages/Agents";
import AiNews from "./pages/AiNews";
import Mcp from "./pages/Mcp";

/**
 * Maintenance mode (currently DISABLED)
 * - Later you can enable via: VITE_MAINTENANCE_MODE=true
 */
const MAINTENANCE_MODE = false; // 🔕 disabled for now

const contentCard = {
  marginTop: 16,
  background: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: 18,
  padding: 14,
  boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",
};

const maintenancePage = {
  minHeight: "70vh",
  display: "grid",
  placeItems: "center",
  padding: 18,
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif',
  color: "#0f172a",
};

const maintenanceCard = {
  maxWidth: 720,
  width: "100%",
  background: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: 18,
  padding: 18,
  boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",
};

const maintenancePill = {
  display: "inline-flex",
  alignItems: "center",
  gap: 8,
  padding: "6px 10px",
  borderRadius: 999,
  border: "1px solid #e2e8f0",
  background: "#f8fafc",
  fontSize: 12,
  fontWeight: 700,
};

export default function App() {
  // 🔒 Maintenance mode gate (inactive)
  if (MAINTENANCE_MODE) {
    return (
      <MainLayout>
        <div style={maintenancePage}>
          <div style={maintenanceCard}>
            <div style={maintenancePill}>🛠️ Maintenance Mode</div>
            <h1 style={{ margin: "12px 0 6px", fontSize: 26, fontWeight: 900 }}>
              We’re deploying an upgrade
            </h1>
            <p style={{ margin: 0, color: "#475569", lineHeight: 1.5 }}>
              The AIML SRE site is temporarily in maintenance while production
              deployment and RAG vector indexing are completed.
            </p>
          </div>
        </div>
      </MainLayout>
    );
  }

  // ⬇️ ORIGINAL APP LOGIC (unchanged)

  const tabs = useMemo(
    () => [
      { key: "home", label: "Home" },
      { key: "runbooks", label: "Runbooks" },
      { key: "rag", label: "RAG Chat" },
      { key: "agents", label: "Agentic AI" },
      { key: "aiNews", label: "AI News" },
      { key: "mcp", label: "MCP Workflow" },
    ],
    []
  );

  const [active, setActive] = useState("home");

  // ✅ Pages that already have their own full-page layout
  const noWrapper = active === "home" || active === "runbooks";

  return (
    <MainLayout>
      <NavTabs tabs={tabs} active={active} onChange={setActive} />

      {noWrapper ? (
        <>
          {active === "home" && <Home onNavigate={setActive} />}
          {active === "runbooks" && <Runbooks />}
        </>
      ) : (
        <div style={contentCard}>
          {active === "rag" && <Rag />}
          {active === "agents" && <Agents />}
          {active === "aiNews" && <AiNews />}
          {active === "mcp" && <Mcp />}
        </div>
      )}
    </MainLayout>
  );
}