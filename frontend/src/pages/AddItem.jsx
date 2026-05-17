/**
 * AddItem.jsx — Thin page shell for /closet/add (Phase U2, May 2026).
 *
 * ──────────────────────────────────────────────────────────────────
 *  This page is a UI shell ONLY. All upload/analyze/save plumbing
 *  lives in `frontend/src/lib/uploadItems.js` (the sealed
 *  "Upload-Items" routine). DO NOT re-implement pipeline logic
 *  here. Any future add-item workflow (single, camera, bulk,
 *  programmatic) MUST go through `uploadItems.start(files, opts)`.
 *  See the docstring at the top of `uploadItems.js` for the
 *  contract.
 * ──────────────────────────────────────────────────────────────────
 *
 * What this file owns:
 *   • file-picker / camera / dropzone UI
 *   • DPP QR scan integration (sessionStorage handoff + scanner)
 *   • the per-card review UI (photo + lightweight inline editor)
 *   • the duplicate dialogs (pre-flight + post-analyze)
 *   • navigation to /closet on batch settled
 *
 * What this file used to own (now in uploadItems.js):
 *   • fingerprinting + duplicate detection
 *   • NDJSON streaming analysis + per-card hydration
 *   • optimistic save + reconcile
 *   • workStore / closetStore wiring
 *   • the >5-photo aggregate progress UX (deleted — per-card now
 *     applies to any count, per Phase U design)
 *   • the full-field "Edit" editor (taxonomy/colour/season/tag pickers)
 *     — dropped per Phase U design; users edit those fields from
 *     /closet/:id after save.
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft, Upload, Plus, Loader2, Eye, Wand2, Shirt, Store,
  HandCoins, Gift, Repeat, Save, Tag, AlertTriangle,
  X, Sparkles, Camera, RefreshCw, QrCode,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { api } from '@/lib/api';
import { useUploadItems } from '@/lib/uploadItems';
import DuplicatePreflightDialog from '@/components/DuplicatePreflightDialog';
import { DppScanner } from '@/components/DppScanner';
import { useAuth } from '@/lib/auth';
import { labelForItemType, labelForIntent } from '@/lib/taxonomy';
import { toast } from 'sonner';

/* -------------------- constants -------------------- */

const INTENT_OPTIONS = [
  { value: 'own',      icon: Shirt,    tone: 'bg-slate-100 text-slate-900 border-slate-200' },
  { value: 'for_sale', icon: HandCoins, tone: 'bg-amber-100 text-amber-900 border-amber-200' },
  { value: 'donate',   icon: Gift,     tone: 'bg-emerald-100 text-emerald-900 border-emerald-200' },
  { value: 'swap',     icon: Repeat,   tone: 'bg-sky-100 text-sky-900 border-sky-200' },
];

const fmtCents = (cents, cur = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: cur || 'USD' }).format(
    (cents || 0) / 100,
  );

/* -------------------- page -------------------- */

export default function AddItem() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [scanOpen, setScanOpen] = useState(false);
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);

  // The sealed Upload-Items pipeline. ALL upload plumbing flows
  // through this hook — see /app/frontend/src/lib/uploadItems.js.
  const {
    cards,
    saving,
    pendingAutoSave,
    preflight,
    start,
    saveAll,
    removeCard,
    retryCard,
    updateField,
    patchCard,
    hydrateFromDpp,
    resolvePreflight,
    clearPreflight,
    acceptDuplicate,
    discardDuplicate,
  } = useUploadItems({
    user,
    onBatchSettled: (result) => {
      // Don't navigate if the batch ended with zero work done —
      // e.g. user discarded every duplicate in the pre-flight
      // dialog. Stay on /add so they can try again without a
      // jarring detour through the closet.
      if (!result || (result.saved?.length || 0) + (result.failed?.length || 0) === 0) {
        return;
      }
      // Fired by the pipeline when every card in the batch reached
      // a terminal state. Navigate to /closet so the user sees their
      // freshly-saved pieces; failures (if any) surface via the
      // closetStore failure dialog on /closet.
      nav('/closet');
    },
  });

  const pickFiles = () => fileInputRef.current?.click();
  const openCamera = () => cameraInputRef.current?.click();
  const openScanner = () => setScanOpen(true);

  // Hydrate from DPP scan (user hit "Scan QR" in TopNav, which
  // opens /closet/add?source=dpp with a draft in sessionStorage).
  useEffect(() => {
    if (searchParams.get('source') !== 'dpp') return;
    let raw = null;
    try {
      raw = sessionStorage.getItem('dpp_draft');
      sessionStorage.removeItem('dpp_draft');
    } catch (_) { /* ignore */ }
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

  const handleFiles = (fileList) => {
    // The pipeline handles fingerprinting, pre-flight duplicate
    // detection, and the count-agnostic per-card flow. Every count
    // (1, 5, 50) uses the same per-card review UI now.
    start(fileList, {
      mode: 'fire-and-forget',
      autoSave: false,
      autoResolveDuplicates: 'prompt', // dialog mounted below
    });
  };

  const saveDisabled =
    saving
    || pendingAutoSave
    || (
      !cards.some((c) => c.status === 'ready')
      && !cards.some((c) => c.status === 'scanning')
    );

  return (
    <div className="container-px max-w-6xl mx-auto pt-6 md:pt-10 pb-28" data-testid="add-item-page">
      {/* Sticky action bar */}
      <div
        className="sticky top-0 z-30 -mx-4 sm:-mx-6 px-4 sm:px-6 py-3 mb-6 bg-background/85 backdrop-blur-md border-b border-border/40 supports-[backdrop-filter]:bg-background/70"
        data-testid="add-item-action-bar"
      >
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => nav(-1)}
            className="rounded-full"
            data-testid="add-item-back"
          >
            <ArrowLeft className="h-4 w-4 me-2 rtl:rotate-180" /> {t('common.back')}
          </Button>
          <div className="flex-1" />
          <Button
            onClick={pickFiles}
            variant="outline"
            className="rounded-xl"
            data-testid="add-item-add-more"
          >
            <Plus className="h-4 w-4 me-2" /> {t('addItem.addPhotos')}
          </Button>
          <Button
            onClick={() => saveAll()}
            disabled={saveDisabled}
            className="rounded-xl"
            data-testid="add-item-save-all"
          >
            {(saving || pendingAutoSave)
              ? <Loader2 className="h-4 w-4 me-2 animate-spin" />
              : <Save className="h-4 w-4 me-2" />}
            {pendingAutoSave
              ? t('addItem.saveAllPending', { defaultValue: 'Saving — waiting for analysis…' })
              : t('addItem.saveAll')}
          </Button>
        </div>
      </div>

      {/* Title block */}
      <div className="mb-6">
        <div className="caps-label text-muted-foreground">{t('addItem.label')}</div>
        <h1 className="font-display text-3xl sm:text-4xl mt-1">{t('addItem.title')}</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-2xl">
          {t('addItem.subtitle')}
        </p>
      </div>

      {/* File inputs (hidden — triggered by buttons) */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        className="sr-only"
        data-testid="add-item-file-input"
        onChange={(e) => { handleFiles(e.target.files); e.target.value = ''; }}
      />
      {/* On mobile, capture="environment" opens the rear camera directly;
          on desktop, browsers fall back to a file picker so the button
          is safe to show everywhere. */}
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="sr-only"
        data-testid="add-item-camera-input"
        onChange={(e) => { handleFiles(e.target.files); e.target.value = ''; }}
      />

      {/* Pre-flight duplicate dialog (Phase Z3 — client-side detection
          against the cached closet snapshot). Wired to the sealed
          pipeline's `resolvePreflight` / `clearPreflight`. */}
      <DuplicatePreflightDialog
        open={!!preflight}
        matches={preflight?.matches || []}
        onResolve={(decisions) => {
          if (preflight) resolvePreflight(decisions);
          else clearPreflight();
        }}
      />

      {/* Post-analysis duplicate-confirm dialog. Pops one card at a
          time when the analyzer flagged a potential match in the closet. */}
      <DuplicateConfirmDialog
        cards={cards}
        onCancel={discardDuplicate}
        onConfirm={acceptDuplicate}
      />

      {/* Empty-state dropzone vs card grid */}
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
                onRetry={() => retryCard(card.id)}
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

/* -------------------- item card (lightweight) -------------------- */
/**
 * Per-card review UI. Phase U2 stripped the full-field "Edit"
 * editor (TaxonomyGrid / WeightedList / QualityRow / SeasonPicker /
 * TagsEditor) — those fields are still saved (from the analyzer),
 * but the user edits them post-save from /closet/:id. The on-card
 * inputs are now restricted to the lightweight identity & intent
 * controls: name + caption + marketplace intent (+ price when
 * intent === 'for_sale').
 */
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

          {/* Lightweight inline editor — Phase U2:
              name + caption + marketplace intent + price (if for_sale). */}
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
            <p className="text-[11px] text-muted-foreground/80" data-testid="add-item-edit-later-hint">
              {t('addItem.editFullDetailsLater', {
                defaultValue: 'Category, colour, size and more — fine-tune anytime from the item page.',
              })}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/* -------------------- inline sub-sections -------------------- */

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
        {intent === 'own' && (
          <Badge variant="outline" className="text-[10px]">
            {t('addItem.intent_own')}
          </Badge>
        )}
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
            <Label className="caps-label text-muted-foreground">
              {t('addItem.price')} ({fields.currency || 'USD'})
            </Label>
            <Input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              autoComplete="off"
              value={
                fields.price_cents != null && fields.price_cents !== ''
                  ? String(Math.round(Number(fields.price_cents) / 100))
                  : '0'
              }
              onChange={(e) => {
                const raw = e.target.value;
                if (raw && !/^\d*$/.test(raw)) return;
                const units = raw === '' ? 0 : Math.max(0, parseInt(raw, 10) || 0);
                onChange({ price_cents: units * 100 });
              }}
              placeholder="0"
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

/* -------------------- DuplicateConfirmDialog --------------------
 * Surfaces a confirm dialog the moment ``analyze`` returns a card
 * whose matched garment already exists in the user's closet. Pops
 * one card at a time. (Kept inline in this file for Phase U2;
 * scheduled to move to its own component in U3.)
 */
function DuplicateConfirmDialog({ cards, onCancel, onConfirm }) {
  const { t } = useTranslation();
  const active = cards.find(
    (c) => c.potentialDuplicate && !c.duplicateConfirmed,
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
