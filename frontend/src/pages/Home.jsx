import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { Sparkles, CloudSun, Calendar, ArrowRight, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/lib/auth';
import { useClosetStore } from '@/lib/useClosetStore';
import { api } from '@/lib/api';
import { AdTicker } from '@/components/AdTicker';
import { LanguagePicker } from '@/components/LanguagePicker';
import { toast } from 'sonner';

// Fallback cards used only if the Trend-Scout endpoint fails or returns empty.
// Shape mirrors the real API (``label``, ``headline``, ``summary``) so the
// renderer below can read ONE consistent set of fields.
const FALLBACK_TRENDS = [
  { id: 'fb-1', label: 'SS26 Runway', headline: 'Butter yellow rules Milan', summary: 'Tailored blazers in soft butter-yellow replace ivory as the spring neutral.' },
  { id: 'fb-2', label: 'Street', headline: 'The quiet-luxe swap', summary: 'Logos out, fabric in: cashmere crewnecks over merino roll-necks dominate weekends.' },
  { id: 'fb-3', label: 'Sustainability', headline: 'Swap before you shop', summary: 'Community swap rooms grew 3x year-over-year; retailers are finally listening.' },
];

export default function Home() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const closet = useClosetStore();
  const isAdmin = (user?.roles || []).includes('admin');
  const [counts, setCounts] = useState(null);
  const [trends, setTrends] = useState(null); // null = loading, [] = empty, [...]
  const [trendDate, setTrendDate] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Pulled into a callback so the admin "🔄 refresh" button can re-fetch
  // the same trends without duplicating logic. The ``setTrends(null)``
  // gate keeps the skeletons visible during the LLM run (~5–10 s).
  const fetchTrends = async () => {
    try {
      const res = await api.trendsLatest(1);
      if (res?.cards?.length) {
        setTrends(res.cards);
        setTrendDate(res.cards[0]?.date || null);
      } else {
        setTrends([]);
      }
    } catch {
      setTrends([]);
    }
  };

  // Admin-only handler. We fire ``trendsRefreshAdmin({ force: true })``
  // so today's cards are regenerated even if they already exist
  // (otherwise the dedupe in ``run_trend_scout`` would skip the call
  // and the user would see no change). The endpoint is ~5–10 seconds
  // because it makes one Gemini call per bucket; we surface a toast
  // both on success and on failure so the user knows where they stand.
  const refreshTrends = async () => {
    if (refreshing) return;
    setRefreshing(true);
    setTrends(null); // restore skeletons while we wait
    try {
      await api.trendsRefreshAdmin(true);
      await fetchTrends();
      toast.success(t('home.trendsRefreshed', { defaultValue: 'Trends refreshed' }));
    } catch (err) {
      toast.error(
        err?.response?.data?.detail
          || t('home.trendsRefreshFailed', { defaultValue: 'Could not refresh trends' }),
      );
      // Recover the stale view so the section isn't stuck on skeletons.
      await fetchTrends();
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        // Read closet count straight from the global store (already
        // populated by AppLayout's prewarm) — no extra round-trip.
        // Marketplace count is still server-side because we don't
        // store all listings client-side.
        const market = await api.listListings({ limit: 1, status: 'active' });
        setCounts({
          closet: closet.total || (closet.items?.length ?? 0),
          market: market.total || 0,
        });
      } catch { setCounts({ closet: closet.total || 0, market: 0 }); }
    })();
    fetchTrends();
    // We intentionally only run this once per mount; closet.total
    // updates flow through the dedicated effect below so the chip
    // stays accurate after add/delete.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the closet chip in sync with store mutations from elsewhere
  // in the app (AddItem, ItemDetail delete, etc.) without a refetch.
  useEffect(() => {
    setCounts((prev) => {
      const closetCount = closet.total || (closet.items?.length ?? 0);
      if (prev && prev.closet === closetCount) return prev;
      return { closet: closetCount, market: prev?.market ?? 0 };
    });
  }, [closet.total, closet.items]);

  const firstName = (user?.display_name || user?.email || '').split(/\s|@/)[0];

  return (
    <div className="container-px max-w-6xl mx-auto pt-6 md:pt-10">
      <section className="relative overflow-hidden rounded-[calc(var(--radius)+6px)] hero-wash-light noise border border-border p-6 md:p-10">
        {/* Floating language picker — small "bulb" in the top-end corner
            of the hero. RTL-safe (end inset). Blends with the hero wash
            via a glassy backdrop. */}
        <div className="absolute top-4 end-4 z-10">
          <LanguagePicker
            className="rounded-full bg-card/70 backdrop-blur-sm border-border shadow-sm hover:bg-card"
            testIdSuffix="home"
          />
        </div>
        <div className="caps-label text-muted-foreground">{t('home.todayLabel')}</div>
        <h1 className="font-display text-3xl sm:text-4xl md:text-5xl leading-[1.05] mt-2" data-testid="home-greeting">
          {t('home.greeting')}<br/>{firstName || t('home.greetingFallback')}.
        </h1>
        <p className="mt-3 text-sm md:text-base text-muted-foreground max-w-xl">
          {t('home.stylistWarmed')}
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Button asChild className="rounded-xl" data-testid="home-ask-stylist-cta">
            <Link to="/stylist"><Sparkles className="h-4 w-4 me-2" /> {t('home.askStylist')}</Link>
          </Button>
          <Button asChild variant="secondary" className="rounded-xl" data-testid="home-closet-cta">
            <Link to="/closet">{t('home.openCloset')} <ArrowRight className="h-4 w-4 ms-2 rtl:rotate-180" /></Link>
          </Button>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <Badge variant="outline" className="rounded-full caps-label border-border bg-card" data-testid="home-weather-chip">
            <CloudSun className="h-3.5 w-3.5 me-1" /> {t('home.weatherAware')}
          </Badge>
          <Badge variant="outline" className="rounded-full caps-label border-border bg-card" data-testid="home-calendar-chip">
            <Calendar className="h-3.5 w-3.5 me-1" /> {t('home.calendarSmart')}
          </Badge>
        </div>
      </section>

      <section className="mt-8 grid grid-cols-1 sm:grid-cols-3 gap-4" data-testid="home-kpis">
        {[
          { label: t('home.piecesInCloset'), value: counts?.closet ?? '—', href: '/closet' },
          { label: t('home.activeListings'), value: counts?.market ?? '—', href: '/market' },
          { label: t('home.platformFee'), value: '7%', sub: t('home.platformFeeSub') },
        ].map((k) => (
          <Card key={k.label} className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
            <CardContent className="p-5">
              <div className="caps-label text-muted-foreground">{k.label}</div>
              <div className="mt-2 font-display text-4xl">{k.value}</div>
              {k.sub && <div className="text-xs text-muted-foreground mt-1">{k.sub}</div>}
              {k.href && (
                <Link to={k.href} className="inline-flex items-center text-sm text-[hsl(var(--accent))] mt-3">
                  {t('common.open')} <ArrowRight className="h-3.5 w-3.5 ms-1 rtl:rotate-180" />
                </Link>
              )}
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="mt-10">
        <div className="flex items-end justify-between mb-4 gap-3">
          <h2 className="font-display text-2xl sm:text-3xl">{t('home.trendScout')}</h2>
          <div className="flex items-center gap-2">
            <div className="caps-label text-muted-foreground">
              {trendDate ? t('home.dailyEditOn', { date: trendDate }) : t('home.dailyEdit')}
            </div>
            {/* Admin-only force-refresh button. Hidden for regular users
                — the daily 07:00 UTC cron + the auto-refresh on read in
                ``latest_trend_cards`` keep the feed fresh without manual
                intervention; this is just a triage / "I want it now"
                lever for the team. */}
            {isAdmin ? (
              <Button
                size="icon"
                variant="ghost"
                onClick={refreshTrends}
                disabled={refreshing}
                aria-label={t('home.refreshTrends', { defaultValue: 'Refresh trends' })}
                title={t('home.refreshTrends', { defaultValue: 'Refresh trends' })}
                className="h-8 w-8 rounded-full text-muted-foreground hover:text-foreground"
                data-testid="home-trends-refresh-btn"
              >
                <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              </Button>
            ) : null}
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="home-trend-scout-feed">
          {trends === null
            ? Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-40 w-full rounded-[calc(var(--radius)+6px)]" />
              ))
            : (trends.length > 0 ? trends : FALLBACK_TRENDS).map((card, i) => {
                // Normalise across (a) the real Trend-Scout payload from
                // ``GET /api/v1/trends/latest`` (``label``/``headline``/``summary``),
                // (b) older fallback shapes (``tag``/``title``/``body``/``blurb``),
                // and (c) the seed/demo payload. Without this normalisation the
                // home page silently rendered empty chips + empty body for the
                // real API because the previous code read ``t.tag``/``t.body``
                // which the API never sets — and ``t`` also shadowed the i18n
                // translator, so even the chip class hung off the wrong value.
                const _prettyBucket = (b) =>
                  (b || '')
                    .replace(/[-_]+/g, ' ')
                    .replace(/\b\w/g, (c) => c.toUpperCase());
                const chip = card.label || _prettyBucket(card.bucket) || card.tag;
                const headline = card.headline || card.title;
                const body = card.summary || card.body || card.blurb;
                const image = card.image_url;
                const key = card.id || `${chip || 'trend'}-${headline || i}`;
                return (
                  <motion.div
                    key={key}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.05 }}
                    data-testid="home-trend-scout-card"
                  >
                    <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial h-full overflow-hidden">
                      {image ? (
                        <div className="aspect-[16/9] bg-secondary overflow-hidden">
                          <img
                            src={image}
                            alt={headline || ''}
                            className="w-full h-full object-cover"
                            loading="lazy"
                          />
                        </div>
                      ) : null}
                      <CardContent className="p-5">
                        {chip ? (
                          <div className="caps-label text-[hsl(var(--accent))]">{chip}</div>
                        ) : null}
                        {headline ? (
                          <h3 className="font-display text-xl mt-2 leading-tight">{headline}</h3>
                        ) : null}
                        {body ? (
                          <p className="text-sm text-muted-foreground mt-3">{body}</p>
                        ) : null}
                      </CardContent>
                    </Card>
                  </motion.div>
                );
              })}
        </div>
      </section>

      <div className="h-10" />

      <AdTicker placement="home-footer" className="-mx-4 sm:-mx-6 lg:-mx-8" />
    </div>
  );
}
