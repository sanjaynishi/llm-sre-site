// ui/src/App.jsx
import React from "react";
import "./App.css";

import MainLayout from "./layouts/MainLayout";
import NavTabs from "./components/NavTabs";

import Runbooks from "./pages/Runbooks";
import Rag from "./pages/Rag";
import Agents from "./pages/Agents";
import AiNews from "./pages/AiNews";

export default function App() {
  const [active, setActive] = React.useState("runbooks");

  const tabs = React.useMemo(
    () => [
      { key: "runbooks", label: "Runbooks" },
      { key: "rag", label: "RAG Chat" },
      { key: "agents", label: "Agentic AI" },
      { key: "news", label: "AI News" },
    ],
    []
  );

  return (
    <MainLayout>
      <NavTabs tabs={tabs} active={active} onChange={setActive} />

      {active === "runbooks" && <Runbooks />}
      {active === "rag" && <Rag />}
      {active === "agents" && <Agents />}
      {active === "news" && <AiNews />}
    </MainLayout>
  );
}