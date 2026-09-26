// Single place that knows where the backend lives.
// VITE_API_BASE_URL is required in production; the localhost fallback applies
// to `vite dev` only and is never used in a production build.
const configured = import.meta.env.VITE_API_BASE_URL;

if (!configured && import.meta.env.PROD) {
  console.error("VITE_API_BASE_URL is not set; API calls will fail.");
}

export const API_BASE_URL = (
  configured || (import.meta.env.DEV ? "http://localhost:8000" : "")
).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(status, body) {
    super(`API request failed with status ${status}`);
    this.status = status;
    this.body = body;
  }
}

export async function apiFetch(path, { params, headers, ...options } = {}) {
  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    });
  }
  const res = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...headers },
  });
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body);
  return body;
}

export const getHealth = () => apiFetch("/api/health");
