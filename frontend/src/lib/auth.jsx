import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api, tokenStore, userStore } from '@/lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => userStore.get());
  const [loading, setLoading] = useState(Boolean(tokenStore.get()) && !userStore.get());

  const refresh = useCallback(async () => {
    if (!tokenStore.get()) {
      setUser(null);
      return null;
    }
    try {
      const me = await api.getMe();
      setUser(me);
      userStore.set(me);
      return me;
    } catch {
      tokenStore.clear();
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    if (tokenStore.get() && !userStore.get()) {
      refresh().finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [refresh]);

  const login = async (email, password) => {
    const res = await api.login({ email, password });
    tokenStore.set(res.access_token);
    userStore.set(res.user);
    setUser(res.user);
    return res.user;
  };

  const register = async (body) => {
    const res = await api.register(body);
    tokenStore.set(res.access_token);
    userStore.set(res.user);
    setUser(res.user);
    return res.user;
  };

  const devBypass = async () => {
    const res = await api.devBypass();
    tokenStore.set(res.access_token);
    userStore.set(res.user);
    setUser(res.user);
    return res.user;
  };

  const logout = () => {
    tokenStore.clear();
    setUser(null);
  };

  const updateUserLocal = (patch) => {
    const next = { ...(user || {}), ...patch };
    setUser(next);
    userStore.set(next);
  };

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, devBypass, logout, refresh, updateUserLocal }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
