/**
 * TransactionLanding — the page a user lands on after clicking an
 * accept / deny button inside a Wave 2 transactional email.
 *
 * The route is reachable without auth so a logged-out browser (e.g. a
 * user checking email on a different device) can still see the final
 * outcome. We fetch a minimal public projection from
 * ``/transactions/:id/landing-summary`` — no buyer/seller IDs, no
 * financial internals — and render a status banner + listing summary.
 */
import { useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { AspectRatio } from '@/components/ui/aspect-ratio';
import { Badge } from '@/components/ui/badge';
import {
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  ArrowRight,
} from 'lucide-react';
import { api } from '@/lib/api';

const fmt = (cents, cur = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: cur }).format(
    (cents || 0) / 100,
  );

const STATUS_COPY = {
  accepted: {
    icon: CheckCircle2,
    tone: 'text-emerald-700 dark:text-emerald-400',
    tint: 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-900',
    title: 'Accepted',
    body:
      'Thanks — the other party has been notified. Check your email for shipping details and tap "Confirm receipt" once the item arrives.',
  },
  denied: {
    icon: XCircle,
    tone: 'text-rose-700 dark:text-rose-400',
    tint: 'bg-rose-50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-900',
    title: 'Declined',
    body:
      'No worries — we let the other party know. The item is still out there; plenty more to explore in the marketplace.',
  },
  pending: {
    icon: Clock,
    tone: 'text-amber-700 dark:text-amber-400',
    tint: 'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-900',
    title: 'Pending',
    body:
      "We're waiting on the other party to accept or decline. We'll email you as soon as they do.",
  },
  invalid: {
    icon: AlertTriangle,
    tone: 'text-muted-foreground',
    tint: 'bg-muted border-border',
    title: 'Link expired or already used',
    body:
      'This link is no longer active. Head back to the marketplace to explore more listings or check your transactions.',
  },
};

export default function TransactionLanding() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const rawStatus = params.get('status') || 'pending';
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    api
      .getLandingSummary(id)
      .then(setData)
      .catch((e) => setError(e?.response?.data?.detail || 'Could not load transaction.'))
      .finally(() => setLoading(false));
  }, [id]);

  // Normalise the status: if the URL says "accepted" but the backend
  // already has ``swap.denied_at`` (token-reuse after a deny), trust
  // the backend. Falls back to the URL query otherwise.
  const resolvedStatus = useMemo(() => {
    const tx = data?.transaction;
    if (tx?.status === 'accepted' || tx?.status === 'completed') return 'accepted';
    if (tx?.status === 'denied') return 'denied';
    if (tx?.status === 'pending') return 'pending';
    return ['accepted', 'denied', 'pending', 'invalid'].includes(rawStatus)
      ? rawStatus
      : 'invalid';
  }, [data, rawStatus]);

  const copy = STATUS_COPY[resolvedStatus] || STATUS_COPY.invalid;
  const Icon = copy.icon;

  const listing = data?.listing;
  const fm = listing?.financial_metadata || {};

  return (
    <div className="container-px max-w-3xl mx-auto pt-6 md:pt-10 pb-16" data-testid="transaction-landing">
      <Card
        className={[
          'rounded-[calc(var(--radius)+6px)] border shadow-editorial mb-6',
          copy.tint,
        ].join(' ')}
      >
        <CardContent className="p-6 flex items-start gap-4">
          <div className={`shrink-0 ${copy.tone}`}>
            <Icon className="h-10 w-10" aria-hidden />
          </div>
          <div className="min-w-0">
            <div className="caps-label opacity-70">Transaction status</div>
            <h1
              className="font-display text-3xl leading-tight mt-1"
              data-testid="transaction-landing-title"
            >
              {copy.title}
            </h1>
            <p className="text-sm mt-2 leading-relaxed" data-testid="transaction-landing-body">
              {copy.body}
            </p>
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <Skeleton className="aspect-[16/9] w-full rounded-[calc(var(--radius)+6px)]" />
      ) : error ? (
        <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
          <CardContent className="p-6 text-sm text-muted-foreground">
            {error}
          </CardContent>
        </Card>
      ) : listing ? (
        <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial overflow-hidden">
          <div className="grid grid-cols-1 md:grid-cols-5">
            <div className="md:col-span-2">
              <AspectRatio ratio={3 / 4} className="bg-secondary">
                {(listing.images || [])[0] ? (
                  <img
                    src={listing.images[0]}
                    alt={listing.title}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-muted-foreground caps-label">
                    No image
                  </div>
                )}
              </AspectRatio>
            </div>
            <CardContent className="md:col-span-3 p-6 space-y-4">
              <div>
                <div className="caps-label text-muted-foreground">
                  {(data?.transaction?.kind || 'transaction').toUpperCase()}
                </div>
                <h2
                  className="font-display text-2xl mt-1"
                  data-testid="transaction-landing-listing-title"
                >
                  {listing.title}
                </h2>
                {listing.mode === 'sell' && fm.list_price_cents != null && (
                  <div className="font-display text-2xl mt-2">
                    {fmt(fm.list_price_cents, fm.currency)}
                  </div>
                )}
              </div>

              <div className="flex flex-wrap gap-2" data-testid="transaction-landing-meta">
                {listing.size && (
                  <Badge variant="outline">Size: {listing.size}</Badge>
                )}
                {listing.condition && (
                  <Badge variant="outline">
                    Condition: {String(listing.condition).replace('_', ' ')}
                  </Badge>
                )}
                {listing.category && (
                  <Badge variant="secondary">{listing.category}</Badge>
                )}
              </div>

              {listing.description && (
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {listing.description}
                </p>
              )}

              <div className="flex flex-wrap gap-2 pt-2">
                <Button asChild variant="secondary" className="rounded-xl" data-testid="transaction-landing-back-market">
                  <Link to="/market">
                    Browse marketplace
                    <ArrowRight className="h-4 w-4 ms-1" />
                  </Link>
                </Button>
                <Button asChild variant="ghost" className="rounded-xl" data-testid="transaction-landing-my-transactions">
                  <Link to="/transactions">My transactions</Link>
                </Button>
              </div>
            </CardContent>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
