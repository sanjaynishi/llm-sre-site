// ui/src/api/client.js

const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

/**
 * If VITE_API_BASE is empty:
 * - In DEV/PROD behind CloudFront: request "/api/..." from same domain => works
 * - In local dev: use Vite proxy (next step) => works
 */
function buildUrl(path) {
  if (!path.startsWith("/")) path = "/" + path;
  return `${API_BASE}${path}`;
}

export async function apiGet(path) {
  const url = buildUrl(path);
  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
  });

  const text = await res.text();
  if (!res.ok) throw new Error(`GET ${url} failed: ${res.status} ${text.slice(0, 200)}`);
  return JSON.parse(text);
}

export async function apiPost(path, body) {
  const url = buildUrl(path);
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body ?? {}),
  });

  const text = await res.text();
  if (!res.ok) throw new Error(`POST ${url} failed: ${res.status} ${text.slice(0, 200)}`);
  return JSON.parse(text);
}