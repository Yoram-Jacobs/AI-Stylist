/**
 * DressApp extension popup.
 *
 * Three states:
 *   1. Loading      — first paint, querying chrome.storage.local for
 *                      a saved token.
 *   2. Disconnected — show a primary "Connect to DressApp" button
 *                      that opens the auth-bridge tab.
 *   3. Connected    — show the user's name/email + a measurements
 *                      summary fetched from /api/v1/users/me, plus
 *                      a "Sign out" link that wipes chrome.storage.
 *
 * The popup intentionally never stores raw measurements; it asks the
 * service worker each time so the source of truth stays the backend.
 * The 5-second cache in the SW is enough to keep the popup snappy on
 * repeated opens.
 */
import { useEffect, useState } from 'react';
import { LogIn, LogOut, Loader2, ShieldCheck, AlertCircle, Ruler, Sparkles, ExternalLink } from 'lucide-react';
import { messages, sendToBackground } from '@/lib/messages.js';
import { authBaseUrl } from '@/lib/api.js';

export default function Popup() {
  const [state, setState] = useState({
    phase: 'loading', // loading | disconnected | connected | error
    user: null,
    measurementsSummary: null,
    error: null,
  });

  async function refresh() {
    setState((s) => ({ ...s, phase: 'loading', error: null }));
    const r = await sendToBackground({ type: messages.AUTH_STATUS });
    if (!r || !r.ok) {
      setState({ phase: 'error', user: null, measurementsSummary: null, error: r?.error || 'Unknown error' });
      return;
    }
    if (!r.token) {
      setState({ phase: 'disconnected', user: null, measurementsSummary: null, error: null });
      return;
    }
    // Connected — fetch /me through the SW (it adds the bearer header).
    const me = await sendToBackground({ type: messages.FETCH_ME });
    if (!me || !me.ok) {
      setState({
        phase: 'connected',
        user: r.user || null,
        measurementsSummary: null,
        error: me?.error || null,
      });
      return;
    }
    setState({
      phase: 'connected',
      user: me.user,
      measurementsSummary: summarize(me.user?.body_measurements || {}),
      error: null,
    });
  }

  useEffect(() => { refresh(); }, []);

  async function connect() {
    const url = `${authBaseUrl()}/extension/connect?ext_id=${encodeURIComponent(chrome.runtime.id)}&v=1`;
    chrome.tabs.create({ url });
  }

  async function disconnect() {
    await sendToBackground({ type: messages.CLEAR_AUTH });
    refresh();
  }

  return (
    <div className="flex flex-col gap-3 p-4" data-testid="dressapp-popup">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <div className="text-sm font-semibold leading-tight">DressApp</div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Shopping assistant</div>
          </div>
        </div>
        <a
          href={authBaseUrl()}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
          data-testid="open-dressapp"
        >
          dressapp.co <ExternalLink className="h-3 w-3" />
        </a>
      </header>

      {state.phase === 'loading' ? (
        <div className="flex h-32 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
      ) : state.phase === 'disconnected' ? (
        <DisconnectedView onConnect={connect} />
      ) : state.phase === 'error' ? (
        <ErrorView error={state.error} onRetry={refresh} />
      ) : (
        <ConnectedView
          user={state.user}
          measurementsSummary={state.measurementsSummary}
          onDisconnect={disconnect}
        />
      )}

      <footer className="mt-2 border-t pt-2 text-center text-[10px] text-muted-foreground">
        Recommendations are estimates. Always confirm with the store's chart.
      </footer>
    </div>
  );
}

function DisconnectedView({ onConnect }) {
  return (
    <div className="flex flex-col items-stretch gap-3">
      <div className="rounded-xl border border-dashed bg-muted/40 p-3 text-center">
        <ShieldCheck className="mx-auto h-6 w-6 text-primary" />
        <p className="mt-2 text-xs text-foreground">Connect to your DressApp account to get personalised size recommendations on every shopping site.</p>
      </div>
      <button
        onClick={onConnect}
        className="flex items-center justify-center gap-2 rounded-xl bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 active:scale-[0.99]"
        data-testid="connect-button"
      >
        <LogIn className="h-4 w-4" /> Connect to DressApp
      </button>
    </div>
  );
}

function ConnectedView({ user, measurementsSummary, onDisconnect }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 rounded-xl border bg-muted/30 p-3">
        {user?.avatar_url ? (
          <img src={user.avatar_url} alt="" className="h-9 w-9 rounded-full object-cover" />
        ) : (
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
            {(user?.full_name || user?.email || '?').slice(0,1).toUpperCase()}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{user?.full_name || user?.email || 'Connected'}</div>
          {user?.email && user?.full_name ? <div className="truncate text-[11px] text-muted-foreground">{user.email}</div> : null}
        </div>
        <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700" data-testid="connected-badge">
          Logged in
        </span>
      </div>

      <MeasurementsCard summary={measurementsSummary} />

      <button
        onClick={onDisconnect}
        className="flex items-center justify-center gap-2 rounded-lg border bg-background px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
        data-testid="disconnect-button"
      >
        <LogOut className="h-3.5 w-3.5" /> Sign out of extension
      </button>
    </div>
  );
}

function MeasurementsCard({ summary }) {
  if (!summary || summary.count === 0) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs" data-testid="no-measurements-card">
        <div className="mb-1 flex items-center gap-1.5 font-medium text-amber-800">
          <AlertCircle className="h-3.5 w-3.5" /> No measurements yet
        </div>
        <div className="text-amber-700">
          Add your chest, waist, and hip measurements in your DressApp profile to enable size recommendations.
        </div>
        <a
          href={`${authBaseUrl()}/me`}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-amber-900 underline"
        >
          Open profile <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    );
  }
  return (
    <div className="rounded-xl border bg-card p-3 text-xs" data-testid="measurements-card">
      <div className="mb-2 flex items-center gap-1.5 font-medium">
        <Ruler className="h-3.5 w-3.5 text-primary" /> Measurements ({summary.count})
      </div>
      <ul className="grid grid-cols-2 gap-x-3 gap-y-1">
        {summary.entries.slice(0, 6).map(([k, v]) => (
          <li key={k} className="flex justify-between">
            <span className="capitalize text-muted-foreground">{k.replace(/_/g, ' ')}</span>
            <span className="font-medium">{v}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ErrorView({ error, onRetry }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-destructive/40 bg-destructive/5 p-3 text-xs text-red-700">
      <div className="flex items-center gap-1.5 font-medium"><AlertCircle className="h-4 w-4" /> Couldn't load extension state</div>
      <div>{error}</div>
      <button onClick={onRetry} className="self-start rounded border bg-background px-2 py-1 font-medium">Retry</button>
    </div>
  );
}

function summarize(m) {
  const entries = Object.entries(m || {}).filter(([, v]) => v !== '' && v !== null && v !== undefined);
  return { count: entries.length, entries };
}
