import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
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
    (cents || 0) / 100
  );

const STATUS_TONE = {
  pending: 'bg-amber-100 text-amber-900 border-amber-200',
  paid: 'bg-emerald-100 text-emerald-900 border-emerald-200',
  cancelled: 'bg-rose-100 text-rose-900 border-rose-200',
  refunded: 'bg-slate-100 text-slate-800 border-slate-200',
};

export default function Transactions() {
  const [role, setRole] = useState('buyer');

  return (
    <div className="container-px max-w-5xl mx-auto pt-6 md:pt-10 pb-20">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="caps-label text-muted-foreground">Ledger</div>
          <h1 className="font-display text-3xl sm:text-4xl mt-1">Your transactions</h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-xl">
            Every purchase or sale you make through DressApp. 7% platform fee is
            applied after Stripe processing.
          </p>
        </div>
        <Button variant="outline" asChild className="rounded-xl" data-testid="transactions-goto-market">
          <Link to="/market"><ArrowUpRight className="h-4 w-4 mr-2" /> Marketplace</Link>
        </Button>
      </div>

      <Tabs value={role} onValueChange={setRole} className="w-full">
        <TabsList className="rounded-xl" data-testid="transactions-role-tabs">
          <TabsTrigger value="buyer" data-testid="transactions-tab-buyer">Purchases</TabsTrigger>
          <TabsTrigger value="seller" data-testid="transactions-tab-seller">Sales</TabsTrigger>
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
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .listTransactions({ role, limit: 100 })
      .then((res) => { if (active) setItems(res.items || []); })
      .catch((err) => toast.error(err?.response?.data?.detail || 'Failed to load transactions'))
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [role]);

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
          {role === 'buyer' ? 'No purchases yet' : 'No sales yet'}
        </h2>
        <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
          {role === 'buyer'
            ? 'Browse the marketplace to discover curated pieces with full fee transparency.'
            : 'List pieces from your closet and track the net payout you can expect here.'}
        </p>
        <Button asChild className="mt-4 rounded-xl" data-testid="transactions-empty-cta">
          <Link to={role === 'buyer' ? '/market' : '/market/create'}>
            {role === 'buyer' ? 'Shop marketplace' : 'Create a listing'}
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="transactions-list">
      {items.map((t) => {
        const cur = t.currency || 'USD';
        const f = t.financial || {};
        return (
          <Card key={t.id} className="rounded-[calc(var(--radius)+6px)] shadow-editorial"
            data-testid="transactions-list-item"
          >
            <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm truncate">
                    Listing {String(t.listing_id || '').slice(0, 8)}…
                  </span>
                  <Badge
                    variant="outline"
                    className={`capitalize text-[11px] ${STATUS_TONE[t.status] || ''}`}
                    data-testid="transactions-status-badge"
                  >
                    {t.status}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {new Date(t.created_at).toLocaleString()}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4 text-right sm:text-left sm:min-w-[340px]">
                <div>
                  <div className="caps-label text-muted-foreground">Gross</div>
                  <div className="font-display text-base">{fmt(f.gross_cents, cur)}</div>
                </div>
                <div>
                  <div className="caps-label text-muted-foreground">Platform 7%</div>
                  <div className="text-sm">{fmt(f.platform_fee_cents, cur)}</div>
                </div>
                <div>
                  <div className="caps-label text-muted-foreground">
                    {role === 'buyer' ? 'You paid' : 'Your net'}
                  </div>
                  <div className="font-display text-base">
                    {role === 'buyer'
                      ? fmt(f.gross_cents, cur)
                      : fmt(f.seller_net_cents, cur)}
                  </div>
                </div>
              </div>
              <Button
                asChild
                variant="ghost"
                size="sm"
                className="rounded-full"
                data-testid="transactions-open-listing"
              >
                <Link to={`/market/${t.listing_id}`}>View</Link>
              </Button>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
