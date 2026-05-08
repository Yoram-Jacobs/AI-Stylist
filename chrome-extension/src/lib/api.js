/**
 * Backend client used by the service worker.
 *
 * The popup and content scripts NEVER call the API directly — they
 * always go through the background SW so the bearer token stays in
 * one place. This also future-proofs us against MV3's
 * service-worker lifecycle (the SW gets a single source of truth
 * for the token).
 *
 * Backend URL discovery order:
 *   1. Persisted ``backend`` value from the auth-handoff (whatever
 *      origin issued the token — dressapp.co in prod, the Emergent
 *      preview URL in dev).
 *   2. Environment-baked default at build time (``VITE_DRESSAPP_BACKEND``).
 *   3. ``https://dressapp.co`` as a final hard-coded fallback.
 */
const FALLBACK_BACKEND = 'https://dressapp.co';

/** Origin used to open the auth-bridge tab from the popup. Same
 *  resolution order as ``apiBase`` minus the auth-bridge can't
 *  rely on a stored value (no token yet). */
export function authBaseUrl() {
  return import.meta.env.VITE_DRESSAPP_BACKEND || FALLBACK_BACKEND;
}

export async function getBackend() {
  const stored = await chrome.storage.local.get(['backend']);
  return stored.backend || authBaseUrl();
}

export async function getToken() {
  const stored = await chrome.storage.local.get(['token']);
  return stored.token || null;
}

async function authedFetch(path, init = {}) {
  const backend = await getBackend();
  const token = await getToken();
  const headers = new Headers(init.headers || {});
  headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const res = await fetch(`${backend}/api/v1${path}`, { ...init, headers });
  if (res.status === 401) {
    // Token expired or revoked. Wipe it so the popup shows the
    // disconnected state on next open instead of looping on a
    // dead session.
    await chrome.storage.local.remove(['token']);
    throw new Error('Session expired — please reconnect from the DressApp popup.');
  }
  return res;
}

export async function fetchMe() {
  const r = await authedFetch('/users/me');
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function analyzeChart(payload) {
  const r = await authedFetch('/sizes/analyze-chart', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const txt = await r.text();
    throw new Error(`HTTP ${r.status}: ${txt.slice(0, 240)}`);
  }
  return r.json();
}
