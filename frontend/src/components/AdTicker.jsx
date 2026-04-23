import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Megaphone } from 'lucide-react';
import { api } from '@/lib/api';
import { useLocation } from '@/lib/location';
import { cn } from '@/lib/utils';

/**
 * AdTicker — horizontal running strip of regional ads.
 *
 * Picks up the viewer's country/region from `LocationProvider` when
 * available, falls back to `undefined` (server returns any ad without
 * targeting). Impressions are tracked best-effort on mount for each ad the
 * user actually sees. The strip auto-rotates every 5s.
 */
export function AdTicker({
  className,
  limit = 6,
  placement = 'footer', // analytics hint only — backend ignores
}) {
  const { t } = useTranslation();
  const loc = useLocation?.();
  const [ads, setAds] = useState([]);
  const [idx, setIdx] = useState(0);
  const trackedRef = useRef(new Set());

  const country = loc?.country_code || undefined;
  const region = loc?.city || loc?.country || undefined;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.adTicker({
          limit,
          ...(country ? { country } : {}),
          ...(region ? { region } : {}),
        });
        if (!cancelled) setAds(res?.items || []);
      } catch {
        if (!cancelled) setAds([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [country, region, limit]);

  useEffect(() => {
    if (ads.length <= 1) return undefined;
    const id = setInterval(() => setIdx((i) => (i + 1) % ads.length), 5000);
    return () => clearInterval(id);
  }, [ads.length]);

  // Impression tracking: record once per ad per mount lifecycle
  useEffect(() => {
    const current = ads[idx];
    if (!current?.id) return;
    if (trackedRef.current.has(current.id)) return;
    trackedRef.current.add(current.id);
    api.trackAdImpression(current.id);
  }, [ads, idx]);

  const current = useMemo(() => ads[idx] || null, [ads, idx]);

  if (!ads.length) return null;

  const onClick = (e) => {
    if (!current?.id) return;
    api.trackAdClick(current.id);
    // Allow default href navigation if cta_url present
    if (!current?.creative?.cta_url) {
      e.preventDefault();
    }
  };

  const creative = current?.creative || {};

  return (
    <div
      className={cn(
        'w-full border-y border-border bg-card/70 backdrop-blur-sm',
        className,
      )}
      data-testid={`ad-ticker-${placement}`}
      role="region"
      aria-label={t('ticker.label')}
    >
      <div className="container-px max-w-6xl mx-auto py-2 flex items-center gap-3 overflow-hidden">
        <div className="shrink-0 inline-flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground">
          <Megaphone className="h-3 w-3" />
          {t('ticker.label')}
        </div>
        <a
          href={creative.cta_url || '#'}
          target={creative.cta_url ? '_blank' : undefined}
          rel="noopener noreferrer"
          onClick={onClick}
          className="flex-1 min-w-0 flex items-center gap-3 text-sm hover:opacity-90 transition-opacity"
          data-testid={`ad-ticker-item-${current?.id}`}
        >
          {creative.image_url && (
            <img
              src={creative.image_url}
              alt=""
              className="h-6 w-6 rounded-full object-cover border border-border shrink-0"
            />
          )}
          <span className="font-medium truncate">{creative.headline}</span>
          {creative.body && (
            <span className="text-muted-foreground truncate hidden sm:inline">
              — {creative.body}
            </span>
          )}
          {creative.cta_label && (
            <span className="ms-auto shrink-0 text-[hsl(var(--accent))] font-medium">
              {creative.cta_label} →
            </span>
          )}
        </a>
        {ads.length > 1 && (
          <div className="shrink-0 flex items-center gap-1" aria-hidden="true">
            {ads.map((_, i) => (
              <span
                key={i}
                className={cn(
                  'h-1.5 w-1.5 rounded-full transition-colors',
                  i === idx ? 'bg-[hsl(var(--accent))]' : 'bg-border',
                )}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
