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
 *   1. Persisted ``backend`` value from the auth-handoff — but ONLY
 *      if it shares the eTLD+1 of the build-time default (so a
 *      preview URL stored from yesterday's testing can't override a
 *      production-targeted build).
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

/**
 * Resolve eTLD+1 (e.g. ``preview.emergentagent.com`` for
 * ``ai-stylist-api.preview.emergentagent.com``; ``dressapp.co`` for
 * ``dressapp.co``). We use this to decide whether a stored
 * ``backend`` is "trusted" — i.e. shares its registrable domain
 * with the build-time default. A preview-URL leftover after a
 * production rebuild fails this check and is ignored.
 */
function _registrableDomain(host) {
  if (!host) return '';
  const parts = host.split('.');
  if (parts.length <= 2) return host;
  // Naive but sufficient for our supported hosts:
  //   dressapp.co              -> dressapp.co
  //   foo.dressapp.co          -> dressapp.co
  //   ai-x.preview.emergentagent.com -> preview.emergentagent.com
  //   ai-x.emergent.host       -> emergent.host
  const tail3 = parts.slice(-3).join('.');
  // Multi-part TLDs / known subdomain-as-namespace patterns.
  if (/(?:preview\.emergentagent\.com|emergent\.host|emergentagent\.com)$/i.test(tail3)) {
    return tail3;
  }
  return parts.slice(-2).join('.');
}

function _sameRegistrableDomain(a, b) {
  try {
    const da = _registrableDomain(new URL(a).host);
    const db = _registrableDomain(new URL(b).host);
    return !!da && !!db && da.toLowerCase() === db.toLowerCase();
  } catch {
    return false;
  }
}

export async function getBackend() {
  const baked = authBaseUrl();
  const stored = (await chrome.storage.local.get(['backend'])).backend;
  if (stored && _sameRegistrableDomain(stored, baked)) {
    return stored;
  }
  // Stale or mismatched stored backend — wipe the whole auth slate
  // (backend + token + user). The token was issued by a different
  // origin and is unusable here; leaving the user object around
  // would also let the popup falsely show a "logged-in" badge for
  // the wrong account. The next handoff will repopulate cleanly.
  if (stored) {
    try {
      await chrome.storage.local.remove(['backend', 'token', 'user', 'issued_at']);
    } catch { /* noop */ }
  }
  return baked;
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
