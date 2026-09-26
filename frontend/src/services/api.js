// Centralized HTTP client. All backend access goes through `request`.
const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

// Conservative limit for ordinary CRUD calls, so a hung backend can never leave a form locked
// forever. Covers the whole exchange (headers and body). Overridable at build time.
const TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS) || 30000;

// kind: 'network' (no response), 'timeout' (no complete response in time), 'http' (non-2xx),
// 'parse' (2xx but unreadable body)
export class ApiError extends Error {
  constructor(message, { status = 0, kind = 'http', details = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.kind = kind;
    this.details = details;
  }

  get isNetwork() { return this.kind === 'network'; }
  get isTimeout() { return this.kind === 'timeout'; }
  get isUnauthorized() { return this.status === 401; }
  get isForbidden() { return this.status === 403; }
  get isNotFound() { return this.status === 404; }
}

// Auth is owned by another module. It can register a token provider and an
// unauthorized handler (e.g. redirect to login) without this file knowing how.
let tokenProvider = () => null;
let unauthorizedHandler = null;
export function setAuthTokenProvider(fn) {
  tokenProvider = fn;
}
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

// FastAPI returns `detail` as a string or as a list of validation errors.
function extractMessage(body, fallback) {
  const detail = body?.detail ?? body?.message;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => {
        if (!d?.msg) return null;
        // loc is like ['body', 'lines', 0, 'quantity']; drop the leading 'body'.
        const field = Array.isArray(d.loc) ? d.loc.filter((p) => p !== 'body').join('.') : '';
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .filter(Boolean);
    if (msgs.length) return msgs.join('; ');
  }
  return fallback;
}

function readJson(text) {
  if (!text) return { ok: true, data: null };
  try {
    return { ok: true, data: JSON.parse(text) };
  } catch {
    return { ok: false, data: null };
  }
}

export async function request(path, { method = 'GET', params, body, signal } = {}) {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, value);
      }
    });
  }

  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const token = tokenProvider();
  if (token) headers.Authorization = `Bearer ${token}`;

  // Own AbortController so the timeout can cancel the request; the caller's signal (if any) is
  // forwarded, and a caller abort is still surfaced as a plain AbortError.
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, TIMEOUT_MS);
  const forwardAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', forwardAbort, { once: true });
  }
  // The request may still have reached the server, so a timeout must not claim it failed.
  const timeoutError = () => new ApiError(
    'The server did not respond in time. If you were saving or changing something, reload to check its current state before trying again.',
    { kind: 'timeout' },
  );

  let text = '';
  let parsed;
  let response;
  try {
    try {
      response = await fetch(url, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
    } catch (err) {
      if (timedOut) throw timeoutError();
      if (err.name === 'AbortError') throw err;
      throw new ApiError('Unable to reach the server. Check your connection.', { kind: 'network' });
    }

    try {
      text = await response.text();
    } catch (err) {
      if (timedOut) throw timeoutError();
      if (err.name === 'AbortError') throw err;
      throw new ApiError('Connection lost while reading the response.', { kind: 'network', status: response.status });
    }
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', forwardAbort);
  }
  parsed = readJson(text);

  if (!response.ok) {
    const error = new ApiError(
      extractMessage(parsed.data, `Request failed (${response.status})`),
      { status: response.status, kind: 'http', details: parsed.data },
    );
    if (error.isUnauthorized && unauthorizedHandler) unauthorizedHandler(error);
    throw error;
  }
  if (!parsed.ok) {
    throw new ApiError('The server returned an unreadable response.', { status: response.status, kind: 'parse' });
  }
  return parsed.data;
}

export const api = {
  get: (path, options) => request(path, { ...options, method: 'GET' }),
  post: (path, body, options) => request(path, { ...options, method: 'POST', body }),
  put: (path, body, options) => request(path, { ...options, method: 'PUT', body }),
};
