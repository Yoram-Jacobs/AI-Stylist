/**
 * Transactions page — Wave 3 rewrite.
 *
 * UX:
 * - Primary tabs by transaction *kind*: All / Buying / Selling / Swaps /
 *   Donations. Counts next to each label so returning users instantly
 *   see where the activity is.
 * - Secondary multi-select chips let users narrow to specific statuses
 *   (pending / accepted / denied / shipped / completed / paid).
 * - Each row shows a kind-appropriate icon + status badge. If the row
 *   is a swap or donate that's been accepted but not yet confirmed by
 *   the current user, we surface a "Confirm receipt" CTA inline so
 *   the happy-path action is one click from the list.
 *
 * Fetch strategy: one pull from ``GET /transactions`` (role=all, limit=100)
 * per session; all filtering is client-side to keep the UI snappy and
 * reduce API churn.
 */
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Toggle } from '@/components/ui/toggle';
import {
  ArrowUpRight,
  Receipt,
  ShoppingBag,
  Repeat,
  HeartHandshake,
  Check,
  Loader2,
  CheckCircle2,
  Clock,
  XCircle,
  Package,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { toast } from 'sonner';

const fmt = (cents, cur = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: cur || 'USD' }).format(
    (cents || 0) / 100,
  );

const STATUS_TONE = {
  pending: 'bg-amber-100 text-amber-900 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900',
  paid: 'bg-emerald-100 text-emerald-900 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900',
  accepted: 'bg-emerald-100 text-emerald-900 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900',
  shipped: 'bg-sky-100 text-sky-900 border-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-900',
  completed: 'bg-emerald-100 text-emerald-900 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900',
  denied: 'bg-rose-100 text-rose-900 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-900',
  cancelled: 'bg-rose-100 text-rose-900 border-rose-200',
  refunded: 'bg-slate-100 text-slate-800 border-slate-200 dark:bg-slate-900 dark:text-slate-300',
  failed: 'bg-rose-100 text-rose-900 border-rose-200',
  disputed: 'bg-amber-100 text-amber-900 border-amber-200',
};

const STATUS_ICON = {
  pending: Clock,
  paid: CheckCircle2,
  accepted: CheckCircle2,
  shipped: Package,
  completed: CheckCircle2,
  denied: XCircle,
  cancelled: XCircle,
  refunded: Receipt,
  failed: XCircle,
  disputed: Clock,
};

const KIND_META = {
  buy: { icon: ShoppingBag, label: 'Purchase' },
  swap: { icon: Repeat, label: 'Swap' },
  donate: { icon: HeartHandshake, label: 'Donation' },
};

const STATUS_FILTER_OPTIONS = [
  'pending', 'accepted', 'denied', 'shipped', 'completed', 'paid', 'refunded',
];

/**
 * Decide whether the current user can click "Confirm receipt" on a row.
 * Rules:
 *   - Only swap/donate rows ever get the CTA (buy flows complete on capture).
 *   - Tx must be in an accepted or shipped state (not pending, denied, or
 *     already completed).
 *   - The current user must NOT have already confirmed their side.
 */
function canConfirmReceipt(tx, userId) {
  if (!userId) return false;
  if (!['swap', 'donate'].includes(tx.kind)) return false;
  if (!['accepted', 'shipped'].includes(tx.status)) return false;
  const role = tx.seller_id === userId ? 'lister' : 'swapper';
  const nested = tx[tx.kind] || {};
  return !nested[`${role}_received_at`];
}

export default function Transactions() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeKind, setActiveKind] = useState('all');
  const [statusFilter, setStatusFilter] = useState([]);

  const refresh = async () => {
    try {
      const res = await api.listTransactions({ role: 'all', limit: 200 });
      setItems(res.items || []);
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('transactions.loadFailed'));
    }
  };

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .listTransactions({ role: 'all', limit: 200 })
      .then((res) => { if (active) setItems(res.items || []); })
      .catch((err) => toast.error(err?.response?.data?.detail || t('transactions.loadFailed')))
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [t]);

  // --------- partitioned counts for the tab labels ---------
  const partitioned = useMemo(() => {
    const me = user?.id;
    const buying = items.filter((tx) => tx.buyer_id === me && (tx.kind || 'buy') === 'buy');
    const selling = items.filter((tx) => tx.seller_id === me && (tx.kind || 'buy') === 'buy');
    const swaps = items.filter((tx) => tx.kind === 'swap');
    const donations = items.filter((tx) => tx.kind === 'donate');
    return { all: items, buying, selling, swaps, donations };
  }, [items, user?.id]);

  const activeItems = useMemo(() => {
    const pool = partitioned[activeKind] || [];
    if (statusFilter.length === 0) return pool;
    return pool.filter((tx) => statusFilter.includes(tx.status));
  }, [partitioned, activeKind, statusFilter]);

  const toggleStatus = (s) =>
    setStatusFilter((cur) =>
      cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s],
    );

  const TAB_DEFS = [
    { value: 'all', label: 'All', count: partitioned.all.length },
    { value: 'buying', label: 'Buying', count: partitioned.buying.length },
    { value: 'selling', label: 'Selling', count: partitioned.selling.length },
    { value: 'swaps', label: 'Swaps', count: partitioned.swaps.length },
    { value: 'donations', label: 'Donations', count: partitioned.donations.length },
  ];

  return (
    <div className="container-px max-w-5xl mx-auto pt-6 md:pt-10 pb-20" data-testid="transactions-page">
      <div className="flex items-end justify-between mb-6 gap-3 flex-wrap">
        <div>
          <div className="caps-label text-muted-foreground">{t('transactions.label')}</div>
          <h1 className="font-display text-3xl sm:text-4xl mt-1">{t('transactions.title')}</h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-xl">{t('transactions.subtitle')}</p>
        </div>
        <Button variant="outline" asChild className="rounded-xl" data-testid="transactions-goto-market">
          <Link to="/market"><ArrowUpRight className="h-4 w-4 me-2" /> {t('transactions.goMarket')}</Link>
        </Button>
      </div>

      <Tabs value={activeKind} onValueChange={setActiveKind} className="w-full">
        <TabsList
          className="rounded-xl flex-wrap h-auto"
          data-testid="transactions-kind-tabs"
        >
          {TAB_DEFS.map((tab) => (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              className="gap-2"
              data-testid={`transactions-tab-${tab.value}`}
            >
              {tab.label}
              <Badge
                variant="secondary"
                className="text-[10px] h-5 px-1.5 min-w-[22px] justify-center"
                data-testid={`transactions-tab-count-${tab.value}`}
              >
                {tab.count}
              </Badge>
            </TabsTrigger>
          ))}
        </TabsList>

        {/* Status filter chips — shared across all tabs. */}
        <div
          className="flex flex-wrap gap-2 mt-5"
          data-testid="transactions-status-filters"
          aria-label="Filter by status"
        >
          {STATUS_FILTER_OPTIONS.map((s) => {
            const Icon = STATUS_ICON[s];
            const active = statusFilter.includes(s);
            return (
              <Toggle
                key={s}
                pressed={active}
                onPressedChange={() => toggleStatus(s)}
                className={[
                  'rounded-full border border-border data-[state=on]:border-[hsl(var(--accent))]',
                  'data-[state=on]:bg-[hsl(var(--accent))]/10 data-[state=on]:text-[hsl(var(--accent))]',
                  'h-8 px-3 text-xs capitalize gap-1.5',
                ].join(' ')}
                data-testid={`transactions-status-chip-${s}`}
              >
                {Icon && <Icon className="h-3 w-3" />}
                {s}
              </Toggle>
            );
          })}
          {statusFilter.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setStatusFilter([])}
              className="h-8 text-xs"
              data-testid="transactions-status-clear"
            >
              Clear
            </Button>
          )}
        </div>

        <TabsContent value={activeKind} className="mt-6">
          {loading ? (
            <div className="space-y-3" data-testid="transactions-loading">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-28 w-full rounded-[calc(var(--radius)+6px)]" />
              ))}
            </div>
          ) : activeItems.length === 0 ? (
            <EmptyState kind={activeKind} hasFilter={statusFilter.length > 0} />
          ) : (
            <div className="space-y-3" data-testid="transactions-list">
              {activeItems.map((tx) => (
                <TransactionRow
                  key={tx.id}
                  tx={tx}
                  userId={user?.id}
                  onConfirmed={refresh}
                />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function EmptyState({ kind, hasFilter }) {
  const { t } = useTranslation();
  const copy = {
    all: {
      title: 'No transactions yet',
      sub: 'Buy, swap, or donate from the marketplace to start building your history.',
    },
    buying: {
      title: t('transactions.emptyPurchases'),
      sub: t('transactions.emptyPurchasesSub'),
    },
    selling: {
      title: t('transactions.emptySales'),
      sub: t('transactions.emptySalesSub'),
    },
    swaps: {
      title: 'No swaps yet',
      sub: "When someone proposes a swap — or you propose one — it'll appear here.",
    },
    donations: {
      title: 'No donations yet',
      sub: "Share something you've outgrown or claim a freebie from your community.",
    },
  }[kind] || copy?.all;

  return (
    <div
      className="text-center py-16 border border-dashed rounded-[calc(var(--radius)+6px)]"
      data-testid="transactions-empty-state"
    >
      <Receipt className="h-8 w-8 mx-auto text-muted-foreground" />
      <h2 className="font-display text-xl mt-3">{copy.title}</h2>
      <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
        {hasFilter
          ? 'Nothing matches the active status filter. Try clearing it.'
          : copy.sub}
      </p>
      <Button asChild className="mt-4 rounded-xl" data-testid="transactions-empty-cta">
        <Link to="/market">Explore the marketplace</Link>
      </Button>
    </div>
  );
}

function TransactionRow({ tx, userId, onConfirmed }) {
  const [busy, setBusy] = useState(false);
  const cur = tx.currency || 'USD';
  const f = tx.financial || {};
  const kind = tx.kind || 'buy';
  const kindMeta = KIND_META[kind] || KIND_META.buy;
  const KIcon = kindMeta.icon;
  const SIcon = STATUS_ICON[tx.status];
  const canConfirm = canConfirmReceipt(tx, userId);
  const isBuyerSide = tx.buyer_id === userId;

  const handleConfirm = async () => {
    setBusy(true);
    try {
      await api.confirmReceipt(tx.id);
      toast.success('Receipt confirmed. Thanks for closing the loop!');
      onConfirmed?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not confirm receipt.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      className="rounded-[calc(var(--radius)+6px)] shadow-editorial"
      data-testid="transactions-list-item"
      data-kind={kind}
      id={`tx-${tx.id}`}
    >
      <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <KIcon className="h-4 w-4 text-[hsl(var(--accent))] shrink-0" />
            <span className="font-medium text-sm truncate">{kindMeta.label}</span>
            <Badge
              variant="outline"
              className={`capitalize text-[11px] gap-1 ${STATUS_TONE[tx.status] || ''}`}
              data-testid="transactions-status-badge"
            >
              {SIcon && <SIcon className="h-3 w-3" />}
              {tx.status}
            </Badge>
            {kind === 'buy' && (
              <span className="text-xs text-muted-foreground">
                · {isBuyerSide ? 'You bought' : 'You sold'}
              </span>
            )}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {new Date(tx.created_at).toLocaleString()}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 sm:gap-6 text-right sm:text-left">
          {kind === 'buy' ? (
            <>
              <div>
                <div className="caps-label text-muted-foreground">Gross</div>
                <div className="font-display text-base">{fmt(f.gross_cents, cur)}</div>
              </div>
              <div>
                <div className="caps-label text-muted-foreground">
                  {isBuyerSide ? 'You paid' : 'You net'}
                </div>
                <div className="font-display text-base">
                  {isBuyerSide ? fmt(f.gross_cents, cur) : fmt(f.seller_net_cents, cur)}
                </div>
              </div>
            </>
          ) : kind === 'donate' ? (
            <div>
              <div className="caps-label text-muted-foreground">
                {(f.gross_cents || 0) > 0 ? 'Shipping' : 'Fee'}
              </div>
              <div className="font-display text-base">
                {(f.gross_cents || 0) > 0 ? fmt(f.gross_cents, cur) : 'Free'}
              </div>
            </div>
          ) : (
            <div>
              <div className="caps-label text-muted-foreground">Swap</div>
              <div className="font-display text-base">Item ↔ Item</div>
            </div>
          )}

          <div className="flex items-center gap-1.5">
            {canConfirm && (
              <Button
                size="sm"
                className="rounded-full"
                onClick={handleConfirm}
                disabled={busy}
                data-testid="transactions-confirm-receipt"
              >
                {busy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <>
                    <Check className="h-3.5 w-3.5 me-1" /> Confirm receipt
                  </>
                )}
              </Button>
            )}
            <Button
              asChild
              variant="ghost"
              size="sm"
              className="rounded-full"
              data-testid="transactions-open-listing"
            >
              <Link to={`/market/${tx.listing_id}`}>View</Link>
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
