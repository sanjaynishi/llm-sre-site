import React, { useMemo, useState } from "react";
import { apiPost } from "../api/client";

const PRESET_QUESTIONS = [
  { id: "az-logs", label: "Azure OpenAI: Troubleshoot 429 / TPM throttling" },
  { id: "az-private", label: "Azure OpenAI: Private endpoint / DNS checklist" },
  { id: "aws-cf", label: "AWS: CloudFront SSL + alias troubleshooting checklist" },
  { id: "tf-state", label: "Terraform: state drift & lockfile fixes (common)" },
  { id: "quantum-1", label: "Quantum (GPT-5.1): QAOA vs VQE with a practical example" },
];

export default function Runbooks() {
  const [qid, setQid] = useState(PRESET_QUESTIONS[0].id);
  const [answer, setAnswer] = useState("");
  const [err, setErr] = useState("");
  const selected = useMemo(() => PRESET_QUESTIONS.find((q) => q.id === qid), [qid]);

  async function ask() {
    setErr("");
    setAnswer("");
    try {
      const res = await apiPost("/api/rag/query", { question_id: qid });
      setAnswer(res?.answer || JSON.stringify(res, null, 2));
    } catch (e) {
      setErr(String(e.message || e));
    }
  }

  return (
    <div style={{ padding: 16, maxWidth: 900 }}>
      <h2>Runbooks (RAG)</h2>
      <p style={{ marginTop: 4, opacity: 0.8 }}>
        Predefined questions only (cost control). Next step: wire /api/rag/query to S3 + DynamoDB + GPT-5.1.
      </p>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
        <div>
          <label>Question</label><br />
          <select value={qid} onChange={(e) => setQid(e.target.value)}>
            {PRESET_QUESTIONS.map((q) => (
              <option key={q.id} value={q.id}>{q.label}</option>
            ))}
          </select>
        </div>

        <button onClick={ask}>Ask</button>
      </div>

      {selected && <p style={{ marginTop: 12 }}><b>Selected:</b> {selected.label}</p>}
      {err && <p style={{ color: "crimson" }}>Not wired yet: {err}</p>}

      {answer && (
        <div style={{ marginTop: 16, padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <pre style={{ whiteSpace: "pre-wrap" }}>{answer}</pre>
        </div>
      )}
    </div>
  );
}
