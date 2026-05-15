/* eslint-disable react/prop-types */
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { X, ImageOff, ExternalLink, Tag, Palette } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

/**
 * ItemFloater — a right-edge side panel that previews a single closet
 * item without dimming the chat behind it (per the user's UX choice
 * 3c: "compare while chatting").
 *
 * Why not <Sheet>? shadcn's Sheet primitive is built on Radix Dialog,
 * which always renders an overlay that intercepts pointer events on the
 * page behind it. We explicitly want the chat to stay interactive so
 * users can scroll the conversation while the floater is open. Hence
 * the custom positioned panel + React Portal.
 *
 * Open/close model:
 *   * Controlled by the parent via the `itemId` prop. When `itemId` is
 *     non-null, the panel is mounted and slides in.
 *   * `onClose()` is called when the user dismisses via the X button,
 *     the ESC key, or by clicking outside the panel.
 *
 * Item shape:
 *   * Loaded lazily via `api.getItem(itemId)` so the floater can be
 *     dropped into any thumbnail call-site that only knows the ID.
 *   * Falls back through the same image URL chain used elsewhere in
 *     the app (reconstructed → segmented → original) so the floater
 *     is visually consistent with the closet grid.
 */
export function ItemFloater({ itemId, onClose }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const panelRef = useRef(null);
  const closeBtnRef = useRef(null);

  const [item, setItem] = useState(null);
  const [error, setError] = useState(null);
  // `entering` controls the slide-in animation. We mount with the
  // panel translated off-screen on the first paint, then flip the
  // flag on the next tick so the transition fires. Without this two-
  // step, React would batch the mount + final transform and the user
  // would see the panel pop into place instead of slide.
  const [entering, setEntering] = useState(true);

  // ---- Lazy fetch the item whenever itemId changes ------------------
  useEffect(() => {
    if (!itemId) return undefined;
    let cancelled = false;
    setItem(null);
    setError(null);
    (async () => {
      try {
        const data = await api.getItem(itemId);
        if (!cancelled) setItem(data);
      } catch (exc) {
        if (!cancelled) setError(exc?.message || 'Failed to load item');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [itemId]);

  // ---- Slide-in on mount, focus the close button --------------------
  useEffect(() => {
    if (!itemId) return undefined;
    const raf = requestAnimationFrame(() => setEntering(false));
    // Move focus into the panel so keyboard users can reach the close
    // button without tabbing through the chat first.
    const tid = setTimeout(() => closeBtnRef.current?.focus(), 250);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(tid);
      setEntering(true);
    };
  }, [itemId]);

  // ---- ESC + click-outside dismiss ----------------------------------
  useEffect(() => {
    if (!itemId) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    const onClick = (e) => {
      // Click outside the panel closes the floater. We deliberately
      // do NOT prevent default or stop propagation here — if the user
      // clicked another thumbnail behind us, that handler should still
      // fire and re-open the floater on the new item.
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        onClose?.();
      }
    };
    window.addEventListener('keydown', onKey);
    // mousedown not click so we don't lose the dismiss to a re-rendering
    // thumbnail underneath us between mousedown and click.
    window.addEventListener('mousedown', onClick);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onClick);
    };
  }, [itemId, onClose]);

  if (!itemId) return null;

  const heroImage =
    item?.reconstructed_image_url ||
    item?.clean_image_url ||
    item?.segmented_image_url ||
    item?.original_image_url ||
    item?.image_url ||
    null;

  const onViewDetails = () => {
    onClose?.();
    navigate(`/closet/${itemId}`);
  };

  // Render via portal so the floater escapes any scroll/overflow
  // containers higher up in the chat DOM tree.
  return createPortal(
    <aside
      ref={panelRef}
      role="complementary"
      aria-label={item?.name || t('stylist.floater.titleLoading', 'Item details')}
      data-testid="item-floater-panel"
      className={cn(
        'fixed right-0 top-0 z-50 h-full w-full sm:w-[360px]',
        'bg-card border-l border-border shadow-2xl',
        'flex flex-col',
        'transition-transform duration-200 ease-out',
        entering ? 'translate-x-full' : 'translate-x-0',
      )}
    >
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <h3
          className="font-display text-sm truncate pe-2"
          data-testid="item-floater-title"
        >
          {item?.name || (
            <Skeleton className="h-4 w-32" />
          )}
        </h3>
        <Button
          ref={closeBtnRef}
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={onClose}
          data-testid="item-floater-close"
          aria-label={t('common.close', 'Close')}
        >
          <X className="h-4 w-4" />
        </Button>
      </header>

      {/* Body — scrollable */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {/* Image */}
        <div className="aspect-square w-full rounded-lg overflow-hidden bg-background border border-border">
          {heroImage ? (
            <img
              src={heroImage}
              alt={item?.name || ''}
              loading="lazy"
              data-testid="item-floater-image"
              className="h-full w-full object-contain"
              onError={(e) => {
                e.currentTarget.style.opacity = '0.25';
              }}
            />
          ) : item ? (
            <div className="h-full w-full flex items-center justify-center text-muted-foreground">
              <ImageOff className="h-10 w-10 opacity-50" />
            </div>
          ) : (
            <Skeleton className="h-full w-full" />
          )}
        </div>

        {/* Error state */}
        {error ? (
          <div
            className="text-xs text-destructive"
            data-testid="item-floater-error"
          >
            {error}
          </div>
        ) : null}

        {/* Metadata stack */}
        {item ? (
          <div className="space-y-3">
            {/* Category + sub-category */}
            <div className="flex flex-wrap items-center gap-1.5">
              {item.category ? (
                <Badge
                  variant="secondary"
                  className="text-[10px] uppercase tracking-wide"
                  data-testid="item-floater-category"
                >
                  <Tag className="h-3 w-3 me-1" />
                  {item.category}
                </Badge>
              ) : null}
              {item.sub_category ? (
                <Badge
                  variant="outline"
                  className="text-[10px]"
                >
                  {item.sub_category}
                </Badge>
              ) : null}
              {item.condition ? (
                <Badge
                  variant="outline"
                  className="text-[10px]"
                  data-testid="item-floater-condition"
                >
                  {item.condition}
                </Badge>
              ) : null}
            </div>

            {/* Color */}
            {item.color ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Palette className="h-3.5 w-3.5" />
                <span data-testid="item-floater-color">{item.color}</span>
              </div>
            ) : null}

            {/* Brand */}
            {item.brand ? (
              <div className="text-xs text-muted-foreground">
                <span className="caps-label">
                  {t('addItem.brand', 'Brand')}:
                </span>{' '}
                <span className="text-foreground">{item.brand}</span>
              </div>
            ) : null}

            {/* Material / Pattern */}
            {(item.material || item.pattern) ? (
              <div className="text-xs text-muted-foreground space-y-1">
                {item.material ? (
                  <div>
                    <span className="caps-label">
                      {t('addItem.material', 'Material')}:
                    </span>{' '}
                    <span className="text-foreground">{item.material}</span>
                  </div>
                ) : null}
                {item.pattern ? (
                  <div>
                    <span className="caps-label">
                      {t('addItem.pattern', 'Pattern')}:
                    </span>{' '}
                    <span className="text-foreground">{item.pattern}</span>
                  </div>
                ) : null}
              </div>
            ) : null}

            {/* Description */}
            {item.description ? (
              <p
                className="text-xs leading-relaxed text-muted-foreground italic border-l-2 border-border ps-3"
                data-testid="item-floater-description"
              >
                {item.description}
              </p>
            ) : null}
          </div>
        ) : !error ? (
          <div className="space-y-2">
            <Skeleton className="h-3 w-1/2" />
            <Skeleton className="h-3 w-2/3" />
            <Skeleton className="h-3 w-1/3" />
          </div>
        ) : null}
      </div>

      {/* Footer CTA */}
      <footer className="px-4 py-3 border-t border-border shrink-0">
        <Button
          className="w-full"
          onClick={onViewDetails}
          disabled={!item}
          data-testid="item-floater-view-details"
        >
          <ExternalLink className="h-4 w-4 me-2" />
          {t('stylist.floater.viewDetails', 'View full details')}
        </Button>
      </footer>
    </aside>,
    document.body,
  );
}
