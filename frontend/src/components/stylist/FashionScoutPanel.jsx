import { useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Sparkles, RefreshCw, ExternalLink, Play, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/auth';
import { useLocation as useAppLocation } from '@/lib/location';

/**
 * Each bucket renders with its own analogous-color gradient so the absence
 * of a real image still reads as intentional editorial design. Tailwind
 * safelists the full class names below in index.css / tailwind.config if
 * needed (they are concrete tokens, so they survive dead-code elimination).
 */
const BUCKET_STYLES = {
  'ss26-runway':
    'from-[hsl(var(--accent))]/80 via-[hsl(var(--accent))]/60 to-[hsl(var(--accent))]/30',
  street:
    'from-slate-900 via-slate-700 to-slate-500',
  sustainability:
    'from-emerald-800 via-emerald-600 to-emerald-400',
  influencers:
    'from-rose-800 via-rose-600 to-rose-400',
  second_hand:
    'from-amber-900 via-amber-700 to-amber-500',
  recycling:
    'from-teal-800 via-teal-600 to-teal-400',
  news_flash:
    'from-indigo-900 via-indigo-700 to-indigo-500',
};

/** Hero visual: image > video poster > colored gradient fallback. */
function ScoutMedia({ card }) {
  const gradient = BUCKET_STYLES[card.bucket] || BUCKET_STYLES['news_flash'];
  if (card.image_url) {
    return (
      <div className="relative aspect-[16/9] overflow-hidden rounded-lg bg-secondary">
        <img
          src={card.image_url}
          alt={card.headline}
          loading="lazy"
          onError={(e) => {
            // If the image is a fabricated URL the <img> errors; we swap to a gradient.
            e.currentTarget.style.display = 'none';
            e.currentTarget.parentElement?.classList.add(
              'bg-gradient-to-br',
              ...gradient.split(' '),
            );
          }}
          className="h-full w-full object-cover"
        />
      </div>
    );
  }
  if (card.video_url) {
    return (
      <div className="relative aspect-[16/9] overflow-hidden rounded-lg">
        <div
          className={cn(
            'absolute inset-0 bg-gradient-to-br',
            gradient,
          )}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="h-12 w-12 rounded-full bg-black/40 backdrop-blur flex items-center justify-center">
            <Play className="h-6 w-6 text-white" />
          </div>
        </div>
      </div>
    );
  }
  return (
    <div
      className={cn(
        'aspect-[16/9] rounded-lg bg-gradient-to-br flex items-center justify-center',
        gradient,
      )}
    >
      <Sparkles className="h-6 w-6 text-white/80" />
    </div>
  );
}

function ScoutCard({ card, t }) {
  const hasSource = card.source_url && card.source_name;
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl border border-border bg-card overflow-hidden shadow-editorial"
      data-testid={`fashion-scout-card-${card.id || card.bucket}`}
    >
      <div className="p-2">
        <ScoutMedia card={card} />
      </div>
      <div className="p-3 pt-1 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <Badge
            variant="outline"
            className="caps-label rounded-full text-[10px] bg-background"
          >
            {card.tag || card.bucket_label || card.bucket}
          </Badge>
          {card.date ? (
            <span className="text-[10px] text-muted-foreground">{card.date}</span>
          ) : null}
        </div>
        <h4 className="font-display text-base leading-snug">{card.headline}</h4>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {card.body}
        </p>
        {hasSource ? (
          <a
            href={card.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[11px] text-[hsl(var(--accent))] hover:underline"
            data-testid={`fashion-scout-source-${card.id || card.bucket}`}
          >
            {t('stylist.scoutSource')}: {card.source_name}
            <ExternalLink className="h-3 w-3" />
          </a>
        ) : null}
      </div>
    </motion.article>
  );
}

export function FashionScoutPanel() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const loc = useAppLocation();
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Regionalize the feed: user's preferred UI language + best-available
  // country code (live device > persisted home_location).
  const language = (user?.preferred_language || i18n.language || 'en')
    .split('-')[0]
    .toLowerCase();
  const country =
    (loc?.country_code || user?.home_location?.country_code || '')
      .toString()
      .toUpperCase() || null;

  const load = useCallback(async () => {
    try {
      const { cards: rows } = await api.fashionScoutFeed(12, {
        language,
        country,
      });
      setCards(rows || []);
    } catch {
      // non-fatal; keep whatever we had
    } finally {
      setLoading(false);
    }
  }, [language, country]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await api.trendsRunNowDev(true);
      await load();
      toast.success(t('stylist.scoutRefreshed'));
    } catch (err) {
      // Generator can take > 60s; even on timeout, fetch whatever landed.
      await load();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="p-3 border-b border-border">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="caps-label text-muted-foreground flex items-center gap-1">
              <Sparkles className="h-3 w-3" />
              {t('stylist.fashionScout')}
            </div>
            <h3 className="font-display text-lg truncate">
              {t('stylist.fashionScout')}
            </h3>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={refresh}
            disabled={refreshing}
            className="rounded-full h-8 shrink-0"
            data-testid="fashion-scout-refresh-btn"
          >
            {refreshing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <>
                <RefreshCw className="h-3.5 w-3.5 me-1" />
                <span className="text-xs">{t('stylist.refreshScout')}</span>
              </>
            )}
          </Button>
        </div>
        <p className="text-[11px] text-muted-foreground mt-1 line-clamp-2">
          {t('stylist.fashionScoutSub')}
        </p>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-3 space-y-3">
          {loading ? (
            <div className="py-8 flex items-center justify-center">
              <Loader2
                className="h-5 w-5 animate-spin text-muted-foreground"
                data-testid="fashion-scout-loading"
              />
            </div>
          ) : cards.length === 0 ? (
            <div
              className="text-center py-8 text-sm text-muted-foreground"
              data-testid="fashion-scout-empty"
            >
              {t('stylist.scoutEmpty')}
            </div>
          ) : (
            cards.map((c) => <ScoutCard key={c.id || c.bucket} card={c} t={t} />)
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
