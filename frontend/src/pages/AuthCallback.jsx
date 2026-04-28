import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Loader2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { tokenStore, userStore } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { toast } from 'sonner';

/**
 * Lands the browser after Google OAuth sign-in. The backend redirects here
 * with a URL hash fragment carrying the freshly minted DressApp JWT, e.g.
 *
 *     /auth/callback#token=ey...&next=/home
 *     /auth/callback#error=token_exchange_failed
 *     /auth/callback#token=ey...&next=/home&warning=calendar_persist_failed
 *
 * We:
 *   1. parse the fragment (never the query string — keeps the JWT out of
 *      every reverse-proxy access log)
 *   2. persist the token + fetch /me
 *   3. surface a success / warning / error toast
 *   4. redirect into the app
 */
export default function AuthCallback() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const { refresh } = useAuth();
  const [error, setError] = useState(null);
  const ranRef = useRef(false); // StrictMode double-invoke guard

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    const hash = window.location.hash || '';
    const params = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash);
    const token = params.get('token');
    const next = params.get('next') || '/home';
    const errCode = params.get('error');
    const warning = params.get('warning');

    const safeNext = next.startsWith('/') && !next.startsWith('//') ? next : '/home';

    if (errCode) {
      setError(errCode);
      return;
    }
    if (!token) {
      setError('missing_token');
      return;
    }

    // 1) Store token, 2) fetch user, 3) toast, 4) redirect.
    tokenStore.set(token);
    userStore.set(null); // force a fresh /me on the AuthProvider refresh
    refresh()
      .then((u) => {
        if (!u) {
          setError('session_failed');
          tokenStore.clear();
          return;
        }
        // Wipe the hash so the token never lingers in browser history.
        try {
          window.history.replaceState(null, '', window.location.pathname);
        } catch {
          /* noop */
        }
        if (warning === 'calendar_persist_failed') {
          toast.warning(t('auth.calendarPersistWarning'));
        } else {
          toast.success(t('auth.signedInWithGoogle'));
        }
        nav(safeNext, { replace: true });
      })
      .catch(() => {
        setError('session_failed');
        tokenStore.clear();
      });
  }, [nav, refresh, t]);

  return (
    <div
      className="min-h-[100dvh] flex items-center justify-center p-6 hero-wash-light noise"
      data-testid="auth-callback-page"
    >
      <Card className="w-full max-w-md rounded-[calc(var(--radius)+6px)] shadow-editorial">
        <CardContent className="p-8 text-center">
          {!error ? (
            <>
              <Loader2
                className="h-8 w-8 mx-auto mb-4 animate-spin text-[hsl(var(--accent))]"
                data-testid="auth-callback-spinner"
              />
              <h1 className="font-display text-2xl mb-2">
                {t('auth.finishingSignIn')}
              </h1>
              <p className="text-sm text-muted-foreground">
                {t('auth.finishingSignInSub')}
              </p>
            </>
          ) : (
            <>
              <AlertCircle
                className="h-8 w-8 mx-auto mb-4 text-destructive"
                data-testid="auth-callback-error-icon"
              />
              <h1 className="font-display text-2xl mb-2">
                {t('auth.signInFailed')}
              </h1>
              <p
                className="text-sm text-muted-foreground mb-6 break-all"
                data-testid="auth-callback-error-message"
              >
                {error}
              </p>
              <Button
                onClick={() => nav('/login', { replace: true })}
                className="rounded-xl"
                data-testid="auth-callback-back-to-login"
              >
                {t('auth.backToLogin')}
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
