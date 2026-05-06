/**
 * useClosetStore — thin React adapter over the singleton closet store.
 *
 * Returns a stable snapshot ({items, total, loading, error}) and
 * memoised mutators. Components can render directly from the
 * snapshot or reach back to ``closetStore`` for imperative ops.
 */
import { useSyncExternalStore, useEffect } from 'react';
import { closetStore } from '@/lib/closetStore';
import { useAuth } from '@/lib/auth';

export function useClosetStore({ prewarm = false } = {}) {
  const snap = useSyncExternalStore(
    closetStore.subscribe.bind(closetStore),
    closetStore.getSnapshot.bind(closetStore),
    closetStore.getSnapshot.bind(closetStore),
  );
  const { user } = useAuth();

  // Optional eager warm-up. Components that mount near the root (App)
  // pass ``prewarm: true`` to fire the initial fetch right after auth
  // resolves — *before* the user navigates to the Closet page.
  useEffect(() => {
    if (!prewarm || !user) return;
    closetStore.prewarm().catch(() => {});
  }, [prewarm, user]);

  return {
    items: snap.items,
    total: snap.total,
    loading: snap.loading,
    error: snap.error,
    lastFullSync: snap.lastFullSync,
    lastIncSync: snap.lastIncSync,
    // Imperative passthroughs so consumers don't need to import the
    // store separately.
    prewarm: closetStore.prewarm.bind(closetStore),
    incrementalSync: closetStore.incrementalSync.bind(closetStore),
    upsert: closetStore.upsert.bind(closetStore),
    remove: closetStore.remove.bind(closetStore),
    replaceAll: closetStore.replaceAll.bind(closetStore),
    reset: closetStore.reset.bind(closetStore),
  };
}
