// ui/src/data/mcpScenarios.js

export const MCP_SCENARIOS = [
    {
      key: "first-call-html",
      title: "MCP: First-call HTML / JSON error (CloudFront 504)",
      description:
        "Diagnose why the first API call sometimes returns HTML or 504 instead of JSON, and explain why retry succeeds.",
      question:
        "Prove why the first click sometimes returns HTML/504 instead of JSON, then show the retry path and recommended mitigations.",
      request: (baseUrl) => ({
        scenario: "first-call-html",
        base_url: baseUrl,
      }),
      expectedSteps: [
        "Create execution plan (LLM)",
        "Probe /api/health",
        "POST /api/runbooks/ask (initial)",
        "Detect HTML/non-JSON or timeout",
        "Retry strategy (small backoff)",
        "POST /api/runbooks/ask (retry)",
        "Root-cause + mitigations (LLM summary)",
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
        base_url: baseUrl, // ✅ important
        audience: "sre",
        intent: "education",
      }),
      expectedSteps: [
        "Create execution plan (LLM)",
        "10-step learning + experimentation plan",
        "Clear what quantum is NOT",
        "Practical SRE analogies",
        "Risks and next actions (LLM summary)",
      ],
    },
  ];