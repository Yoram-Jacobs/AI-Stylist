/**
 * marketplaceStore — browse + my-listings caches for /market.
 *
 * We split the marketplace traffic into two stores because the data
 * shape differs:
 *
 *   • ``browseStore``  — public Active listings, filtered by source /
 *                        category / radius / geo. Used by /market
 *                        Browse tab. Filter combinations are few
 *                        (LRU 16) so memory stays bounded even for
 *                        long sessions.
 *   • ``myListingsStore`` — the current user's own listings (status
 *                          regardless of state), used by the
 *                          /market My Listings tab. Single key.
 *
 * Both expose the same surface as the closet store — prewarm on
 * AppLayout, ensure on page mount, mutation helpers (``upsertItem``
 * / ``removeItem``) for create / delete flows.
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
}
