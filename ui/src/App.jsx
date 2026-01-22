import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";

import NavTabs from "./components/NavTabs.jsx";

// Pages (adjust paths if yours differ)
import Runbook from "./pages/Runbook.jsx";
import Rag from "./pages/Rag.jsx";
import Agents from "./pages/Agents.jsx";

const wrapper = {
  padding: 16,
  maxWidth: 1100,
  margin: "0 auto",
};

export default function App() {
  const tabs = [
    { label: "Runbook", to: "/runbook" },
    { label: "RAG", to: "/rag" },
    { label: "Agentic AI", to: "/agents" },
  ];

  return (
    <div style={wrapper}>
      <NavTabs items={tabs} />

      <div style={{ marginTop: 14 }}>
        <Routes>
          {/* default landing route */}
          <Route path="/" element={<Navigate to="/runbook" replace />} />

          <Route path="/runbook" element={<Runbook />} />
          <Route path="/rag" element={<Rag />} />
          <Route path="/agents" element={<Agents />} />

          {/* fallback */}
          <Route path="*" element={<Navigate to="/runbook" replace />} />
        </Routes>
      </div>
    </div>
  );
}
