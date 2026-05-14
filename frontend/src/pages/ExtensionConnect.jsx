/**
 * Auth bridge between dressapp.co and the DressApp Chrome Extension.
 *
 * Why this page exists
 * --------------------
 * The Chrome extension needs the user's JWT to call ``/api/v1/users/me``
 * and ``/api/v1/sizes/analyze-chart``. The cleanest cross-origin
 * handoff for an extension is:
 *
 *   1. Extension popup opens this page in a new tab with
 *      ``?ext_id=<chrome runtime id>&v=1`` in the query string.
 *   2. This page reads the user's token from ``localStorage`` (it
 *      exists IFF the user is logged in to dressapp.co — any auth
 *      method works, Google or password, because ``tokenStore`` is
 *      single-source-of-truth in ``lib/api.js``).
 *   3. We send the token + user object to the extension via
 *      ``window.postMessage`` to ``window.opener``, OR via the
 *      browser's ``chrome.runtime.sendMessage`` API when the extension
 *      injects a tiny content script on this exact URL pattern.
 *   4. The extension stores the token in ``chrome.storage.local`` and
 *      closes this tab.
 *
 * If the user lands here while logged OUT, we redirect to ``/login``
 * with ``?next=/extension/connect`` so the round-trip survives auth.
 *
 * If the user lands here directly (no ``ext_id``), we render a small
 * info card explaining what this page is for — never leak the token
 * just because someone hit the URL by hand.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Loader2, ShieldCheck, Plug, AlertTriangle, Check } from 'lucide-react';
import { tokenStore, userStore, api } from '@/lib/api';

import { useTranslation } from 'react-i18next';
// Extension IDs we trust to receive the token. Tightening this when
// the extension is published to the Chrome Web Store is a one-line
// change. During development we accept any extension that injects a
// content script onto this exact URL — chrome.runtime.sendMessage
// requires the receiver to be installed locally, so the trust model
// is "the user has installed our extension into their own browser".
const TRUSTED_EXTENSION_IDS = (
  import.meta.env.VITE_EXTENSION_ALLOWED_IDS || ''
)
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);

const HANDOFF_VERSION = 1;

export default function ExtensionConnect() {
  const { t } = useTranslation();

  const [params] = useSearchParams();
  const nav = useNavigate();
  const extId = params.get('ext_id');
  const requestedV = parseInt(params.get('v') || '1', 10);
  // ``?force=1`` (or ``?switch=1``) signals "user clicked 'Switch
  // account' in the DressApp extension popup". We clear the
  // currently-cached web-app auth so the existing useEffect bounces
  // them through ``/login`` for a fresh credential entry. After
  // login they return here, the new token is handed off, and the
  // extension flips identity. Idempotent: ``force_handled`` flag
  // prevents an infinite clear-redirect loop.
  const force = params.get('force') === '1' || params.get('switch') === '1';
  const forceHandledRef = useRef(false);
  if (force && !forceHandledRef.current) {
    forceHandledRef.current = true;
    try {
      tokenStore.clear();
      userStore.clear?.();
    } catch { /* noop — best effort */ }
  }

  const [phase, setPhase] = useState('init'); // init|sending|sent|error|noauth|noopener
  const [error, setError] = useState(null);
  const sentRef = useRef(false);

  const token = tokenStore.get();
  const user = userStore.get();

  const trusted = useMemo(() => {
    if (!extId) return false;
    if (TRUSTED_EXTENSION_IDS.length === 0) return true; // dev mode
    return TRUSTED_EXTENSION_IDS.includes(extId);
  }, [extId]);

  // If the user isn't logged in, bounce them through /login and come
  // back here. The next-param survives the OAuth round-trip via
  // AuthCallback.
  useEffect(() => {
    if (!token || !user) {
      const next = encodeURIComponent(
        `/extension/connect?ext_id=${encodeURIComponent(extId || '')}&v=${requestedV}`,
      );
      nav(`/login?next=${next}`, { replace: true });
    }
  }, [token, user, extId, requestedV, nav]);

  // Auto-trigger handoff when everything is ready, but only once.
  useEffect(() => {
    if (!token || !user || !extId || !trusted) return;
    if (sentRef.current) return;
    if (requestedV !== HANDOFF_VERSION) {
      setPhase('error');
      setError(`Unsupported handoff version ${requestedV}. Update the DressApp extension.`);
      return;
    }
    sentRef.current = true;
    sendToExtension();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, user, extId, trusted, requestedV]);

  async function sendToExtension() {
    setPhase('sending');
    setError(null);
    const payload = {
      type: 'DRESSAPP_EXT_TOKEN',
      version: HANDOFF_VERSION,
      issued_at: new Date().toISOString(),
      token,
      user: {
        id: user.id,
        email: user.email,
        full_name: user.full_name || user.name,
        avatar_url: user.avatar_url || user.picture,
      },
      backend: window.location.origin,
    };

    // Path 1: chrome.runtime.sendMessage — works when the extension
    // injects a content script on this page. Best UX (silent, no
    // window references), so we try it first.
    let delivered = false;
    try {
      // Browsers that aren't Chrome won't have window.chrome.runtime
      // and will throw on the dot-chain — guard carefully.
      const cr = window.chrome && window.chrome.runtime;
      if (cr && typeof cr.sendMessage === 'function') {
        await new Promise((resolve, reject) => {
          try {
            cr.sendMessage(extId, payload, (response) => {
              if (cr.lastError) {
                reject(new Error(cr.lastError.message || 'sendMessage failed'));
                return;
              }
              if (response && response.ok) {
                delivered = true;
                resolve();
              } else {
                reject(new Error('extension did not acknowledge'));
              }
            });
          } catch (e) {
            reject(e);
          }
        });
      }
    } catch (_e) {
      // Fall through to postMessage path.
    }

    // Path 2: window.postMessage to opener. The extension content
    // script listens on this page and forwards the message to its
    // service worker.
    if (!delivered) {
      try {
        const ev = new MessageEvent('message', { data: payload, origin: window.location.origin });
        window.dispatchEvent(ev);
        if (window.opener && !window.opener.closed) {
          window.opener.postMessage(payload, '*');
        }
        delivered = true;
      } catch (e) {
        setPhase('error');
        setError(e.message || 'Could not reach the extension.');
        return;
      }
    }

    setPhase('sent');
    // Auto-close after a short success display so the user lands back
    // on whatever they were doing in their main tab.
    setTimeout(() => {
      try { window.close(); } catch (_) { /* ignore */ }
    }, 2200);
  }

  // ---- Render variants -----------------------------------------------
  if (!token || !user) {
    return (
      <Shell title={t('pages.extensionConnect.redirecting_to_sign_in')}>
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </Shell>
    );
  }

  if (!extId) {
    return (
      <Shell title={t('pages.extensionConnect.dressapp_chrome_extension')}>
        <p className="text-sm text-muted-foreground">
          This page is the auth bridge for the DressApp shopping
          assistant extension. Open it from the extension's popup
          (the &quot;Connect to DressApp&quot; button).
        </p>
        <Button onClick={() => nav('/home')} className="mt-4 rounded-xl">
          {t('pages.extensionConnect.go_to_home')}
        </Button>
      </Shell>
    );
  }

  if (!trusted) {
    return (
      <Shell title={t('pages.extensionConnect.untrusted_extension')} tone="warn">
        <p className="text-sm text-muted-foreground">
          {t('pages.extensionConnect.the_extension_id')} <code className="rounded bg-muted px-1">{extId}</code>{' '}
          is not on the allow-list for this deployment. If you installed
          the extension yourself, ask the DressApp admin to add it.
        </p>
      </Shell>
    );
  }

  if (phase === 'sending' || phase === 'init') {
    return (
      <Shell title={t('pages.extensionConnect.connecting_to_dressapp_extension')}>
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
        <p className="mt-3 text-xs text-muted-foreground">
          {t('pages.extensionConnect.sharing_your_signin_with_the')}
        </p>
      </Shell>
    );
  }

  if (phase === 'sent') {
    return (
      <Shell title="Connected" tone="ok">
        <div className="flex items-center gap-2 text-sm">
          <Check className="h-5 w-5 text-emerald-600" />
          <span>{t('pages.extensionConnect.the_extension_is_signed_in')} <strong>{user.email}</strong>.</span>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          {t('pages.extensionConnect.you_can_close_this_tab')}
        </p>
        <Button
          onClick={() => { try { window.close(); } catch (_) { /* */ } }}
          className="mt-4 rounded-xl"
          data-testid="extension-connect-close"
        >
          Close
        </Button>
      </Shell>
    );
  }

  return (
    <Shell title={t('pages.extensionConnect.connection_failed')} tone="warn">
      <p className="text-sm text-muted-foreground">{error || 'Unknown error.'}</p>
      <Button
        onClick={sendToExtension}
        className="mt-4 rounded-xl"
        data-testid="extension-connect-retry"
      >
        Retry
      </Button>
    </Shell>
  );
}

function Shell({ title, tone, children }) {
  const { t } = useTranslation();

  const Icon =
    tone === 'ok' ? ShieldCheck : tone === 'warn' ? AlertTriangle : Plug;
  const accent =
    tone === 'ok'
      ? 'text-emerald-600'
      : tone === 'warn'
      ? 'text-amber-600'
      : 'text-primary';
  return (
    <div className="flex min-h-[100svh] items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md rounded-2xl border bg-card shadow-sm" data-testid="extension-connect-card">
        <CardContent className="p-6">
          <div className={`mb-4 flex items-center gap-2 ${accent}`}>
            <Icon className="h-5 w-5" />
            <h1 className="text-base font-semibold">{title}</h1>
          </div>
          {children}
        </CardContent>
      </Card>
    </div>
  );
}

// avoid linter warning about unused import in some configs
void api;
