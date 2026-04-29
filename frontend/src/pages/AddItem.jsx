import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft, Upload, Plus, Loader2, Eye, Wand2, Shirt, Store,
  HandCoins, Gift, Repeat, Trash2, Save, Tag, AlertTriangle,
  X, Sparkles, Camera, RefreshCw, QrCode,
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
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { api } from '@/lib/api';
import { DppScanner } from '@/components/DppScanner';
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
  const [searchParams, setSearchParams] = useSearchParams();
  const [cards, setCards] = useState([]); // [{id,file,previewUrl,base64,status,progress,fields,error,dppData?}]
  const [saving, setSaving] = useState(false);
  const [scanOpen, setScanOpen] = useState(false);
  // Background batch state — shown instead of cards when user uploads
  // more than BG_THRESHOLD photos at once. Auto-analyzes + auto-saves
  // each item with sane defaults; user is told to fix any misfits in
  // /closet afterwards.
  const [bgBatch, setBgBatch] = useState(null);
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);

  const pickFiles = () => fileInputRef.current?.click();
  const openCamera = () => cameraInputRef.current?.click();
  const openScanner = () => setScanOpen(true);

  // Hydrate from a DPP scan (e.g. user hit "Scan QR" in TopNav → we're
  // now opening AddItem with ?source=dpp and a draft in sessionStorage).
  useEffect(() => {
    if (searchParams.get('source') !== 'dpp') return;
    let raw = null;
    try {
      raw = sessionStorage.getItem('dpp_draft');
      sessionStorage.removeItem('dpp_draft');
    } catch (_) { /* ignore */ }
    // Always clear the query string so a browser refresh doesn't replay.
    searchParams.delete('source');
    setSearchParams(searchParams, { replace: true });
    if (!raw) return;
    let parsed = null;
    try { parsed = JSON.parse(raw); } catch (_) { return; }
    const res = parsed?.payload;
    if (!res) return;
    hydrateFromDpp(res);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hydrateFromDpp = (res) => {
    const items = res?.items || [];
    const first = items[0] || {};
    const analysis = first.analysis || {};
    const dppData = first.dpp_data || null;
    const hasImage = !!first.crop_base64;
    const mime = first.crop_mime || 'image/png';
    const previewUrl = hasImage
      ? `data:${mime};base64,${first.crop_base64}`
      : null;
    const draft = {
      id: `dpp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      file: null,
      mime: hasImage ? mime : null,
      previewUrl,
      base64: hasImage ? first.crop_base64 : null,
      status: 'ready',
      progress: 100,
      fields: hydrate(analysis),
      error: null,
      label: first.label || analysis.item_type || null,
      dppData,
      source: 'dpp',
    };
    setCards((prev) => [draft, ...prev]);
    toast.success(t('dpp.scanner.imported'));
  };

  const handleScanDecoded = async (payload) => {
    setScanOpen(false);
    if (!payload) return;
    const loadingId = toast.loading(t('dpp.scanner.importing'));
    try {
      const res = await api.importDpp(payload);
      toast.dismiss(loadingId);
      if (res?.parse_error) {
        toast.error(
          t(`dpp.scanner.errors.${res.parse_error}`, {
            defaultValue: t('dpp.scanner.noData'),
          }),
        );
        return;
      }
      hydrateFromDpp(res);
    } catch (err) {
      toast.dismiss(loadingId);
      toast.error(err?.response?.data?.detail || t('dpp.scanner.importFailed'));
    }
  };

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    // For large batches, skip the per-card editor and let the user fix
    // any misfits later from /closet. Threshold kept at 5 — anything
    // above is clearly a "dump my whole wardrobe" moment.
    const BG_THRESHOLD = 5;
    if (files.length > BG_THRESHOLD) {
      return handleBatchBackground(files);
    }
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

  // ------------------------------------------------------------------
  // Background batch upload (>5 photos): analyze + auto-save each one
  // with whatever the analyzer returns, with bounded concurrency. The
  // user gets a single progress card, then lands on /closet to clean up.
  // ------------------------------------------------------------------
  const handleBatchBackground = async (files) => {
    setBgBatch({ total: files.length, processed: 0, saved: 0, failed: 0 });
    toast.success(
      t('addItem.bgUpload.started', {
        count: files.length,
        defaultValue: `Uploading ${files.length} photos in the background…`,
      })
    );

    const CONCURRENCY = 3;
    const queue = [...files];

    const processOne = async (file) => {
      let createdHere = 0;
      let failedHere = 0;
      let b64 = null;
      try {
        b64 = await fileToBase64(file);
      } catch (_) {
        failedHere += 1;
        setBgBatch((b) => (b ? { ...b, processed: b.processed + 1, failed: b.failed + failedHere } : null));
        return;
      }

      // Try analysis; on failure, fall back to saving the raw image
      // with blank fields so the user still gets the item in /closet.
      let analysisItems = null;
      try {
        const resp = await api.analyzeItemImage({ image_base64: b64 });
        analysisItems =
          Array.isArray(resp?.items) && resp.items.length > 0
            ? resp.items
            : [{ analysis: resp, crop_base64: b64, crop_mime: file.type || 'image/jpeg' }];
      } catch (_) {
        analysisItems = [
          { analysis: {}, crop_base64: b64, crop_mime: file.type || 'image/jpeg' },
        ];
      }

      for (const it of analysisItems) {
        const cardLike = {
          base64: it.crop_base64 || b64,
          mime: it.crop_mime || file.type || 'image/jpeg',
          file: null,
          fields: hydrate(it.analysis || {}),
          useReconstructed: false,
        };
        try {
          await api.createItem(buildCreatePayload(cardLike));
          createdHere += 1;
        } catch (_) {
          failedHere += 1;
        }
      }

      setBgBatch((b) =>
        b
          ? {
              ...b,
              processed: b.processed + 1,
              saved: b.saved + createdHere,
              failed: b.failed + failedHere,
            }
          : null
      );
    };

    const workers = Array.from({ length: Math.min(CONCURRENCY, queue.length) }, async () => {
      while (queue.length) {
        const next = queue.shift();
        if (next) await processOne(next);
      }
    });
    await Promise.all(workers);

    // Read final counts from state via functional update so we don't
    // race with React batching.
    setBgBatch((b) => {
      const saved = b?.saved ?? 0;
      const failed = b?.failed ?? 0;
      if (saved && !failed) {
        toast.success(
          t('addItem.bgUpload.done', {
            count: saved,
            defaultValue: `Saved ${saved} items. Edit any misfits in your closet.`,
          })
        );
      } else if (saved && failed) {
        toast.message(
          t('addItem.bgUpload.partial', {
            saved,
            failed,
            defaultValue: `Saved ${saved} · ${failed} failed`,
          })
        );
      } else {
        toast.error(
          t('addItem.bgUpload.failed', {
            defaultValue: 'Could not save any items. Please try again.',
          })
        );
      }
      // Brief pause so the user sees the final 100% before navigating.
      setTimeout(() => {
        if (saved) nav('/closet');
      }, 1200);
      return null;
    });
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
        // Single-item photo — replace the original upload with the
        // analyzer's matted crop so the saved image is the clean PNG
        // cutout (background already removed by rembg server-side).
        // Without this swap the closet would persist the raw JPEG and
        // the user would have to click "Clean background" manually
        // every time, even though the backend already produced the
        // cutout. Reconstruction (Nano Banana) takes priority when
        // validated; otherwise the rembg-matted crop is used.
        const it = items[0];
        const mime = it.crop_mime || 'image/jpeg';
        const rec = it.reconstruction;
        const recValidated = !!(rec && rec.validated && rec.image_b64);
        const cropDataUrl = it.crop_base64
          ? `data:${mime};base64,${it.crop_base64}`
          : null;
        const previewUrl = recValidated
          ? `data:${rec.mime_type || 'image/png'};base64,${rec.image_b64}`
          : cropDataUrl;
        setCards((prev) =>
          prev.map((c) =>
            c.id === card.id
              ? {
                  ...c,
                  status: 'ready',
                  progress: 100,
                  fields: hydrate(it.analysis || {}),
                  label: it.label || null,
                  potentialDuplicate: it.potential_duplicate || null,
                  // Keep the original card.base64 untouched only if the
                  // analyzer didn't return a usable crop (legacy fallback).
                  ...(cropDataUrl
                    ? {
                        mime,
                        previewUrl,
                        base64: it.crop_base64,
                        originalCropUrl: cropDataUrl,
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
                      }
                    : {}),
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
          potentialDuplicate: it.potential_duplicate || null,
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
      <div
        className="sticky top-0 z-30 -mx-4 sm:-mx-6 px-4 sm:px-6 py-3 mb-6 bg-background/85 backdrop-blur-md border-b border-border/40 supports-[backdrop-filter]:bg-background/70"
        data-testid="add-item-action-bar"
      >
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => nav(-1)} className="rounded-full" data-testid="add-item-back">
            <ArrowLeft className="h-4 w-4 me-2 rtl:rotate-180" /> {t('common.back')}
          </Button>
          <div className="flex-1" />
          <Button onClick={pickFiles} variant="outline" className="rounded-xl" disabled={!!bgBatch} data-testid="add-item-add-more">
            <Plus className="h-4 w-4 me-2" /> {t('addItem.addPhotos')}
          </Button>
          <Button
            onClick={saveAll}
            disabled={saving || !!bgBatch || !cards.some((c) => c.status === 'ready')}
            className="rounded-xl"
            data-testid="add-item-save-all"
          >
            {saving ? <Loader2 className="h-4 w-4 me-2 animate-spin" /> : <Save className="h-4 w-4 me-2" />}
            {t('addItem.saveAll')}
          </Button>
        </div>
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

      {/* Duplicate-detection modal. We pop one card at a time — the
          first card with an unconfirmed potentialDuplicate becomes the
          active question. "Cancel" discards that card; "Add anyway"
          stamps it as confirmed and moves on. */}
      <DuplicateConfirmDialog
        cards={cards}
        onCancel={(cardId) => {
          setCards((prev) => {
            const removed = prev.find((c) => c.id === cardId);
            if (removed?.previewUrl?.startsWith('blob:')) URL.revokeObjectURL(removed.previewUrl);
            return prev.filter((c) => c.id !== cardId);
          });
        }}
        onConfirm={(cardId) => {
          setCards((prev) =>
            prev.map((c) =>
              c.id === cardId ? { ...c, duplicateConfirmed: true } : c
            )
          );
        }}
      />

      {bgBatch ? (
        <div
          className="w-full border border-border rounded-[calc(var(--radius)+10px)] p-8 sm:p-10 bg-card flex flex-col items-center text-center"
          data-testid="add-item-bg-batch-card"
          aria-live="polite"
        >
          <div className="h-14 w-14 rounded-full bg-secondary flex items-center justify-center mb-3">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
          <div className="font-display text-xl">
            {t('addItem.bgUpload.processingTitle', { defaultValue: 'Processing your photos…' })}
          </div>
          <div className="text-sm text-muted-foreground mt-1 max-w-md">
            {t('addItem.bgUpload.processingBody', {
              defaultValue: 'You can leave this page — we’ll keep going in the background. Edit any misfits in your closet when we’re done.',
            })}
          </div>
          <div className="mt-5 w-full max-w-md">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span data-testid="bg-batch-counter">
                {bgBatch.processed} / {bgBatch.total}
              </span>
              <span>
                {t('addItem.bgUpload.savedFailed', {
                  saved: bgBatch.saved,
                  failed: bgBatch.failed,
                  defaultValue: `saved ${bgBatch.saved} · failed ${bgBatch.failed}`,
                })}
              </span>
            </div>
            <Progress
              value={bgBatch.total ? (bgBatch.processed / bgBatch.total) * 100 : 0}
              className="h-2"
              data-testid="bg-batch-progress"
            />
          </div>
        </div>
      ) : cards.length === 0 ? (
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
            <Button
              type="button"
              variant="secondary"
              className="rounded-xl"
              onClick={openScanner}
              data-testid="add-item-scan-dpp-button"
            >
              <QrCode className="h-4 w-4 me-2" /> {t('dpp.nav.scanLabel')}
            </Button>
          </div>
          <div className="mt-4 flex items-center justify-center">
            <div className="text-xs text-muted-foreground flex items-center gap-2 max-w-md">
              <Badge variant="outline" className="border-[hsl(var(--accent))] text-[hsl(var(--accent))]">
                {t('dpp.addItem.tileBadge')}
              </Badge>
              <span>{t('dpp.addItem.tileSubtitle')}</span>
            </div>
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
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="rounded-lg"
              onClick={openScanner}
              data-testid="add-item-scan-dpp-more-button"
            >
              <QrCode className="h-4 w-4 me-1.5" /> {t('dpp.nav.scanLabel')}
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
      <DppScanner
        open={scanOpen}
        onOpenChange={setScanOpen}
        onDecoded={handleScanDecoded}
      />
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
    image_base64: asBase64 || undefined,
    image_mime: asBase64 ? (card.mime || card.file?.type || 'image/jpeg') : undefined,
    // Phase Q: forward the reconstructed image when the user kept it
    reconstructed_image_b64: card.useReconstructed && card.reconstructedB64
      ? card.reconstructedB64
      : undefined,
    reconstruction_metadata: card.useReconstructed && card.reconstructionMeta
      ? card.reconstructionMeta
      : undefined,
    // Phase V6: preserve DPP provenance imported via QR scan.
    dpp_data: card.dppData || undefined,
  };
  // Strip undefined to keep payload clean (Pydantic `extra=forbid` still accepts unset fields).
  return Object.fromEntries(Object.entries(body).filter(([, v]) => v !== undefined));
}


/* -------------------- DuplicateConfirmDialog -------------------- */
/**
 * Surfaces a confirm dialog the moment ``analyze`` returns a card whose
 * matched garment already exists in the user's closet. Pops one card at
 * a time — the first card in the list with an unconfirmed
 * ``potentialDuplicate`` becomes the active question. This avoids a
 * stack of overlays when the user uploads a batch of dupes.
 *
 * Pure UI — all state lives on the cards array passed in. Parent owns
 * the cancel/confirm handlers (which mutate ``cards`` to either remove
 * the offending entry or stamp it ``duplicateConfirmed: true``).
 */
function DuplicateConfirmDialog({ cards, onCancel, onConfirm }) {
  const { t } = useTranslation();
  const active = cards.find(
    (c) => c.potentialDuplicate && !c.duplicateConfirmed
  );
  const open = !!active;
  const dup = active?.potentialDuplicate;
  const newTitle =
    active?.fields?.title ||
    active?.fields?.name ||
    active?.fields?.item_type ||
    t('addItem.duplicate.thisItem', { defaultValue: 'this item' });
  const existingTitle =
    dup?.title ||
    dup?.name ||
    dup?.item_type ||
    t('addItem.duplicate.thisItem', { defaultValue: 'this item' });

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        // Treat a backdrop-click / ESC the same as Cancel — discard the
        // upload to keep behaviour predictable.
        if (!o && active) onCancel(active.id);
      }}
    >
      <DialogContent
        className="sm:max-w-md rounded-[calc(var(--radius)+4px)]"
        data-testid="duplicate-confirm-dialog"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-xl">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            {t('addItem.duplicate.title', {
              defaultValue: 'Already in your closet',
            })}
          </DialogTitle>
          <DialogDescription className="text-sm leading-relaxed">
            {t('addItem.duplicate.body', {
              defaultValue:
                'It looks like “{{existing}}” is already in your closet. Do you want to add this new “{{incoming}}” as a duplicate?',
              existing: existingTitle,
              incoming: newTitle,
            })}
          </DialogDescription>
        </DialogHeader>

        {/* Side-by-side preview helps the user confirm visually that
            it's actually the same garment vs a similar-looking one. */}
        <div className="flex items-center gap-3 my-2">
          {dup?.thumbnail_data_url ? (
            <div className="flex-1 flex flex-col items-center gap-1">
              <img
                src={dup.thumbnail_data_url}
                alt={existingTitle}
                className="h-28 w-28 object-contain rounded-lg border border-border bg-secondary/30"
                data-testid="duplicate-existing-thumb"
              />
              <span className="caps-label text-muted-foreground">
                {t('addItem.duplicate.existing', { defaultValue: 'Existing' })}
              </span>
            </div>
          ) : null}
          {active?.previewUrl ? (
            <div className="flex-1 flex flex-col items-center gap-1">
              <img
                src={active.previewUrl}
                alt={newTitle}
                className="h-28 w-28 object-contain rounded-lg border border-border bg-secondary/30"
                data-testid="duplicate-incoming-thumb"
              />
              <span className="caps-label text-muted-foreground">
                {t('addItem.duplicate.incoming', { defaultValue: 'New upload' })}
              </span>
            </div>
          ) : null}
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            type="button"
            variant="outline"
            className="rounded-xl"
            onClick={() => active && onCancel(active.id)}
            data-testid="duplicate-cancel-button"
          >
            <X className="h-4 w-4 me-2" />
            {t('addItem.duplicate.cancel', { defaultValue: 'Discard upload' })}
          </Button>
          <Button
            type="button"
            className="rounded-xl"
            onClick={() => active && onConfirm(active.id)}
            data-testid="duplicate-confirm-button"
          >
            <Plus className="h-4 w-4 me-2" />
            {t('addItem.duplicate.confirm', { defaultValue: 'Add anyway' })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
