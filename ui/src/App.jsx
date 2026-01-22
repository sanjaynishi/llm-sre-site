import NavTabs from "./components/NavTabs";

const NAV_ITEMS = [
  { label: "Runbook", to: "/runbook" },
  { label: "RAG", to: "/rag" },
  { label: "Agentic AI", to: "/agents" },
  // Add more later and it automatically works
];

export default function AppLayout() {
  return (
    <div>
      <header style={{ padding: 16, borderBottom: "1px solid #e5e7eb", background: "#fff" }}>
        <NavTabs items={NAV_ITEMS} />
      </header>

      {/* your Routes here */}
    </div>
  );
}