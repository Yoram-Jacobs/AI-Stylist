import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  Plus,
  Loader2,
  Trash2,
  Pause,
  Play,
  Save,
  X,
  Megaphone,
  AlertTriangle,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';

const DEFAULT_CREATIVE = {
  headline: '',
  body: '',
  image_url: '',
  cta_label: '',
  cta_url: '',
};

const DEFAULT_CAMPAIGN = {
  name: '',
  profession: '',
  creative: { ...DEFAULT_CREATIVE },
  daily_budget_cents: 0,
  bid_cents: 10,
  start_date: '',
  end_date: '',
  target_country: '',
  target_region: '',
  status: 'draft',
};

export default function AdsManager() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);

  const isPro = !!user?.professional?.is_professional;

  const load = async () => {
    try {
      const res = await api.listMyAdCampaigns();
      setItems(res?.items || []);
    } catch {
      setItems([]);
    }
  };

  useEffect(() => {
    if (isPro) load();
    else setItems([]);
  }, [isPro]);

  const openNew = () => {
    setEditing({
      ...DEFAULT_CAMPAIGN,
      profession: user?.professional?.profession || '',
      target_country: user?.home_location?.country_code || '',
      target_region: user?.home_location?.city || '',
    });
    setOpen(true);
  };

  const openEdit = (c) => {
    setEditing({
      ...DEFAULT_CAMPAIGN,
      ...c,
      creative: { ...DEFAULT_CREATIVE, ...(c.creative || {}) },
    });
    setOpen(true);
  };

  const save = async () => {
    if (!editing?.name || !editing?.creative?.headline) {
      toast.error(t('common.error') || 'Missing required fields');
      return;
    }
    setBusy(true);
    try {
      const body = {
        name: editing.name,
        profession: editing.profession || null,
        creative: {
          headline: editing.creative.headline,
          body: editing.creative.body || null,
          image_url: editing.creative.image_url || null,
          cta_label: editing.creative.cta_label || null,
          cta_url: editing.creative.cta_url || null,
        },
        daily_budget_cents: Number(editing.daily_budget_cents) || 0,
        bid_cents: Number(editing.bid_cents) || 0,
        start_date: editing.start_date || null,
        end_date: editing.end_date || null,
        target_country: editing.target_country || null,
        target_region: editing.target_region || null,
        status: editing.status || 'draft',
      };
      if (editing.id) {
        await api.patchAdCampaign(editing.id, body);
        toast.success(t('ads.campaignSaved'));
      } else {
        await api.createAdCampaign(body);
        toast.success(t('ads.campaignCreated'));
      }
      setOpen(false);
      setEditing(null);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('ads.saveFailed'));
    } finally {
      setBusy(false);
    }
  };

  const togglePause = async (c) => {
    const next = c.status === 'active' ? 'paused' : 'active';
    try {
      await api.patchAdCampaign(c.id, { status: next });
      toast.success(t('ads.campaignSaved'));
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('ads.saveFailed'));
    }
  };

  const remove = async (c) => {
    if (!window.confirm(`${t('ads.deleteCampaign')}?`)) return;
    try {
      await api.deleteAdCampaign(c.id);
      toast.success(t('ads.campaignDeleted'));
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('ads.saveFailed'));
    }
  };

  if (!isPro) {
    return (
      <div className="container-px max-w-3xl mx-auto pt-10">
        <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial" data-testid="ads-gated">
          <CardContent className="p-8 text-center">
            <AlertTriangle className="h-8 w-8 mx-auto text-amber-600" />
            <h1 className="font-display text-2xl mt-3">{t('ads.title')}</h1>
            <p className="text-muted-foreground mt-2 max-w-md mx-auto">
              {t('ads.onlyProfessionals')}
            </p>
            <div className="mt-5">
              <Button asChild className="rounded-xl" data-testid="ads-go-profile">
                <Link to="/me">{t('nav.settings')} →</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container-px max-w-5xl mx-auto pt-6 md:pt-10">
      <div className="flex items-end justify-between gap-4 mb-6 flex-wrap">
        <div>
          <div className="caps-label text-muted-foreground">{t('nav.ads')}</div>
          <h1 className="font-display text-3xl sm:text-4xl mt-1" data-testid="ads-title">
            {t('ads.title')}
          </h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-xl">
            {t('ads.subtitle')}
          </p>
        </div>
        <Button onClick={openNew} className="rounded-xl" data-testid="ads-new-btn">
          <Plus className="h-4 w-4 me-1" />
          {t('ads.newCampaign')}
        </Button>
      </div>

      {items === null ? (
        <div className="flex items-center justify-center py-20 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial" data-testid="ads-empty">
          <CardContent className="p-10 text-center">
            <Megaphone className="h-8 w-8 mx-auto text-muted-foreground" />
            <p className="text-muted-foreground mt-3">{t('ads.empty')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3" data-testid="ads-list">
          {items.map((c) => (
            <AdCampaignRow
              key={c.id}
              campaign={c}
              onEdit={() => openEdit(c)}
              onToggle={() => togglePause(c)}
              onDelete={() => remove(c)}
            />
          ))}
        </div>
      )}

      {/* Campaign editor dialog */}
      <Dialog open={open} onOpenChange={(v) => { if (!v) { setOpen(false); setEditing(null); } }}>
        <DialogContent className="sm:max-w-2xl max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">
              {editing?.id ? t('ads.editCampaign') : t('ads.newCampaign')}
            </DialogTitle>
          </DialogHeader>
          {editing && <AdCampaignForm form={editing} onChange={setEditing} />}
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => { setOpen(false); setEditing(null); }}
              className="rounded-xl"
            >
              <X className="h-4 w-4 me-1" /> {t('common.cancel')}
            </Button>
            <Button onClick={save} disabled={busy} className="rounded-xl" data-testid="ads-save-btn">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : (<><Save className="h-4 w-4 me-1" /> {t('ads.saveCampaign')}</>)}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AdCampaignRow({ campaign: c, onEdit, onToggle, onDelete }) {
  const { t } = useTranslation();
  const metrics = useMemo(
    () => ({
      impressions: c.impressions || 0,
      clicks: c.clicks || 0,
      spent: ((c.spent_cents || 0) / 100).toFixed(2),
    }),
    [c],
  );

  return (
    <Card
      className="rounded-[calc(var(--radius)+6px)] shadow-editorial"
      data-testid={`ads-row-${c.id}`}
    >
      <CardContent className="p-5">
        <div className="flex items-start gap-4 flex-wrap md:flex-nowrap">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-display text-lg truncate">{c.name}</h3>
              <Badge variant="outline" className="rounded-full text-[10px] bg-card">
                {t(`ads.status_${c.status}`, { defaultValue: c.status })}
              </Badge>
              {c.target_country && (
                <Badge variant="outline" className="rounded-full text-[10px] bg-card">
                  {c.target_country}{c.target_region ? ` · ${c.target_region}` : ''}
                </Badge>
              )}
            </div>
            <div className="mt-1 text-sm font-medium truncate">
              {c.creative?.headline}
            </div>
            {c.creative?.body && (
              <div className="text-xs text-muted-foreground truncate">
                {c.creative.body}
              </div>
            )}
            <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
              <span><b className="text-foreground">{metrics.impressions}</b> {t('ads.metrics.impressions')}</span>
              <span><b className="text-foreground">{metrics.clicks}</b> {t('ads.metrics.clicks')}</span>
              <span><b className="text-foreground">{metrics.spent}</b> {t('ads.metrics.spent')} ¢</span>
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Button
              size="sm"
              variant="outline"
              className="rounded-lg"
              onClick={onToggle}
              data-testid={`ads-row-${c.id}-toggle`}
            >
              {c.status === 'active' ? (
                <><Pause className="h-3.5 w-3.5 me-1" /> {t('ads.pause')}</>
              ) : (
                <><Play className="h-3.5 w-3.5 me-1" /> {t('ads.resume')}</>
              )}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="rounded-lg"
              onClick={onEdit}
              data-testid={`ads-row-${c.id}-edit`}
            >
              {t('common.edit')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="rounded-lg text-rose-700"
              onClick={onDelete}
              data-testid={`ads-row-${c.id}-delete`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function AdCampaignForm({ form, onChange }) {
  const { t } = useTranslation();
  const set = (patch) => onChange({ ...form, ...patch });
  const setCreative = (patch) =>
    onChange({ ...form, creative: { ...form.creative, ...patch } });

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <Label>{t('ads.campaignName')}</Label>
          <Input
            value={form.name}
            onChange={(e) => set({ name: e.target.value })}
            className="rounded-xl mt-1"
            data-testid="ads-form-name"
          />
        </div>
        <div>
          <Label>{t('ads.profession')}</Label>
          <Input
            value={form.profession || ''}
            onChange={(e) => set({ profession: e.target.value })}
            className="rounded-xl mt-1"
            data-testid="ads-form-profession"
          />
        </div>
      </div>

      <div className="space-y-3">
        <div className="caps-label text-muted-foreground">{t('ads.creative.title')}</div>
        <Input
          value={form.creative.headline}
          onChange={(e) => setCreative({ headline: e.target.value })}
          placeholder={t('ads.creative.headline')}
          className="rounded-xl"
          data-testid="ads-form-headline"
        />
        <Textarea
          rows={2}
          value={form.creative.body || ''}
          onChange={(e) => setCreative({ body: e.target.value })}
          placeholder={t('ads.creative.body')}
          className="rounded-xl"
          data-testid="ads-form-body"
        />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input
            value={form.creative.image_url || ''}
            onChange={(e) => setCreative({ image_url: e.target.value })}
            placeholder={t('ads.creative.imageUrl')}
            className="rounded-xl"
          />
          <Input
            value={form.creative.cta_label || ''}
            onChange={(e) => setCreative({ cta_label: e.target.value })}
            placeholder={t('ads.creative.ctaLabel')}
            className="rounded-xl"
          />
          <Input
            value={form.creative.cta_url || ''}
            onChange={(e) => setCreative({ cta_url: e.target.value })}
            placeholder={t('ads.creative.ctaUrl')}
            className="rounded-xl md:col-span-2"
          />
        </div>
      </div>

      <div className="space-y-3">
        <div className="caps-label text-muted-foreground">{t('ads.budget.title')}</div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>{t('ads.budget.daily')}</Label>
            <Input
              type="number"
              min="0"
              value={form.daily_budget_cents}
              onChange={(e) => set({ daily_budget_cents: e.target.value })}
              className="rounded-xl mt-1"
              data-testid="ads-form-daily-budget"
            />
          </div>
          <div>
            <Label>{t('ads.budget.bid')}</Label>
            <Input
              type="number"
              min="0"
              value={form.bid_cents}
              onChange={(e) => set({ bid_cents: e.target.value })}
              className="rounded-xl mt-1"
              data-testid="ads-form-bid"
            />
          </div>
        </div>
        <div className="text-xs text-muted-foreground">{t('ads.budget.hint')}</div>
      </div>

      <div className="space-y-3">
        <div className="caps-label text-muted-foreground">{t('ads.schedule.title')}</div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>{t('ads.schedule.start')}</Label>
            <Input
              type="date"
              value={form.start_date || ''}
              onChange={(e) => set({ start_date: e.target.value })}
              className="rounded-xl mt-1"
            />
          </div>
          <div>
            <Label>{t('ads.schedule.end')}</Label>
            <Input
              type="date"
              value={form.end_date || ''}
              onChange={(e) => set({ end_date: e.target.value })}
              className="rounded-xl mt-1"
            />
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <div className="caps-label text-muted-foreground">{t('ads.targeting.title')}</div>
        <div className="grid grid-cols-2 gap-3">
          <Input
            value={form.target_country || ''}
            onChange={(e) => set({ target_country: e.target.value })}
            placeholder={t('ads.targeting.country')}
            className="rounded-xl"
            data-testid="ads-form-country"
          />
          <Input
            value={form.target_region || ''}
            onChange={(e) => set({ target_region: e.target.value })}
            placeholder={t('ads.targeting.region')}
            className="rounded-xl"
            data-testid="ads-form-region"
          />
        </div>
      </div>

      <div>
        <Label>{t('ads.statusLabel')}</Label>
        <Select value={form.status || 'draft'} onValueChange={(v) => set({ status: v })}>
          <SelectTrigger className="rounded-xl mt-1" data-testid="ads-form-status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {['draft', 'active', 'paused', 'ended'].map((s) => (
              <SelectItem key={s} value={s}>
                {t(`ads.status_${s}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
