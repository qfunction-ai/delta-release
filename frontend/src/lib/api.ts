/**
 * Centralized API access.
 *
 * All pages should use `apiFetch()` instead of raw `fetch()`.
 * It automatically prepends the base URL and includes credentials
 * (cookies) for authentication.
 *
 * Auth is handled via httpOnly cookies set by the server on login.
 * The JWT is never accessible to JavaScript, preventing XSS token theft.
 */

/// <reference types="vite/client" />

const API_URL: string = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Block mixed-content requests: if the page is HTTPS but the API URL is HTTP,
// auth cookies would be sent in cleartext. Throw instead of silently proceeding.
let _mixedContentBlocked = false;
if (typeof window !== 'undefined' && window.location.protocol === 'https:' && API_URL.startsWith('http://')) {
  _mixedContentBlocked = true;
  console.error(
    'SECURITY: VITE_API_URL is using HTTP while the page is served over HTTPS. ' +
    'All API requests are blocked. Set VITE_API_URL to an HTTPS URL in production.'
  );
}

/**
 * Build headers for API requests.
 * Auth is handled via httpOnly cookies — no Authorization header needed.
 */
export function apiHeaders(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
  };
}

/**
 * Fetch wrapper that prepends the API base URL and includes credentials.
 * The httpOnly cookie is automatically sent by the browser with
 * credentials: 'include' (for cross-origin requests).
 *
 * Blocks requests if mixed-content is detected (HTTPS page with HTTP API URL).
 *
 * Usage: `apiFetch('/api/agents')` instead of `fetch('http://localhost:8000/api/agents', ...)``
 */
/**
 * Normalize RequestInit.headers into a plain Record<string, string>.
 * Handles Headers objects, [key, value][] tuples, and Record<string, string>.
 */
function normalizeHeaders(headers: RequestInit['headers'] | undefined): Record<string, string> {
  if (!headers) return {};
  if (headers instanceof Headers) {
    const out: Record<string, string> = {};
    headers.forEach((value, key) => { out[key] = value; });
    return out;
  }
  if (Array.isArray(headers)) {
    const out: Record<string, string> = {};
    for (const [key, value] of headers) {
      out[key] = value;
    }
    return out;
  }
  return headers as Record<string, string>;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (_mixedContentBlocked) {
    throw new Error(
      'Blocked: API URL uses HTTP while page is served over HTTPS. ' +
      'Set VITE_API_URL to an HTTPS URL.'
    );
  }
  const url = `${API_URL}${path}`;
  // When the body is FormData, omit Content-Type so the browser sets the
  // multipart/form-data header with the correct boundary automatically.
  const isFormData = init.body instanceof FormData;
  const baseHeaders = isFormData ? {} : apiHeaders();
  const headers = { ...baseHeaders, ...normalizeHeaders(init.headers) };
  const response = await fetch(url, { ...init, headers, credentials: 'include' });

  // Centralized 401 handling: if the JWT has expired or been revoked,
  // dispatch an event so the AuthProvider can redirect to login.
  // This avoids every page having to check 401 individually.
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent('api:unauthorized'));
  }

  return response;
}

/**
 * Extract an error message from an API response.
 * Tries to parse JSON and return `data.detail`, otherwise returns the fallback.
 */
export async function extractApiError(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json();
    return data.detail || fallback;
  } catch {
    return fallback;
  }
}

export { API_URL };

/** @internal Test-only hook to simulate mixed-content detection */
export function _setMixedContentBlocked(value: boolean) {
  _mixedContentBlocked = value;
}
