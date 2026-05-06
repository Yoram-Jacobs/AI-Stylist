/**
 * createCachedStore — tiny factory for a "list endpoint" cache shared
 * across the app.
 *
 * Designed for pages whose data is naturally a list keyed by a small
 * filter object (Marketplace, Experts directory, future Trends feed,
 * etc.). Mirrors the same UX wins we built for the closet:
 *
 *   • **Eager prewarm** — App boot kicks ONE fetch with the default
 *     filters so the page paints instantly on first visit.
 *   • **Sticky on navigation** — switching tabs back and forth hits
 *     the in-memory cache; the page never re-fetches by accident.
 *   • **Stale-while-revalidate** — when the user comes back after
 *     ``staleAfterMs`` we paint the cached snapshot first, then
 *     silently refresh.
 *   • **Mutation-aware** — pages can call ``invalidate()`` after a
 *     write so the next read pulls fresh data.
 *
 * Implementation notes
 *   * Uses a tiny pub/sub + ``useSyncExternalStore`` so React picks
 *     up changes without forcing every consumer to memoise their
 *     filter objects.
 *   * Bounded LRU (default 16 entries). Filter combinations are few
 *     in practice; this keeps memory bounded even for very long
 *     sessions.
 *   * Keys are produced via a stable JSON.stringify with sorted keys
 *     so ``{a:1,b:2}`` and ``{b:2,a:1}`` hit the same cache slot.
 */

import { useSyncExternalStore } from 'react';

const _stableKey = (obj) => {
  if (!obj || typeof obj !== 'object') return String(obj ?? '');
  const sorted = {};
  Object.keys(obj).sort().forEach((k) => {
    const v = obj[k];
    if (v == null || v === '') return;
    sorted[k] = v;
  });
  return JSON.stringify(sorted);
};

/**
 * @param {object} opts
 * @param {(filters: object) => Promise<{items: any[], total: number}>} opts.fetcher
 * @param {number} [opts.staleAfterMs=120000]   2 min stale window
 * @param {number} [opts.cacheLimit=16]         LRU max entries
 * @param {string} [opts.name='cached-store']   debug label
 * @returns
 */
export function createCachedStore({
  fetcher,
  staleAfterMs = 2 * 60 * 1000,
  cacheLimit = 16,
  name = 'cached-store',
}) {
  // Map<key, {items, total, ts, inflight?: Promise}>
  const cache = new Map();
  const listeners = new Set();
  let initialised = false;

  const _notify = () => {
    listeners.forEach((fn) => {
      try { fn(); } catch { /* ignore */ }
    });
  };

  const _touch = (key) => {
    // LRU touch — re-insert so iteration order keeps it newest.
    const v = cache.get(key);
    if (v) {
      cache.delete(key);
      cache.set(key, v);
    }
    // Evict oldest entries when over the limit.
    while (cache.size > cacheLimit) {
      const oldest = cache.keys().next().value;
      cache.delete(oldest);
    }
  };

  const get = (filters) => cache.get(_stableKey(filters));

  const isFresh = (entry) =>
    !!entry && Date.now() - (entry.ts || 0) < staleAfterMs;

  const ensure = async (filters, { force = false } = {}) => {
    const key = _stableKey(filters);
    const existing = cache.get(key);
    if (!force && existing && existing.inflight) return existing.inflight;
    if (!force && isFresh(existing)) return existing;

    // Fire the network call. We stash the promise in the cache slot
    // so concurrent callers de-dupe to the same in-flight request.
    const inflight = (async () => {
      try {
        const res = await fetcher(filters);
        const items = res?.items || [];
        const total = typeof res?.total === 'number' ? res.total : items.length;
        cache.set(key, { items, total, ts: Date.now() });
        _touch(key);
        _notify();
        return { items, total };
      } catch (err) {
        // Don't poison the cache on failure; let the next call retry.
        const slot = cache.get(key);
        if (slot && slot.inflight === inflight) {
          delete slot.inflight;
        }
        throw err;
      }
    })();

    // Stash inflight on the existing/new slot so concurrent callers wait.
    const slot = cache.get(key) || { items: [], total: 0, ts: 0 };
    slot.inflight = inflight;
    cache.set(key, slot);
    return inflight;
  };

  const upsertItem = (filters, item) => {
    if (!item || !item.id) return;
    const key = _stableKey(filters);
    const slot = cache.get(key);
    if (!slot) return;
    const idx = slot.items.findIndex((it) => it.id === item.id);
    if (idx >= 0) {
      slot.items = [
        ...slot.items.slice(0, idx),
        { ...slot.items[idx], ...item },
        ...slot.items.slice(idx + 1),
      ];
    } else {
      slot.items = [item, ...slot.items];
      slot.total += 1;
    }
    _notify();
  };

  const removeItem = (filters, itemId) => {
    if (!itemId) return;
    const key = _stableKey(filters);
    const slot = cache.get(key);
    if (!slot) return;
    const before = slot.items.length;
    slot.items = slot.items.filter((it) => it.id !== itemId);
    if (slot.items.length !== before) {
      slot.total = Math.max(0, slot.total - 1);
      _notify();
    }
  };

  const invalidate = (filters) => {
    if (filters === undefined) {
      cache.clear();
    } else {
      cache.delete(_stableKey(filters));
    }
    _notify();
  };

  const subscribe = (fn) => {
    listeners.add(fn);
    return () => listeners.delete(fn);
  };

  // Tiny token used by useSyncExternalStore to detect changes.
  const getSnapshotToken = () => {
    // Hash size + most-recent ts so any insertion / refresh notifies.
    let hash = cache.size;
    for (const v of cache.values()) hash = hash * 31 + (v.ts || 0);
    return hash;
  };

  const prewarm = async (filters) => {
    if (initialised) return get(filters);
    initialised = true;
    try {
      return await ensure(filters);
    } catch {
      // Swallow — prewarm is best-effort. Failures will surface on
      // the next page-driven call.
      initialised = false;
      return null;
    }
  };

  const reset = () => {
    cache.clear();
    initialised = false;
    _notify();
  };

  return {
    name,
    get,
    isFresh,
    ensure,
    prewarm,
    upsertItem,
    removeItem,
    invalidate,
    subscribe,
    getSnapshotToken,
    reset,
  };
}

/**
 * Tiny React adapter — call inside a component to subscribe and get
 * a stable {items, total, loading, error} for the supplied filters.
 *
 * Fires ``ensure(filters)`` on mount and whenever the stable filter
 * key changes.
 */
export function useCachedList(store, filters, { revalidateOnMount = true } = {}) {
  // Subscribe to the store so re-renders happen on cache mutations.
  useSyncExternalStore(
    store.subscribe,
    store.getSnapshotToken,
    store.getSnapshotToken,
  );

  const entry = store.get(filters);
  const items = entry?.items || [];
  const total = entry?.total || 0;
  const fresh = store.isFresh(entry);
  const loading = !!entry?.inflight && items.length === 0;
  const refreshing = !!entry?.inflight && items.length > 0;

  // Lazy revalidate. We can't useEffect here because that'd require
  // a stable filter object per call — instead we just fire-and-forget
  // the ensure() call. Stale-while-revalidate semantics: returns
  // cached data immediately and quietly refreshes in the background.
  if (revalidateOnMount && (!entry || !fresh)) {
    // Don't await — render with whatever we already have.
    store.ensure(filters).catch(() => {});
  }

  return { items, total, loading, refreshing, ensure: () => store.ensure(filters, { force: true }) };
}
