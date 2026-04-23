/**
 * LocationProvider — centralises device geolocation + permission state and
 * optionally persists the coords to the authenticated user's profile.
 *
 * The web has no native-app-style "first run" lifecycle, so we approximate
 * it with a `localStorage` flag per device. Components can use the
 * `LocationBanner` to show a soft in-app rationale before we trigger the
 * browser permission prompt — matching the UX users expect on mobile.
 *
 * When the app is eventually wrapped with Capacitor/Expo, the same hook
 * interface maps 1:1 onto the native plugin, so UI code does not need to
 * change.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { api } from '@/lib/api';

const LocationContext = createContext(null);

const STORAGE_KEY = 'dressapp.location.v1';
// When the user has never opened the location prompt on this device, we
// record it here so we don't nag them across every page.
const PROMPT_FLAG_KEY = 'dressapp.location.promptedAt.v1';

const loadCached = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

const saveCached = (value) => {
  try {
    if (value) localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* quota / private mode — ignore */
  }
};

/**
 * Reverse-geocode via OpenStreetMap Nominatim. We round coordinates to ~1km
 * granularity for the cache key to keep the request count low and honor the
 * service's fair-use policy. No API key required.
 */
const reverseGeocode = async (lat, lng) => {
  try {
    const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat.toFixed(
      2,
    )}&lon=${lng.toFixed(2)}&zoom=10&addressdetails=1&accept-language=${
      navigator.language || 'en'
    }`;
    const res = await fetch(url, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) return null;
    const json = await res.json();
    const addr = json?.address || {};
    return {
      city:
        addr.city ||
        addr.town ||
        addr.village ||
        addr.municipality ||
        addr.county ||
        null,
      region: addr.state || addr.region || null,
      country: addr.country || null,
      country_code: (addr.country_code || '').toUpperCase() || null,
    };
  } catch {
    return null;
  }
};

export function LocationProvider({ children }) {
  const cached = loadCached();
  const [state, setState] = useState({
    coords: cached?.coords || null,
    accuracy_m: cached?.accuracy_m || null,
    city: cached?.city || null,
    country: cached?.country || null,
    country_code: cached?.country_code || null,
    lastUpdatedAt: cached?.lastUpdatedAt || null,
    permissionState: 'unknown',
    available: typeof navigator !== 'undefined' && !!navigator.geolocation,
  });

  // Probe the Permissions API non-intrusively so the UI knows whether to
  // show the soft rationale or immediately reflect a granted/denied state.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!navigator.permissions?.query) {
        setState((s) => ({
          ...s,
          permissionState: state.coords ? 'granted' : 'prompt',
        }));
        return;
      }
      try {
        const status = await navigator.permissions.query({ name: 'geolocation' });
        if (cancelled) return;
        setState((s) => ({ ...s, permissionState: status.state }));
        status.onchange = () => {
          setState((s) => ({ ...s, permissionState: status.state }));
        };
      } catch {
        setState((s) => ({ ...s, permissionState: 'prompt' }));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const persistToServer = useCallback(async (payload) => {
    try {
      await api.patchMe({
        home_location: {
          lat: payload.coords.lat,
          lng: payload.coords.lng,
          city: payload.city || null,
          country: payload.country || null,
          country_code: payload.country_code || null,
          updated_at: payload.lastUpdatedAt,
        },
      });
    } catch {
      // Profile may be unauthenticated on the login page — swallow silently.
    }
  }, []);

  /**
   * Ask the browser for the user's current position. Shows the native
   * permission prompt if required. Resolves with the new state payload on
   * success; rejects with a typed error on failure.
   */
  const request = useCallback(
    ({ persist = true } = {}) =>
      new Promise((resolve, reject) => {
        if (!navigator.geolocation) {
          setState((s) => ({ ...s, permissionState: 'unavailable' }));
          reject(new Error('unavailable'));
          return;
        }
        try {
          localStorage.setItem(PROMPT_FLAG_KEY, String(Date.now()));
        } catch {
          /* ignore */
        }
        navigator.geolocation.getCurrentPosition(
          async (pos) => {
            const coords = {
              lat: pos.coords.latitude,
              lng: pos.coords.longitude,
            };
            const payload = {
              coords,
              accuracy_m: pos.coords.accuracy || null,
              city: null,
              country: null,
              country_code: null,
              lastUpdatedAt: new Date().toISOString(),
            };
            // Best-effort reverse geocode (non-blocking for the UI state update).
            const geo = await reverseGeocode(coords.lat, coords.lng);
            if (geo) Object.assign(payload, geo);
            setState((s) => ({
              ...s,
              ...payload,
              permissionState: 'granted',
            }));
            saveCached(payload);
            if (persist) persistToServer(payload);
            resolve(payload);
          },
          (err) => {
            setState((s) => ({
              ...s,
              permissionState: err.code === 1 ? 'denied' : s.permissionState,
            }));
            reject(err);
          },
          { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 },
        );
      }),
    [persistToServer],
  );

  const forget = useCallback(async () => {
    saveCached(null);
    setState((s) => ({
      ...s,
      coords: null,
      accuracy_m: null,
      city: null,
      country: null,
      country_code: null,
      lastUpdatedAt: null,
    }));
    try {
      await api.patchMe({ home_location: null });
    } catch {
      /* ignore */
    }
  }, []);

  const shouldPrompt = useCallback(() => {
    if (!state.available) return false;
    if (state.coords) return false;
    if (state.permissionState === 'denied') return false;
    try {
      return !localStorage.getItem(PROMPT_FLAG_KEY);
    } catch {
      return true;
    }
  }, [state.available, state.coords, state.permissionState]);

  const dismissPrompt = useCallback(() => {
    try {
      localStorage.setItem(PROMPT_FLAG_KEY, String(Date.now()));
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(
    () => ({ ...state, request, forget, shouldPrompt, dismissPrompt }),
    [state, request, forget, shouldPrompt, dismissPrompt],
  );

  return (
    <LocationContext.Provider value={value}>
      {children}
    </LocationContext.Provider>
  );
}

export function useLocation() {
  const ctx = useContext(LocationContext);
  if (!ctx) {
    throw new Error('useLocation must be used within <LocationProvider>');
  }
  return ctx;
}
