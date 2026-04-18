import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { AspectRatio } from '@/components/ui/aspect-ratio';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { SourceTagBadge } from '@/components/SourceTagBadge';
import { Plus } from 'lucide-react';
import { api } from '@/lib/api';
import { toast } from 'sonner';

const fmt = (cents, cur = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: cur }).format((cents || 0) / 100);

const SOURCES = ['all', 'Shared', 'Retail'];
const CATEGORIES = ['all', 'top', 'bottom', 'outerwear', 'shoes', 'accessory', 'dress'];

export default function Marketplace() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ source: 'all', category: 'all' });

  const load = async () => {
    setLoading(true);
    try {
      const params = { status: 'active' };
      if (filters.source !== 'all') params.source = filters.source;
      if (filters.category !== 'all') params.category = filters.category;
      const res = await api.listListings(params);
      setItems(res.items || []);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load marketplace');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filters.source, filters.category]);

  return (
    <div className="container-px max-w-6xl mx-auto pt-6 md:pt-10">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="caps-label text-muted-foreground">Marketplace</div>
          <h1 className="font-display text-3xl sm:text-4xl mt-1">Shop, swap, donate</h1>
        </div>
        <Button asChild className="rounded-xl" data-testid="marketplace-create-listing">
          <Link to="/market/create"><Plus className="h-4 w-4 mr-2" /> Create listing</Link>
        </Button>
      </div>

      <Tabs defaultValue="browse" className="w-full">
        <TabsList className="rounded-xl" data-testid="marketplace-tabs">
          <TabsTrigger value="browse" data-testid="marketplace-tab-browse">Browse</TabsTrigger>
          <TabsTrigger value="mine" data-testid="marketplace-tab-mine">My listings</TabsTrigger>
          <TabsTrigger value="tx" data-testid="marketplace-tab-transactions">Transactions</TabsTrigger>
        </TabsList>

        <TabsContent value="browse" className="mt-4">
          <div className="flex flex-wrap gap-2 mb-4">
            <Select value={filters.source} onValueChange={(v) => setFilters((f) => ({ ...f, source: v }))}>
              <SelectTrigger className="w-[140px] rounded-xl" data-testid="market-source-select"><SelectValue /></SelectTrigger>
              <SelectContent>{SOURCES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
            <Select value={filters.category} onValueChange={(v) => setFilters((f) => ({ ...f, category: v }))}>
              <SelectTrigger className="w-[140px] rounded-xl" data-testid="market-category-select"><SelectValue /></SelectTrigger>
              <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
            </Select>
          </div>

          {loading && (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i}><Skeleton className="aspect-[3/4] w-full rounded-[calc(var(--radius)+6px)]" /></div>
              ))}
            </div>
          )}

          {!loading && items.length === 0 && (
            <div className="text-center py-16" data-testid="marketplace-empty-state">
              <h2 className="font-display text-2xl">Nothing matching yet</h2>
              <p className="text-sm text-muted-foreground mt-2">Try widening your filters or check back after today's Trend-Scout update.</p>
            </div>
          )}

          {!loading && items.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4" data-testid="marketplace-grid">
              {items.map((l) => (
                <Link key={l.id} to={`/market/${l.id}`} data-testid="marketplace-item-card">
                  <Card className="rounded-[calc(var(--radius)+6px)] overflow-hidden shadow-editorial hover:shadow-editorial-md transition-shadow">
                    <AspectRatio ratio={3 / 4} className="bg-secondary">
                      {(l.images || [])[0]
                        ? <img src={l.images[0]} alt={l.title} className="w-full h-full object-cover" />
                        : <div className="w-full h-full flex items-center justify-center text-muted-foreground caps-label">No image</div>}
                    </AspectRatio>
                    <CardContent className="p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="font-medium text-sm truncate">{l.title}</div>
                        <SourceTagBadge source={l.source} />
                      </div>
                      <div className="mt-1 flex items-center justify-between">
                        <div className="font-display text-lg">{fmt(l.financial_metadata?.list_price_cents)}</div>
                        <div className="text-[11px] text-muted-foreground">net {fmt(l.financial_metadata?.estimated_seller_net_cents)}</div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="mine"><MyListings /></TabsContent>
        <TabsContent value="tx"><Transactions /></TabsContent>
      </Tabs>
    </div>
  );
}

function MyListings() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      try {
        const { data: me } = await (await fetch((process.env.REACT_APP_BACKEND_URL + '/api/v1/auth/me'), { headers: { Authorization: `Bearer ${localStorage.getItem('dressapp.token')}` } })).json().then((d) => ({ data: d }));
        const res = await api.listListings({ seller_id: me.id, limit: 50 });
        setItems(res.items || []);
      } catch { /* ignore */ }
      finally { setLoading(false); }
    })();
  }, []);
  if (loading) return <div className="py-10 caps-label text-muted-foreground">Loading…</div>;
  if (items.length === 0) return <div className="py-10 text-sm text-muted-foreground">You have no listings yet.</div>;
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4" data-testid="market-my-listings-grid">
      {items.map((l) => (
        <Link key={l.id} to={`/market/${l.id}`}>
          <Card className="rounded-[calc(var(--radius)+6px)] overflow-hidden shadow-editorial">
            <AspectRatio ratio={3/4} className="bg-secondary">
              {(l.images||[])[0] ? <img src={l.images[0]} alt={l.title} className="w-full h-full object-cover"/> : null}
            </AspectRatio>
            <CardContent className="p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium text-sm truncate">{l.title}</div>
                <SourceTagBadge source={l.source} />
              </div>
              <div className="text-xs text-muted-foreground mt-1">{l.status}</div>
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}

function Transactions() {
  const [tab, setTab] = useState('buyer');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    setLoading(true);
    api.listTransactions({ role: tab }).then((res) => setItems(res.items || [])).finally(() => setLoading(false));
  }, [tab]);
  return (
    <div className="pt-2">
      <div className="flex gap-2 mb-4">
        {['buyer', 'seller'].map((t) => (
          <Button key={t} size="sm" variant={tab === t ? 'default' : 'secondary'}
            onClick={() => setTab(t)} className="rounded-full capitalize" data-testid={`tx-tab-${t}`}>{t}</Button>
        ))}
      </div>
      {loading ? <div className="caps-label text-muted-foreground">Loading…</div>
        : items.length === 0 ? <div className="text-sm text-muted-foreground">No transactions yet.</div>
        : (
          <div className="space-y-3" data-testid="tx-list">
            {items.map((t) => (
              <Card key={t.id} className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
                <CardContent className="p-4 flex items-center justify-between">
                  <div>
                    <div className="font-medium text-sm">Listing {t.listing_id.slice(0, 8)}…</div>
                    <div className="text-xs text-muted-foreground">{t.status} · {new Date(t.created_at).toLocaleString()}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-display text-lg">{fmt(t.financial?.gross_cents, t.currency)}</div>
                    <div className="text-[11px] text-muted-foreground">platform {fmt(t.financial?.platform_fee_cents, t.currency)} · seller {fmt(t.financial?.seller_net_cents, t.currency)}</div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
    </div>
  );
}
