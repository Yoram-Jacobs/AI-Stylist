import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Calendar, CheckCircle2, AlertCircle, Loader2, Link as LinkIcon, Unlink } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';

/**
 * Self-contained card that lets the user connect/disconnect Google Calendar.
 *
 * Also handles the post-OAuth redirect: when the URL carries
 * `?calendar=connected` or `?calendar=error` we show a toast and strip the
 * query param.
 */
export const CalendarConnect = () => {
  const { t } = useTranslation();
  const [status, setStatus] = useState({ connected: false, google_email: null });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const location = useLocation();
  const nav = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const s = await api.calendarStatus();
      setStatus(s || { connected: false });
    } catch {
      // non-fatal — leave status as disconnected
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const params = new URLSearchParams(location.search);
    const cal = params.get('calendar');
    if (cal === 'connected') {
      toast.success(t('calendar.connected'));
      params.delete('calendar');
      nav({ pathname: location.pathname, search: params.toString() }, { replace: true });
    } else if (cal === 'error') {
      const reason = params.get('reason') || 'unknown_error';
      toast.error(`${t('calendar.connectFailed')}: ${reason.replaceAll('_', ' ')}`);
      params.delete('calendar');
      params.delete('reason');
      nav({ pathname: location.pathname, search: params.toString() }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connect = async () => {
    setBusy(true);
    try {
      const { authorization_url } = await api.googleOAuthStart();
      if (!authorization_url) throw new Error('missing url');
      window.location.href = authorization_url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('calendar.connectFailedGeneric'));
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      await api.googleOAuthDisconnect();
      setStatus({ connected: false, google_email: null });
      toast.success(t('calendar.disconnected'));
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('calendar.disconnectFailed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      className="rounded-[calc(var(--radius)+6px)] shadow-editorial"
      data-testid="calendar-connect-card"
    >
      <CardContent className="p-6">
        <div className="flex flex-col sm:flex-row items-start gap-4">
          <div className="h-10 w-10 rounded-full bg-secondary flex items-center justify-center shrink-0">
            <Calendar className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0 w-full">
            <div className="flex items-center gap-2">
              <div className="caps-label text-muted-foreground">{t('calendar.context')}</div>
              {loading ? null : status.connected ? (
                <Badge
                  variant="outline"
                  className="bg-emerald-50 text-emerald-800 border-emerald-200 text-[11px]"
                  data-testid="calendar-connected-badge"
                >
                  <CheckCircle2 className="h-3 w-3 me-1" /> {t('calendar.connectedBadge')}
                </Badge>
              ) : (
                <Badge
                  variant="outline"
                  className="text-[11px]"
                  data-testid="calendar-disconnected-badge"
                >
                  {t('calendar.notConnected')}
                </Badge>
              )}
            </div>
            <h3 className="font-display text-xl mt-1">{t('calendar.title')}</h3>
            <p className="text-sm text-muted-foreground mt-1 max-w-xl">
              {t('calendar.description')}
            </p>
            {status.connected && status.google_email ? (
              <div
                className="text-xs text-muted-foreground mt-2"
                data-testid="calendar-connected-email"
              >
                {t('calendar.signedInAs')} <span className="font-medium">{status.google_email}</span>
              </div>
            ) : null}
          </div>
          <div className="shrink-0 w-full sm:w-auto">
            {loading ? (
              <Button variant="secondary" disabled className="rounded-xl w-full sm:w-auto">
                <Loader2 className="h-4 w-4 animate-spin" />
              </Button>
            ) : status.connected ? (
              <Button
                variant="outline"
                disabled={busy}
                onClick={disconnect}
                className="rounded-xl w-full sm:w-auto"
                data-testid="calendar-disconnect-button"
              >
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Unlink className="h-4 w-4 me-2" /> {t('calendar.disconnectAction')}
                  </>
                )}
              </Button>
            ) : (
              <Button
                disabled={busy}
                onClick={connect}
                className="rounded-xl w-full sm:w-auto"
                data-testid="calendar-connect-button"
              >
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <LinkIcon className="h-4 w-4 me-2" /> {t('calendar.connectAction')}
                  </>
                )}
              </Button>
            )}
          </div>
        </div>
        {!loading && !status.connected ? (
          <div className="mt-4 flex items-start gap-2 text-xs text-muted-foreground">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span>
              {t('calendar.offlineHint')} <em>{t('calendar.includeCalendarEm')}</em>.
            </span>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
};
