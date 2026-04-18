import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { toast } from 'sonner';
import { Loader2, ArrowLeft } from 'lucide-react';
import { api } from '@/lib/api';

const fmt = (cents, cur = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: cur }).format((cents || 0) / 100);

export default function CreateListing() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const initialItem = params.get('itemId');
  const [closet, setCloset] = useState([]);
  const [form, setForm] = useState({
    closet_item_id: initialItem || '',
    source: 'Shared',
    mode: 'sell',
    title: '',
    description: '',
    category: 'top',
    size: '',
    condition: 'like_new',
    list_price_cents: 2500,
  });
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listCloset({ limit: 100 })
      .then((r) => setCloset(r.items || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (initialItem) {
      const it = closet.find((c) => c.id === initialItem);
      if (it) setForm((f) => ({ ...f, title: it.title, category: it.category }));
    }
  }, [initialItem, closet]);

  useEffect(() => {
    if (!form.list_price_cents) { setPreview(null); return; }
    api.feePreview(form.list_price_cents).then(setPreview).catch(() => setPreview(null));
  }, [form.list_price_cents]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const body = {
        closet_item_id: form.closet_item_id || null,
        source: form.source,
        mode: form.mode,
        title: form.title,
        description: form.description || null,
        category: form.category,
        size: form.size || null,
        condition: form.condition,
        images: [],
        list_price_cents: Number(form.list_price_cents) || 0,
        currency: 'USD',
      };
      const linked = closet.find((c) => c.id === form.closet_item_id);
      if (linked?.segmented_image_url || linked?.original_image_url) {
        body.images = [linked.segmented_image_url || linked.original_image_url];
      }
      const listing = await api.createListing(body);
      toast.success('Listed on marketplace');
      nav(`/market/${listing.id}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not create listing');
    } finally { setBusy(false); }
  };

  return (
    <div className="container-px max-w-3xl mx-auto pt-4 md:pt-10">
      <button onClick={() => nav(-1)} className="inline-flex items-center text-sm text-muted-foreground mb-4">
        <ArrowLeft className="h-4 w-4 mr-1" /> Back
      </button>
      <h1 className="font-display text-3xl md:text-4xl">Create a listing</h1>
      <p className="text-sm text-muted-foreground mt-1">Platform fee is 7%, calculated after Stripe processing fees.</p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
        <Card className="md:col-span-2 rounded-[calc(var(--radius)+6px)] shadow-editorial">
          <CardContent className="p-6">
            <form onSubmit={submit} className="space-y-5" data-testid="create-listing-form">
              <div>
                <Label>Link to closet item (optional)</Label>
                <Select value={form.closet_item_id || 'none'} onValueChange={(v) => setForm({ ...form, closet_item_id: v === 'none' ? '' : v })}>
                  <SelectTrigger className="rounded-xl" data-testid="listing-closet-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None (custom listing)</SelectItem>
                    {closet.map((c) => <SelectItem key={c.id} value={c.id}>{c.title}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Source</Label>
                  <Select value={form.source} onValueChange={(v) => setForm({ ...form, source: v })}>
                    <SelectTrigger className="rounded-xl" data-testid="listing-source-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Shared">Shared (community)</SelectItem>
                      <SelectItem value="Retail">Retail</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Mode</Label>
                  <Select value={form.mode} onValueChange={(v) => setForm({ ...form, mode: v })}>
                    <SelectTrigger className="rounded-xl" data-testid="listing-mode-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="sell">Sell</SelectItem>
                      <SelectItem value="swap">Swap</SelectItem>
                      <SelectItem value="donate">Donate</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div>
                <Label>Title</Label>
                <Input required value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  className="rounded-xl" data-testid="listing-title-input" />
              </div>
              <div>
                <Label>Description</Label>
                <Textarea value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  rows={3} className="rounded-xl" data-testid="listing-description-input" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Size</Label>
                  <Input value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })}
                    className="rounded-xl" data-testid="listing-size-input" />
                </div>
                <div>
                  <Label>Condition</Label>
                  <Select value={form.condition} onValueChange={(v) => setForm({ ...form, condition: v })}>
                    <SelectTrigger className="rounded-xl" data-testid="listing-condition-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="new">New</SelectItem>
                      <SelectItem value="like_new">Like new</SelectItem>
                      <SelectItem value="good">Good</SelectItem>
                      <SelectItem value="fair">Fair</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div>
                <Label>Price (USD)</Label>
                <Input type="number" min={0} step={1}
                  value={(form.list_price_cents / 100).toString()}
                  onChange={(e) => setForm({ ...form, list_price_cents: Math.max(0, Math.round(Number(e.target.value) * 100) || 0) })}
                  className="rounded-xl" data-testid="listing-price-input" />
              </div>

              <Button type="submit" disabled={busy || !form.title} className="w-full rounded-xl" data-testid="listing-publish-button">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Publish listing'}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial h-fit" data-testid="marketplace-fee-breakdown">
          <CardContent className="p-5">
            <div className="caps-label text-muted-foreground">Fee preview</div>
            <div className="font-display text-2xl mt-1" data-testid="fee-gross">{fmt(preview?.gross_cents || form.list_price_cents)}</div>
            <dl className="mt-4 text-sm space-y-2">
              <div className="flex justify-between"><dt className="text-muted-foreground">List price</dt><dd>{fmt(preview?.gross_cents || form.list_price_cents)}</dd></div>
              <div className="flex justify-between"><dt className="text-muted-foreground">Stripe fee</dt><dd>− {fmt(preview?.stripe_fee_cents || 0)}</dd></div>
              <div className="flex justify-between"><dt className="text-muted-foreground">Platform (7%)</dt><dd>− {fmt(preview?.platform_fee_cents || 0)}</dd></div>
              <div className="flex justify-between font-medium border-t border-border pt-2"><dt>You receive</dt><dd data-testid="fee-seller-net">{fmt(preview?.seller_net_cents || 0)}</dd></div>
            </dl>
            <p className="text-[11px] text-muted-foreground mt-3">7% is calculated after Stripe processing fees (2.9% + $0.30).</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
