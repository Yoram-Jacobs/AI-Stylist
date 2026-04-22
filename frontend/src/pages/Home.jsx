import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { Sparkles, CloudSun, Calendar, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/lib/auth';
import { api } from '@/lib/api';

// Fallback cards used only if the Trend-Scout endpoint fails or returns empty.
const FALLBACK_TRENDS = [
  { tag: 'SS26 Runway', headline: 'Butter yellow rules Milan', body: 'Tailored blazers in soft butter-yellow replace ivory as the spring neutral.' },
  { tag: 'Street', headline: 'The quiet-luxe swap', body: 'Logos out, fabric in: cashmere crewnecks over merino roll-necks dominate weekends.' },
  { tag: 'Sustainability', headline: 'Swap before you shop', body: 'Community swap rooms grew 3x year-over-year; retailers are finally listening.' },
];

export default function Home() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [counts, setCounts] = useState(null);
  const [trends, setTrends] = useState(null); // null = loading, [] = empty, [...]
  const [trendDate, setTrendDate] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const closet = await api.listCloset({ limit: 1 });
        const market = await api.listListings({ limit: 1, status: 'active' });
        setCounts({ closet: closet.total || 0, market: market.total || 0 });
      } catch { setCounts({ closet: 0, market: 0 }); }
    })();
    (async () => {
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
    })();
  }, []);

  const firstName = (user?.display_name || user?.email || '').split(/\s|@/)[0];

  return (
    <div className="container-px max-w-6xl mx-auto pt-6 md:pt-10">
      <section className="relative overflow-hidden rounded-[calc(var(--radius)+6px)] hero-wash-light noise border border-border p-6 md:p-10">
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
        <div className="flex items-end justify-between mb-4">
          <h2 className="font-display text-2xl sm:text-3xl">{t('home.trendScout')}</h2>
          <div className="caps-label text-muted-foreground">
            {trendDate ? t('home.dailyEditOn', { date: trendDate }) : t('home.dailyEdit')}
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="home-trend-scout-feed">
          {trends === null
            ? Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-40 w-full rounded-[calc(var(--radius)+6px)]" />
              ))
            : (trends.length > 0 ? trends : FALLBACK_TRENDS).map((t, i) => {
                const headline = t.headline || t.title;
                const body = t.body || t.blurb;
                return (
                  <motion.div
                    key={`${t.tag}-${headline}`}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.05 }}
                    data-testid="home-trend-scout-card"
                  >
                    <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial h-full">
                      <CardContent className="p-5">
                        <div className="caps-label text-[hsl(var(--accent))]">{t.tag}</div>
                        <h3 className="font-display text-xl mt-2 leading-tight">{headline}</h3>
                        <p className="text-sm text-muted-foreground mt-3">{body}</p>
                      </CardContent>
                    </Card>
                  </motion.div>
                );
              })}
        </div>
      </section>

      <div className="h-10" />
    </div>
  );
}
