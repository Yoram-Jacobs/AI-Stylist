/**
 * MV3 service worker — the extension's brain.
 *
 * Responsibilities:
 *  * Handle the auth handoff message from the dressapp.co
 *    auth-bridge content script and persist the token in
 *    chrome.storage.local.
 *  * Answer popup / content-script queries about auth status,
 *    user profile, and chart analysis. Centralising the API
 *    client here means the bearer token never leaves storage.
 *  * Cache the user profile for 5 minutes to spare the backend
 *    on rapid popup opens.
 *
 * MV3 quirk: this worker can be killed by the browser at any time.
 * We therefore avoid in-memory state for anything important; the
 * 5-minute cache is best-effort and recovers naturally on miss.
 */
import { messages } from '@/lib/messages.js';
import { fetchMe, analyzeChart } from '@/lib/api.js';

const ME_TTL_MS = 5 * 60 * 1000;
let meCache = null;

async function handleHandoff(payload) {
  // Sanity-check the payload before persisting. If anything looks
  // off, fail hard — a corrupt token is worse than no token.
  if (!payload || payload.type !== 'DRESSAPP_EXT_TOKEN') return { ok: false, error: 'wrong type' };
  if (typeof payload.token !== 'string' || payload.token.length < 16) return { ok: false, error: 'bad token' };
  if (typeof payload.backend !== 'string' || !/^https?:\/\//.test(payload.backend)) return { ok: false, error: 'bad backend url' };

  await chrome.storage.local.set({
    token:    payload.token,
    user:     payload.user || null,
    backend:  payload.backend,
    issued_at: payload.issued_at || new Date().toISOString(),
  });
  meCache = null;
  return { ok: true };
}

async function handleAuthStatus() {
  const s = await chrome.storage.local.get(['token', 'user', 'issued_at', 'backend']);
  return {
    ok: true,
    token: s.token || null,
    user: s.user || null,
    issued_at: s.issued_at || null,
    backend: s.backend || null,
  };
}

async function handleClearAuth() {
  // Wipe ALL auth-related state, including the cached ``backend`` URL.
  // Leaving ``backend`` behind causes a subtle bug where the next
  // reconnect (which the popup opens via the build-time ``authBaseUrl``)
  // succeeds against, say, dressapp.co — but the persisted ``backend``
  // value from a previous preview-environment session keeps routing
  // every API call to the wrong host. Clearing it forces the next
  // handoff to repopulate it cleanly.
  await chrome.storage.local.remove(['token', 'user', 'issued_at', 'backend']);
  meCache = null;
  return { ok: true };
}

async function handleFetchMe() {
  if (meCache && (Date.now() - meCache.ts) < ME_TTL_MS) {
    return { ok: true, user: meCache.user, cached: true };
  }
  try {
    const user = await fetchMe();
    meCache = { ts: Date.now(), user };
    // Also stash in storage so popup can show stale data immediately
    // while the background refreshes.
    await chrome.storage.local.set({ user });
    return { ok: true, user };
  } catch (e) {
    return { ok: false, error: e?.message || 'fetch /me failed' };
  }
}

async function handleAnalyze(payload) {
  try {
    const result = await analyzeChart(payload);
    return { ok: true, result };
  } catch (e) {
    return { ok: false, error: e?.message || 'analyze failed' };
  }
}

async function handleCaptureVisibleTab(sender) {
  try {
    // Use the sender tab's windowId explicitly so we never capture
    // the wrong window when the SW wakes from sleep. ``activeTab`` +
    // host_permissions on the listed stores cover the auth model.
    const windowId = sender?.tab?.windowId;
    const dataUrl = await chrome.tabs.captureVisibleTab(
      windowId,
      { format: 'jpeg', quality: 70 },
    );
    if (typeof dataUrl !== 'string') {
      return { ok: false, error: 'captureVisibleTab returned no data' };
    }
    const i = dataUrl.indexOf(',');
    return { ok: true, image_b64: i >= 0 ? dataUrl.slice(i + 1) : dataUrl };
  } catch (e) {
    const msg = e?.message || 'captureVisibleTab failed';
    return {
      ok: false,
      error: msg,
      // Chrome surfaces the missing-permission state via two
      // distinct strings depending on platform/version. Match all
      // of them so the content script can prompt for an upgrade.
      needs_permission:
        /<all_urls>|activeTab|cannot access|no host permission|MAY_BE_REMOTELY_HOSTED/i
          .test(msg),
    };
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Dispatch table.
  const handlers = {
    [messages.RECEIVE_HANDOFF]:     () => handleHandoff(msg.payload || msg),
    [messages.AUTH_STATUS]:         () => handleAuthStatus(),
    [messages.CLEAR_AUTH]:          () => handleClearAuth(),
    [messages.FETCH_ME]:            () => handleFetchMe(),
    [messages.ANALYZE_CHART]:       () => handleAnalyze(msg.payload),
    [messages.CAPTURE_VISIBLE_TAB]: () => handleCaptureVisibleTab(sender),
  };
  const handler = handlers[msg?.type];
  if (!handler) {
    sendResponse({ ok: false, error: `unknown message type ${msg?.type}` });
    return false;
  }
  // Returning true keeps the message channel open for async work.
  handler().then(sendResponse).catch((e) => sendResponse({ ok: false, error: e?.message || 'handler threw' }));
  return true;
});

// Also accept handoff messages posted to externally_connectable origins
// (i.e. a script running on dressapp.co calling chrome.runtime.sendMessage
// with our extension ID). This is the path the ExtensionConnect page
// uses when it isn't loaded inside an injected content script.
if (chrome.runtime.onMessageExternal) {
  chrome.runtime.onMessageExternal.addListener((msg, sender, sendResponse) => {
    if (msg?.type !== 'DRESSAPP_EXT_TOKEN') {
      sendResponse({ ok: false, error: 'unsupported external message' });
      return false;
    }
    handleHandoff(msg).then(sendResponse);
    return true;
  });
}
