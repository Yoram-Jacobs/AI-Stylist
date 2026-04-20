import { useEffect, useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { Table, TableHeader, TableHead, TableRow, TableBody, TableCell } from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  RefreshCcw, Users as UsersIcon, ShoppingBag, Receipt, Activity, Sparkles,
  Settings, KeyRound, AlertTriangle, CheckCircle2, ShieldCheck, ShieldOff,
  Play, Search,
} from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';

const fmtCents = (cents, cur = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: cur || 'USD' }).format(
    (cents || 0) / 100
  );

const fmtNum = (n) => new Intl.NumberFormat('en-US').format(n || 0);

const PROVIDER_TONE = {
  ok: 'bg-emerald-100 text-emerald-900 border-emerald-200',
  warn: 'bg-amber-100 text-amber-900 border-amber-200',
  bad: 'bg-rose-100 text-rose-900 border-rose-200',
  idle: 'bg-slate-100 text-slate-800 border-slate-200',
};

const tone = (errorRate) => {
  if (errorRate === undefined || errorRate === null) return 'idle';
  if (errorRate === 0) return 'ok';
  if (errorRate < 0.2) return 'warn';
  return 'bad';
};

export default function Admin() {
  const { user } = useAuth();
  const isAdmin = (user?.roles || []).includes('admin');
  if (user && !isAdmin) return <Navigate to="/home" replace />;

  return (
    <div className="container-px max-w-7xl mx-auto pt-6 md:pt-10 pb-20" data-testid="admin-page">
      <div className="flex items-end justify-between mb-6 gap-4 flex-wrap">
        <div>
          <div className="caps-label text-muted-foreground">Operations</div>
          <h1 className="font-display text-3xl sm:text-4xl mt-1">Admin Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-xl">
            Live ops surface for users, marketplace, AI providers, and the
            Trend-Scout agent. All actions are scoped to admin role.
          </p>
        </div>
        <Button asChild variant="outline" className="rounded-xl" data-testid="admin-back-home">
          <Link to="/home">Back to app</Link>
        </Button>
      </div>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="rounded-xl flex-wrap h-auto p-1" data-testid="admin-tabs">
          <TabsTrigger value="overview" data-testid="admin-tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="providers" data-testid="admin-tab-providers">Providers</TabsTrigger>
          <TabsTrigger value="trends" data-testid="admin-tab-trends">Trend-Scout</TabsTrigger>
          <TabsTrigger value="users" data-testid="admin-tab-users">Users</TabsTrigger>
          <TabsTrigger value="listings" data-testid="admin-tab-listings">Listings</TabsTrigger>
          <TabsTrigger value="transactions" data-testid="admin-tab-transactions">Transactions</TabsTrigger>
          <TabsTrigger value="system" data-testid="admin-tab-system">System</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-6"><OverviewSection /></TabsContent>
        <TabsContent value="providers" className="mt-6"><ProvidersSection /></TabsContent>
        <TabsContent value="trends" className="mt-6"><TrendScoutSection /></TabsContent>
        <TabsContent value="users" className="mt-6"><UsersSection /></TabsContent>
        <TabsContent value="listings" className="mt-6"><ListingsSection /></TabsContent>
        <TabsContent value="transactions" className="mt-6"><TransactionsSection /></TabsContent>
        <TabsContent value="system" className="mt-6"><SystemSection /></TabsContent>
      </Tabs>
    </div>
  );
}

// -------------------- Overview --------------------
function OverviewSection() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const refresh = async () => {
    setLoading(true);
    try {
      setData(await api.adminOverview());
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load overview');
    } finally {
      setLoading(false);
    }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { refresh(); }, []);

  if (loading || !data) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="admin-overview-loading">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-[calc(var(--radius)+6px)]" />
        ))}
      </div>
    );
  }

  const r = data.revenue_cents || {};
  const cards = [
    { label: 'Users', value: fmtNum(data.users.total), sub: `+${fmtNum(data.users.new_24h)} new in 24h`, icon: UsersIcon, testid: 'admin-stat-users' },
    { label: 'Closet items', value: fmtNum(data.closet_items.total), sub: 'across all users', icon: Sparkles, testid: 'admin-stat-closet' },
    { label: 'Active listings', value: fmtNum(data.listings.active), sub: `${fmtNum(data.listings.total)} total`, icon: ShoppingBag, testid: 'admin-stat-listings' },
    { label: 'Transactions', value: fmtNum(data.transactions.total), sub: `${fmtNum(data.transactions.paid)} paid`, icon: Receipt, testid: 'admin-stat-transactions' },
    { label: 'Gross volume', value: fmtCents(r.gross), sub: 'lifetime, paid only', icon: Receipt, testid: 'admin-stat-gross' },
    { label: 'Platform fees', value: fmtCents(r.platform_fee), sub: '7% revenue', icon: Receipt, testid: 'admin-stat-platform-fee' },
    { label: 'Stylist 24h', value: fmtNum(data.stylist.messages_24h), sub: `${fmtNum(data.stylist.messages_7d)} this week`, icon: Activity, testid: 'admin-stat-stylist' },
    { label: 'Trend cards live', value: fmtNum(data.trend_scout.count), sub: 'today\u2019s edition', icon: Sparkles, testid: 'admin-stat-trend' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button variant="outline" onClick={refresh} className="rounded-xl" data-testid="admin-overview-refresh">
          <RefreshCcw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="admin-overview-grid">
        {cards.map((c) => (
          <Card key={c.label} className="rounded-[calc(var(--radius)+6px)] shadow-editorial" data-testid={c.testid}>
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div className="caps-label text-muted-foreground">{c.label}</div>
                <c.icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="font-display text-3xl mt-2">{c.value}</div>
              <div className="text-xs text-muted-foreground mt-1">{c.sub}</div>
            </CardContent>
          </Card>
        ))}
      </div>
      <ProvidersInline summary={data.providers || []} />
    </div>
  );
}

function ProvidersInline({ summary }) {
  if (!summary?.length) {
    return (
      <Card className="rounded-[calc(var(--radius)+6px)]">
        <CardContent className="p-6 text-sm text-muted-foreground">
          No provider activity yet. Trigger a stylist call or trend run to populate.
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
      <CardContent className="p-5">
        <h3 className="font-display text-xl mb-3">Provider activity (last 200 calls)</h3>
        <ProviderTable rows={summary} />
      </CardContent>
    </Card>
  );
}

function ProviderTable({ rows }) {
  return (
    <div className="overflow-x-auto">
      <Table data-testid="admin-providers-table">
        <TableHeader>
          <TableRow>
            <TableHead>Provider</TableHead>
            <TableHead className="text-right">Calls</TableHead>
            <TableHead className="text-right">Errors</TableHead>
            <TableHead className="text-right">Error rate</TableHead>
            <TableHead className="text-right">avg ms</TableHead>
            <TableHead className="text-right">p95 ms</TableHead>
            <TableHead>Last</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((p) => (
            <TableRow key={p.provider} data-testid="admin-providers-row">
              <TableCell className="font-mono text-xs">{p.provider}</TableCell>
              <TableCell className="text-right">{fmtNum(p.total)}</TableCell>
              <TableCell className="text-right">{fmtNum(p.fail)}</TableCell>
              <TableCell className="text-right">
                <Badge variant="outline" className={`text-[11px] ${PROVIDER_TONE[tone(p.error_rate)]}`}>
                  {(p.error_rate * 100).toFixed(1)}%
                </Badge>
              </TableCell>
              <TableCell className="text-right">{fmtNum(p.avg_ms)}</TableCell>
              <TableCell className="text-right">{fmtNum(p.p95_ms)}</TableCell>
              <TableCell className="text-xs">
                <div className="flex items-center gap-1">
                  {p.last_ok ? (
                    <CheckCircle2 className="h-3 w-3 text-emerald-700" />
                  ) : (
                    <AlertTriangle className="h-3 w-3 text-rose-700" />
                  )}
                  <span className="truncate max-w-[260px]" title={p.last_error || ''}>
                    {p.last_ok ? 'ok' : (p.last_error || 'error')}
                  </span>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// -------------------- Providers --------------------
function ProvidersSection() {
  const [summary, setSummary] = useState(null);
  const [usage, setUsage] = useState(null);
  const refresh = async () => {
    try {
      const [p, u] = await Promise.all([api.adminProviders(), api.adminLlmUsage()]);
      setSummary(p?.summary || []);
      setUsage(u);
    } catch (err) {
      toast.error('Failed to load provider data');
    }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { refresh(); }, []);

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button variant="outline" onClick={refresh} className="rounded-xl" data-testid="admin-providers-refresh">
          <RefreshCcw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>
      <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
        <CardContent className="p-5">
          <h3 className="font-display text-xl mb-3">All providers</h3>
          {summary === null ? (
            <Skeleton className="h-32 w-full" />
          ) : summary.length === 0 ? (
            <p className="text-sm text-muted-foreground">No calls recorded yet.</p>
          ) : (
            <ProviderTable rows={summary} />
          )}
        </CardContent>
      </Card>

      <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial" data-testid="admin-llm-usage-card">
        <CardContent className="p-5">
          <div className="flex items-start gap-4">
            <div className="h-10 w-10 rounded-full bg-secondary flex items-center justify-center shrink-0">
              <KeyRound className="h-5 w-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="caps-label text-muted-foreground">Emergent LLM Key</div>
              <h3 className="font-display text-xl mt-1">Universal key usage</h3>
              {usage === null ? (
                <Skeleton className="h-5 w-64 mt-2" />
              ) : usage.available ? (
                <pre className="text-xs bg-secondary rounded-lg p-3 mt-2 overflow-x-auto" data-testid="admin-llm-usage-data">
                  {JSON.stringify(usage.usage, null, 2)}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground mt-2">
                  {usage.reason || 'Live usage not available.'}{' '}
                  {usage.manage_url && (
                    <a className="underline" href={usage.manage_url} target="_blank" rel="noreferrer">
                      Manage in Emergent profile
                    </a>
                  )}
                </p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// -------------------- Trend-Scout --------------------
function TrendScoutSection() {
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState(false);
  const refresh = async () => {
    try {
      const res = await api.adminTrendScout(30);
      setItems(res.items || []);
    } catch { toast.error('Failed to load trend reports'); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { refresh(); }, []);

  const run = async () => {
    setBusy(true);
    try {
      const res = await api.adminTrendScoutRun(true);
      toast.success(`Generated ${res.generated?.length || 0} card(s)`);
      await refresh();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Run failed');
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={refresh} className="rounded-xl" data-testid="admin-trends-refresh">
          <RefreshCcw className="h-4 w-4 mr-2" /> Refresh
        </Button>
        <Button onClick={run} disabled={busy} className="rounded-xl" data-testid="admin-trends-run">
          <Play className="h-4 w-4 mr-2" /> {busy ? 'Running...' : 'Force run now'}
        </Button>
      </div>
      {items === null ? (
        <Skeleton className="h-40 w-full rounded-[calc(var(--radius)+6px)]" />
      ) : items.length === 0 ? (
        <Card className="rounded-[calc(var(--radius)+6px)]">
          <CardContent className="p-6 text-sm text-muted-foreground">
            No trend reports yet. Hit "Force run now" to seed.
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="admin-trends-grid">
          {items.map((t) => (
            <Card key={t.id || `${t.bucket}-${t.date}`} className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
              <CardContent className="p-5">
                <div className="flex items-center justify-between">
                  <Badge variant="outline" className="text-[11px]">{t.bucket_label || t.bucket}</Badge>
                  <span className="caps-label text-muted-foreground">{t.date}</span>
                </div>
                <h3 className="font-display text-lg mt-2 leading-tight">{t.headline}</h3>
                <p className="text-sm text-muted-foreground mt-2">{t.body}</p>
                <div className="text-[11px] text-muted-foreground mt-3 font-mono">{t.model}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// -------------------- Users --------------------
function UsersSection() {
  const [items, setItems] = useState(null);
  const [q, setQ] = useState('');
  const [total, setTotal] = useState(0);

  const refresh = async (search = q) => {
    try {
      const res = await api.adminUsers({ q: search || undefined, limit: 50 });
      setItems(res.items || []);
      setTotal(res.total || 0);
    } catch { toast.error('Failed to load users'); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { refresh(''); }, []);

  const togglePromotion = async (u) => {
    const isAdmin = (u.roles || []).includes('admin');
    try {
      if (isAdmin) await api.adminDemoteUser(u.id);
      else await api.adminPromoteUser(u.id);
      toast.success(isAdmin ? 'Removed admin role' : 'Promoted to admin');
      refresh();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Action failed');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-md">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search by email or display name"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && refresh()}
            className="pl-9 rounded-xl"
            data-testid="admin-users-search"
          />
        </div>
        <Button onClick={() => refresh()} variant="outline" className="rounded-xl" data-testid="admin-users-search-btn">
          Search
        </Button>
        <span className="text-xs text-muted-foreground ml-auto">{fmtNum(total)} total</span>
      </div>
      <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table data-testid="admin-users-table">
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Display name</TableHead>
                  <TableHead>Roles</TableHead>
                  <TableHead className="text-right">Closet</TableHead>
                  <TableHead className="text-right">Listings</TableHead>
                  <TableHead>Calendar</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items === null ? (
                  <TableRow><TableCell colSpan={8}><Skeleton className="h-8 w-full" /></TableCell></TableRow>
                ) : items.length === 0 ? (
                  <TableRow><TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-6">No users match.</TableCell></TableRow>
                ) : items.map((u) => {
                  const isAdmin = (u.roles || []).includes('admin');
                  return (
                    <TableRow key={u.id} data-testid="admin-users-row">
                      <TableCell className="text-sm">{u.email}</TableCell>
                      <TableCell className="text-sm">{u.display_name}</TableCell>
                      <TableCell>
                        {(u.roles || []).map((r) => (
                          <Badge key={r} variant="outline" className="text-[11px] mr-1">{r}</Badge>
                        ))}
                      </TableCell>
                      <TableCell className="text-right text-sm">{fmtNum(u.closet_count)}</TableCell>
                      <TableCell className="text-right text-sm">{fmtNum(u.listing_count)}</TableCell>
                      <TableCell>
                        {u.calendar_connected ? (
                          <Badge variant="outline" className="bg-emerald-50 text-emerald-800 border-emerald-200 text-[11px]">connected</Badge>
                        ) : (
                          <Badge variant="outline" className="text-[11px]">no</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          className="rounded-lg text-xs"
                          onClick={() => togglePromotion(u)}
                          data-testid="admin-user-toggle-admin"
                        >
                          {isAdmin ? <ShieldOff className="h-3 w-3 mr-1" /> : <ShieldCheck className="h-3 w-3 mr-1" />}
                          {isAdmin ? 'Demote' : 'Promote'}
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// -------------------- Listings --------------------
function ListingsSection() {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState('');
  const refresh = async () => {
    try {
      const res = await api.adminListings({ status: status || undefined, limit: 100 });
      setItems(res.items || []);
    } catch { toast.error('Failed to load listings'); }
  };
  useEffect(() => { refresh(); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  const setListingStatus = async (id, newStatus) => {
    try {
      await api.adminSetListingStatus(id, newStatus);
      toast.success(`Listing set to ${newStatus}`);
      refresh();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Update failed');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {['', 'active', 'paused', 'sold', 'removed'].map((s) => (
          <Button
            key={s || 'all'}
            size="sm"
            variant={status === s ? 'default' : 'outline'}
            onClick={() => setStatus(s)}
            className="rounded-xl"
            data-testid={`admin-listings-filter-${s || 'all'}`}
          >
            {s || 'All'}
          </Button>
        ))}
      </div>
      <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table data-testid="admin-listings-table">
              <TableHeader>
                <TableRow>
                  <TableHead>Listing</TableHead>
                  <TableHead>Seller</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Source tag</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items === null ? (
                  <TableRow><TableCell colSpan={7}><Skeleton className="h-8 w-full" /></TableCell></TableRow>
                ) : items.length === 0 ? (
                  <TableRow><TableCell colSpan={7} className="text-center text-sm text-muted-foreground py-6">No listings.</TableCell></TableRow>
                ) : items.map((l) => (
                  <TableRow key={l.id} data-testid="admin-listings-row">
                    <TableCell className="text-xs font-mono">{(l.id || '').slice(0, 8)}…</TableCell>
                    <TableCell className="text-xs font-mono">{(l.seller_id || '').slice(0, 8)}…</TableCell>
                    <TableCell className="text-right">{fmtCents(l.list_price_cents, l.currency)}</TableCell>
                    <TableCell><Badge variant="outline" className="capitalize text-[11px]">{l.status}</Badge></TableCell>
                    <TableCell><Badge variant="outline" className="text-[11px]">{l.source_tag || '—'}</Badge></TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {l.created_at ? new Date(l.created_at).toLocaleDateString() : '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        {l.status !== 'paused' && (
                          <Button size="sm" variant="ghost" className="text-xs h-7" onClick={() => setListingStatus(l.id, 'paused')} data-testid="admin-listing-pause">
                            Pause
                          </Button>
                        )}
                        {l.status !== 'active' && (
                          <Button size="sm" variant="ghost" className="text-xs h-7" onClick={() => setListingStatus(l.id, 'active')} data-testid="admin-listing-activate">
                            Activate
                          </Button>
                        )}
                        {l.status !== 'removed' && (
                          <Button size="sm" variant="ghost" className="text-xs h-7 text-rose-700" onClick={() => setListingStatus(l.id, 'removed')} data-testid="admin-listing-remove">
                            Remove
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// -------------------- Transactions --------------------
function TransactionsSection() {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState('');
  const refresh = async () => {
    try {
      const res = await api.adminTransactions({ status: status || undefined, limit: 100 });
      setItems(res.items || []);
    } catch { toast.error('Failed to load transactions'); }
  };
  useEffect(() => { refresh(); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  const aggregate = (items || []).reduce(
    (acc, t) => {
      const f = t.financial || {};
      if (t.status === 'paid') {
        acc.gross += f.gross_cents || 0;
        acc.platform += f.platform_fee_cents || 0;
        acc.stripe += f.stripe_fee_cents || 0;
        acc.net += f.seller_net_cents || 0;
      }
      return acc;
    },
    { gross: 0, platform: 0, stripe: 0, net: 0 }
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {['', 'pending', 'paid', 'cancelled', 'refunded'].map((s) => (
          <Button
            key={s || 'all'}
            size="sm"
            variant={status === s ? 'default' : 'outline'}
            onClick={() => setStatus(s)}
            className="rounded-xl"
            data-testid={`admin-transactions-filter-${s || 'all'}`}
          >
            {s || 'All'}
          </Button>
        ))}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Gross (paid)', value: fmtCents(aggregate.gross), id: 'agg-gross' },
          { label: 'Platform 7%', value: fmtCents(aggregate.platform), id: 'agg-platform' },
          { label: 'Stripe fees', value: fmtCents(aggregate.stripe), id: 'agg-stripe' },
          { label: 'Seller net', value: fmtCents(aggregate.net), id: 'agg-net' },
        ].map((c) => (
          <Card key={c.id} className="rounded-[calc(var(--radius)+6px)]" data-testid={`admin-tx-${c.id}`}>
            <CardContent className="p-4">
              <div className="caps-label text-muted-foreground">{c.label}</div>
              <div className="font-display text-xl mt-1">{c.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table data-testid="admin-transactions-table">
              <TableHeader>
                <TableRow>
                  <TableHead>Tx</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Gross</TableHead>
                  <TableHead className="text-right">Platform</TableHead>
                  <TableHead className="text-right">Stripe</TableHead>
                  <TableHead className="text-right">Seller net</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items === null ? (
                  <TableRow><TableCell colSpan={7}><Skeleton className="h-8 w-full" /></TableCell></TableRow>
                ) : items.length === 0 ? (
                  <TableRow><TableCell colSpan={7} className="text-center text-sm text-muted-foreground py-6">No transactions.</TableCell></TableRow>
                ) : items.map((t) => {
                  const f = t.financial || {};
                  return (
                    <TableRow key={t.id} data-testid="admin-transactions-row">
                      <TableCell className="text-xs font-mono">{(t.id || '').slice(0, 8)}…</TableCell>
                      <TableCell><Badge variant="outline" className="capitalize text-[11px]">{t.status}</Badge></TableCell>
                      <TableCell className="text-right">{fmtCents(f.gross_cents, t.currency)}</TableCell>
                      <TableCell className="text-right">{fmtCents(f.platform_fee_cents, t.currency)}</TableCell>
                      <TableCell className="text-right">{fmtCents(f.stripe_fee_cents, t.currency)}</TableCell>
                      <TableCell className="text-right">{fmtCents(f.seller_net_cents, t.currency)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {t.created_at ? new Date(t.created_at).toLocaleString() : '—'}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// -------------------- System --------------------
function SystemSection() {
  const [data, setData] = useState(null);
  useEffect(() => {
    api.adminSystem().then(setData).catch(() => toast.error('Failed to load system info'));
  }, []);
  if (!data) return <Skeleton className="h-40 w-full rounded-[calc(var(--radius)+6px)]" />;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="admin-system-grid">
      <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
        <CardContent className="p-5">
          <h3 className="font-display text-xl mb-3 flex items-center gap-2">
            <Settings className="h-4 w-4" /> AI configuration
          </h3>
          <dl className="text-sm space-y-2">
            {Object.entries(data.ai || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4">
                <dt className="text-muted-foreground">{k}</dt>
                <dd className="font-mono text-xs text-right break-all">{String(v)}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
      <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
        <CardContent className="p-5">
          <h3 className="font-display text-xl mb-3 flex items-center gap-2">
            <KeyRound className="h-4 w-4" /> API keys present
          </h3>
          <ul className="text-sm space-y-2">
            {Object.entries(data.keys_present || {}).map(([k, ok]) => (
              <li key={k} className="flex items-center justify-between">
                <span className="font-mono text-xs">{k}</span>
                <Badge
                  variant="outline"
                  className={`text-[11px] ${ok ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-rose-50 text-rose-800 border-rose-200'}`}
                  data-testid={`admin-key-${k.toLowerCase()}`}
                >
                  {ok ? 'set' : 'missing'}
                </Badge>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial md:col-span-2">
        <CardContent className="p-5">
          <h3 className="font-display text-xl mb-3 flex items-center gap-2">
            <Activity className="h-4 w-4" /> Trend-Scout
          </h3>
          <div className="text-sm flex flex-wrap gap-x-8 gap-y-2">
            <div>Enabled: <Badge variant="outline" className="ml-1 text-[11px]">{String(data.trend_scout?.enabled)}</Badge></div>
            <div>Daily UTC: <span className="font-mono">{data.trend_scout?.schedule_utc}</span></div>
            <div>Dev bypass: <Badge variant="outline" className="ml-1 text-[11px]">{String(data.dev?.allow_dev_bypass)}</Badge></div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
