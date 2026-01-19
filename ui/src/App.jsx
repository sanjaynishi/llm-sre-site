import React, { useState } from "react";
import Agents from "./pages/Agents";
import Runbooks from "./pages/Runbooks";
import "./App.css";

export default function App() {
  const [tab, setTab] = useState("runbooks");

  return (
    <div>
      <header style={{ padding: 16, borderBottom: "1px solid #eee" }}>
        <h1 style={{ margin: 0 }}>AIML LLM SRE / DevOps</h1>
        <p style={{ margin: "6px 0 0", opacity: 0.8 }}>
          Azure OpenAI first • AWS AI next • Runbooks + Agentic tools
        </p>

        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <button onClick={() => setTab("runbooks")} disabled={tab === "runbooks"}>
            Runbooks (RAG)
          </button>
          <button onClick={() => setTab("agents")} disabled={tab === "agents"}>
            Agentic AI
          </button>
        </div>
      </header>

      {tab === "runbooks" ? <Runbooks /> : <Agents />}
    </div>
  );
}
