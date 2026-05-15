import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ImageOff } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import { labelForRole } from '@/lib/taxonomy';
import { cn } from '@/lib/utils';
import { ShareOutfitButton } from '@/components/stylist/ShareOutfitButton';

/**
 * Renders a single outfit recommendation. When recommendation items include
 * `closet_item_id`, we fetch and embed the item's image so the user sees
 * *proof* of the suggestion rather than just text.
 *
 * Image fetching is lazy and memoized per card instance to avoid hammering
 * the API when the chat thread re-renders.
 */
export function OutfitRecommendationCard({ rec, index, sessionId, onItemClick }) {
  const { t } = useTranslation();
  const items = rec.items || [];
  const ids = items
    .map((it) => it.closet_item_id)
    .filter(Boolean);
  const [images, setImages] = useState({});

  useEffect(() => {
    let cancelled = false;
    const toFetch = ids.filter((id) => !(id in images));
    if (toFetch.length === 0) return () => {};
    (async () => {
      const fetched = {};
      await Promise.all(
        toFetch.map(async (id) => {
          try {
            const item = await api.getItem(id);
            fetched[id] =
              item?.reconstructed_image_url ||
              item?.segmented_image_url ||
              item?.image_url ||
              null;
          } catch {
            fetched[id] = null;
          }
        }),
      );
      if (!cancelled) setImages((prev) => ({ ...prev, ...fetched }));
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids.join('|')]);

  const withImages = items.filter((it) => images[it.closet_item_id]);
  const heroImage = withImages[0]
    ? images[withImages[0].closet_item_id]
    : null;

  return (
    <div
      className="rounded-xl bg-secondary/60 border border-border overflow-hidden"
      data-testid={`outfit-recommendation-${index}`}
    >
      {heroImage ? (
        <div className="relative aspect-[16/9] bg-background">
          {/* Phase S3: hero is a button when the parent supplies
              onItemClick — opens the side-sheet floater instead of
              hard-navigating, so the chat thread stays in view. */}
          {onItemClick && withImages[0]?.closet_item_id ? (
            <button
              type="button"
              onClick={() => onItemClick(withImages[0].closet_item_id)}
              className="absolute inset-0 group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--accent))] focus-visible:ring-offset-0"
              data-testid={`outfit-recommendation-${index}-hero-button`}
              aria-label={rec.name || `Outfit ${index + 1}`}
            >
              <img
                src={heroImage}
                alt={rec.name || `Outfit ${index + 1}`}
                loading="lazy"
                onError={(e) => {
                  e.currentTarget.style.opacity = '0.25';
                }}
                className="absolute inset-0 w-full h-full object-cover transition-transform group-hover:scale-[1.02]"
              />
            </button>
          ) : (
            <img
              src={heroImage}
              alt={rec.name || `Outfit ${index + 1}`}
              loading="lazy"
              onError={(e) => {
                e.currentTarget.style.opacity = '0.25';
              }}
              className="absolute inset-0 w-full h-full object-cover"
            />
          )}
          {withImages.length > 1 ? (
            <div className="absolute bottom-2 right-2 flex -space-x-2 pointer-events-none">
              {withImages.slice(1, 4).map((it, i) => (
                <div
                  key={`${it.closet_item_id}-${i}`}
                  className="h-8 w-8 rounded-full border-2 border-background overflow-hidden bg-card"
                >
                  <img
                    src={images[it.closet_item_id]}
                    alt={it.description || it.role}
                    loading="lazy"
                    className="h-full w-full object-cover"
                  />
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="p-3">
        <div className="caps-label text-[hsl(var(--accent))]">
          {t('stylist.outfitN', { n: index + 1 })}
        </div>
        <div className="font-display text-base mt-1">{rec.name}</div>
        <ul className="text-xs text-muted-foreground mt-2 space-y-1">
          {items.map((it, j) => {
            // Phase S3: each row's thumb is a button when the parent
            // supplies onItemClick AND we have a closet_item_id —
            // otherwise fall back to the static rendering.
            const cid = it.closet_item_id;
            const hasImage = cid && images[cid];
            const clickable = onItemClick && cid;
            const thumb = hasImage ? (
              <img
                src={images[cid]}
                alt={it.description || it.role}
                loading="lazy"
                className="h-8 w-8 rounded-md object-cover bg-background border border-border shrink-0"
              />
            ) : (
              <span
                className={cn(
                  'h-8 w-8 rounded-md bg-background border border-dashed border-border shrink-0',
                  'flex items-center justify-center',
                )}
                aria-hidden="true"
              >
                <ImageOff className="h-3 w-3 text-muted-foreground opacity-60" />
              </span>
            );
            return (
              <li
                key={j}
                // ``min-w-0`` lets the text span below shrink under
                // the thumbnail's fixed width when the description
                // contains a long unbreakable token — same fix as
                // the outer chat bubble.
                className="flex min-w-0 items-center gap-2"
                data-testid={`outfit-recommendation-${index}-item-${j}`}
              >
                {clickable ? (
                  <button
                    type="button"
                    onClick={() => onItemClick(cid)}
                    className="shrink-0 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--accent))] hover:opacity-90 transition-opacity"
                    data-testid={`outfit-recommendation-${index}-item-${j}-thumb`}
                    aria-label={it.description || labelForRole(it.role, t) || it.role}
                  >
                    {thumb}
                  </button>
                ) : (
                  thumb
                )}
                <span className="flex-1 min-w-0 break-words">
                  {it.description || labelForRole(it.role, t) || it.role}
                  {it.role ? (
                    <Badge
                      variant="outline"
                      className="ms-2 text-[9px] py-0 px-1 h-4 rounded-sm"
                    >
                      {labelForRole(it.role, t)}
                    </Badge>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>
        {rec.why ? <p className="text-xs mt-2 italic break-words">{rec.why}</p> : null}
        <div className="mt-3 flex items-center justify-end">
          <ShareOutfitButton rec={rec} sessionId={sessionId} />
        </div>
      </div>
    </div>
  );
}
