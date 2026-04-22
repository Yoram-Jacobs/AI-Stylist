import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Sparkles,
  ShoppingBag,
  X,
  Loader2,
  ExternalLink,
  Volume2,
  VolumeX,
  CloudSun,
  ArrowUp,
  ArrowDown,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';
import { isTTSSupported, speak, cancelSpeak } from '@/lib/speech';

/**
 * Outfit Completion bottom sheet.
 *
 * Given 1..N anchor items selected in the closet, fetches complementary
 * pieces (ranked by FashionCLIP similarity + category diversity) and
 * renders them alongside a Stylist-generated rationale. Optionally
 * extends the search to active marketplace listings.
 */
function ItemThumb({ item, showScore = false, scoreLabel = null, linkTo = null }) {
  const src = item?.original_image_url || item?.segmented_image_url || null;
  const title = item?.title || item?.name || item?.category || 'Item';
  const cat = item?.category;
  const inner = (
    <div className="group">
      <div className="aspect-square rounded-xl overflow-hidden bg-secondary border border-border relative">
        {src ? (
          <img
            src={src}
            alt={title}
            className="h-full w-full object-cover transition-transform group-hover:scale-105"
          />
        ) : (
          <div className="h-full w-full flex items-center justify-center text-muted-foreground text-xs">
            {cat || '—'}
          </div>
        )}
        {showScore && scoreLabel != null && (
          <Badge
            variant="secondary"
            className="absolute top-2 end-2 text-[10px] bg-background/90 backdrop-blur"
          >
            {scoreLabel}
          </Badge>
        )}
      </div>
      <div className="mt-1.5 text-xs font-medium truncate">{title}</div>
      {cat && <div className="text-[10px] caps-label text-muted-foreground">{cat}</div>}
    </div>
  );
  if (linkTo) {
    return (
      <Link to={linkTo} className="block">
        {inner}
      </Link>
    );
  }
  return inner;
}

export function OutfitCompletionSheet({ open, onOpenChange, anchorIds = [], anchorsHint = [] }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [includeMarketplace, setIncludeMarketplace] = useState(false);
  const [occasion, setOccasion] = useState('');
  const [speaking, setSpeaking] = useState(false);
  // Order-aware anchor list (1st = highest centroid weight server-side).
  // Seeded from anchorsHint each time the sheet opens so the user can
  // reshuffle priority without leaving Closet.
  const [orderedAnchors, setOrderedAnchors] = useState([]);

  const ttsSupported = isTTSSupported();
  const userLang = user?.preferred_language || 'en';

  // Re-seed the order every time the caller passes a new anchor set.
  // We key off the joined ids so drifting React re-renders don't wipe
  // the user's manual reorder while the sheet stays open.
  useEffect(() => {
    if (!open) return;
    const hintIds = anchorsHint.map((a) => a.id).join('|');
    const currentIds = orderedAnchors.map((a) => a.id).join('|');
    if (hintIds !== currentIds) {
      setOrderedAnchors(anchorsHint);
      setResult(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, anchorsHint]);

  const moveAnchor = (idx, dir) => {
    setOrderedAnchors((prev) => {
      const next = [...prev];
      const target = idx + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[idx], next[target]] = [next[target], next[idx]];
      return next;
    });
  };

  const runCompletion = async () => {
    const ids = (orderedAnchors.length ? orderedAnchors.map((a) => a.id) : anchorIds);
    if (!ids.length) return;
    setLoading(true);
    setResult(null);
    try {
      const data = await api.completeOutfit({
        itemIds: ids,
        includeMarketplace,
        occasion: occasion.trim() || null,
        limit: 6,
      });
      setResult(data);
      if (!data.rationale && !data.closet_suggestions?.length && !data.market_suggestions?.length) {
        toast.message(t('outfitCompletion.empty'));
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('outfitCompletion.error'));
    } finally {
      setLoading(false);
    }
  };

  const toggleSpeak = () => {
    if (!ttsSupported || !result) return;
    const textToSpeak = result.spoken_reply || result.rationale;
    if (!textToSpeak) return;
    if (speaking) {
      cancelSpeak();
      setSpeaking(false);
      return;
    }
    setSpeaking(true);
    speak(textToSpeak, userLang, {
      onEnd: () => setSpeaking(false),
      onError: () => setSpeaking(false),
    });
  };

  const handleOpenChange = (next) => {
    if (!next) {
      cancelSpeak();
      setSpeaking(false);
    }
    onOpenChange?.(next);
  };

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-xl lg:max-w-2xl overflow-hidden p-0 flex flex-col"
        data-testid="outfit-completion-sheet"
      >
        <SheetHeader className="p-5 border-b border-border">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-[hsl(var(--accent))]" />
            <SheetTitle className="font-display text-2xl">
              {t('outfitCompletion.title')}
            </SheetTitle>
          </div>
          <SheetDescription>
            {t('outfitCompletion.subtitle', { count: anchorIds.length })}
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1">
          <div className="p-5 space-y-5">
            {/* Anchors preview (order-aware — first anchor has highest weight) */}
            {orderedAnchors.length > 0 && (
              <div>
                <div className="flex items-baseline justify-between mb-2">
                  <div className="caps-label text-muted-foreground">
                    {t('outfitCompletion.anchorsLabel')}
                  </div>
                  {orderedAnchors.length > 1 && (
                    <div className="caps-label text-[10px] text-muted-foreground">
                      {t('outfitCompletion.priorityHint')}
                    </div>
                  )}
                </div>
                <div
                  className="grid grid-cols-3 sm:grid-cols-4 gap-3"
                  data-testid="outfit-completion-anchor-grid"
                >
                  {orderedAnchors.map((a, idx) => (
                    <div key={a.id} className="relative">
                      <ItemThumb item={a} />
                      {/* Priority pill */}
                      <div
                        className="absolute top-2 start-2 h-5 min-w-[20px] px-1.5 rounded-full bg-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))] text-[10px] font-semibold flex items-center justify-center"
                        aria-label={t('outfitCompletion.priorityLabel', { n: idx + 1 })}
                        data-testid={`outfit-completion-anchor-priority-${idx}`}
                      >
                        {idx + 1}
                      </div>
                      {/* Reorder controls (only when >1 anchors) */}
                      {orderedAnchors.length > 1 && (
                        <div className="absolute top-2 end-2 flex flex-col gap-1">
                          <button
                            type="button"
                            onClick={() => moveAnchor(idx, -1)}
                            disabled={idx === 0}
                            aria-label={t('outfitCompletion.moveUp')}
                            data-testid={`outfit-completion-anchor-up-${idx}`}
                            className="h-6 w-6 rounded-full bg-background/90 border border-border backdrop-blur flex items-center justify-center disabled:opacity-40 hover:bg-secondary transition-colors"
                          >
                            <ArrowUp className="h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            onClick={() => moveAnchor(idx, 1)}
                            disabled={idx === orderedAnchors.length - 1}
                            aria-label={t('outfitCompletion.moveDown')}
                            data-testid={`outfit-completion-anchor-down-${idx}`}
                            className="h-6 w-6 rounded-full bg-background/90 border border-border backdrop-blur flex items-center justify-center disabled:opacity-40 hover:bg-secondary transition-colors"
                          >
                            <ArrowDown className="h-3 w-3" />
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Controls */}
            <div className="rounded-2xl border border-border bg-secondary/40 p-4 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <label
                  htmlFor="oc-marketplace"
                  className="text-sm inline-flex items-center gap-2 cursor-pointer"
                >
                  <ShoppingBag className="h-4 w-4" />
                  {t('outfitCompletion.includeMarketplace')}
                </label>
                <Switch
                  id="oc-marketplace"
                  checked={includeMarketplace}
                  onCheckedChange={setIncludeMarketplace}
                  data-testid="outfit-completion-marketplace-switch"
                />
              </div>
              <Input
                value={occasion}
                onChange={(e) => setOccasion(e.target.value)}
                placeholder={t('outfitCompletion.occasionPlaceholder')}
                className="rounded-xl"
                data-testid="outfit-completion-occasion-input"
              />
              <Button
                onClick={runCompletion}
                disabled={loading || anchorIds.length === 0}
                className="w-full rounded-xl"
                data-testid="outfit-completion-run-button"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 me-2 animate-spin" />
                    {t('outfitCompletion.thinking')}
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 me-2" />
                    {t('outfitCompletion.cta')}
                  </>
                )}
              </Button>
            </div>

            {loading && (
              <div className="space-y-3" data-testid="outfit-completion-loading">
                <div className="h-4 rounded shimmer w-3/4" />
                <div className="h-4 rounded shimmer w-1/2" />
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="aspect-square rounded-xl shimmer" />
                  ))}
                </div>
              </div>
            )}

            {result && !loading && (
              <div className="space-y-5" data-testid="outfit-completion-result">
                {result.weather_summary && (
                  <div
                    className="inline-flex items-center gap-2 rounded-full border border-border bg-secondary/60 px-3 py-1.5 text-xs"
                    data-testid="outfit-completion-weather-badge"
                  >
                    <CloudSun className="h-3.5 w-3.5 text-[hsl(var(--accent))]" />
                    <span className="caps-label text-muted-foreground">
                      {t('stylist.weatherAware')}
                    </span>
                    <span className="font-medium">{result.weather_summary}</span>
                  </div>
                )}
                {/* Rationale */}
                {result.rationale && (
                  <div className="rounded-2xl border border-border bg-card p-4">
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="caps-label text-[hsl(var(--accent))]">
                        {t('outfitCompletion.rationaleLabel')}
                      </div>
                      {ttsSupported && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={toggleSpeak}
                          className="h-7 rounded-full"
                          data-testid="outfit-completion-speak-button"
                          aria-label={
                            speaking ? t('stylist.stopSpeaking') : t('stylist.playReply')
                          }
                        >
                          {speaking ? (
                            <VolumeX className="h-3.5 w-3.5" />
                          ) : (
                            <Volume2 className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      )}
                    </div>
                    <p className="text-sm whitespace-pre-wrap">{result.rationale}</p>
                    {result.do_dont?.length > 0 && (
                      <ul className="text-xs text-muted-foreground list-disc pl-5 mt-3 space-y-0.5">
                        {result.do_dont.map((d, i) => (
                          <li key={i}>{d}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {/* Outfit recommendations from the stylist */}
                {result.outfit_recommendations?.length > 0 && (
                  <div className="space-y-3">
                    {result.outfit_recommendations.map((rec, i) => (
                      <div
                        key={i}
                        className="rounded-2xl border border-border bg-secondary/60 p-4"
                      >
                        <div className="caps-label text-[hsl(var(--accent))]">
                          {t('stylist.outfitN', { n: i + 1 })}
                        </div>
                        <div className="font-display text-base mt-1">{rec.name}</div>
                        <ul className="text-xs text-muted-foreground list-disc pl-5 mt-2 space-y-0.5">
                          {(rec.items || []).map((it, j) => (
                            <li key={j}>{it.description || it.role}</li>
                          ))}
                        </ul>
                        {rec.why && <p className="text-xs mt-2 italic">{rec.why}</p>}
                      </div>
                    ))}
                  </div>
                )}

                {/* Closet suggestions */}
                {result.closet_suggestions?.length > 0 ? (
                  <div>
                    <div className="caps-label text-muted-foreground mb-2">
                      {t('outfitCompletion.fromClosetLabel')}
                    </div>
                    <div
                      className="grid grid-cols-3 sm:grid-cols-4 gap-3"
                      data-testid="outfit-completion-closet-grid"
                    >
                      {result.closet_suggestions.map((s) => (
                        <ItemThumb
                          key={s.id}
                          item={s}
                          showScore
                          scoreLabel={`${Math.round((s._score || 0) * 100)}%`}
                          linkTo={`/closet/${s.id}`}
                        />
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground italic">
                    {t('outfitCompletion.noClosetSuggestions')}
                  </div>
                )}

                {/* Marketplace suggestions */}
                {result.market_suggestions?.length > 0 && (
                  <div>
                    <div className="caps-label text-muted-foreground mb-2 inline-flex items-center gap-1.5">
                      <ShoppingBag className="h-3.5 w-3.5" />
                      {t('outfitCompletion.fromMarketplaceLabel')}
                    </div>
                    <div
                      className="grid grid-cols-3 sm:grid-cols-4 gap-3"
                      data-testid="outfit-completion-marketplace-grid"
                    >
                      {result.market_suggestions.map((lg) => (
                        <ItemThumb
                          key={lg.id}
                          item={{
                            ...lg,
                            original_image_url: (lg.images || [])[0] || null,
                          }}
                          showScore
                          scoreLabel={`${Math.round((lg._score || 0) * 100)}%`}
                          linkTo={`/marketplace/${lg.id}`}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {!result.has_embeddings && (
                  <div
                    className="rounded-xl border border-dashed border-border bg-secondary/30 p-3 text-xs text-muted-foreground"
                    data-testid="outfit-completion-no-embeddings-hint"
                  >
                    <ExternalLink className="h-3.5 w-3.5 inline me-1" />
                    {t('outfitCompletion.embeddingsMissingHint')}
                  </div>
                )}
              </div>
            )}
          </div>
        </ScrollArea>

        <div className="border-t border-border p-4 flex justify-end gap-2 bg-background">
          <Button
            variant="ghost"
            onClick={() => handleOpenChange(false)}
            data-testid="outfit-completion-close-button"
          >
            <X className="h-4 w-4 me-2" />
            {t('common.close')}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

export default OutfitCompletionSheet;
