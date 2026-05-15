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

// Phase Z2.3 — minimum gap between two consecutive ``repairHashes``
// passes. The repair is idempotent (a second pass right after a
// successful one reports every row as ``unchanged``), but it still
// streams the full closet through PIL on the server. 6 h is enough
// that a daily-active user gets one repair per session window, and
// a multi-tab refresh storm doesn't spam the endpoint.
const MIN_REPAIR_INTERVAL_MS = 6 * 60 * 60 * 1000;

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
  // Phase Z4 — optimistic "Save all" support. ``lastSaveFailures``
  // is a transient list of save-failure descriptors produced when
  // an optimistic upload to the closet couldn't be persisted on the
  // server. The Closet page reads this and renders a one-shot
  // warning dialog with the failed items' thumbnails + filenames so
  // the user knows exactly what didn't make it (instead of silently
  // disappearing from the optimistic view). Cleared by
  // ``dismissSaveFailures`` once the user acknowledges the dialog.
  lastSaveFailures: [],
  // Phase Z2.3 — live progress snapshot for the streaming
  // ``/closet/repair-hashes`` pass. Subscribers (e.g. the Closet
  // header chip) re-render as fields tick. ``running`` flips to
  // true the instant we POST; everything else fills in from the
  // NDJSON stream. When ``running`` returns to false, ``lastRunAt``
  // holds the epoch-ms timestamp of the most recent completion —
  // used by the auto-trigger to throttle re-runs.
  repairProgress: {
    running: false,
    scanned: 0,
    total: 0,
    repaired: 0,
    cleared: 0,
    failed: 0,
    lastRunAt: 0,
    lastError: null,
  },
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
      // Phase Z2.3 — fire-and-forget hash repair. We don't await
      // because (a) the closet UI must paint immediately from the
      // freshly-loaded snapshot, and (b) the repair pass can take
      // several seconds on a 300-item closet — the user shouldn't
      // see a spinner for that. Throttled by MIN_REPAIR_INTERVAL_MS
      // so a rapid prewarm → navigate → prewarm cycle doesn't spam
      // the endpoint.
      if (Date.now() - (_state.repairProgress?.lastRunAt || 0) >= MIN_REPAIR_INTERVAL_MS) {
        this.repairHashes().catch((err) => {
          // eslint-disable-next-line no-console
          console.info('closet hash repair failed (will retry next session)', err?.message || err);
        });
      }
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
      lastSaveFailures: [],
      repairProgress: {
        running: false,
        scanned: 0,
        total: 0,
        repaired: 0,
        cleared: 0,
        failed: 0,
        lastRunAt: 0,
        lastError: null,
      },
    });
  },

  /**
   * Phase Z2.3 — stream the server-side closet-hash repair pass and
   * splice each row's patch into the local store as it arrives.
   *
   * The repair endpoint emits an NDJSON stream of ``{type, ...}``
   * events; we forward per-row patches into ``upsert`` so the
   * duplicate detector starts seeing corrected hashes mid-stream
   * (no need to wait for the full pass to complete). The
   * ``repairProgress`` snapshot is updated on every event so a
   * subscribed UI chip can show "Tuning duplicate detector… 47/300"
   * live.
   *
   * Returns the final ``done`` summary object. Re-throws on
   * unrecoverable stream errors so callers can decide whether to
   * retry; the auto-trigger in ``prewarm`` deliberately catches
   * and downgrades to a console.info because a failed repair is
   * not a fatal app condition.
   */
  async repairHashes({ dryRun = false, onlyMissing = false } = {}) {
    if (_state.repairProgress?.running) {
      return null;  // already running — don't fan out concurrent passes
    }
    _set({
      repairProgress: {
        running: true,
        scanned: 0,
        total: 0,
        repaired: 0,
        cleared: 0,
        failed: 0,
        lastRunAt: _state.repairProgress?.lastRunAt || 0,
        lastError: null,
      },
    });
    try {
      const done = await api.repairClosetHashes({
        dryRun,
        onlyMissing,
        onEvent: (ev) => {
          if (!ev || typeof ev !== 'object') return;
          if (ev.type === 'start') {
            _set({
              repairProgress: {
                ..._state.repairProgress,
                running: true,
                scanned: 0,
                total: Number(ev.total) || 0,
                repaired: 0,
                cleared: 0,
                failed: 0,
                lastError: null,
              },
            });
            return;
          }
          if (ev.type === 'item') {
            // Splice the patch into the matching closet row so the
            // detector picks up the corrected hashes immediately —
            // no need to wait for the ``done`` event.
            if (ev.id && ev.patch && typeof ev.patch === 'object') {
              const items = _state.items;
              const idx = items.findIndex((it) => it.id === ev.id);
              if (idx >= 0) {
                const merged = { ...items[idx], ...ev.patch };
                const nextItems = [
                  ...items.slice(0, idx),
                  merged,
                  ...items.slice(idx + 1),
                ];
                _set({ items: nextItems });
              }
            }
            const p = _state.repairProgress || {};
            _set({
              repairProgress: {
                ...p,
                scanned: (p.scanned || 0) + 1,
                repaired: (p.repaired || 0) + (ev.status === 'repaired' ? 1 : 0),
                cleared: (p.cleared || 0) + (ev.status === 'cleared' ? 1 : 0),
                failed: (p.failed || 0) + (ev.status === 'failed' ? 1 : 0),
              },
            });
            return;
          }
          if (ev.type === 'done') {
            _set({
              repairProgress: {
                running: false,
                scanned: Number(ev.scanned) || 0,
                total: Number(ev.scanned) || 0,
                repaired: Number(ev.repaired) || 0,
                cleared: Number(ev.cleared) || 0,
                failed: Number(ev.failed) || 0,
                lastRunAt: Date.now(),
                lastError: null,
              },
            });
          }
        },
      });
      return done;
    } catch (err) {
      _set({
        repairProgress: {
          ..._state.repairProgress,
          running: false,
          lastRunAt: Date.now(),
          lastError: err?.message || String(err),
        },
      });
      throw err;
    }
  },

  /**
   * Phase Z4 — record one or more "Save all" failures so the Closet
   * page can surface a single dialog summarising what didn't sync.
   *
   * Each failure descriptor should carry at minimum:
   *   { id, title, filename, thumbnail, error }
   *
   * ``id`` is the optimistic UUID we used (purely identifying for
   * de-duplication if recordSaveFailures fires more than once on
   * the same batch). ``thumbnail`` is a data URL the dialog renders
   * inline so the user can recognise their photo without another
   * round-trip.
   */
  recordSaveFailures(failures) {
    if (!Array.isArray(failures) || failures.length === 0) return;
    const existing = _state.lastSaveFailures || [];
    const byId = new Map(existing.map((f) => [f.id, f]));
    for (const f of failures) {
      if (!f || !f.id) continue;
      byId.set(f.id, f);
    }
    _set({ lastSaveFailures: Array.from(byId.values()) });
  },

  /** Dismiss the save-failures dialog. Idempotent. */
  dismissSaveFailures() {
    if (!_state.lastSaveFailures || _state.lastSaveFailures.length === 0) {
      return;
    }
    _set({ lastSaveFailures: [] });
  },
};
