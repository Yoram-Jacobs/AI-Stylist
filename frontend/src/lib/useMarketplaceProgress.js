/**
 * useMarketplaceProgress — React adapter over the singleton
 * ``marketplaceProgress`` pub/sub in ``marketplaceStore.js``.
 *
 * Returns a stable snapshot ``{browse, backfill}`` plus the two
 * stream-drive methods so a component can do everything from a
 * single import:
 *
 *     const { backfill, streamBackfill } = useMarketplaceProgress();
 *     <Button onClick={streamBackfill}>Sync</Button>
 *     <StreamingProgressChip progress={backfill} ... />
 */
import { useSyncExternalStore } from 'react';
import { marketplaceProgress } from '@/lib/marketplaceStore';

export function useMarketplaceProgress() {
  const snap = useSyncExternalStore(
    marketplaceProgress.subscribe.bind(marketplaceProgress),
    marketplaceProgress.getSnapshot.bind(marketplaceProgress),
    marketplaceProgress.getSnapshot.bind(marketplaceProgress),
  );
  return {
    browse: snap.browse,
    backfill: snap.backfill,
    streamBrowse: marketplaceProgress.streamBrowse.bind(marketplaceProgress),
    streamBackfill: marketplaceProgress.streamBackfill.bind(marketplaceProgress),
    reset: marketplaceProgress.reset.bind(marketplaceProgress),
  };
}
