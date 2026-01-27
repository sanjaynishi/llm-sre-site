// ui/src/data/mcpScenarios.js

export const MCP_SCENARIOS = [
    {
      key: "first-call-html",
      title: "MCP: First-call HTML / JSON error (CloudFront 504)",
      description:
        "Diagnose why the first API call sometimes returns HTML/504 instead of JSON, and show why a retry succeeds.",
      question:
        "Prove why the first click sometimes returns HTML/504 instead of JSON, then show the retry path and recommended mitigations.",
      request: (baseUrl) => ({
        scenario: "first-call-html",
        base_url: baseUrl,
      }),
      expectedSteps: [
        "Create execution plan",
        "Probe /api/health",
        "POST /api/runbooks/ask (initial)",
        "Detect HTML or timeout",
        "Retry with adjusted strategy",
        "Explain CloudFront + Lambda cold-start behavior",
        "Recommend mitigations",
      ],
    },
  
    {
      key: "quantum-sre-10",
      title: "MCP: Quantum Computing for SRE (10-step orchestration)",
      description:
        "Explain quantum computing in practical SRE terms and orchestrate a safe, realistic learning path.",
      question:
        "Explain quantum computing for an SRE audience, validate claims vs reality, compare classical vs quantum, and produce a safe 10-step learning and experimentation plan.",
      request: (baseUrl) => ({
        scenario: "quantum-sre-10",
        base_url: baseUrl, // ✅ always include so backend tools use same domain
        audience: "sre",
        intent: "education",
      }),
      expectedSteps: [
        "Define goal and constraints",
        "Clarify what quantum is NOT",
        "Explain qubits and superposition",
        "Explain entanglement practically",
        "Compare classical vs quantum workloads",
        "Identify real enterprise use-cases",
        "Identify anti-patterns",
        "Choose safe simulators",
        "Design learning roadmap",
        "Summarize risks and next steps",
      ],
    },
  ];