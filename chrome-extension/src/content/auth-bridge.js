/**
 * Auth-bridge content script.
 *
 * Injected by manifest.json on the ``/extension/connect`` URL pattern
 * (both production dressapp.co and the Emergent preview origin).
 * Listens on ``window`` for the postMessage the page emits with the
 * shape ``{ type: 'DRESSAPP_EXT_TOKEN', token, user, backend, ... }``
 * and forwards it to the SW via chrome.runtime.sendMessage. Acks back
 * to the page via window.postMessage so the React component can flip
 * to its "sent" state.
 *
 * Security model: we only accept messages whose ``event.source ===
 * window`` (no cross-origin frames) AND whose ``event.origin`` matches
 * the location origin we were injected onto. That prevents a malicious
 * iframe inside dressapp.co from spoofing a token send.
 */
import { messages } from '@/lib/messages.js';

const SELF_ORIGIN = window.location.origin;

window.addEventListener('message', async (event) => {
  if (event.source !== window) return;
  if (event.origin !== SELF_ORIGIN) return;
  const data = event.data;
  if (!data || data.type !== 'DRESSAPP_EXT_TOKEN') return;

  try {
    const ack = await new Promise((resolve) => {
      chrome.runtime.sendMessage({ type: messages.RECEIVE_HANDOFF, payload: data }, (resp) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        resolve(resp || { ok: false, error: 'empty response' });
      });
    });
    // Echo back to the page so the React component can confirm.
    window.postMessage({ type: 'DRESSAPP_EXT_TOKEN_ACK', ok: !!ack.ok, error: ack.error || null }, SELF_ORIGIN);
  } catch (e) {
    window.postMessage({ type: 'DRESSAPP_EXT_TOKEN_ACK', ok: false, error: e?.message || 'ack failed' }, SELF_ORIGIN);
  }
});
