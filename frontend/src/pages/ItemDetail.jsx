import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft,
  Sparkles,
  Trash2,
  Store,
  Loader2,
  Wand2,
  Mic,
  Square,
  RefreshCw,
  Save,
  Undo2,
  Plus,
  X,
  CheckCircle2,
  Camera,
  QrCode,
  Leaf,
  Globe2,
  Wrench,
  BadgeCheck,
  ExternalLink,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AspectRatio } from '@/components/ui/aspect-ratio';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { SourceTagBadge } from '@/components/SourceTagBadge';
import { DppPanel } from '@/components/DppPanel';
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
  labelForFormality,
  labelForSubCategory,
  labelForItemType,
} from '@/lib/taxonomy';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';
import { isSTTSupported, createRecognition } from '@/lib/speech';

/* -------------------- enum option lists (kept in-file to avoid a cross-page coupling) -------------------- */
const CATEGORY_OPTIONS = [
  'Top',
  'Bottom',
  'Outerwear',
  'Full Body',
  'Footwear',
  'Accessories',
  'Underwear',
];
const DRESS_CODE_OPTIONS = [
  'casual',
  'smart-casual',
  'business',
  'formal',
  'athletic',
  'loungewear',
];
const GENDER_OPTIONS = ['men', 'women', 'unisex', 'kids'];
const SEASON_OPTIONS = ['spring', 'summer', 'fall', 'winter', 'all'];
const STATE_OPTIONS = ['new', 'used'];
const CONDITION_OPTIONS = ['bad', 'fair', 'good', 'excellent'];
const QUALITY_OPTIONS = ['budget', 'mid', 'premium', 'luxury'];
const PATTERN_OPTIONS = [
  'solid',
  'striped',
  'plaid',
  'floral',
  'herringbone',
  'polka',
  'paisley',
  'geometric',
  'abstract',
];
const FORMALITY_OPTIONS = ['casual', 'smart-casual', 'business', 'formal'];
const INTENT_OPTIONS = ['own', 'for_sale', 'donate', 'swap'];
const CURRENCY_OPTIONS = ['USD', 'EUR', 'GBP', 'ILS'];

const EDITABLE_FIELDS = [
  'title',
  'name',
  'caption',
  'category',
  'sub_category',
  'item_type',
  'brand',
  'gender',
  'dress_code',
  'season',
  'tradition',
  'size',
  'color',
  'material',
  'pattern',
  'state',
  'condition',
  'quality',
  'repair_advice',
  'price_cents',
  'currency',
  'marketplace_intent',
  'formality',
  'cultural_tags',
  'tags',
  'notes',
];

/** Pick the subset of fields we mutate + normalise to a stable shape. */
function toFormState(item) {
  return {
    title: item.title || '',
    name: item.name || '',
    caption: item.caption || '',
    category: item.category || 'Top',
    sub_category: item.sub_category || '',
    item_type: item.item_type || '',
    brand: item.brand || '',
    gender: item.gender || '',
    dress_code: item.dress_code || '',
    season: Array.isArray(item.season) ? item.season : [],
    tradition: item.tradition || '',
    size: item.size || '',
    color: item.color || '',
    material: item.material || '',
    pattern: item.pattern || '',
    state: item.state || '',
    condition: item.condition || '',
    quality: item.quality || '',
    repair_advice: item.repair_advice || '',
    price_cents: item.price_cents ?? '',
    currency: item.currency || 'USD',
    marketplace_intent: item.marketplace_intent || 'own',
    formality: item.formality || '',
    cultural_tags: Array.isArray(item.cultural_tags) ? item.cultural_tags : [],
    tags: Array.isArray(item.tags) ? item.tags : [],
    notes: item.notes || '',
  };
}

/** Compute the PATCH body from a form snapshot: include only the fields
 *  that actually changed from the loaded item. Empty-string fields that
 *  were previously set are translated to ``null`` (clear the field).
 *  Multi-select arrays are sent as the full array whenever they differ.
 */
function diffPatch(loaded, form) {
  const baseline = toFormState(loaded);
  const out = {};
  for (const key of EDITABLE_FIELDS) {
    const a = baseline[key];
    const b = form[key];
    const isArr = Array.isArray(a) || Array.isArray(b);
    if (isArr) {
      const aa = Array.isArray(a) ? a : [];
      const bb = Array.isArray(b) ? b : [];
      if (aa.length !== bb.length || aa.some((v, i) => v !== bb[i])) {
        out[key] = bb;
      }
      continue;
    }
    // price_cents: user types dollars in the UI; convert before send.
    if (key === 'price_cents') {
      const parsed = b === '' || b == null ? null : Math.round(Number(b));
      if (parsed !== a) {
        out[key] = Number.isFinite(parsed) ? parsed : null;
      }
      continue;
    }
    if ((a || '') !== (b || '')) {
      out[key] = b === '' ? null : b;
    }
  }
  return out;
}

/* -------------------- generic chip-list editor -------------------- */
function ChipList({ value, onChange, placeholder, disabled, testidPrefix }) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    if (value.includes(trimmed)) { setDraft(''); return; }
    onChange([...value, trimmed]);
    setDraft('');
  };
  return (
    <div
      className="flex flex-wrap gap-1.5 items-center rounded-xl border border-border bg-background px-2 py-1.5 min-h-10"
      data-testid={`${testidPrefix}-chiplist`}
    >
      {value.map((v) => (
        <Badge
          key={v}
          variant="secondary"
          className="rounded-full text-[11px] inline-flex items-center gap-1"
          data-testid={`${testidPrefix}-chip-${v}`}
        >
          {v}
          {!disabled && (
            <button
              type="button"
              onClick={() => onChange(value.filter((x) => x !== v))}
              className="hover:text-destructive"
              aria-label={`Remove ${v}`}
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </Badge>
      ))}
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); add(); }
        }}
        placeholder={placeholder}
        disabled={disabled}
        className="h-7 text-xs border-0 shadow-none flex-1 min-w-24 focus-visible:ring-0 px-1"
        data-testid={`${testidPrefix}-input`}
      />
      {!disabled && draft.trim() && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={add}
          className="h-7 px-2 text-xs"
          data-testid={`${testidPrefix}-add`}
        >
          <Plus className="h-3 w-3" />
        </Button>
      )}
    </div>
  );
}

/* -------------------- localized-display hint -------------------- */
/**
 * Shows a small secondary line below free-text taxonomy inputs (sub_category,
 * item_type) with the localized display when the raw DB value matches a
 * known taxonomy token. Hidden otherwise.
 */
function LocalizedHint({ raw, translated }) {
  const trimmed = String(raw || '').trim();
  if (!trimmed || !translated || translated === trimmed) return null;
  return (
    <div
      className="mt-1 text-[11px] text-muted-foreground flex items-center gap-1 truncate"
      data-testid="localized-display-hint"
    >
      <span aria-hidden="true">·</span>
      <span>{translated}</span>
    </div>
  );
}

/* -------------------- multi-select pill group -------------------- */
function PillMultiSelect({ value, options, onChange, testidPrefix, format }) {
  const toggle = (opt) => {
    onChange(
      value.includes(opt) ? value.filter((v) => v !== opt) : [...value, opt],
    );
  };
  return (
    <div
      className="flex flex-wrap gap-1.5"
      data-testid={`${testidPrefix}-pillgroup`}
    >
      {options.map((opt) => {
        const on = value.includes(opt);
        return (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            data-testid={`${testidPrefix}-pill-${opt}`}
            className={`rounded-full border px-3 py-1 text-xs transition-colors ${
              on
                ? 'bg-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))] border-[hsl(var(--accent))]'
                : 'bg-card border-border hover:bg-secondary'
            }`}
          >
            {format ? format(opt) : opt}
          </button>
        );
      })}
    </div>
  );
}

/* -------------------- single-select shadcn wrapper that tolerates "" -------------------- */
function NullableSelect({ value, onChange, options, placeholder, testid, format }) {
  // Shadcn Select rejects empty string as a value; we map "" -> __none__ for the control.
  const v = value || '__none__';
  return (
    <Select
      value={v}
      onValueChange={(next) => onChange(next === '__none__' ? '' : next)}
    >
      <SelectTrigger className="rounded-xl h-10" data-testid={testid}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__none__">—</SelectItem>
        {options.map((o) => (
          <SelectItem key={o} value={o}>
            {format ? format(o) : o}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/* ========================= Page ========================= */
export default function ItemDetail() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { id } = useParams();
  const nav = useNavigate();

  const [item, setItem] = useState(null);
  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Repair state
  const [repairHint, setRepairHint] = useState('');
  const [repairing, setRepairing] = useState(false);
  // Clean-background progress %, simulated client-side because the
  // backend matting endpoint is a single non-streaming POST. We tick
  // the bar towards ~92% over ~14s (roughly the p95 duration of the
  // SegFormer + rembg pipeline) and snap to 100% on completion.
  const [repairProgress, setRepairProgress] = useState(0);
  const [dictating, setDictating] = useState(false);
  const [dictationInterim, setDictationInterim] = useState('');
  const [showingOriginal, setShowingOriginal] = useState(false);

  // Phase V6 — photo add/replace state
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const photoInputRef = useRef(null);
  const onPickPhoto = () => photoInputRef.current?.click();
  const onPhotoFileChosen = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setUploadingPhoto(true);
    const loadingId = toast.loading(t('itemDetail.photo.running'));
    try {
      const imageBase64 = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || '').split(',')[1] || '');
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
      const res = await api.setItemPhoto(id, {
        imageBase64,
        imageMime: file.type || 'image/jpeg',
        autoSegment: true,
      });
      setItem(res.item);
      toast.dismiss(loadingId);
      toast.success(t('itemDetail.photo.success'));
    } catch (err) {
      toast.dismiss(loadingId);
      toast.error(err?.response?.data?.detail || t('itemDetail.photo.error'));
    } finally {
      setUploadingPhoto(false);
    }
  };
  const recognitionRef = useRef(null);
  const sttSupported = useRef(isSTTSupported());

  // Variant edit state (existing feature, preserved)
  const [editPrompt, setEditPrompt] = useState('');
  const [editing, setEditing] = useState(false);

  /* ------------------- load + sync ------------------- */
  const load = async () => {
    try {
      const data = await api.getItem(id);
      setItem(data);
      setForm(toFormState(data));
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('itemDetail.notFound'));
      nav('/closet');
    } finally {
      setLoading(false);
    }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [id]);
  useEffect(() => () => {
    try { recognitionRef.current?.abort?.(); } catch { /* ignore */ }
  }, []);

  const patch = useMemo(
    () => (item && form ? diffPatch(item, form) : {}),
    [item, form],
  );
  const isDirty = Object.keys(patch).length > 0;

  const setField = (key, val) => setForm((f) => ({ ...f, [key]: val }));

  /* ------------------- save / discard ------------------- */
  const onSave = async () => {
    if (!isDirty || saving) return;
    setSaving(true);
    try {
      const updated = await api.updateItem(id, patch);
      setItem(updated);
      setForm(toFormState(updated));
      toast.success(t('itemDetail.detailsSaved'));
      // Per UX spec: after a successful edit, take the user back
      // to the closet so they immediately see the updated item in
      // its grid context (rather than staying on the detail page).
      nav('/closet');
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('itemDetail.saveFailed'));
    } finally {
      setSaving(false);
    }
  };
  const onDiscard = () => {
    if (!item) return;
    setForm(toFormState(item));
    toast.message(t('itemDetail.changesDiscarded'));
  };

  /* ------------------- Clean background (Phase V Fix 2) ------------------- */
  const onRepair = async () => {
    if (repairing) return;
    setRepairing(true);
    setShowingOriginal(false);
    setRepairProgress(4);
    // Asymptotic ramp: each tick closes ~7% of the remaining gap to 92%,
    // so the bar feels lively at the start and decelerates as it nears
    // the cap — never reaching 100% until the API actually returns.
    const ticker = setInterval(() => {
      setRepairProgress((p) => {
        if (p >= 92) return 92;
        const next = p + Math.max(1, Math.round((92 - p) * 0.07));
        return Math.min(92, next);
      });
    }, 350);
    try {
      const res = await api.cleanItemBackground(id);
      if (res.applied) {
        toast.success(t('itemDetail.cleanBackground.success'));
        setItem(res.item);
        setForm(toFormState(res.item));
        setRepairHint('');
      } else {
        toast.warning(res.detail || t('itemDetail.cleanBackground.rejected'));
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('itemDetail.cleanBackground.error'));
    } finally {
      clearInterval(ticker);
      setRepairProgress(100);
      // Brief delay so the user sees the bar hit 100% before it
      // collapses — feels more "complete" than yanking it instantly.
      setTimeout(() => {
        setRepairing(false);
        setRepairProgress(0);
      }, 350);
    }
  };
  const startDictation = () => {
    if (!sttSupported.current) return;
    const rec = createRecognition({
      lang: user?.preferred_language || 'en',
      onInterim: (txt) => setDictationInterim(txt || ''),
      onFinal: (finalText) => {
        if (finalText) {
          setRepairHint((prev) =>
            prev ? `${prev} ${finalText}`.slice(0, 240) : finalText.slice(0, 240),
          );
        }
      },
      onEnd: () => {
        setDictating(false);
        setDictationInterim('');
        recognitionRef.current = null;
      },
      onError: () => toast.error(t('stylist.micDenied')),
    });
    if (!rec) return;
    recognitionRef.current = rec;
    rec.start();
    setDictating(true);
  };
  const stopDictation = () => {
    try { recognitionRef.current?.stop?.(); } catch { /* ignore */ }
  };

  /* ------------------- variant generation (unchanged) ------------------- */
  const onGenerateVariant = async () => {
    if (!editPrompt.trim()) return;
    setEditing(true);
    try {
      const res = await api.editItemImage(id, editPrompt.trim());
      toast.success(t('itemDetail.variantGenerated'));
      setItem((it) => ({ ...it, variants: res.variants }));
      setEditPrompt('');
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('itemDetail.editUnavailable'));
    } finally {
      setEditing(false);
    }
  };

  const onDelete = async () => {
    try {
      await api.deleteItem(id);
      toast.success(t('itemDetail.deleted'));
      nav('/closet');
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('closet.deleteFailed'));
    }
  };

  if (loading || !item || !form) {
    return (
      <div className="container-px max-w-5xl mx-auto pt-6">
        <div className="aspect-[3/4] w-full rounded-[calc(var(--radius)+6px)] shimmer" />
      </div>
    );
  }

  const hasReconstruction = !!item.reconstructed_image_url;
  const preferredImage =
    (!showingOriginal && item.reconstructed_image_url) ||
    item.segmented_image_url ||
    item.original_image_url;
  const reconstructionReasons =
    (item.reconstruction_metadata && item.reconstruction_metadata.reasons) || [];

  /* ========================= RENDER ========================= */
  return (
    <div className="container-px max-w-5xl mx-auto pt-4 md:pt-8 pb-24">
      {/* Top bar */}
      <div className="flex items-center justify-between gap-3 mb-4">
        <button
          onClick={() => nav(-1)}
          className="inline-flex items-center text-sm text-muted-foreground"
          data-testid="item-back"
        >
          <ArrowLeft className="h-4 w-4 me-1 rtl:rotate-180" /> {t('common.back')}
        </button>
        <div className="flex items-center gap-2">
          {isDirty && (
            <Badge
              variant="outline"
              className="rounded-full text-[10px] py-0 h-6"
              data-testid="item-edit-dirty-badge"
            >
              {t('itemDetail.edit.unsaved', { count: Object.keys(patch).length })}
            </Badge>
          )}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onDiscard}
            disabled={!isDirty || saving}
            data-testid="item-edit-discard-button"
          >
            <Undo2 className="h-4 w-4 me-1.5" /> {t('itemDetail.edit.discard')}
          </Button>
          <Button
            type="button"
            onClick={onSave}
            disabled={!isDirty || saving}
            size="sm"
            className="rounded-xl"
            data-testid="item-edit-save-button"
          >
            {saving ? (
              <><Loader2 className="h-4 w-4 animate-spin me-1.5" />{t('itemDetail.edit.saving')}</>
            ) : (
              <><Save className="h-4 w-4 me-1.5" />{t('itemDetail.edit.save')}</>
            )}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
        {/* ---------- Image column ---------- */}
        <div className="md:col-span-3 space-y-4">
          <Card className="rounded-[calc(var(--radius)+6px)] overflow-hidden shadow-editorial relative">
            <AspectRatio ratio={3 / 4} className="bg-secondary">
              {preferredImage ? (
                <img
                  src={preferredImage}
                  alt={form.title || item.title}
                  className="w-full h-full object-cover"
                  data-testid="item-detail-main-image"
                />
              ) : (
                <div
                  className="w-full h-full flex flex-col items-center justify-center gap-3 text-muted-foreground bg-gradient-to-br from-muted/50 to-muted/20 p-6 text-center"
                  data-testid="item-detail-no-image"
                >
                  {item.dpp_data ? (
                    <>
                      <QrCode className="h-10 w-10 text-[hsl(var(--accent))]/70" />
                      <div className="text-sm max-w-xs">
                        {t('itemDetail.photo.placeholderHint')}
                      </div>
                    </>
                  ) : (
                    <div className="text-sm">{t('itemDetail.noImage')}</div>
                  )}
                  <Button
                    type="button"
                    variant="default"
                    size="sm"
                    className="rounded-xl mt-1"
                    onClick={onPickPhoto}
                    disabled={uploadingPhoto}
                    data-testid="item-detail-add-photo-btn"
                  >
                    {uploadingPhoto ? (
                      <Loader2 className="h-4 w-4 me-2 animate-spin" />
                    ) : (
                      <Camera className="h-4 w-4 me-2" />
                    )}
                    {t('itemDetail.photo.addLabel')}
                  </Button>
                </div>
              )}
            </AspectRatio>
            {/* Replace photo button (subtle, shown only when an image exists) */}
            {preferredImage && (
              <button
                type="button"
                onClick={onPickPhoto}
                disabled={uploadingPhoto}
                className="absolute bottom-3 end-3 inline-flex items-center gap-1.5 rounded-full bg-background/90 backdrop-blur border border-border px-2.5 py-1 text-[11px] font-medium hover:bg-secondary transition-colors disabled:opacity-60"
                data-testid="item-detail-replace-photo-btn"
              >
                {uploadingPhoto ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Camera className="h-3 w-3" />
                )}
                {t('itemDetail.photo.replaceLabel')}
              </button>
            )}
            {/* Hidden file input for add/replace photo */}
            <input
              ref={photoInputRef}
              type="file"
              accept="image/*"
              className="sr-only"
              data-testid="item-detail-photo-input"
              onChange={onPhotoFileChosen}
            />
            {hasReconstruction && (
              <>
                <div
                  className="absolute top-3 start-3 inline-flex items-center gap-1.5 rounded-full bg-background/90 backdrop-blur border border-border px-2.5 py-1 text-[11px] font-semibold"
                  data-testid="item-detail-repaired-badge"
                >
                  <Wand2 className="h-3 w-3 text-[hsl(var(--accent))]" />
                  {showingOriginal
                    ? t('itemDetail.repair.showingOriginal')
                    : t('itemDetail.repair.showingRepaired')}
                </div>
                <button
                  type="button"
                  onClick={() => setShowingOriginal((s) => !s)}
                  className="absolute top-3 end-3 inline-flex items-center gap-1.5 rounded-full bg-background/90 backdrop-blur border border-border px-2.5 py-1 text-[11px] font-medium hover:bg-secondary transition-colors"
                  data-testid="item-detail-toggle-reconstruction"
                >
                  <RefreshCw className="h-3 w-3" />
                  {showingOriginal
                    ? t('itemDetail.repair.showRepaired')
                    : t('itemDetail.repair.showOriginal')}
                </button>
              </>
            )}
            <div className="absolute bottom-3 start-3 flex items-center gap-2">
              <SourceTagBadge source={item.source} />
              <Badge
                variant="outline"
                className="rounded-full text-[10px] bg-background/90 backdrop-blur"
              >
                {labelForCategory(form.category, t)}
              </Badge>
            </div>
          </Card>

          {/* Variant carousel (existing) */}
          {item.variants && item.variants.length > 0 && (
            <div>
              <div className="caps-label text-muted-foreground mb-2">
                {t('itemDetail.variants')}
              </div>
              <div className="flex gap-3 overflow-x-auto pb-2" data-testid="item-variant-carousel">
                {item.variants.map((v, i) => (
                  <a key={i} href={v.url} target="_blank" rel="noreferrer" className="flex-shrink-0 w-28">
                    <div className="aspect-[3/4] rounded-xl overflow-hidden border border-border">
                      <img src={v.url} alt={v.prompt} className="w-full h-full object-cover" />
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1 truncate">{v.prompt}</div>
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* DPP provenance panel (Phase V6) — shown when an item was imported via QR scan */}
          <DppPanel dppData={item.dpp_data} />

          {/* Clean background card (Phase V Fix 2) */}
          <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial" data-testid="item-clean-bg-card">
            <CardContent className="p-5 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="caps-label text-muted-foreground">
                  {t('itemDetail.cleanBackground.label')}
                </div>
              </div>
              <p className="text-sm text-muted-foreground">
                {t('itemDetail.cleanBackground.subtitle')}
              </p>
              <Button
                onClick={onRepair}
                disabled={repairing}
                className="w-full rounded-xl"
                data-testid="item-clean-bg-button"
              >
                {repairing ? (
                  <><Loader2 className="h-4 w-4 me-2 animate-spin" />{t('itemDetail.cleanBackground.running')}</>
                ) : (
                  <><Wand2 className="h-4 w-4 me-2" />{hasReconstruction ? t('itemDetail.cleanBackground.retryCta') : t('itemDetail.cleanBackground.cta')}</>
                )}
              </Button>
              {repairing && (
                <div className="space-y-2" data-testid="item-clean-bg-progress">
                  <Progress
                    value={repairProgress}
                    className="h-2 w-full"
                    data-testid="item-clean-bg-progress-bar"
                  />
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] text-muted-foreground italic">
                      {t('itemDetail.cleanBackground.progressHint')}
                    </p>
                    <span
                      className="text-[11px] tabular-nums text-muted-foreground"
                      data-testid="item-clean-bg-progress-pct"
                    >
                      {Math.round(repairProgress)}%
                    </span>
                  </div>
                </div>
              )}
              <p className="text-[10px] text-muted-foreground/80 italic">
                {t('itemDetail.cleanBackground.disclaimer')}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* ---------- Edit form column ---------- */}
        <div className="md:col-span-2 space-y-4" data-testid="item-edit-form">
          {/* Identity */}
          <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
            <CardContent className="p-5 space-y-3">
              <div className="caps-label text-muted-foreground">{t('itemDetail.edit.sectionIdentity')}</div>
              <Field label={t('itemDetail.edit.title')} htmlFor="f-title" required>
                <Input
                  id="f-title"
                  value={form.title}
                  onChange={(e) => setField('title', e.target.value)}
                  className="rounded-xl"
                  data-testid="item-edit-field-title"
                />
              </Field>
              <Field label={t('itemDetail.edit.name')} htmlFor="f-name">
                <Input
                  id="f-name"
                  value={form.name}
                  onChange={(e) => setField('name', e.target.value)}
                  className="rounded-xl"
                  data-testid="item-edit-field-name"
                />
              </Field>
              <Field label={t('itemDetail.edit.brand')} htmlFor="f-brand">
                <Input
                  id="f-brand"
                  value={form.brand}
                  onChange={(e) => setField('brand', e.target.value)}
                  className="rounded-xl"
                  data-testid="item-edit-field-brand"
                />
              </Field>
              <Field label={t('itemDetail.edit.caption')} htmlFor="f-caption">
                <Textarea
                  id="f-caption"
                  value={form.caption}
                  onChange={(e) => setField('caption', e.target.value)}
                  rows={2}
                  className="rounded-xl resize-none"
                  data-testid="item-edit-field-caption"
                />
              </Field>
            </CardContent>
          </Card>

          {/* Taxonomy */}
          <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
            <CardContent className="p-5 space-y-3">
              <div className="caps-label text-muted-foreground">{t('itemDetail.edit.sectionTaxonomy')}</div>
              <Field label={t('itemDetail.edit.category')}>
                <NullableSelect
                  value={form.category}
                  onChange={(v) => setField('category', v || 'Top')}
                  options={CATEGORY_OPTIONS}
                  placeholder={t('itemDetail.edit.category')}
                  testid="item-edit-field-category"
                  format={(o) => labelForCategory(o, t)}
                />
              </Field>
              <Field label={t('itemDetail.edit.subCategory')} htmlFor="f-sub">
                <Input
                  id="f-sub"
                  value={form.sub_category}
                  onChange={(e) => setField('sub_category', e.target.value)}
                  className="rounded-xl"
                  data-testid="item-edit-field-sub_category"
                />
                <LocalizedHint raw={form.sub_category} translated={labelForSubCategory(form.sub_category, t)} />
              </Field>
              <Field label={t('itemDetail.edit.itemType')} htmlFor="f-itemtype">
                <Input
                  id="f-itemtype"
                  value={form.item_type}
                  onChange={(e) => setField('item_type', e.target.value)}
                  className="rounded-xl"
                  data-testid="item-edit-field-item_type"
                />
                <LocalizedHint raw={form.item_type} translated={labelForItemType(form.item_type, t)} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label={t('itemDetail.edit.gender')}>
                  <NullableSelect
                    value={form.gender}
                    onChange={(v) => setField('gender', v)}
                    options={GENDER_OPTIONS}
                    placeholder="—"
                    testid="item-edit-field-gender"
                    format={(o) => labelForGender(o, t)}
                  />
                </Field>
                <Field label={t('itemDetail.edit.dressCode')}>
                  <NullableSelect
                    value={form.dress_code}
                    onChange={(v) => setField('dress_code', v)}
                    options={DRESS_CODE_OPTIONS}
                    placeholder="—"
                    testid="item-edit-field-dress_code"
                    format={(o) => labelForDressCode(o, t)}
                  />
                </Field>
              </div>
              <Field label={t('itemDetail.edit.season')}>
                <PillMultiSelect
                  value={form.season}
                  options={SEASON_OPTIONS}
                  onChange={(v) => setField('season', v)}
                  testidPrefix="item-edit-field-season"
                  format={(o) => labelForSeason(o, t)}
                />
              </Field>
              <Field label={t('itemDetail.edit.tradition')} htmlFor="f-tradition">
                <Input
                  id="f-tradition"
                  value={form.tradition}
                  onChange={(e) => setField('tradition', e.target.value)}
                  className="rounded-xl"
                  placeholder={t('itemDetail.edit.traditionPlaceholder')}
                  data-testid="item-edit-field-tradition"
                />
              </Field>
            </CardContent>
          </Card>

          {/* Composition */}
          <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
            <CardContent className="p-5 space-y-3">
              <div className="caps-label text-muted-foreground">{t('itemDetail.edit.sectionComposition')}</div>
              <div className="grid grid-cols-2 gap-3">
                <Field label={t('itemDetail.edit.size')} htmlFor="f-size">
                  <Input
                    id="f-size"
                    value={form.size}
                    onChange={(e) => setField('size', e.target.value)}
                    className="rounded-xl"
                    data-testid="item-edit-field-size"
                  />
                </Field>
                <Field label={t('itemDetail.edit.color')} htmlFor="f-color">
                  <Input
                    id="f-color"
                    value={form.color}
                    onChange={(e) => setField('color', e.target.value)}
                    className="rounded-xl"
                    data-testid="item-edit-field-color"
                  />
                </Field>
                <Field label={t('itemDetail.edit.material')} htmlFor="f-material">
                  <Input
                    id="f-material"
                    value={form.material}
                    onChange={(e) => setField('material', e.target.value)}
                    className="rounded-xl"
                    data-testid="item-edit-field-material"
                  />
                </Field>
                <Field label={t('itemDetail.edit.pattern')}>
                  <NullableSelect
                    value={form.pattern}
                    onChange={(v) => setField('pattern', v)}
                    options={PATTERN_OPTIONS}
                    placeholder="—"
                    testid="item-edit-field-pattern"
                    format={(o) => labelForPattern(o, t)}
                  />
                </Field>
              </div>
            </CardContent>
          </Card>

          {/* Quality */}
          <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
            <CardContent className="p-5 space-y-3">
              <div className="caps-label text-muted-foreground">{t('itemDetail.edit.sectionQuality')}</div>
              <div className="grid grid-cols-3 gap-3">
                <Field label={t('itemDetail.edit.state')}>
                  <NullableSelect
                    value={form.state}
                    onChange={(v) => setField('state', v)}
                    options={STATE_OPTIONS}
                    placeholder="—"
                    testid="item-edit-field-state"
                    format={(o) => labelForState(o, t)}
                  />
                </Field>
                <Field label={t('itemDetail.edit.condition')}>
                  <NullableSelect
                    value={form.condition}
                    onChange={(v) => setField('condition', v)}
                    options={CONDITION_OPTIONS}
                    placeholder="—"
                    testid="item-edit-field-condition"
                    format={(o) => labelForCondition(o, t)}
                  />
                </Field>
                <Field label={t('itemDetail.edit.qualityTier')}>
                  <NullableSelect
                    value={form.quality}
                    onChange={(v) => setField('quality', v)}
                    options={QUALITY_OPTIONS}
                    placeholder="—"
                    testid="item-edit-field-quality"
                    format={(o) => labelForQuality(o, t)}
                  />
                </Field>
              </div>
              <Field label={t('itemDetail.edit.repairAdvice')} htmlFor="f-repair">
                <Textarea
                  id="f-repair"
                  value={form.repair_advice}
                  onChange={(e) => setField('repair_advice', e.target.value)}
                  rows={2}
                  className="rounded-xl resize-none"
                  data-testid="item-edit-field-repair_advice"
                />
              </Field>
            </CardContent>
          </Card>

          {/* Pricing & intent */}
          <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
            <CardContent className="p-5 space-y-3">
              <div className="caps-label text-muted-foreground">{t('itemDetail.edit.sectionPricing')}</div>
              <div className="grid grid-cols-3 gap-3">
                <Field label={t('itemDetail.edit.priceCents')} htmlFor="f-price">
                  <Input
                    id="f-price"
                    type="number"
                    min="0"
                    step="1"
                    value={form.price_cents}
                    onChange={(e) => setField('price_cents', e.target.value)}
                    className="rounded-xl"
                    data-testid="item-edit-field-price_cents"
                  />
                </Field>
                <Field label={t('itemDetail.edit.currency')}>
                  <NullableSelect
                    value={form.currency}
                    onChange={(v) => setField('currency', v || 'USD')}
                    options={CURRENCY_OPTIONS}
                    placeholder="USD"
                    testid="item-edit-field-currency"
                  />
                </Field>
                <Field label={t('itemDetail.edit.intent')}>
                  <NullableSelect
                    value={form.marketplace_intent}
                    onChange={(v) => setField('marketplace_intent', v || 'own')}
                    options={INTENT_OPTIONS}
                    placeholder="own"
                    testid="item-edit-field-marketplace_intent"
                    format={(o) => labelForIntent(o, t)}
                  />
                </Field>
              </div>
            </CardContent>
          </Card>

          {/* Organization */}
          <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
            <CardContent className="p-5 space-y-3">
              <div className="caps-label text-muted-foreground">{t('itemDetail.edit.sectionOrganization')}</div>
              <Field label={t('itemDetail.edit.formality')}>
                <NullableSelect
                  value={form.formality}
                  onChange={(v) => setField('formality', v)}
                  options={FORMALITY_OPTIONS}
                  placeholder="—"
                  testid="item-edit-field-formality"
                  format={(o) => labelForFormality(o, t)}
                />
              </Field>
              <Field label={t('itemDetail.edit.tags')}>
                <ChipList
                  value={form.tags}
                  onChange={(v) => setField('tags', v)}
                  placeholder={t('itemDetail.edit.tagPlaceholder')}
                  testidPrefix="item-edit-field-tags"
                />
              </Field>
              <Field label={t('itemDetail.edit.culturalTags')}>
                <ChipList
                  value={form.cultural_tags}
                  onChange={(v) => setField('cultural_tags', v)}
                  placeholder={t('itemDetail.edit.culturalTagPlaceholder')}
                  testidPrefix="item-edit-field-cultural_tags"
                />
              </Field>
              <Field label={t('itemDetail.edit.notes')} htmlFor="f-notes">
                <Textarea
                  id="f-notes"
                  value={form.notes}
                  onChange={(e) => setField('notes', e.target.value)}
                  rows={3}
                  className="rounded-xl resize-none"
                  data-testid="item-edit-field-notes"
                />
              </Field>
            </CardContent>
          </Card>

          {/* Variant generator (existing) */}
          <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial" data-testid="item-edit-image-card">
            <CardContent className="p-5 space-y-3">
              <div className="caps-label text-muted-foreground">{t('itemDetail.generateVariant')}</div>
              <p className="text-sm text-muted-foreground">{t('itemDetail.generateVariantSub')}</p>
              <Input
                value={editPrompt}
                onChange={(e) => setEditPrompt(e.target.value)}
                placeholder={t('itemDetail.variantPlaceholder')}
                className="rounded-xl"
                data-testid="item-edit-prompt-input"
              />
              <Button onClick={onGenerateVariant} disabled={editing || !editPrompt.trim()} className="w-full rounded-xl" data-testid="item-generate-variant-button">
                {editing ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Sparkles className="h-4 w-4 me-2" />{t('itemDetail.generateVariant')}</>}
              </Button>
            </CardContent>
          </Card>

          {/* Bottom actions */}
          <div className="grid grid-cols-2 gap-3">
            <Button asChild variant="secondary" className="rounded-xl" data-testid="item-list-for-sale">
              <Link to={`/market/create?itemId=${item.id}`}>
                <Store className="h-4 w-4 me-2" />{t('itemDetail.listForSale')}
              </Link>
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" className="rounded-xl" data-testid="item-delete-button">
                  <Trash2 className="h-4 w-4 me-2" />{t('common.delete')}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t('itemDetail.removeTitle')}</AlertDialogTitle>
                  <AlertDialogDescription>{t('itemDetail.removeBody')}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                  <AlertDialogAction onClick={onDelete} data-testid="item-delete-confirm">
                    {t('common.delete')}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </div>

      {/* Sticky Save footer on mobile (form is long) */}
      {isDirty && (
        <div
          className="md:hidden fixed bottom-4 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 rounded-full bg-background/95 backdrop-blur border border-border shadow-lg px-3 py-2"
          data-testid="item-edit-sticky-save"
        >
          <CheckCircle2 className="h-4 w-4 text-[hsl(var(--accent))]" />
          <span className="text-xs text-muted-foreground">
            {t('itemDetail.edit.unsaved', { count: Object.keys(patch).length })}
          </span>
          <Button type="button" size="sm" onClick={onSave} disabled={saving} className="rounded-full h-8">
            {saving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <><Save className="h-3.5 w-3.5 me-1" />{t('itemDetail.edit.save')}</>
            )}
          </Button>
        </div>
      )}
    </div>
  );
}

/* -------------------- small field wrapper -------------------- */
function Field({ label, children, htmlFor, required }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={htmlFor} className="caps-label text-muted-foreground text-[10px]">
        {label}{required ? ' *' : ''}
      </Label>
      {children}
    </div>
  );
}
