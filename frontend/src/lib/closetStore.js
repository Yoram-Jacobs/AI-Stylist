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

// We hold the canonical snapshot in a single mutable variable but
// **never** mutate the object's properties in place. Every state
// transition replaces ``_state`` with a fresh object reference so
// ``useSyncExternalStore`` consumers (which compare snapshots via
// ``Object.is``) see the change and re-render. Mutators below all
// go through ``_set`` for this reason.
let _state = {
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

/**
 * Replace ``_state`` with a shallow-merged copy and notify
 * subscribers. Always supply the *complete* delta you want to apply
 * — partial keys merge into the previous snapshot.
 */
function _set(patch) {
  _state = { ..._state, ...patch };
  _notify();
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
    _set({ loading: true, error: null });
    try {
      const res = await api.listCloset({ limit: 2000 });
      const next = (res.items || []).slice().sort(_byCreatedDesc);
      const now = Date.now();
      _set({
        items: next,
        total: res.total || next.length,
        lastFullSync: now,
        lastIncSync: now,
      });
      return next;
    } catch (err) {
      _set({ error: err });
      throw err;
    } finally {
      _set({ loading: false });
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

      const changedItems = diffRes?.items || [];
      const liveIds = new Set(idsRes?.ids || []);

      // Build the next items list off the current snapshot. We avoid
      // mutating _state until we have the final shape, then publish
      // it in a single _set() call.
      let nextItems = _state.items;
      let mutations = 0;
      if (changedItems.length) {
        const byId = new Map(nextItems.map((it) => [it.id, it]));
        for (const it of changedItems) {
          byId.set(it.id, { ...(byId.get(it.id) || {}), ...it });
        }
        nextItems = Array.from(byId.values()).sort(_byCreatedDesc);
        mutations += changedItems.length;
      }
      const beforeCount = nextItems.length;
      nextItems = nextItems.filter((it) => liveIds.has(it.id));
      const removed = beforeCount - nextItems.length;
      mutations += removed;

      _set({
        items: mutations ? nextItems : _state.items,
        total: idsRes?.total || nextItems.length,
        lastIncSync: Date.now(),
      });
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
    const items = _state.items;
    const idx = items.findIndex((it) => it.id === item.id);
    let nextItems;
    let nextTotal = _state.total;
    if (idx >= 0) {
      const merged = { ...items[idx], ...item };
      nextItems = [
        ...items.slice(0, idx),
        merged,
        ...items.slice(idx + 1),
      ].sort(_byCreatedDesc);
    } else {
      nextItems = [item, ...items].sort(_byCreatedDesc);
      nextTotal = _state.total + 1;
    }
    _set({ items: nextItems, total: nextTotal });
  },

  /** Optimistic delete. Used after a successful DELETE /closet/{id}. */
  remove(itemId) {
    if (!itemId) return;
    const before = _state.items.length;
    const nextItems = _state.items.filter((it) => it.id !== itemId);
    if (nextItems.length !== before) {
      _set({
        items: nextItems,
        total: Math.max(0, _state.total - (before - nextItems.length)),
      });
    }
  },

  /** Bulk replace — used by the page after a filtered/semantic search. */
  replaceAll(items, total) {
    const sorted = (items || []).slice().sort(_byCreatedDesc);
    const now = Date.now();
    _set({
      items: sorted,
      total: typeof total === 'number' ? total : sorted.length,
      lastFullSync: now,
      lastIncSync: now,
    });
  },

  /** Hard reset — call on logout so the next user doesn't see stale data. */
  reset() {
    _set({
      items: [],
      total: 0,
      lastFullSync: 0,
      lastIncSync: 0,
      error: null,
    });
  },
};
