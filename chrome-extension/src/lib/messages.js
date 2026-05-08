// Message-type catalogue shared by every part of the extension.
// Centralised so a typo in a string literal can't silently break
// the SW <-> popup <-> content-script wire.
export const messages = {
  AUTH_STATUS:        'AUTH_STATUS',
  RECEIVE_HANDOFF:    'RECEIVE_HANDOFF',
  CLEAR_AUTH:         'CLEAR_AUTH',
  FETCH_ME:           'FETCH_ME',
  ANALYZE_CHART:      'ANALYZE_CHART',
};

/** Promise-wrapper around chrome.runtime.sendMessage so callers can
 *  ``await sendToBackground({type, ...})`` instead of dealing with
 *  callbacks. Returns ``{ok:false, error}`` for any failure mode
 *  (no extension context, runtime.lastError, throw inside handler). */
export function sendToBackground(payload) {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(payload, (response) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        resolve(response || { ok: false, error: 'empty response' });
      });
    } catch (e) {
      resolve({ ok: false, error: e?.message || 'sendMessage threw' });
    }
  });
}
