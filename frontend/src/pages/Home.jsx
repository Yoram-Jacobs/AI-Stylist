import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Sparkles, CloudSun, Calendar, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/lib/auth';
import { api } from '@/lib/api';

const TRENDS = [
  { tag: 'SS26 Runway', title: 'Butter yellow rules Milan', blurb: 'Tailored blazers in soft butter-yellow replace ivory as the spring neutral.' },
  { tag: 'Street', title: 'The quiet-luxe swap', blurb: 'Logos out, fabric in: cashmere crewnecks over merino roll-necks dominate weekends.' },
  { tag: 'Sustainability', title: 'Swap before you shop', blurb: 'Community swap rooms grew 3x year-over-year; retailers are finally listening.' },
];

export default function Home() {
  const { user } = useAuth();
  const [counts, setCounts] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const closet = await api.listCloset({ limit: 1 });
        const market = await api.listListings({ limit: 1, status: 'active' });
        setCounts({ closet: closet.total || 0, market: market.total || 0 });
      } catch { setCounts({ closet: 0, market: 0 }); }
    })();
  }, []);

  const firstName = (user?.display_name || user?.email || '').split(/\s|@/)[0];

  return (
    <div className="container-px max-w-6xl mx-auto pt-6 md:pt-10">
      <section className="relative overflow-hidden rounded-[calc(var(--radius)+6px)] hero-wash-light noise border border-border p-6 md:p-10">
        <div className="caps-label text-muted-foreground">Today</div>
        <h1 className="font-display text-3xl sm:text-4xl md:text-5xl leading-[1.05] mt-2" data-testid="home-greeting">
          Good to see you,<br/>{firstName || 'there'}.
        </h1>
        <p className="mt-3 text-sm md:text-base text-muted-foreground max-w-xl">
          Your stylist is warmed up and your closet is one tap away.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Button asChild className="rounded-xl" data-testid="home-ask-stylist-cta">
            <Link to="/stylist"><Sparkles className="h-4 w-4 mr-2" /> Ask the stylist</Link>
          </Button>
          <Button asChild variant="secondary" className="rounded-xl" data-testid="home-closet-cta">
            <Link to="/closet">Open closet <ArrowRight className="h-4 w-4 ml-2" /></Link>
          </Button>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <Badge variant="outline" className="rounded-full caps-label border-border bg-card" data-testid="home-weather-chip">
            <CloudSun className="h-3.5 w-3.5 mr-1" /> Weather-aware
          </Badge>
          <Badge variant="outline" className="rounded-full caps-label border-border bg-card" data-testid="home-calendar-chip">
            <Calendar className="h-3.5 w-3.5 mr-1" /> Calendar-smart
          </Badge>
        </div>
      </section>

      <section className="mt-8 grid grid-cols-1 sm:grid-cols-3 gap-4" data-testid="home-kpis">
        {[
          { label: 'Pieces in your closet', value: counts?.closet ?? '—', href: '/closet' },
          { label: 'Active marketplace listings', value: counts?.market ?? '—', href: '/market' },
          { label: 'Platform fee', value: '7%', sub: 'after Stripe fees' },
        ].map((k) => (
          <Card key={k.label} className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
            <CardContent className="p-5">
              <div className="caps-label text-muted-foreground">{k.label}</div>
              <div className="mt-2 font-display text-4xl">{k.value}</div>
              {k.sub && <div className="text-xs text-muted-foreground mt-1">{k.sub}</div>}
              {k.href && (
                <Link to={k.href} className="inline-flex items-center text-sm text-[hsl(var(--accent))] mt-3">
                  Open <ArrowRight className="h-3.5 w-3.5 ml-1" />
                </Link>
              )}
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="mt-10">
        <div className="flex items-end justify-between mb-4">
          <h2 className="font-display text-2xl sm:text-3xl">Trend-Scout</h2>
          <div className="caps-label text-muted-foreground">Daily edit</div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="home-trend-scout-feed">
          {TRENDS.map((t, i) => (
            <motion.div key={t.title} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial h-full">
                <CardContent className="p-5">
                  <div className="caps-label text-[hsl(var(--accent))]">{t.tag}</div>
                  <h3 className="font-display text-xl mt-2 leading-tight">{t.title}</h3>
                  <p className="text-sm text-muted-foreground mt-3">{t.blurb}</p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      </section>

      <div className="h-10" />
    </div>
  );
}
