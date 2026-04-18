import { Outlet, Navigate } from 'react-router-dom';
import { TopNav } from '@/components/TopNav';
import { BottomTabs } from '@/components/BottomTabs';
import { useAuth } from '@/lib/auth';
import { Loader2 } from 'lucide-react';

export const AppLayout = () => {
  const { user, loading } = useAuth();
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
      <TopNav />
      <main className="flex-1 pb-safe-tabs md:pb-10">
        <Outlet />
      </main>
      <BottomTabs />
    </div>
  );
};
