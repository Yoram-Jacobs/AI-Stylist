/**
 * closetStore.js — singleton in-memory store for the user's closet.
 *
 * Goals
 *   1. **Eager load**: as soon as the user is authenticated (App boot),
 *      we kick off ONE network round-trip and stash the full closet.
 *      By the time the user taps "Closet" the data is already there.
 *   2. **Sticky on navigation**: returning to /closet does NOT trigger
 *      a full refetch. The page paints from the store immediately and
 *      runs an *incremental* sync (`?updated_after=<lastSync>`) in the
 *      background to pick up anything that changed elsewhere.
 *   3. **Mutation-aware**: when AddItem creates a card, ItemDetail
 *      edits a field, or Closet deletes selected items, those mutations
 *      patch the store directly so the UI reflects them without
 *      another round-trip.
 *
 * Implementation choice: a tiny pub/sub module (no Redux / Zustand).
 * The closet page subscribes via ``useClosetStore`` (a thin
 * ``useSyncExternalStore`` hook) and gets a stable snapshot on each
 * render. This keeps bundle size & cognitive overhead minimal — the
 * state is naturally global because there's exactly one logged-in
 * user and exactly one closet at a time.
 */

import { api } from '@/lib/api';

// Treat the store as fresh for this many ms after the last full
// fetch. Within that window /closet revisits don't trigger any
// network at all. Long enough that quick "tap closet → tap home → tap
// closet" loops feel instant; short enough that a multi-tab user gets
// reasonably current data.
const FRESH_MS = 5 * 60 * 1000; // 5 minutes

// Skip incremental syncs that fire too quickly (e.g. focus-blur-focus
// in 1 second). Avoids hammering the backend on iOS Safari where the
// page receives a focus event every time the address bar collapses.
const MIN_INCREMENTAL_SYNC_INTERVAL_MS = 30 * 1000;

const _state = {
  items: [],          // canonical list, sorted by created_at desc
  total: 0,
  lastFullSync: 0,    // epoch ms of the last full /closet fetch
  lastIncSync: 0,     // epoch ms of the last incremental sync
  loading: false,
  error: null,
};

const _listeners = new Set();
function _notify() {
  _listeners.forEach((fn) => {
    try { fn(); } catch { /* ignore */ }
  });
}

function _byCreatedDesc(a, b) {
  const ax = a?.created_at || '';
  const bx = b?.created_at || '';
  return ax < bx ? 1 : ax > bx ? -1 : 0;
}

// ----- Public API -----

export const closetStore = {
  /** Whole snapshot (used by useSyncExternalStore). */
  getSnapshot() {
    return _state;
  },

  subscribe(fn) {
    _listeners.add(fn);
    return () => _listeners.delete(fn);
  },

  /**
   * Eager full-fetch. Called from App.jsx right after the user signs
   * in / refreshes a logged-in session. Idempotent — safe to call any
   * number of times; it won't fetch again within the FRESH_MS window.
   */
  async prewarm({ force = false } = {}) {
    if (!force && _state.loading) return _state.items;
    if (!force && _state.lastFullSync && Date.now() - _state.lastFullSync < FRESH_MS) {
      return _state.items;
    }
    _state.loading = true;
    _state.error = null;
    _notify();
    try {
      const res = await api.listCloset({ limit: 2000 });
      const next = (res.items || []).slice().sort(_byCreatedDesc);
      _state.items = next;
      _state.total = res.total || next.length;
      _state.lastFullSync = Date.now();
      _state.lastIncSync = _state.lastFullSync;
      return next;
    } catch (err) {
      _state.error = err;
      throw err;
    } finally {
      _state.loading = false;
      _notify();
    }
  },

  /**
   * Incremental sync. Fetches only items whose ``updated_at`` is later
   * than our last sync, plus an ids-only call to detect deletions.
   * Designed to be called on focus/visibility events from the Closet
   * page — keeps the snapshot fresh without re-shipping multi-MB
   * thumbnails.
   *
   * Returns the number of items added/updated.
   */
  async incrementalSync() {
    if (!_state.lastFullSync) {
      // Never fully populated — incremental makes no sense yet.
      return this.prewarm();
    }
    if (Date.now() - _state.lastIncSync < MIN_INCREMENTAL_SYNC_INTERVAL_MS) {
      return 0;
    }
    const since = new Date(_state.lastIncSync).toISOString();
    try {
      // Run both in parallel — diffs (with thumbnails) + the
      // currently-existing IDs (cheap, used to detect deletions).
      const [diffRes, idsRes] = await Promise.all([
        api.listCloset({ limit: 2000, updated_after: since }),
        api.listCloset({ limit: 2000, ids_only: 1 }),
      ]);
      _state.lastIncSync = Date.now();

      const changedItems = diffRes?.items || [];
      const liveIds = new Set(idsRes?.ids || []);

      let mutations = 0;
      // 1) Apply upserts.
      if (changedItems.length) {
        const byId = new Map(_state.items.map((it) => [it.id, it]));
        for (const it of changedItems) {
          byId.set(it.id, { ...(byId.get(it.id) || {}), ...it });
        }
        _state.items = Array.from(byId.values()).sort(_byCreatedDesc);
        mutations += changedItems.length;
      }
      // 2) Drop anything that disappeared remotely.
      const before = _state.items.length;
      _state.items = _state.items.filter((it) => liveIds.has(it.id));
      const removed = before - _state.items.length;
      mutations += removed;
      _state.total = idsRes?.total || _state.items.length;

      if (mutations) _notify();
      return mutations;
    } catch (err) {
      // Soft-fail — keep the cached view rather than wiping it.
      // Logging at info level so it's visible in dev without being
      // noisy in prod.
      // eslint-disable-next-line no-console
      console.info('closet incremental sync failed', err?.message || err);
      return 0;
    }
  },

  /** Optimistic upsert. Used after a successful create/update. */
  upsert(item) {
    if (!item || !item.id) return;
    const idx = _state.items.findIndex((it) => it.id === item.id);
    if (idx >= 0) {
      const merged = { ..._state.items[idx], ...item };
      _state.items = [
        ..._state.items.slice(0, idx),
        merged,
        ..._state.items.slice(idx + 1),
      ].sort(_byCreatedDesc);
    } else {
      _state.items = [item, ..._state.items].sort(_byCreatedDesc);
      _state.total += 1;
    }
    _notify();
  },

  /** Optimistic delete. Used after a successful DELETE /closet/{id}. */
  remove(itemId) {
    if (!itemId) return;
    const before = _state.items.length;
    _state.items = _state.items.filter((it) => it.id !== itemId);
    if (_state.items.length !== before) {
      _state.total = Math.max(0, _state.total - (before - _state.items.length));
      _notify();
    }
  },

  /** Bulk replace — used by the page after a filtered/semantic search. */
  replaceAll(items, total) {
    _state.items = (items || []).slice().sort(_byCreatedDesc);
    _state.total = typeof total === 'number' ? total : _state.items.length;
    _state.lastFullSync = Date.now();
    _state.lastIncSync = _state.lastFullSync;
    _notify();
  },

  /** Hard reset — call on logout so the next user doesn't see stale data. */
  reset() {
    _state.items = [];
    _state.total = 0;
    _state.lastFullSync = 0;
    _state.lastIncSync = 0;
    _state.error = null;
    _notify();
  },
};
