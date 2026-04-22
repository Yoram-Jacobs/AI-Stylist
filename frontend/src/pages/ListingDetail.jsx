import { useEffect, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { AspectRatio } from '@/components/ui/aspect-ratio';
import { Badge } from '@/components/ui/badge';
import { SourceTagBadge } from '@/components/SourceTagBadge';
import { ArrowLeft, Eye, Loader2, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';

const fmt = (cents, cur = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: cur }).format((cents || 0) / 100);

export default function ListingDetail() {
  const { t } = useTranslation();
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [buying, setBuying] = useState(false);
  const [similar, setSimilar] = useState([]);
  const [similarMode, setSimilarMode] = useState(null);
  const [similarLoading, setSimilarLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setSimilarLoading(true);
    api.getListing(id)
      .then(setListing)
      .catch(() => { toast.error(t('market.listingNotFound')); nav('/market'); })
      .finally(() => setLoading(false));

    api.getSimilarListings(id, { limit: 6 })
      .then((res) => { setSimilar(res.items || []); setSimilarMode(res.mode || null); })
      .catch(() => { /* non-fatal */ })
      .finally(() => setSimilarLoading(false));
  }, [id, nav, t]);

  const onBuy = async () => {
    setBuying(true);
    try {
      const tx = await api.createTransaction({ listing_id: id });
      toast.success(t('market.txReserved'));
      nav(`/market#tx-${tx.id}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('market.purchaseFailed'));
    } finally { setBuying(false); }
  };

  if (loading) {
    return (
      <div className="container-px max-w-4xl mx-auto pt-6">
        <Skeleton className="aspect-[3/4] w-full rounded-[calc(var(--radius)+6px)]" />
      </div>
    );
  }
  if (!listing) return null;

  const fm = listing.financial_metadata || {};
  const isOwner = listing.seller_id === user?.id;

  return (
    <div className="container-px max-w-5xl mx-auto pt-4 md:pt-10">
      <button onClick={() => nav(-1)} className="inline-flex items-center text-sm text-muted-foreground mb-4">
        <ArrowLeft className="h-4 w-4 me-1 rtl:rotate-180" /> {t('common.back')}
      </button>
      <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
        <div className="md:col-span-3">
          <Card className="rounded-[calc(var(--radius)+6px)] overflow-hidden shadow-editorial">
            <AspectRatio ratio={3 / 4} className="bg-secondary">
              {(listing.images || [])[0]
                ? <img src={listing.images[0]} alt={listing.title} className="w-full h-full object-cover" />
                : <div className="w-full h-full flex items-center justify-center text-muted-foreground">{t('market.noImage')}</div>}
            </AspectRatio>
          </Card>
        </div>
        <div className="md:col-span-2 space-y-4">
          <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
            <CardContent className="p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h1 className="font-display text-2xl leading-tight" data-testid="listing-detail-title">{listing.title}</h1>
                  <div className="text-xs text-muted-foreground mt-1">
                    <Eye className="inline h-3 w-3 me-1" />{t('market.viewsCount', { count: listing.views || 0 })}
                  </div>
                </div>
                <SourceTagBadge source={listing.source} />
              </div>
              <div className="mt-3 font-display text-3xl" data-testid="listing-detail-price">{fmt(fm.list_price_cents, fm.currency)}</div>
              {listing.description && <p className="text-sm text-muted-foreground mt-3">{listing.description}</p>}
            </CardContent>
          </Card>

          <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial" data-testid="listing-detail-fee-breakdown">
            <CardContent className="p-5">
              <div className="caps-label text-muted-foreground">{t('market.feeBreakdown')}</div>
              <dl className="mt-3 text-sm space-y-2">
                <div className="flex justify-between"><dt className="text-muted-foreground">{t('market.listPrice')}</dt><dd>{fmt(fm.list_price_cents, fm.currency)}</dd></div>
                <div className="flex justify-between"><dt className="text-muted-foreground">{t('market.processingFee')}</dt><dd>− {fmt(fm.stripe_processing_fee_fixed_cents)} + 2.9%</dd></div>
                <div className="flex justify-between"><dt className="text-muted-foreground">{t('market.platformFee')}</dt><dd></dd></div>
                <div className="flex justify-between font-medium border-t border-border pt-2"><dt>{t('market.sellerNet')}</dt><dd>{fmt(fm.estimated_seller_net_cents, fm.currency)}</dd></div>
              </dl>
            </CardContent>
          </Card>

          {isOwner ? (
            <Button asChild variant="secondary" className="w-full rounded-xl" data-testid="listing-edit-button">
              <Link to={`/market`}>{t('market.manageInMine')}</Link>
            </Button>
          ) : listing.status === 'active' ? (
            <Button onClick={onBuy} disabled={buying} className="w-full rounded-xl" data-testid="listing-buy-button">
              {buying ? <Loader2 className="h-4 w-4 animate-spin" /> : t('market.reserveFor', { price: fmt(fm.list_price_cents, fm.currency) })}
            </Button>
          ) : (
            <div className="rounded-xl border border-border bg-secondary/60 p-4 text-sm text-muted-foreground" data-testid="listing-status-notice">
              {t('market.statusNotice', { status: listing.status })}
            </div>
          )}
        </div>
      </div>

      {/* Items like this */}
      {(similarLoading || similar.length > 0) && (
        <section className="mt-10" aria-labelledby="similar-listings-heading" data-testid="listing-similar-section">
          <div className="flex items-end justify-between mb-4">
            <div>
              <div className="caps-label text-muted-foreground flex items-center gap-1.5">
                {similarMode === 'embedding' ? (
                  <><Sparkles className="h-3 w-3 text-[hsl(var(--accent))]" /> {t('market.similarVisual')}</>
                ) : similarMode === 'category' ? (
                  <>{t('market.similarPopular')}</>
                ) : (
                  <>{t('market.similarYouMightLike')}</>
                )}
              </div>
              <h2 id="similar-listings-heading" className="font-display text-2xl mt-1">{t('market.similarTitle')}</h2>
            </div>
            <Button asChild variant="ghost" size="sm" className="rounded-lg">
              <Link to="/market">{t('market.seeAll')}</Link>
            </Button>
          </div>

          {similarLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="aspect-[3/4] w-full rounded-[calc(var(--radius)+6px)]" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4" data-testid="listing-similar-grid">
              {similar.map((s) => {
                const sm = s.financial_metadata || {};
                return (
                  <Link key={s.id} to={`/market/${s.id}`} className="block group" data-testid="listing-similar-card">
                    <Card className="rounded-[calc(var(--radius)+6px)] overflow-hidden border-border shadow-editorial group-hover:shadow-editorial-md transition-shadow">
                      <AspectRatio ratio={3 / 4} className="bg-secondary relative">
                        {(s.images || [])[0]
                          ? <img src={s.images[0]} alt={s.title} className="w-full h-full object-cover" />
                          : <div className="w-full h-full flex items-center justify-center text-muted-foreground caps-label">{t('market.noImage')}</div>}
                        {typeof s._score === 'number' && (
                          <Badge variant="outline"
                            className="absolute top-2 right-2 bg-background/85 backdrop-blur text-[10px] border-[hsl(var(--accent))]/50 flex items-center gap-1"
                            data-testid="listing-similar-score">
                            <Sparkles className="h-2.5 w-2.5 text-[hsl(var(--accent))]" />
                            {Math.round(s._score * 100)}%
                          </Badge>
                        )}
                      </AspectRatio>
                      <CardContent className="p-3">
                        <div className="font-medium text-sm truncate">{s.title}</div>
                        <div className="text-xs text-muted-foreground mt-0.5">{fmt(sm.list_price_cents, sm.currency)}</div>
                      </CardContent>
                    </Card>
                  </Link>
                );
              })}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
