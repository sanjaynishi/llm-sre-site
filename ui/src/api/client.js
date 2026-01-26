// ui/src/api/client.js

const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

/**
 * If VITE_API_BASE is empty:
 * - DEV/PROD behind CloudFront → "/api/..." same origin
 * - Local dev → Vite proxy handles "/api"
 */
function buildUrl(path) {
  if (!path.startsWith("/")) path = "/" + path;
  return `${API_BASE}${path}`;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function parseJsonOrThrow(resp, text) {
  const ct = (resp.headers.get("content-type") || "").toLowerCase();

  if (ct.includes("application/json")) {
    try {
      return JSON.parse(text || "{}");
    } catch {
      throw new Error(
        `Invalid JSON from API. First 200 chars: ${(text || "").slice(0, 200)}`
      );
    }
  }

  throw new Error(
    `Expected JSON but got "${ct || "unknown"}". ` +
      `This usually means CloudFront/S3 returned HTML. ` +
      `(First 200 chars): ${(text || "").slice(0, 200)}`
  );
}

async function requestWithRetry(
  url,
  options,
  { retries = 1, retryDelayMs = 700 } = {}
) {
  let lastErr;

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const resp = await fetch(url, options);
      const text = await resp.text();

      // Retry on CloudFront / edge transient failures
      if ([502, 503, 504].includes(resp.status)) {
        throw new Error(`HTTP ${resp.status}: ${text.slice(0, 200)}`);
      }

      // Non-OK but not retryable (4xx etc)
      if (!resp.ok) {
        const data = parseJsonOrThrow(resp, text);
        const msg =
          data?.error?.message || `${options.method} ${url} failed (${resp.status})`;
        throw new Error(msg);
      }

      // OK → parse JSON
      return parseJsonOrThrow(resp, text);
    } catch (err) {
      lastErr = err;
      if (attempt < retries) {
        await sleep(retryDelayMs);
        continue;
      }
      throw lastErr;
    }
  }

  throw lastErr;
}

export async function apiGet(path) {
  const url = buildUrl(path);
  return requestWithRetry(
    url,
    {
      method: "GET",
      headers: { Accept: "application/json" },
    },
    { retries: 1, retryDelayMs: 700 }
  );
}

export async function apiPost(path, body) {
  const url = buildUrl(path);
  return requestWithRetry(
    url,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body ?? {}),
    },
    { retries: 1, retryDelayMs: 700 }
  );
}