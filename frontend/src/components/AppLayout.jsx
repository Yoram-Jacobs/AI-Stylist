import { Outlet, Navigate } from 'react-router-dom';
import { useEffect } from 'react';
import { TopNav } from '@/components/TopNav';
import { BottomTabs } from '@/components/BottomTabs';
import { LanguageSync } from '@/components/LanguageSync';
import { LocationBanner } from '@/components/LocationBanner';
import { useAuth } from '@/lib/auth';
import { closetStore } from '@/lib/closetStore';
import { Loader2 } from 'lucide-react';

export const AppLayout = () => {
  const { user, loading } = useAuth();

  // Eager closet warm-up.
  //
  // We fire ONE /closet fetch the moment auth resolves, **before**
  // the user navigates anywhere. By the time they tap "Closet" the
  // store is already hydrated and the page paints instantly. The
  // prewarm is idempotent — Closet.jsx's own ``useClosetStore`` won't
  // double-fire it within the FRESH_MS window.
  //
  // We also reset the store on logout so a different user's data
  // never leaks across sessions on the same browser.
  useEffect(() => {
    if (loading) return;
    if (user) {
      closetStore.prewarm().catch(() => {});
    } else {
      closetStore.reset();
    }
  }, [user, loading]);

  if (loading) {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;

  return (
    <div className="page-shell">
      <LanguageSync />
      <TopNav />
      <LocationBanner />
      <main id="main-content" tabIndex={-1} className="flex-1 pb-safe-tabs md:pb-10">
        <Outlet />
      </main>
      <BottomTabs />
    </div>
  );
};
