/**
 * workStore.js — cross-page work tracker for The Eyes.
 *
 * Patch M20 (May 2026)
 * --------------------
 * The Closet page's local polling loop has a known weakness — when the
 * user navigates away from the page, the React component unmounts and
 * polling stops, so any matte / reconstruction BackgroundTask that
 * completes while the user is elsewhere never updates the local
 * cache. Result: the "Polishing photo…" badge sticks around on the
 * very last in-progress card the next time the user lands on Closet,
 * even though the backend has long since finished.
 *
 * This module owns a single global poller that runs at the App.jsx
 * level so it survives navigation. It also tracks active /analyze
 * jobs so the floating progress pill (``WorkProgressFloater``) can
 * tell the user something is happening even after they leave
 * AddItem.jsx mid-batch.
 *
 * The store is intentionally tiny — useSyncExternalStore pattern, no
 * Zustand / Redux — to keep cold-start fast and avoid pulling another
 * dep into the bundle.
 */

import { api } from '@/lib/api';
import { closetStore } from '@/lib/closetStore';

const POLL_INTERVAL_MS = 3000;
// Hard ceiling: stop polling for any single item after this. Prevents
// a wedged BackgroundTask from keeping the poller alive forever.
const ITEM_POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

const _listeners = new Set();
let _state = {
  // Active /analyze upload jobs keyed by frontend card id. Each value
  // is `{ id, label, startedAt, items, total }` where `items` ramps
  // from 0 → `total` as ``onItem`` frames arrive on the NDJSON stream.
  analyzeJobs: {},
  // Set of item ids whose matte / reconstruction BackgroundTask is
  // still pending in the backend. We poll each until ``clean_image_status``
  // flips out of "pending" or the timeout elapses.
  polishPendingIds: new Set(),
  // Snapshot of the latest "batch": when ``registerPolishItems``
  // is called, we stash how many items the user just saved so the
  // floater can show "Polishing 3 / 8 photos" cleanly. Resets to
  // 0 / 0 once the batch drains.
  polishBatchTotal: 0,
  polishBatchCompleted: 0,
  // Per-item registration timestamp so we can stop polling stalled
  // items after ITEM_POLL_TIMEOUT_MS.
  _polishStartedAt: {},
  // Callback fired exactly once per batch drain — used by App.jsx to
  // pop the "You have news in your closet" toast. The store doesn't
  // own toast UI; it just emits the signal.
  _onBatchDoneSubscribers: new Set(),
};

function _notify() {
  _listeners.forEach((fn) => {
    try { fn(); } catch { /* swallow listener errors */ }
  });
}

function _set(patch) {
  _state = { ..._state, ...patch };
  _notify();
}

let _pollerHandle = null;

async function _pollOnce() {
  const pendingIds = Array.from(_state.polishPendingIds);
  if (pendingIds.length === 0) {
    // Nothing to do this tick. Don't notify, no state churn.
    return;
  }

  // Prune items that have been pending longer than the timeout —
  // their BackgroundTask is presumed wedged. We accept whatever
  // state the local store has and let the user pull-to-refresh
  // manually if it ever recovers.
  const now = Date.now();
  const timedOut = pendingIds.filter(
    (id) => now - (_state._polishStartedAt[id] || now) > ITEM_POLL_TIMEOUT_MS,
  );
  if (timedOut.length) {
    const next = new Set(_state.polishPendingIds);
    const nextStartedAt = { ..._state._polishStartedAt };
    for (const id of timedOut) {
      next.delete(id);
      delete nextStartedAt[id];
    }
    _set({
      polishPendingIds: next,
      _polishStartedAt: nextStartedAt,
      polishBatchCompleted: _state.polishBatchCompleted + timedOut.length,
    });
    if (next.size === 0) _onBatchDrained();
    return;
  }

  // GET each pending item. We swallow per-item errors so a transient
  // 5xx on one item doesn't kill the rest. Wrap each error so we can
  // distinguish a 404 (item DELETED by the backend — e.g. Patch 12m
  // dropped a phantom region whose matte came back blank from both
  // SegFormer and rembg) from transient network errors. A 404 is
  // TERMINAL — we drop the item from the polish queue AND from the
  // local closet store so the user doesn't see a permanently
  // pending "white window" card.
  const results = await Promise.all(
    pendingIds.map((id) =>
      api.getItem(id).catch((err) => ({ _err: err, _id: id })),
    ),
  );

  let drained = false;
  const nextSet = new Set(_state.polishPendingIds);
  const nextStartedAt = { ..._state._polishStartedAt };
  let newlyCompleted = 0;

  for (const item of results) {
    if (!item) continue;
    // Patch 12m handling — backend deletion surfaces as 404.
    if (item._err) {
      const status = item._err?.response?.status;
      if (status === 404) {
        nextSet.delete(item._id);
        delete nextStartedAt[item._id];
        newlyCompleted += 1;
        try { closetStore.remove(item._id); } catch { /* swallow */ }
      }
      // Any other error (network blip, 5xx) — leave the item in
      // the queue; next tick will retry.
      continue;
    }
    if (!item.id) continue;
    // Always push the freshest doc into closetStore so the Closet
    // page picks it up next render — even if the status is still
    // "pending" we want the latest analysis fields / thumbnails.
    try {
      closetStore.upsert(item);
    } catch { /* swallow */ }
    // "ready" / "failed" / null all mean "no longer in flight".
    if (item.clean_image_status !== 'pending') {
      nextSet.delete(item.id);
      delete nextStartedAt[item.id];
      newlyCompleted += 1;
    }
  }

  if (newlyCompleted > 0) {
    drained = nextSet.size === 0;
    _set({
      polishPendingIds: nextSet,
      _polishStartedAt: nextStartedAt,
      polishBatchCompleted: _state.polishBatchCompleted + newlyCompleted,
    });
  }
  if (drained) _onBatchDrained();
}

function _onBatchDrained() {
  // Capture the batch totals BEFORE we reset them so subscribers can
  // include the count in their UX ("3 items polished").
  const finalTotal = _state.polishBatchTotal;
  const finalCompleted = _state.polishBatchCompleted;
  // Reset counters so the next ``registerPolishItems`` call starts
  // a fresh batch label.
  _set({
    polishBatchTotal: 0,
    polishBatchCompleted: 0,
  });
  _state._onBatchDoneSubscribers.forEach((fn) => {
    try { fn({ total: finalTotal, completed: finalCompleted }); }
    catch { /* swallow */ }
  });
}

function _ensurePollerRunning() {
  if (_pollerHandle != null) return;
  _pollerHandle = setInterval(() => {
    _pollOnce().catch(() => { /* swallow */ });
  }, POLL_INTERVAL_MS);
}

function _maybeStopPoller() {
  // Stop the timer when there's nothing left to poll, so we don't
  // bombard the API with empty ticks. The next ``registerPolishItems``
  // call will spin it back up.
  if (_state.polishPendingIds.size === 0 && _pollerHandle != null) {
    clearInterval(_pollerHandle);
    _pollerHandle = null;
  }
}

export const workStore = {
  getSnapshot() { return _state; },

  subscribe(fn) {
    _listeners.add(fn);
    return () => _listeners.delete(fn);
  },

  /**
   * Mark an /analyze job as started. ``id`` is the frontend card id
   * (the same one AddItem.jsx uses to track in-flight uploads), so
   * the floater can render "Analyzing 3 photos" by counting keys.
   * ``total`` is the expected item count from the streaming DETECT
   * frame; it's bumped to N once the frame arrives via
   * :meth:`updateAnalyze`.
   */
  registerAnalyze(id, label = null) {
    if (!id) return;
    _set({
      analyzeJobs: {
        ..._state.analyzeJobs,
        [id]: {
          id,
          label,
          startedAt: Date.now(),
          items: 0,
          total: 0,
        },
      },
    });
  },

  /**
   * Update progress for an in-flight analyze job. Called by the
   * streaming consumer in AddItem.jsx as DETECT / ITEM frames arrive.
   */
  updateAnalyze(id, patch) {
    if (!id || !_state.analyzeJobs[id]) return;
    _set({
      analyzeJobs: {
        ..._state.analyzeJobs,
        [id]: { ..._state.analyzeJobs[id], ...patch },
      },
    });
  },

  /**
   * Mark an analyze job as finished. We keep the entry in state for
   * a moment so the floater can show a brief "✓ Done" before
   * disappearing; the cleanup tick removes it.
   */
  completeAnalyze(id) {
    if (!id) return;
    const next = { ..._state.analyzeJobs };
    delete next[id];
    _set({ analyzeJobs: next });
  },

  /**
   * Register a batch of newly-saved items that have a deferred
   * matte / reconstruction BackgroundTask running. The global
   * poller will GET each one every POLL_INTERVAL_MS until the
   * backend flips ``clean_image_status`` out of "pending".
   *
   * ``items`` is the array returned from the /closet save calls;
   * we accept either the bare ids or full item docs.
   */
  registerPolishItems(items) {
    const ids = (items || [])
      .map((x) => (typeof x === 'string' ? x : x?.id))
      .filter(Boolean);
    if (ids.length === 0) return;
    const nextSet = new Set(_state.polishPendingIds);
    const nextStartedAt = { ..._state._polishStartedAt };
    const now = Date.now();
    let added = 0;
    for (const id of ids) {
      if (!nextSet.has(id)) {
        nextSet.add(id);
        nextStartedAt[id] = now;
        added += 1;
      }
    }
    if (added === 0) return;
    _set({
      polishPendingIds: nextSet,
      _polishStartedAt: nextStartedAt,
      polishBatchTotal: _state.polishBatchTotal + added,
    });
    _ensurePollerRunning();
  },

  /**
   * Subscribe to "batch fully drained" signals. The callback is
   * invoked with ``{ total, completed }`` exactly once per polish
   * batch. Used by App.jsx to fire the toast.
   */
  onBatchDone(fn) {
    if (!fn) return () => {};
    _state._onBatchDoneSubscribers.add(fn);
    return () => _state._onBatchDoneSubscribers.delete(fn);
  },

  /** Test / triage hook — drops everything and stops the poller. */
  reset() {
    if (_pollerHandle != null) {
      clearInterval(_pollerHandle);
      _pollerHandle = null;
    }
    _state = {
      analyzeJobs: {},
      polishPendingIds: new Set(),
      polishBatchTotal: 0,
      polishBatchCompleted: 0,
      _polishStartedAt: {},
      _onBatchDoneSubscribers: _state._onBatchDoneSubscribers,
    };
    _notify();
  },

  // Internal — exposed for testing the polling loop directly.
  _pollOnce,
  _maybeStopPoller,
};
