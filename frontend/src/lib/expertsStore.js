/**
 * expertsStore — cached list backing the /experts directory.
 *
 * The directory's filter set is small (profession, country, region,
 * free-text), and the underlying endpoint paginates server-side. We
 * cache up to 16 filter combinations under stale-while-revalidate so
 * navigating between Home / Closet / Experts feels instant.
 *
 * The prewarm fires the **default** view (no filters) at app boot —
 * that's the variant most users land on first. As soon as they apply
 * filters the page calls ``ensure`` itself.
 */

import { api } from '@/lib/api';
import { createCachedStore } from '@/lib/createCachedStore';

export const expertsStore = createCachedStore({
  name: 'experts-directory',
  staleAfterMs: 5 * 60 * 1000, // experts directory changes slowly
  fetcher: async (filters) => api.listProfessionals({
    limit: 40,
    ...filters,
  }),
});

export const DEFAULT_EXPERTS_FILTERS = Object.freeze({});

export async function prewarmExperts() {
  try {
    await expertsStore.prewarm(DEFAULT_EXPERTS_FILTERS);
  } catch { /* prewarm is best-effort */ }
}

export function resetExperts() {
  expertsStore.reset();
}
