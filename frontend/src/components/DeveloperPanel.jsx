/**
 * Admin-only "Developer / Internal" panel surfaced inside Profile →
 * Settings.
 *
 * Visible ONLY when the logged-in user has the ``admin`` role
 * (mirrors the same gate used by ``Admin.jsx`` and ``TopNav.jsx``).
 * Anyone else: the parent Profile page renders nothing for this
 * accordion, no API calls happen, no information leaks.
 *
 * Capabilities:
 *  - Read the active Eyes provider on the current pod ("gemma" or
 *    "gemini") and surface where it came from (env default vs DB
 *    override) along with the URL-configured / token-set booleans
 *    so admins can confirm the pod actually has the Gemma endpoint
 *    wired before flipping the switch.
 *  - Toggle Gemini <-> Gemma at runtime. Writes to
 *    ``config.{_id: 'eyes_provider'}`` via ``POST /api/v1/admin/eyes``
 *    so the choice survives a backend container restart and is
 *    picked up within ~5 s by every analyse call.
 *  - "Clear override" resets the doc and reverts to env-default
 *    without dirtying the audit log with a manual flip back.
 *  - Last-call summary (provider, latency, ok/err, age) so admins
 *    can confirm Gemma is actually answering before relying on it.
 *
 * Per the user's choice: per-pod scope. We don't broadcast — each
 * pod's admin sees + flips its OWN pod's behaviour.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Accordion, AccordionContent, AccordionItem, AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Loader2, RefreshCw, Eye, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';

/**
 * Format a UTC ISO timestamp as a short relative-time string for the
 * "last call: 12 s ago" badge. Falls back to the raw string on parse
 * errors so we never show 'NaN' / 'Invalid Date' to admins.
 */
function relativeAge(iso) {
  if (!iso) return '—';
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return iso;
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.round(hr / 24)}d ago`;
}

export function DeveloperPanel({ user }) {
  const isAdmin = (user?.roles || []).includes('admin');
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  // Track the pending toggle target so the optimistic UI feels
  // instant while the POST is in flight.
  const [pending, setPending] = useState(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  async function refresh({ silent = false } = {}) {
    if (!isAdmin) return;
    if (!silent) setLoading(true);
    setError(null);
    try {
      const data = await api.adminEyesStatus();
      if (!mountedRef.current) return;
      setStatus(data);
    } catch (e) {
      if (!mountedRef.current) return;
      setError(e?.response?.data?.detail || e?.message || 'Failed to load');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }

  useEffect(() => {
    if (isAdmin) refresh();
  }, [isAdmin]);

  if (!isAdmin) return null;

  async function setProvider(next) {
    if (!status) return;
    if (saving) return;
    setSaving(true);
    setPending(next);
    try {
      const data = await api.adminEyesSet(next);
      setStatus(data);
      toast.success(
        next ? `Eyes provider → ${next}` : 'Eyes override cleared',
      );
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || 'Update failed';
      toast.error(msg);
    } finally {
      setSaving(false);
      setPending(null);
    }
  }

  // Optimistic value for the Switch while a POST is in flight.
  const visualProvider = pending !== null
    ? pending
    : (status?.active_provider || 'gemini');
  const isGemma = visualProvider === 'gemma';

  const lastCall = status?.last_call;
  const lastCallOk = lastCall?.ok === true;
  const lastCallProvider = lastCall?.extra?.provider || lastCall?.provider || '—';
  const lastCallLatency = lastCall?.latency_ms != null
    ? `${(lastCall.latency_ms / 1000).toFixed(2)}s`
    : '—';

  return (
    <Accordion type="single" collapsible className="w-full" data-testid="developer-panel">
      <AccordionItem value="dev" className="border-none">
        <AccordionTrigger
          className="rounded-xl px-4 py-3 hover:no-underline border bg-card"
          data-testid="developer-panel-trigger"
        >
          <span className="flex items-center gap-2 text-sm font-medium">
            <Eye className="h-4 w-4" />
            Developer / Internal
            <Badge variant="secondary" className="ms-2 text-[10px] uppercase tracking-wide">
              admin
            </Badge>
          </span>
        </AccordionTrigger>
        <AccordionContent className="pt-3">
          <Card className="rounded-xl border-dashed">
            <CardContent className="space-y-4 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium">Eyes vision provider</div>
                  <div className="text-xs text-muted-foreground">
                    Routes the closet analyzer between Google's Gemini
                    2.5 Flash and the self-hosted Gemma-4 E2B endpoint.
                    Override is persisted in this pod's Mongo and
                    survives container restarts. If Gemma is unreachable,
                    the request automatically falls back to Gemini.
                  </div>
                </div>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="rounded-full"
                  onClick={() => refresh()}
                  disabled={loading || saving}
                  data-testid="developer-eyes-refresh"
                  aria-label="Refresh status"
                >
                  {loading
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <RefreshCw className="h-4 w-4" />}
                </Button>
              </div>

              {error ? (
                <div
                  role="alert"
                  className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive"
                  data-testid="developer-eyes-error"
                >
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>{error}</span>
                </div>
              ) : null}

              {/* Toggle row */}
              <div className="flex items-center justify-between gap-3 rounded-lg border bg-background px-3 py-2">
                <div className="text-sm">
                  <span className="text-muted-foreground">Active:</span>{' '}
                  <span className="font-semibold" data-testid="developer-eyes-active">
                    {visualProvider === 'gemma' ? 'Gemma-4 E2B (self-hosted)' : 'Gemini 2.5 Flash (Google)'}
                  </span>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">
                    Source: {status?.source === 'db' ? 'DB override' : 'env default'}
                    {' · '}env default: {status?.env_default || '—'}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`text-[11px] uppercase tracking-wide ${isGemma ? 'text-muted-foreground' : 'text-foreground'}`}>
                    Gemini
                  </span>
                  <Switch
                    checked={isGemma}
                    onCheckedChange={(v) => setProvider(v ? 'gemma' : 'gemini')}
                    disabled={saving || loading || !status}
                    aria-label="Toggle Eyes provider"
                    data-testid="developer-eyes-toggle"
                  />
                  <span className={`text-[11px] uppercase tracking-wide ${isGemma ? 'text-foreground' : 'text-muted-foreground'}`}>
                    Gemma
                  </span>
                </div>
              </div>

              {/* Wiring sanity row */}
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div
                  className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 ${status?.gemma_url_set ? 'bg-emerald-50 border-emerald-200 text-emerald-900 dark:bg-emerald-950/30 dark:border-emerald-900 dark:text-emerald-200' : 'bg-amber-50 border-amber-200 text-amber-900 dark:bg-amber-950/30 dark:border-amber-900 dark:text-amber-200'}`}
                  data-testid="developer-eyes-url-flag"
                >
                  {status?.gemma_url_set
                    ? <CheckCircle2 className="h-3.5 w-3.5" />
                    : <AlertTriangle className="h-3.5 w-3.5" />}
                  <span className="truncate">
                    Gemma URL: {status?.gemma_url || 'not set'}
                  </span>
                </div>
                <div
                  className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 ${status?.api_token_set ? 'bg-emerald-50 border-emerald-200 text-emerald-900 dark:bg-emerald-950/30 dark:border-emerald-900 dark:text-emerald-200' : 'bg-amber-50 border-amber-200 text-amber-900 dark:bg-amber-950/30 dark:border-amber-900 dark:text-amber-200'}`}
                  data-testid="developer-eyes-token-flag"
                >
                  {status?.api_token_set
                    ? <CheckCircle2 className="h-3.5 w-3.5" />
                    : <AlertTriangle className="h-3.5 w-3.5" />}
                  <span>
                    Bearer token: {status?.api_token_set ? 'configured' : 'missing'}
                  </span>
                </div>
              </div>

              {/* Last-call summary */}
              <div className="rounded-lg border px-3 py-2 text-xs" data-testid="developer-eyes-last-call">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">Last analyze call</span>
                  <Badge
                    variant={lastCall ? (lastCallOk ? 'default' : 'destructive') : 'outline'}
                    className="text-[10px] uppercase"
                  >
                    {lastCall ? (lastCallOk ? 'ok' : 'error') : 'no calls yet'}
                  </Badge>
                </div>
                {lastCall ? (
                  <div className="mt-1 text-muted-foreground">
                    via <span className="font-medium text-foreground">{lastCallProvider}</span>
                    {' · '}{lastCallLatency}
                    {' · '}{relativeAge(lastCall.ts || lastCall.timestamp)}
                    {lastCall.error ? (
                      <div className="mt-0.5 truncate text-destructive" title={lastCall.error}>
                        {lastCall.error}
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="mt-1 text-muted-foreground">
                    Trigger an analyze (any closet item → Analyze) to populate.
                  </div>
                )}
              </div>

              {/* Override controls */}
              <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                <div className="text-[11px] text-muted-foreground">
                  {status?.override
                    ? <>Override set by <span className="font-medium">{status.updated_by || 'unknown'}</span> · {relativeAge(status.updated_at)}</>
                    : 'No DB override — using env default.'}
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="rounded-lg"
                  onClick={() => setProvider(null)}
                  disabled={saving || loading || !status?.override}
                  data-testid="developer-eyes-clear"
                >
                  Clear override
                </Button>
              </div>
            </CardContent>
          </Card>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}

export default DeveloperPanel;
