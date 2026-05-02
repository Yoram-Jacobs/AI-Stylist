/**
 * SwapPickerModal — lets a would-be swapper pick ONE of their own
 * closet items to offer in exchange for a marketplace listing.
 *
 * UX notes:
 * - Single-select grid (tap a card to select, tap again to deselect).
 * - Pulls from ``/closet`` with a lean projection (closet list endpoint
 *   already strips heavy base64 image fields, so the payload stays
 *   grid-friendly).
 * - Submitting calls ``api.proposeSwap(listingId, offeredItemId)`` and
 *   bubbles the resulting transaction id back via ``onSwapCreated`` so
 *   the parent can navigate to the transactions page / landing.
 */
import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { AspectRatio } from '@/components/ui/aspect-ratio';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, Loader2, ShirtIcon } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';

export function SwapPickerModal({
  open,
  onOpenChange,
  listingId,
  listingTitle,
  onSwapCreated,
}) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSelected(null);
    setLoading(true);
    api
      .listCloset({ limit: 100 })
      .then((res) => {
        // Endpoint returns either { items: [...] } or a raw array.
        const list = Array.isArray(res) ? res : res?.items || [];
        // Only user's own items (already filtered server-side) with
        // a visible image + title — filter out unfinished drafts.
        setItems(list.filter((it) => it.title));
      })
      .catch(() => toast.error('Could not load your closet.'))
      .finally(() => setLoading(false));
  }, [open]);

  const imageFor = (it) =>
    it.thumbnail_data_url
    || it.segmented_image_url
    || it.reconstructed_image_url
    || it.original_image_url
    || null;

  const handleSubmit = async () => {
    if (!selected) return;
    setSubmitting(true);
    try {
      const tx = await api.proposeSwap(listingId, selected);
      toast.success('Swap proposal sent. The lister will get an email with accept / decline links.');
      onOpenChange(false);
      onSwapCreated?.(tx);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not send swap proposal.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-3xl"
        data-testid="swap-picker-modal"
      >
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">
            Offer an item in exchange
          </DialogTitle>
          <DialogDescription>
            Pick one item from your closet to swap for{' '}
            <span className="font-medium text-foreground">
              {listingTitle || 'this listing'}
            </span>
            . The lister will be emailed to accept or decline.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[55vh] pr-2 -mr-2">
          {loading ? (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton
                  key={i}
                  className="aspect-[3/4] w-full rounded-[calc(var(--radius)+4px)]"
                />
              ))}
            </div>
          ) : items.length === 0 ? (
            <div
              className="py-12 text-center text-sm text-muted-foreground flex flex-col items-center gap-3"
              data-testid="swap-picker-empty"
            >
              <ShirtIcon className="h-10 w-10 opacity-40" />
              <div>You don&apos;t have any items to offer yet.</div>
              <div className="text-xs">
                Add items to your closet first, then try again.
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3" data-testid="swap-picker-grid">
              {items.map((it) => {
                const img = imageFor(it);
                const isSelected = selected === it.id;
                return (
                  <button
                    key={it.id}
                    type="button"
                    onClick={() => setSelected(isSelected ? null : it.id)}
                    className={[
                      'group relative rounded-[calc(var(--radius)+4px)] overflow-hidden',
                      'border transition-shadow text-left',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--accent))]',
                      isSelected
                        ? 'border-[hsl(var(--accent))] shadow-editorial-md ring-2 ring-[hsl(var(--accent))]'
                        : 'border-border hover:shadow-editorial',
                    ].join(' ')}
                    data-testid={`swap-picker-item-${it.id}`}
                    data-selected={isSelected ? 'true' : 'false'}
                  >
                    <AspectRatio ratio={3 / 4} className="bg-secondary">
                      {img ? (
                        <img
                          src={img}
                          alt={it.title}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-muted-foreground caps-label">
                          No image
                        </div>
                      )}
                      {isSelected && (
                        <div className="absolute top-2 right-2 rounded-full bg-background/95 text-[hsl(var(--accent))] p-1 shadow">
                          <CheckCircle2 className="h-5 w-5" />
                        </div>
                      )}
                    </AspectRatio>
                    <div className="p-2">
                      <div className="font-medium text-sm truncate">
                        {it.title}
                      </div>
                      <div className="flex items-center gap-1.5 mt-1">
                        {it.brand && (
                          <span className="text-xs text-muted-foreground truncate">
                            {it.brand}
                          </span>
                        )}
                        {it.source === 'Shared' && (
                          <Badge variant="outline" className="text-[10px] py-0">
                            Shared
                          </Badge>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </ScrollArea>

        <DialogFooter className="mt-4">
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
            data-testid="swap-picker-cancel"
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!selected || submitting}
            className="rounded-xl"
            data-testid="swap-picker-submit"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Sending…
              </>
            ) : (
              'Propose swap'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default SwapPickerModal;
