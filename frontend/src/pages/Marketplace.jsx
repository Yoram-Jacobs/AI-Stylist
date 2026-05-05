import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { AspectRatio } from '@/components/ui/aspect-ratio';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { SourceTagBadge } from '@/components/SourceTagBadge';
import { Plus, MapPin } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import { labelForCategory, labelForSource, labelForIntent } from '@/lib/taxonomy';
import { useLocation as useAppLocation } from '@/lib/location';
import { toast } from 'sonner';

const fmt = (cents, cur = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: cur }).format((cents || 0) / 100);

// Marketplace filter dropdown.
//
// Replaced the catch-all "Shared" with the three concrete marketplace
// modes so users can drill straight to "Just show me items For sale"
// or "Just show me Donations".
//
// Values in {Retail} key on listing.source; values in
// {for_sale, swap, donate} key on listing.mode (where ``for_sale`` →
// ``mode=sell`` on the wire).
const SOURCES = ['all', 'for_sale', 'swap', 'donate', 'Retail'];
const _INTENT_VALUES = new Set(['for_sale', 'swap', 'donate']);
const _INTENT_TO_MODE = { for_sale: 'sell', swap: 'swap', donate: 'donate' };
const CATEGORIES = ['all', 'top', 'bottom', 'outerwear', 'shoes', 'accessory', 'dress'];
const RADIUS_OPTIONS = ['any', '5', '25', '50', '200'];

export default function Marketplace() {
  const { t } = useTranslation();
  const loc = useAppLocation();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ source: 'all', category: 'all', radius: 'any' });

  const load = async () => {
    setLoading(true);
    try {
      const params = { status: 'active' };
      // Source filter is multiplexed on the marketplace page: classic
      // source values (Retail) hit ``?source=…`` while the new intent
      // values (for_sale/swap/donate) hit ``?mode=…`` (with for_sale →
      // sell on the wire). The marketplace browse always implies
      // source=Shared so we don't need to send it explicitly.
      if (filters.source === 'Retail') {
        params.source = 'Retail';
      } else if (_INTENT_VALUES.has(filters.source)) {
        params.mode = _INTENT_TO_MODE[filters.source];
      }
      if (filters.category !== 'all') params.category = filters.category;
      // Attach coords whenever we have them so the server can rank results
      // by proximity; honour the user's radius filter when it's not "any".
      if (loc?.coords?.lat != null && loc?.coords?.lng != null) {
        params.lat = loc.coords.lat;
        params.lng = loc.coords.lng;
        if (filters.radius !== 'any') params.radius_km = Number(filters.radius);
      }
      const res = await api.listListings(params);
      setItems(res.items || []);
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('market.loadFailed'));
    } finally { setLoading(false); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [filters.source, filters.category, filters.radius, loc?.coords?.lat, loc?.coords?.lng]);

  return (
    <div className="container-px max-w-6xl mx-auto pt-6 md:pt-10">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="caps-label text-muted-foreground">{t('market.title')}</div>
          <h1 className="font-display text-3xl sm:text-4xl mt-1">{t('market.hero')}</h1>
        </div>
        <Button asChild className="rounded-xl" data-testid="marketplace-create-listing">
          <Link to="/market/create"><Plus className="h-4 w-4 me-2" /> {t('market.createListing')}</Link>
        </Button>
      </div>

      <Tabs defaultValue="browse" className="w-full">
        <TabsList className="rounded-xl" data-testid="marketplace-tabs">
          <TabsTrigger value="browse" data-testid="marketplace-tab-browse">{t('market.browse')}</TabsTrigger>
          <TabsTrigger value="mine" data-testid="marketplace-tab-mine">{t('market.myListings')}</TabsTrigger>
          <TabsTrigger value="tx" data-testid="marketplace-tab-transactions">{t('market.transactionsTab')}</TabsTrigger>
        </TabsList>

        <TabsContent value="browse" className="mt-4">
          <div className="flex flex-wrap gap-2 mb-4">
            <Select value={filters.source} onValueChange={(v) => setFilters((f) => ({ ...f, source: v }))}>
              <SelectTrigger className="w-[140px] rounded-xl" data-testid="market-source-select"><SelectValue /></SelectTrigger>
              <SelectContent>{SOURCES.map((s) => (
                <SelectItem key={s} value={s}>
                  {_INTENT_VALUES.has(s) ? labelForIntent(s, t) : labelForSource(s, t)}
                </SelectItem>
              ))}</SelectContent>
            </Select>
            <Select value={filters.category} onValueChange={(v) => setFilters((f) => ({ ...f, category: v }))}>
              <SelectTrigger className="w-[140px] rounded-xl" data-testid="market-category-select"><SelectValue /></SelectTrigger>
              <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{labelForCategory(c, t)}</SelectItem>)}</SelectContent>
            </Select>
            {loc?.coords ? (
              <Select
                value={filters.radius}
                onValueChange={(v) => setFilters((f) => ({ ...f, radius: v }))}
              >
                <SelectTrigger
                  className="w-[160px] rounded-xl"
                  data-testid="market-radius-select"
                >
                  <MapPin className="h-3.5 w-3.5 me-1 text-[hsl(var(--accent))]" />
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RADIUS_OPTIONS.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r === 'any'
                        ? t('market.anyDistance')
                        : t('market.radiusKm', { km: r })}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Badge
                variant="outline"
                className="text-[11px] rounded-full bg-card"
                data-testid="market-location-hint"
              >
                <MapPin className="h-3 w-3 me-1" />
                {t('market.needLocationForNearby')}
              </Badge>
            )}
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
              <h2 className="font-display text-2xl">{t('market.noMatching')}</h2>
              <p className="text-sm text-muted-foreground mt-2">{t('market.noMatchingSub')}</p>
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
                        : <div className="w-full h-full flex items-center justify-center text-muted-foreground caps-label">{t('market.noImage')}</div>}
                    </AspectRatio>
                    <CardContent className="p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="font-medium text-sm truncate">{l.title}</div>
                        <SourceTagBadge source={l.source} mode={l.mode} />
                      </div>
                      <div className="mt-1 flex items-center justify-between">
                        <div className="font-display text-lg">{fmt(l.financial_metadata?.list_price_cents)}</div>
                        <div className="text-[11px] text-muted-foreground">
                          {t('market.netShort', { amount: fmt(l.financial_metadata?.estimated_seller_net_cents) })}
                        </div>
                      </div>
                      {typeof l.distance_km === 'number' ? (
                        <Badge
                          variant="outline"
                          className="mt-2 text-[10px] rounded-full bg-card gap-1"
                          data-testid="marketplace-item-distance"
                        >
                          <MapPin className="h-2.5 w-2.5" />
                          {t('market.distanceKmAway', { km: l.distance_km })}
                        </Badge>
                      ) : null}
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="mine"><MyListings /></TabsContent>
        <TabsContent value="tx"><InlineTransactions /></TabsContent>
      </Tabs>
    </div>
  );
}

function MyListings() {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [removingId, setRemovingId] = useState(null);
  const [syncing, setSyncing] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const me = await api.me();
      const res = await api.listListings({ seller_id: me.id, limit: 50 });
      setItems(res.items || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  // Hard-delete the listing AND reset the linked closet item back to
  // private/own (handled atomically on the backend). The closet card
  // flips to "Private" on next render so the user gets immediate
  // feedback that the item is no longer on the marketplace.
  const removeListing = async (l) => {
    if (!window.confirm(t('market.confirmRemoveListing', { defaultValue: `Remove "${l.title}" from the marketplace?` }))) return;
    setRemovingId(l.id);
    try {
      await api.deleteListing(l.id);
      toast.success(t('market.listingRemoved', { defaultValue: 'Removed from marketplace' }));
      setItems((prev) => prev.filter((x) => x.id !== l.id));
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('market.removeFailed', { defaultValue: 'Could not remove listing' }));
    } finally {
      setRemovingId(null);
    }
  };

  // One-shot rescue for users whose closet items have a
  // marketplace_intent set (swap/donate/for_sale) but never made it
  // to the marketplace — typically because they pre-date the
  // auto-list pipeline. Idempotent on the server, so re-running is
  // safe.
  const syncMarketplace = async () => {
    setSyncing(true);
    try {
      const res = await api.backfillMarketplaceListings();
      const created = res?.created || 0;
      const skipped = res?.skipped_existing || 0;
      const synced = res?.source_synced || 0;
      const candidates = res?.candidates || 0;
      if (candidates === 0) {
        toast.info(t('market.syncNoCandidates', {
          defaultValue: 'Nothing to sync — no closet items have a marketplace intent set.',
        }));
      } else {
        toast.success(t('market.syncDone', {
          defaultValue: `Synced ${candidates} item(s): ${created} listed, ${skipped} already on marketplace${synced ? `, ${synced} re-flagged Shared` : ''}.`,
        }));
      }
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('market.syncFailed', { defaultValue: 'Could not sync marketplace' }));
    } finally {
      setSyncing(false);
    }
  };

  if (loading) return <div className="py-10 caps-label text-muted-foreground">{t('market.loading')}</div>;

  return (
    <div className="space-y-4">
      {/* Top bar: sync rescue button + count */}
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm text-muted-foreground" data-testid="my-listings-count">
          {t('market.myListingsCount', { count: items.length, defaultValue: `${items.length} listing${items.length === 1 ? '' : 's'}` })}
        </div>
        <Button
          variant="outline"
          size="sm"
          className="rounded-full"
          onClick={syncMarketplace}
          disabled={syncing}
          data-testid="sync-marketplace-btn"
        >
          {syncing
            ? t('market.syncing', { defaultValue: 'Syncing…' })
            : t('market.syncMarketplace', { defaultValue: 'Sync from closet' })}
        </Button>
      </div>

      {items.length === 0 ? (
        <div className="py-10 text-sm text-muted-foreground">{t('market.noMyListings')}</div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4" data-testid="market-my-listings-grid">
          {items.map((l) => (
            <Card
              key={l.id}
              className="rounded-[calc(var(--radius)+6px)] overflow-hidden shadow-editorial group relative"
              data-testid={`my-listing-card-${l.id}`}
            >
              <Link to={`/market/${l.id}`} className="block">
                <AspectRatio ratio={3 / 4} className="bg-secondary">
                  {(l.images || [])[0] ? <img src={l.images[0]} alt={l.title} className="w-full h-full object-cover" /> : null}
                </AspectRatio>
                <CardContent className="p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-sm truncate">{l.title}</div>
                    <SourceTagBadge source={l.source} mode={l.mode} />
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {l.status}
                  </div>
                </CardContent>
              </Link>
              <div className="px-3 pb-3">
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full rounded-lg text-xs h-8 text-rose-700 hover:text-rose-800 hover:bg-rose-50"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    removeListing(l);
                  }}
                  disabled={removingId === l.id}
                  data-testid={`my-listing-remove-${l.id}`}
                >
                  {removingId === l.id
                    ? t('market.removing', { defaultValue: 'Removing…' })
                    : t('market.removeListing', { defaultValue: 'Remove listing' })}
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function InlineTransactions() {
  const { t } = useTranslation();
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
        {['buyer', 'seller'].map((role) => (
          <Button key={role} size="sm" variant={tab === role ? 'default' : 'secondary'}
            onClick={() => setTab(role)} className="rounded-full capitalize" data-testid={`tx-tab-${role}`}>
            {role === 'buyer' ? t('transactions.buyer') : t('transactions.seller')}
          </Button>
        ))}
      </div>
      {loading ? <div className="caps-label text-muted-foreground">{t('market.loading')}</div>
        : items.length === 0 ? <div className="text-sm text-muted-foreground">{t('market.noTx')}</div>
        : (
          <div className="space-y-3" data-testid="tx-list">
            {items.map((tx) => (
              <Card key={tx.id} className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
                <CardContent className="p-4 flex items-center justify-between">
                  <div>
                    <div className="font-medium text-sm">{t('transactions.listingShort', { id: tx.listing_id.slice(0, 8) })}</div>
                    <div className="text-xs text-muted-foreground">{tx.status} · {new Date(tx.created_at).toLocaleString()}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-display text-lg">{fmt(tx.financial?.gross_cents, tx.currency)}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {t('market.platformFee')}: {fmt(tx.financial?.platform_fee_cents, tx.currency)} · {t('market.sellerNet')}: {fmt(tx.financial?.seller_net_cents, tx.currency)}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
    </div>
  );
}
