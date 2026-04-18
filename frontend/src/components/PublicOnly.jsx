import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '@/lib/auth';

export const PublicOnly = () => {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user) return <Navigate to="/home" replace />;
  return <Outlet />;
};
