import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { ArrowUpRight, Receipt } from 'lucide-react';
import { api } from '@/lib/api';
import { toast } from 'sonner';

const fmt = (cents, cur = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: cur || 'USD' }).format(
    (cents || 0) / 100,
  );

const STATUS_TONE = {
  pending: 'bg-amber-100 text-amber-900 border-amber-200',
  paid: 'bg-emerald-100 text-emerald-900 border-emerald-200',
  cancelled: 'bg-rose-100 text-rose-900 border-rose-200',
  refunded: 'bg-slate-100 text-slate-800 border-slate-200',
};

export default function Transactions() {
  const { t } = useTranslation();
  const [role, setRole] = useState('buyer');

  return (
    <div className="container-px max-w-5xl mx-auto pt-6 md:pt-10 pb-20">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="caps-label text-muted-foreground">{t('transactions.label')}</div>
          <h1 className="font-display text-3xl sm:text-4xl mt-1">{t('transactions.title')}</h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-xl">{t('transactions.subtitle')}</p>
        </div>
        <Button variant="outline" asChild className="rounded-xl" data-testid="transactions-goto-market">
          <Link to="/market"><ArrowUpRight className="h-4 w-4 me-2" /> {t('transactions.goMarket')}</Link>
        </Button>
      </div>

      <Tabs value={role} onValueChange={setRole} className="w-full">
        <TabsList className="rounded-xl" data-testid="transactions-role-tabs">
          <TabsTrigger value="buyer" data-testid="transactions-tab-buyer">{t('transactions.purchases')}</TabsTrigger>
          <TabsTrigger value="seller" data-testid="transactions-tab-seller">{t('transactions.sales')}</TabsTrigger>
        </TabsList>
        <TabsContent value="buyer" className="mt-6">
          <TransactionsList role="buyer" />
        </TabsContent>
        <TabsContent value="seller" className="mt-6">
          <TransactionsList role="seller" />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function TransactionsList({ role }) {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .listTransactions({ role, limit: 100 })
      .then((res) => { if (active) setItems(res.items || []); })
      .catch((err) => toast.error(err?.response?.data?.detail || t('transactions.loadFailed')))
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [role, t]);

  if (loading) {
    return (
      <div className="space-y-3" data-testid="transactions-loading">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-[calc(var(--radius)+6px)]" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="text-center py-16 border border-dashed rounded-[calc(var(--radius)+6px)]"
        data-testid="transactions-empty-state"
      >
        <Receipt className="h-8 w-8 mx-auto text-muted-foreground" />
        <h2 className="font-display text-xl mt-3">
          {role === 'buyer' ? t('transactions.emptyPurchases') : t('transactions.emptySales')}
        </h2>
        <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
          {role === 'buyer' ? t('transactions.emptyPurchasesSub') : t('transactions.emptySalesSub')}
        </p>
        <Button asChild className="mt-4 rounded-xl" data-testid="transactions-empty-cta">
          <Link to={role === 'buyer' ? '/market' : '/market/create'}>
            {role === 'buyer' ? t('transactions.shopCTA') : t('transactions.createCTA')}
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="transactions-list">
      {items.map((tx) => {
        const cur = tx.currency || 'USD';
        const f = tx.financial || {};
        return (
          <Card key={tx.id} className="rounded-[calc(var(--radius)+6px)] shadow-editorial"
            data-testid="transactions-list-item">
            <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm truncate">
                    {t('transactions.listingShort', { id: String(tx.listing_id || '').slice(0, 8) })}
                  </span>
                  <Badge
                    variant="outline"
                    className={`capitalize text-[11px] ${STATUS_TONE[tx.status] || ''}`}
                    data-testid="transactions-status-badge"
                  >
                    {tx.status}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {new Date(tx.created_at).toLocaleString()}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4 text-right sm:text-left sm:min-w-[340px]">
                <div>
                  <div className="caps-label text-muted-foreground">{t('transactions.gross')}</div>
                  <div className="font-display text-base">{fmt(f.gross_cents, cur)}</div>
                </div>
                <div>
                  <div className="caps-label text-muted-foreground">{t('transactions.platform7')}</div>
                  <div className="text-sm">{fmt(f.platform_fee_cents, cur)}</div>
                </div>
                <div>
                  <div className="caps-label text-muted-foreground">
                    {role === 'buyer' ? t('transactions.youPaid') : t('transactions.yourNet')}
                  </div>
                  <div className="font-display text-base">
                    {role === 'buyer' ? fmt(f.gross_cents, cur) : fmt(f.seller_net_cents, cur)}
                  </div>
                </div>
              </div>
              <Button asChild variant="ghost" size="sm" className="rounded-full"
                data-testid="transactions-open-listing">
                <Link to={`/market/${tx.listing_id}`}>{t('transactions.view')}</Link>
              </Button>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
