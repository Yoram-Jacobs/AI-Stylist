/**
 * marketplaceStore — browse + my-listings caches for /market.
 *
 * We split the marketplace traffic into two cached stores because the
 * data shape differs:
 *
 *   • ``browseStore``     — public Active listings, filtered by source /
 *                           category / radius / geo. Used by /market
 *                           Browse tab. Filter combinations are few
 *                           (LRU 16) so memory stays bounded even for
 *                           long sessions.
 *   • ``myListingsStore`` — the current user's own listings (status
 *                           regardless of state), used by the
 *                           /market My Listings tab. Single key.
 *
 * Both expose the same surface as the closet store — prewarm on
 * AppLayout, ensure on page mount, mutation helpers (``upsertItem``
 * / ``removeItem``) for create / delete flows.
 *
 * Phase Z2.4 — server → client streaming.
 * =======================================
 * Two surfaces below participate in the streaming-progress pattern
 * established by the closet hash-repair endpoint:
 *
 *   1. ``streamBrowse(filters)`` — opens ``GET /listings/stream`` and
 *      upserts each incoming listing into the matching ``browseStore``
 *      slot, so the marketplace grid paints cards progressively
 *      instead of all-at-once at the end of the request. The cached
 *      store's existing slot semantics + ``useCachedList`` hook are
 *      reused unchanged.
 *
 *   2. ``streamBackfill()`` — opens ``POST /closet/marketplace/backfill/stream``
 *      and emits one event per candidate. Powers the "Sync from
 *      closet" UX in the My Listings tab so the user sees
 *      "Listed 12/47" tick live instead of a multi-second
 *      "Syncing…" spinner.
 *
 * Both methods drive a small pub/sub progress snapshot
 * (``browseProgress`` / ``backfillProgress``) consumed by
 * ``StreamingProgressChip`` wrappers next to their respective UI
 * actions. The cached stores themselves stay generic — only
 * marketplace-specific orchestration lives here.
 */

import { api } from '@/lib/api';
import { createCachedStore } from '@/lib/createCachedStore';

export const browseStore = createCachedStore({
  name: 'marketplace-browse',
  staleAfterMs: 90 * 1000, // browse moves quickly; revalidate after 90s
  fetcher: async (filters) => api.listListings({
    status: 'active',
    limit: 50,
    ...filters,
  }),
});

export const myListingsStore = createCachedStore({
  name: 'marketplace-mine',
  staleAfterMs: 60 * 1000,
  fetcher: async (filters) => api.listListings({
    limit: 50,
    ...filters,
  }),
});

/**
 * Default browse filter for the prewarm. We deliberately don't
 * include radius / geo here — those vary per session and per user,
 * so we let the page request its own variant on mount. The default
 * "all sources, all categories" view is what most users land on
 * anyway, and the prewarm makes the first paint instant for them.
 */
export const DEFAULT_BROWSE_FILTERS = Object.freeze({});

export async function prewarmMarketplace(userId) {
  // Fire both prewarms in parallel — they hit the same endpoint with
  // different query params so the network can pipeline them.
  return Promise.allSettled([
    browseStore.prewarm(DEFAULT_BROWSE_FILTERS),
    userId
      ? myListingsStore.prewarm({ seller_id: userId })
      : Promise.resolve(null),
  ]);
}

export function resetMarketplace() {
  browseStore.reset();
  myListingsStore.reset();
  // Phase Z2.4 — also wipe transient streaming progress on logout
  // so the next user doesn't briefly see the previous user's "12
  // listed" success chip.
  marketplaceProgress.reset();
}

// ─────────────────────────────────────────────────────────────────────
// Phase Z2.4 — streaming progress pub/sub
// ─────────────────────────────────────────────────────────────────────
// A second, very small store dedicated to the live progress snapshots
// for the two streaming surfaces. Kept separate from the cached
// content stores because:
//   * The lifecycle is different (progress is transient; cache slots
//     persist across navigations).
//   * The cached stores are deliberately generic — adding a
//     "progress" concept to ``createCachedStore`` would muddy the
//     primitive for every other consumer (closet, experts, …).
//   * Components that only care about the chip don't have to depend
//     on the (much heavier) listings cache.
//
// Snapshot shape mirrors the closet's ``repairProgress`` so the
// reusable ``StreamingProgressChip`` can render it without
// per-domain knowledge.
const _initialProgress = {
  browse: {
    running: false,
    scanned: 0,
    total: 0,
    failed: 0,
    lastRunAt: 0,
    lastError: null,
    geo: false,
  },
  backfill: {
    running: false,
    scanned: 0,
    total: 0,
    created: 0,
    skipped: 0,
    source_synced: 0,
    failed: 0,
    lastRunAt: 0,
    lastError: null,
  },
};

let _progressState = JSON.parse(JSON.stringify(_initialProgress));
const _progressListeners = new Set();
function _notifyProgress() {
  _progressListeners.forEach((fn) => {
    try { fn(); } catch { /* ignore */ }
  });
}
function _setProgress(domain, patch) {
  _progressState = {
    ..._progressState,
    [domain]: { ..._progressState[domain], ...patch },
  };
  _notifyProgress();
}

// Per-domain in-flight controllers so a new stream call can abort
// the previous one. Without this, switching marketplace filters
// rapidly would leave several streams writing into different cache
// slots while the user's grid renders whichever one happens to
// flush last. The closet's repair stream doesn't need this because
// it only ever runs once per session window; the marketplace
// browse stream can fire repeatedly as filters change.
const _streamControllers = {
  browse: null,
  backfill: null,
};

export const marketplaceProgress = {
  getSnapshot: () => _progressState,
  subscribe: (fn) => {
    _progressListeners.add(fn);
    return () => _progressListeners.delete(fn);
  },
  reset: () => {
    // Cancel any in-flight streams before wiping state — otherwise
    // a logged-out user could still see late-arriving items from
    // their previous session bleed into the next user's view.
    Object.values(_streamControllers).forEach((c) => {
      try { c?.abort(); } catch { /* ignore */ }
    });
    _streamControllers.browse = null;
    _streamControllers.backfill = null;
    _progressState = JSON.parse(JSON.stringify(_initialProgress));
    _notifyProgress();
  },

  /**
   * Stream the browse listings into ``browseStore`` for the given
   * filter combination. Items are upserted as they arrive so the
   * marketplace grid (which subscribes via ``useCachedList``) paints
   * progressively. Resolves with the final ``{type:'done', emitted}``
   * summary from the stream.
   *
   * Cancellation
   * ------------
   * Calling this again before the previous stream finishes aborts
   * the previous one. This is the right behaviour for filter
   * changes — the previous stream's results are no longer relevant
   * the moment the user picks a different category / radius.
   * Callers may also pass their own ``signal`` (e.g. from a React
   * cleanup function); both signals are honoured.
   */
  async streamBrowse(filters, { signal: externalSignal } = {}) {
    // Abort any prior browse stream — its results are stale by
    // definition because the new call has different filters (or
    // the same filters but we're explicitly refreshing).
    try { _streamControllers.browse?.abort(); } catch { /* ignore */ }
    const controller = new AbortController();
    _streamControllers.browse = controller;
    if (externalSignal) {
      if (externalSignal.aborted) controller.abort();
      else externalSignal.addEventListener('abort', () => {
        try { controller.abort(); } catch { /* ignore */ }
      }, { once: true });
    }

    _setProgress('browse', {
      running: true,
      scanned: 0,
      total: 0,
      failed: 0,
      lastError: null,
      geo: false,
    });

    // IMPORTANT — we DELIBERATELY do not ``browseStore.invalidate``
    // up front. The previous implementation cleared the slot at
    // stream start, which produced a "Nothing matching yet" empty
    // state if the stream was aborted before the first item
    // arrived (a common case: location coords resolve a few hundred
    // ms after the page mounts, which mutates ``browseParams`` and
    // aborts the in-flight stream). By holding the existing items
    // until we've seen at least one fresh item, the grid stays
    // populated across rapid filter / coord changes.
    //
    // Instead, we track ``seenIds`` and, on a successful ``done``
    // event, prune any items whose id wasn't emitted by this
    // stream — i.e. the diff between "what we had before" and
    // "what the server says now". Aborts skip the prune entirely
    // so the previous, non-stale subset survives.
    const seenIds = new Set();

    try {
      const done = await api.streamListings({
        params: { status: 'active', limit: 50, ...filters },
        signal: controller.signal,
        onEvent: (ev) => {
          if (!ev || typeof ev !== 'object') return;
          if (ev.type === 'start') {
            _setProgress('browse', {
              total: Number(ev.total) || 0,
              geo: !!ev.geo,
            });
            return;
          }
          if (ev.type === 'item' && ev.data && ev.data.id) {
            seenIds.add(ev.data.id);
            browseStore.upsertItem(filters, ev.data);
            _setProgress('browse', {
              scanned: (_progressState.browse.scanned || 0) + 1,
            });
            return;
          }
          if (ev.type === 'done') {
            // Atomically prune items the server no longer returns
            // for this filter set. ``upsertItem`` mutated the slot
            // in-place; here we just remove anything whose id
            // wasn't streamed.
            const slot = browseStore.get(filters);
            if (slot && Array.isArray(slot.items)) {
              const stale = slot.items
                .filter((it) => !seenIds.has(it.id))
                .map((it) => it.id);
              stale.forEach((id) => browseStore.removeItem(filters, id));
            }
            _setProgress('browse', {
              running: false,
              lastRunAt: Date.now(),
            });
          }
        },
      });
      if (_streamControllers.browse === controller) {
        _streamControllers.browse = null;
      }
      return done;
    } catch (err) {
      const aborted =
        err?.name === 'AbortError' ||
        err?.message === 'AbortError' ||
        controller.signal.aborted;
      _setProgress('browse', {
        running: false,
        lastRunAt: Date.now(),
        lastError: aborted ? null : (err?.message || String(err)),
      });
      if (_streamControllers.browse === controller) {
        _streamControllers.browse = null;
      }
      if (aborted) return null;
      throw err;
    }
  },

  /**
   * Stream the marketplace backfill — auto-list any closet items
   * whose ``marketplace_intent`` is set but never made it onto the
   * marketplace. Emits per-candidate events so the UI can show
   * "Listed 5/12 · Skipped 2" tick live.
   *
   * On completion, invalidates both ``browseStore`` and
   * ``myListingsStore`` so the next read picks up the freshly
   * created listings.
   */
  async streamBackfill({ onItem } = {}) {
    if (_progressState.backfill.running) return null;
    _setProgress('backfill', {
      running: true,
      scanned: 0,
      total: 0,
      created: 0,
      skipped: 0,
      source_synced: 0,
      failed: 0,
      lastError: null,
    });
    try {
      const done = await api.streamMarketplaceBackfill({
        onEvent: (ev) => {
          if (!ev || typeof ev !== 'object') return;
          if (ev.type === 'start') {
            _setProgress('backfill', {
              total: Number(ev.total) || 0,
            });
            return;
          }
          if (ev.type === 'item') {
            // Per-item callback lets the caller (page) wire a toast
            // for failures without subscribing to the snapshot.
            try { onItem?.(ev); } catch { /* ignore */ }
            const p = _progressState.backfill;
            const inc = ev.status === 'created' ? { created: (p.created || 0) + 1 }
              : ev.status === 'skipped' ? { skipped: (p.skipped || 0) + 1 }
              : ev.status === 'source_synced' ? { source_synced: (p.source_synced || 0) + 1 }
              : ev.status === 'failed' ? { failed: (p.failed || 0) + 1 }
              : {};
            _setProgress('backfill', {
              scanned: (p.scanned || 0) + 1,
              ...inc,
            });
            return;
          }
          if (ev.type === 'done') {
            _setProgress('backfill', {
              running: false,
              lastRunAt: Date.now(),
            });
          }
        },
      });
      // Bust both caches so the next render shows the new listings.
      browseStore.invalidate();
      myListingsStore.invalidate();
      return done;
    } catch (err) {
      _setProgress('backfill', {
        running: false,
        lastRunAt: Date.now(),
        lastError: err?.message || String(err),
      });
      throw err;
    }
  },
};
