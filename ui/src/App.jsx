import React, { useMemo, useState } from "react";

import MainLayout from "./layouts/MainLayout";
import NavTabs from "./components/NavTabs";

import Runbooks from "./pages/Runbooks";
import Rag from "./pages/Rag";
import Agents from "./pages/Agents";
import AiNews from "./pages/AiNews";
import Mcp from "./pages/Mcp";

const contentCard = {
  marginTop: 16,
  background: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: 18,
  padding: 14,
  boxShadow: "0 10px 22px rgba(17, 24, 39, 0.06)",
};

export default function App() {
  const tabs = useMemo(
    () => [
      { key: "runbooks", label: "Runbooks" },
      { key: "rag", label: "RAG Chat" },
      { key: "agents", label: "Agentic AI" },
      { key: "aiNews", label: "AI News" },
      { key: "mcp", label: "MCP Workflow" }, // ✅ new tab
    ],
    []
  );

  const [active, setActive] = useState("runbooks");

  return (
    <MainLayout>
      <NavTabs tabs={tabs} active={active} onChange={setActive} />

      <div style={contentCard}>
        {active === "runbooks" && <Runbooks />}
        {active === "rag" && <Rag />}
        {active === "agents" && <Agents />}
        {active === "aiNews" && <AiNews />}
        {active === "mcp" && <Mcp />}
      </div>
    </MainLayout>
  );
}