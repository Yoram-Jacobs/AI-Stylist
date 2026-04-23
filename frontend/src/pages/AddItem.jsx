import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft, Upload, Plus, Loader2, Eye, Wand2, Shirt, Store,
  HandCoins, Gift, Repeat, Trash2, Save, Tag, AlertTriangle,
  X, Sparkles, Camera, RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import { api } from '@/lib/api';
import {
  labelForCategory,
  labelForDressCode,
  labelForGender,
  labelForPattern,
  labelForSeason,
  labelForState,
  labelForCondition,
  labelForQuality,
  labelForIntent,
  labelForItemType,
} from '@/lib/taxonomy';
import { toast } from 'sonner';

/* -------------------- constants -------------------- */
const CATEGORY_OPTIONS = [
  'Top', 'Bottom', 'Outerwear', 'Full Body', 'Footwear', 'Accessories', 'Underwear',
];
const DRESS_CODE_OPTIONS = [
  'casual', 'smart-casual', 'business', 'formal', 'athletic', 'loungewear',
];
const GENDER_OPTIONS = ['men', 'women', 'unisex', 'kids'];
const SEASON_OPTIONS = ['spring', 'summer', 'fall', 'winter', 'all'];
const STATE_OPTIONS = ['new', 'used'];
const CONDITION_OPTIONS = ['bad', 'fair', 'good', 'excellent'];
const QUALITY_OPTIONS = ['budget', 'mid', 'premium', 'luxury'];
const PATTERN_OPTIONS = [
  'solid', 'striped', 'plaid', 'floral', 'herringbone', 'polka', 'paisley',
  'geometric', 'abstract',
];
const INTENT_OPTIONS = [
  { value: 'own', icon: Shirt, tone: 'bg-slate-100 text-slate-900 border-slate-200' },
  { value: 'for_sale', icon: HandCoins, tone: 'bg-amber-100 text-amber-900 border-amber-200' },
  { value: 'donate', icon: Gift, tone: 'bg-emerald-100 text-emerald-900 border-emerald-200' },
  { value: 'swap', icon: Repeat, tone: 'bg-sky-100 text-sky-900 border-sky-200' },
];

const fileToBase64 = (file) =>
  new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onerror = reject;
    r.onload = () => {
      const s = String(r.result || '');
      const comma = s.indexOf(',');
      resolve(comma >= 0 ? s.slice(comma + 1) : s);
    };
    r.readAsDataURL(file);
  });

const fmtCents = (cents, cur = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: cur || 'USD' }).format(
    (cents || 0) / 100
  );

const blankFields = () => ({
  name: '', title: '', caption: '',
  category: '', sub_category: '', item_type: '', brand: '',
  gender: '', dress_code: '', season: [], tradition: '',
  colors: [], fabric_materials: [], pattern: '',
  state: '', condition: '', quality: '',
  size: '', price_cents: '',
  marketplace_intent: 'own',
  repair_advice: '',
  tags: [],
});

/** Coerce analyze payload into a plain, editable form dict. */
const hydrate = (a) => ({
  ...blankFields(),
  ...Object.fromEntries(Object.entries(a || {}).filter(([k]) => k in blankFields())),
});

/* -------------------- page -------------------- */
export default function AddItem() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [cards, setCards] = useState([]); // [{id,file,previewUrl,base64,status,progress,fields,error}]
  const [saving, setSaving] = useState(false);
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);

  const pickFiles = () => fileInputRef.current?.click();
  const openCamera = () => cameraInputRef.current?.click();

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    const drafts = await Promise.all(
      files.map(async (file) => {
        const b64 = await fileToBase64(file);
        return {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          file,
          mime: file.type || 'image/jpeg',
          previewUrl: URL.createObjectURL(file),
          base64: b64,
          status: 'scanning', // scanning | ready | error | saving | saved
          progress: 4,
          fields: blankFields(),
          error: null,
          label: null,
        };
      })
    );
    setCards((prev) => [...prev, ...drafts]);
    // Kick off parallel analysis.
    drafts.forEach((d) => analyzeCard(d));
  };

  const analyzeCard = async (card) => {
    // Faux-progress timer so the scanning animation paces with the API call.
    const startedAt = Date.now();
    const tick = setInterval(() => {
      const elapsed = (Date.now() - startedAt) / 1000;
      const target = Math.min(92, 4 + elapsed * 5); // reaches ~92 by 18s
      setCards((prev) =>
        prev.map((c) => (c.id === card.id && c.status === 'scanning' ? { ...c, progress: target } : c))
      );
    }, 250);
    try {
      const resp = await api.analyzeItemImage({ image_base64: card.base64 });
      clearInterval(tick);
      // New API shape: { items: [...], count, ...topLevelAnalysisMirror }.
      // Legacy callers that still get a single object without `items` keep working.
      const items = Array.isArray(resp?.items) && resp.items.length > 0 ? resp.items : null;

      if (!items) {
        // Legacy single-object response.
        setCards((prev) =>
          prev.map((c) =>
            c.id === card.id
              ? { ...c, status: 'ready', progress: 100, fields: hydrate(resp) }
              : c
          )
        );
        return;
      }

      if (items.length === 1) {
        // Single-item photo — keep the original preview, just hydrate fields.
        const it = items[0];
        setCards((prev) =>
          prev.map((c) =>
            c.id === card.id
              ? {
                  ...c,
                  status: 'ready',
                  progress: 100,
                  fields: hydrate(it.analysis || {}),
                  label: it.label || null,
                }
              : c
          )
        );
        return;
      }

      // Multi-item photo — replace the single placeholder card with one
      // fully-editable card per detected piece. Each new card owns the
      // crop image so saving persists only the relevant garment.
      const newCards = items.map((it, idx) => {
        const mime = it.crop_mime || 'image/jpeg';
        const rec = it.reconstruction;
        const recValidated = !!(rec && rec.validated && rec.image_b64);
        const previewUrl = recValidated
          ? `data:${rec.mime_type || 'image/png'};base64,${rec.image_b64}`
          : `data:${mime};base64,${it.crop_base64}`;
        return {
          id: `${card.id}-${idx}`,
          file: null,
          mime,
          previewUrl,
          base64: it.crop_base64,
          originalCropUrl: `data:${mime};base64,${it.crop_base64}`,
          reconstructedUrl: recValidated
            ? `data:${rec.mime_type || 'image/png'};base64,${rec.image_b64}`
            : null,
          reconstructedB64: recValidated ? rec.image_b64 : null,
          reconstructionMeta: recValidated
            ? {
                reasons: rec.reasons || [],
                prompt: rec.prompt,
                model: rec.model,
                mime_type: rec.mime_type,
              }
            : null,
          useReconstructed: recValidated,
          status: 'ready',
          progress: 100,
          fields: hydrate(it.analysis || {}),
          error: null,
          label: it.label || null,
        };
      });
      if (card.previewUrl?.startsWith('blob:')) URL.revokeObjectURL(card.previewUrl);
      setCards((prev) => {
        const idx = prev.findIndex((c) => c.id === card.id);
        if (idx < 0) return prev;
        return [...prev.slice(0, idx), ...newCards, ...prev.slice(idx + 1)];
      });
      toast.success(
        t('addItem.detected', { count: items.length })
      );
    } catch (err) {
      clearInterval(tick);
      const msg = err?.response?.data?.detail || t('addItem.analyzeFailed');
      setCards((prev) =>
        prev.map((c) =>
          c.id === card.id ? { ...c, status: 'error', progress: 0, error: msg } : c
        )
      );
      toast.error(msg);
    }
  };

  const retryCard = (card) => {
    setCards((prev) =>
      prev.map((c) => (c.id === card.id ? { ...c, status: 'scanning', progress: 4, error: null } : c))
    );
    analyzeCard(card);
  };

  const removeCard = (cardId) => {
    setCards((prev) => {
      const target = prev.find((c) => c.id === cardId);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((c) => c.id !== cardId);
    });
  };

  const updateField = (cardId, patch) => {
    setCards((prev) =>
      prev.map((c) => (c.id === cardId ? { ...c, fields: { ...c.fields, ...patch } } : c))
    );
  };

  // Phase Q: patch top-level card props (e.g., `useReconstructed` toggle).
  const patchCard = (cardId, patch) => {
    setCards((prev) =>
      prev.map((c) => (c.id === cardId ? { ...c, ...patch } : c))
    );
  };

  const saveAll = async () => {
    const ready = cards.filter((c) => c.status === 'ready' || c.status === 'error' /* still savable if user fills */);
    if (!ready.length) { toast.error(t('addItem.nothingToSave')); return; }
    setSaving(true);
    let ok = 0; let fail = 0;
    for (const card of ready) {
      if (card.status === 'error' && !card.fields.title) { fail += 1; continue; }
      setCards((prev) => prev.map((c) => (c.id === card.id ? { ...c, status: 'saving' } : c)));
      try {
        const body = buildCreatePayload(card);
        if (!body.title) { throw new Error('Title is required'); }
        await api.createItem(body);
        ok += 1;
        setCards((prev) => prev.map((c) => (c.id === card.id ? { ...c, status: 'saved' } : c)));
      } catch (err) {
        fail += 1;
        setCards((prev) => prev.map((c) =>
          c.id === card.id
            ? { ...c, status: 'error', error: err?.response?.data?.detail || err.message || 'Save failed' }
            : c));
      }
    }
    setSaving(false);
    if (ok && !fail) toast.success(t('addItem.savedCount', { count: ok }));
    else if (ok && fail) toast.message(`${t('addItem.savedCount', { count: ok })} · ${fail} ${t('common.error')}`);
    else toast.error(t('addItem.noneSaved'));
    if (ok && !fail) setTimeout(() => nav('/closet'), 800);
  };

  return (
    <div className="container-px max-w-6xl mx-auto pt-6 md:pt-10 pb-28" data-testid="add-item-page">
      <div className="flex items-center gap-2 mb-6">
        <Button variant="ghost" size="sm" onClick={() => nav(-1)} className="rounded-full" data-testid="add-item-back">
          <ArrowLeft className="h-4 w-4 me-2 rtl:rotate-180" /> {t('common.back')}
        </Button>
        <div className="flex-1" />
        <Button onClick={pickFiles} variant="outline" className="rounded-xl" data-testid="add-item-add-more">
          <Plus className="h-4 w-4 me-2" /> {t('addItem.addPhotos')}
        </Button>
        <Button
          onClick={saveAll}
          disabled={saving || !cards.some((c) => c.status === 'ready')}
          className="rounded-xl"
          data-testid="add-item-save-all"
        >
          {saving ? <Loader2 className="h-4 w-4 me-2 animate-spin" /> : <Save className="h-4 w-4 me-2" />}
          {t('addItem.saveAll')}
        </Button>
      </div>

      <div className="mb-6">
        <div className="caps-label text-muted-foreground">{t('addItem.label')}</div>
        <h1 className="font-display text-3xl sm:text-4xl mt-1">{t('addItem.title')}</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-2xl">
          {t('addItem.subtitle')}
        </p>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        className="sr-only"
        data-testid="add-item-file-input"
        onChange={(e) => { handleFiles(e.target.files); e.target.value = ''; }}
      />
      {/* Native camera capture — on mobile, `capture="environment"` opens
          the rear camera directly; on desktop, falls back to a file
          picker so the button is safe to show everywhere. */}
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="sr-only"
        data-testid="add-item-camera-input"
        onChange={(e) => { handleFiles(e.target.files); e.target.value = ''; }}
      />

      {cards.length === 0 ? (
        <div
          className="w-full border-2 border-dashed border-border rounded-[calc(var(--radius)+10px)] p-10 sm:p-12 bg-card flex flex-col items-center text-center"
          data-testid="add-item-dropzone"
        >
          <div className="h-14 w-14 rounded-full bg-secondary flex items-center justify-center mb-3">
            <Eye className="h-6 w-6" />
          </div>
          <div className="font-display text-xl">{t('addItem.dropzoneTitle')}</div>
          <div className="text-sm text-muted-foreground mt-1 max-w-md">
            {t('addItem.dropzoneBody')}
          </div>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
            <Button
              type="button"
              className="rounded-xl"
              onClick={openCamera}
              data-testid="add-item-open-camera-button"
            >
              <Camera className="h-4 w-4 me-2" /> {t('addItem.takePhoto')}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="rounded-xl"
              onClick={pickFiles}
              data-testid="add-item-pick-files-button"
            >
              <Upload className="h-4 w-4 me-2" /> {t('addItem.uploadPhotos')}
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-end gap-2 mb-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="rounded-lg"
              onClick={openCamera}
              data-testid="add-item-camera-more-button"
            >
              <Camera className="h-4 w-4 me-1.5" /> {t('addItem.takePhoto')}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="rounded-lg"
              onClick={pickFiles}
              data-testid="add-item-upload-more-button"
            >
              <Plus className="h-4 w-4 me-1.5" /> {t('addItem.addPhotos')}
            </Button>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-testid="add-item-cards-grid">
            {cards.map((card) => (
              <ItemCard
                key={card.id}
                card={card}
                onRetry={() => retryCard(card)}
                onRemove={() => removeCard(card.id)}
                onChange={(patch) => updateField(card.id, patch)}
                onCardPatch={(patch) => patchCard(card.id, patch)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* -------------------- item card -------------------- */
function ItemCard({ card, onRetry, onRemove, onChange, onCardPatch }) {
  const { t } = useTranslation();
  const { fields, status, progress, previewUrl, error } = card;
  const isBusy = status === 'scanning';
  const saved = status === 'saved';
  const hasReconstruction = !!(card.reconstructedUrl && card.reconstructionMeta);
  const showingReconstructed = hasReconstruction && card.useReconstructed;

  return (
    <Card
      className={`rounded-[calc(var(--radius)+10px)] shadow-editorial overflow-hidden ${saved ? 'opacity-75' : ''}`}
      data-testid="add-item-card"
    >
      <CardContent className="p-0">
        <div className="grid grid-cols-1 md:grid-cols-[220px_1fr] gap-0">
          {/* Photo + scanning */}
          <div className="relative bg-secondary/40">
            <div
              className={`aspect-[3/4] md:aspect-auto md:h-full w-full ${isBusy ? 'scanning' : ''}`}
              data-testid="add-item-card-photo"
            >
              <img
                src={previewUrl}
                alt={fields.name || fields.title || 'Pending garment'}
                className="w-full h-full object-cover"
              />
            </div>
            {hasReconstruction && !isBusy && (
              <div
                className="absolute top-2 start-2 inline-flex items-center gap-1.5 rounded-full bg-background/90 backdrop-blur border border-border px-2 py-1 text-[10px] font-semibold"
                data-testid="add-item-repaired-badge"
              >
                <Wand2 className="h-3 w-3 text-[hsl(var(--accent))]" />
                {showingReconstructed
                  ? t('itemDetail.repair.showingRepaired')
                  : t('itemDetail.repair.showingOriginal')}
              </div>
            )}
            {hasReconstruction && !isBusy && (
              <button
                type="button"
                onClick={() => onCardPatch?.({
                  useReconstructed: !showingReconstructed,
                  previewUrl: showingReconstructed
                    ? card.originalCropUrl
                    : card.reconstructedUrl,
                })}
                className="absolute top-2 end-2 inline-flex items-center gap-1 rounded-full bg-background/90 backdrop-blur border border-border px-2 py-1 text-[10px] font-medium hover:bg-secondary transition-colors"
                data-testid="add-item-toggle-reconstruction"
                aria-label={showingReconstructed
                  ? t('itemDetail.repair.ariaShowOriginal')
                  : t('itemDetail.repair.ariaShowRepaired')}
              >
                {showingReconstructed ? (
                  <><RefreshCw className="h-3 w-3" /> {t('itemDetail.repair.toggleOriginal')}</>
                ) : (
                  <><Wand2 className="h-3 w-3" /> {t('itemDetail.repair.toggleAI')}</>
                )}
              </button>
            )}
            {isBusy && (
              <div
                className="absolute bottom-0 left-0 right-0 bg-background/80 backdrop-blur-sm px-3 py-2"
                data-testid="add-item-scanning-overlay"
              >
                <div className="flex items-center gap-2 text-xs">
                  <Eye className="h-3.5 w-3.5 text-[hsl(var(--accent))] animate-pulse" />
                  <span className="font-medium">{t('addItem.scanning')}…</span>
                </div>
                <Progress value={progress} className="h-1 mt-1.5" />
              </div>
            )}
            {status === 'error' && !isBusy && (
              <div className="absolute bottom-0 left-0 right-0 bg-rose-50/95 text-rose-900 px-3 py-2 text-xs flex items-start gap-2">
                <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                <span className="flex-1">{error || t('addItem.analyzeFailed')}</span>
                <button onClick={onRetry} className="underline shrink-0" data-testid="add-item-retry">
                  {t('addItem.tryAgain')}
                </button>
              </div>
            )}
            {saved && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/60 backdrop-blur-[2px]">
                <Badge className="bg-emerald-600 text-white">{t('addItem.saved')}</Badge>
              </div>
            )}
            {!saved && (
              <button
                type="button"
                onClick={onRemove}
                className="absolute top-2 right-2 h-8 w-8 rounded-full bg-background/80 backdrop-blur flex items-center justify-center hover:bg-background"
                aria-label={t('addItem.removePhoto')}
                data-testid="add-item-remove"
              >
                <X className="h-4 w-4" />
              </button>
            )}
            {card.label && !isBusy && status !== 'error' && (
              <div
                className="absolute top-2 left-2 max-w-[70%]"
                data-testid="add-item-detected-label"
              >
                <Badge
                  variant="outline"
                  className="bg-background/85 backdrop-blur text-[10px] capitalize border-border/60 flex items-center gap-1"
                >
                  <Sparkles className="h-2.5 w-2.5 text-[hsl(var(--accent))]" />
                  {labelForItemType(card.label, t)}
                </Badge>
              </div>
            )}
          </div>

          {/* Fields */}
          <div className="p-5 space-y-4">
            <NameCaption fields={fields} onChange={onChange} disabled={saved} />
            <IntentSelector fields={fields} onChange={onChange} disabled={saved} />
            {fields.repair_advice && (
              <div
                className="flex items-start gap-2 p-3 rounded-xl bg-amber-50 text-amber-900 text-xs"
                data-testid="add-item-repair-advice"
              >
                <Wand2 className="h-4 w-4 mt-0.5 shrink-0" />
                <div>
                  <div className="font-medium">{t('addItem.repairTip')}</div>
                  <div className="mt-0.5">{fields.repair_advice}</div>
                </div>
              </div>
            )}
            <TaxonomyGrid fields={fields} onChange={onChange} disabled={saved} />
            <WeightedList
              labelKey="addItem.color"
              items={fields.colors}
              onChange={(v) => onChange({ colors: v })}
              placeholder={t('addItem.colorSlotPlaceholder')}
              disabled={saved}
              testid="add-item-colors"
            />
            <WeightedList
              labelKey="addItem.material"
              items={fields.fabric_materials}
              onChange={(v) => onChange({ fabric_materials: v })}
              placeholder={t('addItem.fabricSlotPlaceholder')}
              disabled={saved}
              testid="add-item-fabrics"
            />
            <QualityRow fields={fields} onChange={onChange} disabled={saved} />
            <SeasonPicker fields={fields} onChange={onChange} disabled={saved} />
            <TagsEditor
              items={fields.tags}
              onChange={(v) => onChange({ tags: v })}
              disabled={saved}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* -------------------- sub-sections -------------------- */
function NameCaption({ fields, onChange, disabled }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      <div>
        <Label className="caps-label text-muted-foreground">{t('addItem.itemName')}</Label>
        <Input
          value={fields.name || ''}
          onChange={(e) => onChange({ name: e.target.value })}
          placeholder={t('addItem.namePlaceholder')}
          disabled={disabled}
          data-testid="add-item-name"
          className="mt-1 font-display text-xl bg-transparent border-0 border-b rounded-none px-0 focus-visible:ring-0 focus-visible:border-[hsl(var(--accent))]"
        />
      </div>
      <div>
        <Label className="caps-label text-muted-foreground">{t('addItem.caption')}</Label>
        <Textarea
          value={fields.caption || ''}
          onChange={(e) => onChange({ caption: e.target.value })}
          rows={2}
          placeholder={t('addItem.captionPlaceholder')}
          disabled={disabled}
          data-testid="add-item-caption"
          className="mt-1 resize-none"
        />
      </div>
    </div>
  );
}

function IntentSelector({ fields, onChange, disabled }) {
  const { t } = useTranslation();
  const intent = fields.marketplace_intent || 'own';
  // Only compute preview for 'for_sale'
  const priceCents = Number(fields.price_cents) || 0;
  const stripeFee = intent === 'for_sale' ? Math.round(priceCents * 0.029) + (priceCents > 0 ? 30 : 0) : 0;
  const netAfterStripe = Math.max(0, priceCents - stripeFee);
  const platformFee = Math.round(netAfterStripe * 0.07);
  const sellerNet = netAfterStripe - platformFee;

  return (
    <div className="rounded-2xl border border-border p-3 bg-secondary/30">
      <div className="flex items-center justify-between mb-2">
        <Label className="caps-label text-muted-foreground flex items-center gap-1">
          <Tag className="h-3 w-3" /> {t('addItem.marketplaceIntent')}
        </Label>
        <Badge variant="outline" className="text-[10px]">
          {t('addItem.intent_own')}
        </Badge>
      </div>
      <div
        className="grid grid-cols-2 sm:grid-cols-4 gap-2"
        role="radiogroup"
        aria-label={t('addItem.marketplaceIntent')}
      >
        {INTENT_OPTIONS.map((o) => {
          const active = intent === o.value;
          const Icon = o.icon;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={disabled}
              onClick={() => onChange({ marketplace_intent: o.value })}
              data-testid={`add-item-intent-${o.value}`}
              className={`rounded-xl border px-3 py-2 text-sm flex items-center justify-center gap-1.5 transition-colors ${
                active ? `${o.tone} font-medium` : 'bg-background text-muted-foreground hover:text-foreground border-border'
              }`}
            >
              <Icon className="h-3.5 w-3.5" /> {labelForIntent(o.value, t)}
            </button>
          );
        })}
      </div>
      {intent === 'for_sale' && (
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="add-item-fee-preview">
          <div>
            <Label className="caps-label text-muted-foreground">{t('addItem.price')} (USD)</Label>
            <Input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={fields.price_cents ? (Number(fields.price_cents) / 100).toFixed(2) : ''}
              onChange={(e) => {
                const v = e.target.value.trim();
                onChange({ price_cents: v ? Math.round(parseFloat(v) * 100) : '' });
              }}
              placeholder="0.00"
              disabled={disabled}
              data-testid="add-item-price"
              className="mt-1 rounded-xl"
            />
          </div>
          <div className="text-xs text-muted-foreground self-end">
            <div className="flex justify-between"><span>{t('addItem.stripeFee')}</span><span className="font-mono">{fmtCents(stripeFee)}</span></div>
            <div className="flex justify-between"><span>{t('transactions.platform7')}</span><span className="font-mono">{fmtCents(platformFee)}</span></div>
            <div className="flex justify-between font-medium text-foreground"><span>{t('addItem.youReceive')}</span><span className="font-mono">{fmtCents(sellerNet)}</span></div>
          </div>
        </div>
      )}
    </div>
  );
}

function TaxonomyGrid({ fields, onChange, disabled }) {
  const { t } = useTranslation();
  const row = (label, value, setter, options, testid, placeholder, formatter) => (
    <div>
      <Label className="caps-label text-muted-foreground">{label}</Label>
      {options ? (
        <Select value={value || ''} onValueChange={(v) => setter(v === '__clear' ? '' : v)} disabled={disabled}>
          <SelectTrigger className="mt-1 rounded-xl" data-testid={testid}>
            <SelectValue placeholder={placeholder || t('addItem.selectPlaceholder')} />
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o} value={o}>
                {formatter ? formatter(o, t) : o}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <Input
          value={value || ''}
          onChange={(e) => setter(e.target.value)}
          placeholder={placeholder || ''}
          disabled={disabled}
          data-testid={testid}
          className="mt-1 rounded-xl"
        />
      )}
    </div>
  );

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
      {row(t('addItem.category'), fields.category, (v) => onChange({ category: v }), CATEGORY_OPTIONS, 'add-item-category', t('addItem.categoryPlaceholder'), labelForCategory)}
      {row(t('addItem.subCategory'), fields.sub_category, (v) => onChange({ sub_category: v }), null, 'add-item-subcategory', t('addItem.subCategoryPlaceholder'))}
      {row(t('addItem.itemType'), fields.item_type, (v) => onChange({ item_type: v }), null, 'add-item-itemtype', t('addItem.itemTypePlaceholder'))}
      {row(t('addItem.brand'), fields.brand, (v) => onChange({ brand: v }), null, 'add-item-brand', t('addItem.brandPlaceholder'))}
      {row(t('itemDetail.edit.gender'), fields.gender, (v) => onChange({ gender: v }), GENDER_OPTIONS, 'add-item-gender', t('addItem.genderPlaceholder'), labelForGender)}
      {row(t('addItem.dressCode'), fields.dress_code, (v) => onChange({ dress_code: v }), DRESS_CODE_OPTIONS, 'add-item-dresscode', t('addItem.dressCodePlaceholder'), labelForDressCode)}
      {row(t('addItem.pattern'), fields.pattern, (v) => onChange({ pattern: v }), PATTERN_OPTIONS, 'add-item-pattern', t('addItem.patternPlaceholder'), labelForPattern)}
      {row(t('addItem.tradition'), fields.tradition, (v) => onChange({ tradition: v }), null, 'add-item-tradition', t('addItem.traditionPlaceholder'))}
      {row(t('addItem.size'), fields.size, (v) => onChange({ size: v }), null, 'add-item-size', t('addItem.sizePlaceholder'))}
    </div>
  );
}

function QualityRow({ fields, onChange, disabled }) {
  const { t } = useTranslation();
  const cell = (label, value, setter, options, testid, formatter) => (
    <div>
      <Label className="caps-label text-muted-foreground">{label}</Label>
      <Select value={value || ''} onValueChange={(v) => setter(v === '__clear' ? '' : v)} disabled={disabled}>
        <SelectTrigger className="mt-1 rounded-xl" data-testid={testid}>
          <SelectValue placeholder={t('addItem.selectPlaceholder')} />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {formatter ? formatter(o, t) : o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
  return (
    <div className="grid grid-cols-3 gap-3">
      {cell(t('addItem.state'), fields.state, (v) => onChange({ state: v }), STATE_OPTIONS, 'add-item-state', labelForState)}
      {cell(t('addItem.condition'), fields.condition, (v) => onChange({ condition: v }), CONDITION_OPTIONS, 'add-item-condition', labelForCondition)}
      {cell(t('addItem.qualityLabel'), fields.quality, (v) => onChange({ quality: v }), QUALITY_OPTIONS, 'add-item-quality', labelForQuality)}
    </div>
  );
}

function SeasonPicker({ fields, onChange, disabled }) {
  const { t } = useTranslation();
  const active = new Set(fields.season || []);
  const toggle = (s) => {
    const next = new Set(active);
    if (s === 'all') { next.clear(); next.add('all'); }
    else {
      next.delete('all');
      if (next.has(s)) next.delete(s); else next.add(s);
    }
    onChange({ season: Array.from(next) });
  };
  return (
    <div>
      <Label className="caps-label text-muted-foreground">{t('addItem.season')}</Label>
      <div className="mt-1 flex flex-wrap gap-1.5" data-testid="add-item-season">
        {SEASON_OPTIONS.map((s) => {
          const on = active.has(s);
          return (
            <button
              key={s}
              type="button"
              disabled={disabled}
              onClick={() => toggle(s)}
              aria-pressed={on}
              data-testid={`add-item-season-${s}`}
              className={`rounded-full px-3 py-1 text-xs border ${
                on ? 'bg-[hsl(var(--accent))] text-white border-[hsl(var(--accent))]' : 'bg-background border-border text-muted-foreground'
              }`}
            >
              {labelForSeason(s, t)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function WeightedList({ label, labelKey, items, onChange, placeholder, disabled, testid }) {
  const { t } = useTranslation();
  const safe = Array.isArray(items) ? items : [];
  const sum = safe.reduce((s, it) => s + (Number(it.pct) || 0), 0);
  const update = (i, patch) => onChange(safe.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const remove = (i) => onChange(safe.filter((_, j) => j !== i));
  const add = () => onChange([...safe, { name: '', pct: 0 }]);
  const heading = labelKey ? t(labelKey) : label;
  return (
    <div>
      <div className="flex items-center justify-between">
        <Label className="caps-label text-muted-foreground">{heading}</Label>
        <span className={`text-[10px] font-mono ${sum === 100 ? 'text-emerald-700' : sum > 100 ? 'text-rose-700' : 'text-muted-foreground'}`}>
          {sum}%
        </span>
      </div>
      <div className="mt-1 space-y-1.5" data-testid={testid}>
        {safe.map((it, i) => (
          <div key={i} className="flex items-center gap-2">
            <Input
              value={it.name || ''}
              onChange={(e) => update(i, { name: e.target.value })}
              placeholder={placeholder}
              disabled={disabled}
              className="flex-1 rounded-xl h-9"
              data-testid={`${testid}-name-${i}`}
            />
            <Input
              type="number"
              min="0"
              max="100"
              value={it.pct ?? ''}
              onChange={(e) => update(i, { pct: e.target.value === '' ? null : Math.max(0, Math.min(100, Number(e.target.value))) })}
              className="w-16 rounded-xl h-9 text-right"
              disabled={disabled}
              data-testid={`${testid}-pct-${i}`}
            />
            <span className="text-xs text-muted-foreground">%</span>
            <button
              type="button"
              onClick={() => remove(i)}
              disabled={disabled}
              className="h-9 w-9 rounded-full flex items-center justify-center hover:bg-secondary"
              aria-label={t('addItem.removeEntryAria', { label: it.name || heading })}
              data-testid={`${testid}-remove-${i}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={add}
          disabled={disabled}
          className="text-xs h-8 rounded-lg"
          data-testid={`${testid}-add`}
        >
          <Plus className="h-3 w-3 me-1" /> {t('addItem.addAction')}
        </Button>
      </div>
    </div>
  );
}

function TagsEditor({ items, onChange, disabled }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState('');
  const add = () => {
    const v = draft.trim();
    if (!v) return;
    if (!items.includes(v)) onChange([...items, v]);
    setDraft('');
  };
  return (
    <div>
      <Label className="caps-label text-muted-foreground">{t('addItem.tags')}</Label>
      <div className="mt-1 flex flex-wrap gap-1.5" data-testid="add-item-tags">
        {items.map((tag) => (
          <Badge key={tag} variant="outline" className="text-[11px] pl-2 pr-1 flex items-center gap-1">
            {tag}
            <button
              type="button"
              onClick={() => onChange(items.filter((x) => x !== tag))}
              disabled={disabled}
              className="h-4 w-4 rounded-full hover:bg-secondary flex items-center justify-center"
              aria-label={t('addItem.removeTagAria', { label: tag })}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
        <div className="flex items-center gap-1">
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
            placeholder={t('addItem.addTag')}
            disabled={disabled}
            className="h-8 text-xs rounded-full w-32"
            data-testid="add-item-tag-input"
          />
          <Button type="button" size="sm" variant="ghost" className="text-xs h-8" onClick={add} disabled={disabled || !draft.trim()}>
            <Plus className="h-3 w-3" />
          </Button>
        </div>
      </div>
    </div>
  );
}

/* -------------------- payload builder -------------------- */
function buildCreatePayload(card) {
  const f = card.fields || {};
  const asBase64 = card.base64;
  // Drop empty/falsy optional keys to satisfy enum validators on the backend.
  const body = {
    source: f.marketplace_intent && f.marketplace_intent !== 'own' ? 'Shared' : 'Private',
    name: f.name || undefined,
    title: f.name || f.title || 'Unnamed garment',
    caption: f.caption || undefined,
    category: f.category || 'Top',
    sub_category: f.sub_category || undefined,
    item_type: f.item_type || undefined,
    brand: f.brand || undefined,
    gender: f.gender || undefined,
    dress_code: f.dress_code || undefined,
    season: f.season || [],
    tradition: f.tradition || undefined,
    size: f.size || undefined,
    color: (f.colors && f.colors[0]?.name) || undefined,
    colors: (f.colors || []).filter((c) => c.name),
    fabric_materials: (f.fabric_materials || []).filter((c) => c.name),
    pattern: f.pattern || undefined,
    state: f.state || undefined,
    condition: f.condition || undefined,
    quality: f.quality || undefined,
    repair_advice: f.repair_advice || undefined,
    price_cents: f.price_cents === '' || f.price_cents == null ? undefined : Number(f.price_cents),
    currency: 'USD',
    marketplace_intent: f.marketplace_intent || 'own',
    tags: f.tags || [],
    image_base64: asBase64,
    image_mime: card.mime || card.file?.type || 'image/jpeg',
    // Phase Q: forward the reconstructed image when the user kept it
    reconstructed_image_b64: card.useReconstructed && card.reconstructedB64
      ? card.reconstructedB64
      : undefined,
    reconstruction_metadata: card.useReconstructed && card.reconstructionMeta
      ? card.reconstructionMeta
      : undefined,
  };
  // Strip undefined to keep payload clean (Pydantic `extra=forbid` still accepts unset fields).
  return Object.fromEntries(Object.entries(body).filter(([, v]) => v !== undefined));
}
