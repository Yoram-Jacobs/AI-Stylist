import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { MapPin, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { useLocation } from '@/lib/location';

/**
 * Self-contained "Location" settings card. Mirrors the Calendar card's
 * ergonomics: a rationale, a connected/not-connected indicator, and a
 * primary action. Uses `useLocation` for state + commands so the Profile
 * page stays declarative.
 */
export const LocationCard = () => {
  const { t } = useTranslation();
  const loc = useLocation();
  const [busy, setBusy] = useState(false);

  const connected = !!loc.coords;
  const unavailable = !loc.available || loc.permissionState === 'unavailable';
  const denied = loc.permissionState === 'denied';

  const request = async () => {
    setBusy(true);
    try {
      await loc.request();
      toast.success(t('location.granted'));
    } catch (err) {
      if (err?.code === 1) toast.error(t('location.denied'));
    } finally {
      setBusy(false);
    }
  };

  const forget = async () => {
    setBusy(true);
    try {
      await loc.forget();
      toast.success(t('location.forgotten'));
    } finally {
      setBusy(false);
    }
  };

  const fmtCoord = (v) =>
    typeof v === 'number' ? v.toFixed(4) : String(v || '—');

  const cityLine =
    [loc.city, loc.country_code || loc.country].filter(Boolean).join(' · ') ||
    '—';

  return (
    <Card
      className="rounded-[calc(var(--radius)+6px)] shadow-editorial"
      data-testid="location-card"
    >
      <CardContent className="p-6">
        <div className="flex items-start gap-4">
          <div className="h-10 w-10 rounded-full bg-secondary flex items-center justify-center shrink-0">
            <MapPin className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <div className="caps-label text-muted-foreground">
                {t('location.sectionTitle')}
              </div>
              {connected ? (
                <Badge
                  variant="outline"
                  className="bg-emerald-50 text-emerald-800 border-emerald-200 text-[11px]"
                  data-testid="location-connected-badge"
                >
                  <CheckCircle2 className="h-3 w-3 me-1" />
                  {t('location.granted')}
                </Badge>
              ) : denied ? (
                <Badge
                  variant="outline"
                  className="bg-rose-50 text-rose-800 border-rose-200 text-[11px]"
                >
                  {t('location.denied')}
                </Badge>
              ) : (
                <Badge variant="outline" className="text-[11px]">
                  {t('location.notNow')}
                </Badge>
              )}
            </div>
            <h3 className="font-display text-xl mt-1">{t('location.title')}</h3>
            <p className="text-sm text-muted-foreground mt-1 max-w-xl">
              {t('location.rationale')}
            </p>

            {connected ? (
              <dl
                className="text-xs text-muted-foreground mt-3 grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-1"
                data-testid="location-details"
              >
                <div>
                  <dt className="caps-label text-[10px]">
                    {t('location.cityLabel')}
                  </dt>
                  <dd className="font-medium text-foreground">{cityLine}</dd>
                </div>
                <div>
                  <dt className="caps-label text-[10px]">
                    {t('location.lastKnown')}
                  </dt>
                  <dd className="font-mono">
                    {fmtCoord(loc.coords.lat)}, {fmtCoord(loc.coords.lng)}
                  </dd>
                </div>
                {loc.accuracy_m ? (
                  <div>
                    <dt className="caps-label text-[10px]">
                      {t('location.accuracyLabel')}
                    </dt>
                    <dd className="font-mono">
                      ±{Math.round(loc.accuracy_m)} {t('location.metersShort')}
                    </dd>
                  </div>
                ) : null}
              </dl>
            ) : null}

            {denied ? (
              <div className="mt-3 flex items-start gap-2 text-xs text-muted-foreground">
                <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                <span>{t('location.deniedHint')}</span>
              </div>
            ) : null}
          </div>

          <div className="shrink-0 flex flex-col gap-2">
            {unavailable ? (
              <Badge variant="outline">{t('location.unavailable')}</Badge>
            ) : connected ? (
              <>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={request}
                  className="rounded-xl"
                  data-testid="location-refresh-btn"
                >
                  {busy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    t('location.retry')
                  )}
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={forget}
                  className="rounded-xl"
                  data-testid="location-forget-btn"
                >
                  {t('location.forget')}
                </Button>
              </>
            ) : (
              <Button
                disabled={busy || denied}
                onClick={request}
                className="rounded-xl"
                data-testid="location-enable-btn"
              >
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <MapPin className="h-4 w-4 me-2" />
                    {t('location.allow')}
                  </>
                )}
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
