// ui/src/data/predefinedQuestions.js
export const PREDEFINED_QUESTIONS = [
    // ---- Deployment / CloudFront / UI ----
    "How do I invalidate CloudFront cache after deploying the UI?",
    "What are the CloudFront behaviors for /api/* vs SPA routes?",
    "How do I verify CloudFront is serving the latest index.html?",
    "What headers should I check to confirm caching (x-cache, age, etag)?",
    "What’s the recommended cache policy for SPA assets vs index.html?",
    "How do I troubleshoot a CloudFront 403/404 for static assets?",
  
    // ---- API Gateway / Lambda ----
    "How do I troubleshoot API Gateway 500 errors for /api/agents?",
    "How do I validate Lambda permissions for API Gateway invoke?",
    "How do I enable and read Lambda logs for debugging production issues?",
    "How do I test Lambda locally vs via API Gateway?",
    "What environment variables are required for the agent API Lambda?",
    "How do I rotate OPENAI_API_KEY safely without redeploying code?",
  
    // ---- RAG / Chroma / Indexing ----
    "How do I build Chroma vector indexes for runbook PDFs?",
    "Where are Chroma vectors stored in S3 and how are they loaded in Lambda?",
    "How do I handle sqlite3 version issues for Chroma in Lambda?",
    "How do I validate the Chroma collection count and documents indexed?",
    "How do I re-index only changed runbook PDFs (incremental indexing)?",
    "What is top_k and how does it affect retrieval accuracy/cost?",
  
    // ---- Security / Threat model ----
    "What are the primary threats in the LLM-SRE architecture and mitigations?",
    "How do I restrict CORS origins properly for dev vs prod?",
    "What IAM permissions does Lambda need for S3 runbook access?",
    "How do I prevent secrets exposure in Lambda env vars and logs?",
    "How do I add basic auth / WAF / rate limiting for the /api endpoints?",
  
    // ---- Observability / Reliability ----
    "What metrics and logs should we track for the RAG pipeline?",
    "How do we detect retrieval failures vs LLM failures in the API?",
    "How do we handle cold starts and cache Chroma safely in /tmp?",
    "How do we implement timeouts/retries for OpenAI calls in Lambda?",
  
    // ---- Quantum computing (ONLY answered if your runbooks cover it) ----
    "What is a qubit and how is it different from a classical bit?",
    "Explain superposition and measurement in practical terms.",
    "What is entanglement and how is it used in algorithms?",
    "What is a quantum gate model (Hadamard, CNOT) and why it matters?",
    "Explain QAOA and where it fits in optimization problems.",
    "What is Grover’s algorithm and when is it useful?",
    "What is Shor’s algorithm and what does it mean for cryptography?",
    "What is a QUBO formulation and how do we map a problem to QUBO?",
    "How can quantum centroids help log clustering (high-level idea)?",
    "What are practical limitations of today’s NISQ devices?",
  ];