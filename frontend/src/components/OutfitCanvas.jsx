/**
 * OutfitCanvas — Phase R Stylist Power-Up
 *
 * Renders the structured outfit response returned by
 * `POST /api/v1/stylist/compose-outfit`. Two display modes:
 *
 *   - `compact`: a single chat-bubble-friendly card with a horizontal
 *     row of selected slots and a "View full outfit" CTA. Used inline
 *     in Stylist.jsx message stream.
 *
 *   - `full`:    head-to-toe canvas with rejected panel, marketplace
 *     strip, and optional pro card. Used inside the modal that opens
 *     when the user taps the CTA, or on the dedicated /stylist/compose
 *     route.
 *
 * Designed to be model-agnostic — the UI consumes a stable schema so
 * swapping the backend brain (Gemma 4 fine-tune, Phase O) requires zero
 * frontend changes.
 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles, AlertTriangle, ShoppingBag, UserRound, X, ImageOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

const SLOT_LABELS = {
  top: 'Top',
  bottom: 'Bottom',
  dress: 'Dress',
  outerwear: 'Outerwear',
  shoes: 'Shoes',
  accessory: 'Accessory',
  bag: 'Bag',
  headwear: 'Headwear',
};

const REJECT_LABELS = {
  duplicate: 'Near-duplicate',
  wrong_category: 'Wrong category',
  color_clash: 'Color clash',
  wrong_formality: 'Off formality',
  wrong_season: 'Wrong season',
  off_brief: 'Off brief',
  low_quality: 'Image too low quality',
};

function formatPrice(cents, currency) {
  if (cents == null) return null;
  const symbol = currency === 'USD' ? '$' : currency === 'EUR' ? '€' : currency === 'ILS' ? '₪' : (currency || '');
  return `${symbol}${(cents / 100).toFixed(0)}`;
}

function CandidateImage({ src, alt, className }) {
  if (!src) {
    return (
      <div
        className={cn(
          'flex items-center justify-center bg-secondary text-muted-foreground',
          className,
        )}
      >
        <ImageOff className="h-5 w-5" />
      </div>
    );
  }
  return <img src={src} alt={alt || ''} loading="lazy" decoding="async" className={cn('object-cover', className)} />;
}

function SlotCard({ slot, candidate, onOpen }) {
  const label = SLOT_LABELS[slot.role] || slot.role;
  const empty = slot.is_gap || !candidate;
  return (
    <button
      type="button"
      onClick={onOpen}
      data-testid={`outfit-slot-${slot.role}`}
      className={cn(
        'group relative flex flex-col items-center gap-1 rounded-2xl p-2',
        'border border-border bg-card hover:border-[hsl(var(--accent))]/60',
        'transition-colors min-w-[96px] w-[96px] sm:w-[120px]',
      )}
    >
      <div
        className={cn(
          'relative w-full aspect-[3/4] rounded-xl overflow-hidden',
          empty ? 'border-2 border-dashed border-border bg-secondary/40' : '',
        )}
      >
        {empty ? (
          <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
            <span className="opacity-70">{label}</span>
          </div>
        ) : (
          <CandidateImage src={candidate.image_data_url} alt={candidate.title || label} className="h-full w-full" />
        )}
        {!empty && candidate.source === 'closet' && (
          <Badge variant="secondary" className="absolute top-1 left-1 text-[10px] px-1 py-0">closet</Badge>
        )}
        {empty && (
          <Badge variant="outline" className="absolute top-1 left-1 text-[10px] px-1 py-0 border-amber-500 text-amber-600 dark:text-amber-400">gap</Badge>
        )}
      </div>
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      {!empty && candidate.title && (
        <div className="text-xs leading-tight line-clamp-2 text-foreground/90 px-1">{candidate.title}</div>
      )}
    </button>
  );
}

function RejectedRow({ reject, candidate }) {
  if (!candidate) return null;
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-card/60 p-2" data-testid="outfit-rejected-row">
      <CandidateImage src={candidate.image_data_url} alt={candidate.title || ''} className="h-12 w-12 rounded-md flex-shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium truncate">{candidate.title || 'Garment'}</div>
        <div className="text-[11px] text-muted-foreground">
          <span className="text-amber-600 dark:text-amber-400">{REJECT_LABELS[reject.reason] || reject.reason}</span>
          {reject.detail && ` — ${reject.detail}`}
        </div>
      </div>
    </div>
  );
}

function MarketplaceCard({ s }) {
  return (
    <Link
      to={`/marketplace/${s.listing_id}`}
      className="block rounded-xl border border-border bg-card hover:border-[hsl(var(--accent))]/60 transition-colors min-w-[160px] w-[160px]"
      data-testid="outfit-marketplace-card"
    >
      <CandidateImage src={s.image_url} alt={s.title} className="w-full aspect-square rounded-t-xl" />
      <div className="p-2">
        <div className="text-xs font-medium line-clamp-2 leading-tight">{s.title}</div>
        <div className="mt-1 flex items-center justify-between">
          <span className="text-xs text-foreground/70">{formatPrice(s.price_cents, s.currency) || '—'}</span>
          {s.fills_slot && (
            <Badge variant="outline" className="text-[10px] px-1 py-0">{SLOT_LABELS[s.fills_slot] || s.fills_slot}</Badge>
          )}
        </div>
      </div>
    </Link>
  );
}

function ProfessionalCard({ pro }) {
  return (
    <div
      className="rounded-xl border border-[hsl(var(--accent))]/40 bg-[hsl(var(--accent))]/5 p-3 flex gap-3"
      data-testid="outfit-pro-card"
    >
      <div className="h-12 w-12 rounded-full overflow-hidden bg-secondary flex-shrink-0">
        {pro.avatar_url ? (
          <img src={pro.avatar_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center"><UserRound className="h-6 w-6 text-muted-foreground" /></div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold truncate">{pro.display_name}</div>
        <div className="text-xs text-muted-foreground">
          {[pro.profession, pro.location].filter(Boolean).join(' · ') || 'Fashion pro'}
        </div>
        <div className="text-xs mt-1 text-foreground/80">{pro.why_suggested}</div>
        <Link
          to={`/experts/${pro.professional_id}`}
          className="text-xs font-medium text-[hsl(var(--accent))] hover:underline mt-1 inline-block"
        >
          View profile →
        </Link>
      </div>
    </div>
  );
}

/** Compact in-chat preview. Tap to open the full canvas modal. */
export function OutfitCanvasPreview({ canvas, onExpand }) {
  const candidatesById = useMemo(() => {
    const map = {};
    (canvas.candidates || []).forEach((c) => { map[c.candidate_id] = c; });
    return map;
  }, [canvas.candidates]);

  const slots = canvas.slots || [];
  const filled = slots.filter((s) => !s.is_gap).length;
  const gaps = slots.length - filled;
  const market = canvas.marketplace_suggestions || [];

  return (
    <div className="rounded-2xl border border-border bg-card p-3 space-y-2" data-testid="outfit-canvas-preview">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-[hsl(var(--accent))]" />
        <span className="text-sm font-medium">{canvas.summary || 'Your outfit'}</span>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1" data-testid="outfit-slot-strip">
        {slots.map((slot, i) => (
          <SlotCard
            key={slot.role + i}
            slot={slot}
            candidate={slot.candidate_id ? candidatesById[slot.candidate_id] : null}
            onOpen={onExpand}
          />
        ))}
      </div>
      <div className="flex items-center justify-between gap-2 pt-1">
        <div className="text-xs text-muted-foreground">
          {filled} selected · {gaps > 0 && <span className="text-amber-600 dark:text-amber-400">{gaps} gap{gaps !== 1 ? 's' : ''}</span>}
          {market.length > 0 && <span className="ms-2">· {market.length} marketplace match{market.length !== 1 ? 'es' : ''}</span>}
        </div>
        <Button onClick={onExpand} size="sm" variant="secondary" data-testid="outfit-canvas-expand-btn">
          View full outfit
        </Button>
      </div>
    </div>
  );
}

/** Full canvas — used inside a modal or on /stylist/compose. */
export function OutfitCanvasFull({ canvas, onClose, embedded = false }) {
  const candidatesById = useMemo(() => {
    const map = {};
    (canvas.candidates || []).forEach((c) => { map[c.candidate_id] = c; });
    return map;
  }, [canvas.candidates]);

  const slots = canvas.slots || [];
  const rejected = canvas.rejected || [];
  const market = canvas.marketplace_suggestions || [];
  const pro = canvas.professional_suggestion;

  return (
    <div
      className={cn(
        'space-y-4',
        embedded ? '' : 'p-4 sm:p-6 overflow-y-auto',
      )}
      data-testid="outfit-canvas-full"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[hsl(var(--accent))]">
            <Sparkles className="h-4 w-4" />
            <span className="text-xs font-semibold uppercase tracking-wide">Outfit canvas</span>
          </div>
          <h2 className="text-lg font-semibold mt-1 leading-snug">{canvas.summary || 'Your outfit'}</h2>
          {canvas.brief && (
            <p className="text-xs text-muted-foreground mt-1">Brief: <span className="italic">{canvas.brief}</span></p>
          )}
        </div>
        {onClose && (
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close" data-testid="outfit-canvas-close">
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {canvas.detailed_rationale && (
        <p className="text-sm text-foreground/80 leading-relaxed">{canvas.detailed_rationale}</p>
      )}

      {/* Selected slots */}
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">The look</div>
        <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1">
          {slots.map((slot, i) => (
            <SlotCard
              key={slot.role + i}
              slot={slot}
              candidate={slot.candidate_id ? candidatesById[slot.candidate_id] : null}
              onOpen={() => {}}
            />
          ))}
        </div>
      </div>

      {/* Rejected */}
      {rejected.length > 0 && (
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            <AlertTriangle className="h-3.5 w-3.5" />
            Rejected ({rejected.length})
          </div>
          <div className="grid sm:grid-cols-2 gap-2">
            {rejected.map((r, i) => (
              <RejectedRow key={r.candidate_id + i} reject={r} candidate={candidatesById[r.candidate_id]} />
            ))}
          </div>
        </div>
      )}

      {/* Marketplace strip */}
      {market.length > 0 && (
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            <ShoppingBag className="h-3.5 w-3.5" />
            Marketplace matches ({market.length})
          </div>
          <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1">
            {market.map((s) => <MarketplaceCard key={s.listing_id} s={s} />)}
          </div>
        </div>
      )}

      {/* Professional referral */}
      {pro && (
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">A pro can help</div>
          <ProfessionalCard pro={pro} />
        </div>
      )}
    </div>
  );
}

/** Convenience wrapper: button + modal, all in one. */
export function OutfitCanvasMessage({ canvas }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <OutfitCanvasPreview canvas={canvas} onExpand={() => setOpen(true)} />
      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setOpen(false)}
          data-testid="outfit-canvas-modal"
        >
          <div
            className="bg-background border border-border rounded-2xl max-w-2xl w-full max-h-[88vh] overflow-y-auto shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <OutfitCanvasFull canvas={canvas} onClose={() => setOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
}
