/* eslint-disable react/prop-types */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import {
  UploadCloud,
  Image as ImgIcon,
  Search,
  Check,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { useClosetStore } from '@/lib/useClosetStore';
import { bestImageUrl } from '@/lib/itemImage';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

/**
 * AttachmentPicker — unified composer attachment surface (Phase S2).
 *
 * Replaces the bare ``<input type="file">`` in Stylist.jsx with a single
 * trigger that opens a side sheet offering TWO ways to attach garments
 * to the chat turn:
 *
 *   1. Upload tab    — drag-and-drop or native file browser, multi-file.
 *   2. From Closet   — searchable, multi-select grid of the user's
 *                      existing closet items.
 *
 * Both sources can be used in the SAME confirmation (per user UX
 * choice 1c), e.g. "the bag I already own + this new top I'm thinking
 * about buying". The picker fetches closet items' images as Blobs on
 * confirm and converts them to ``File`` objects so the parent's
 * existing submit pipeline (single-image ``/stylist`` for 1 attachment,
 * multi-image ``/stylist/compose-outfit`` for 2+) keeps working
 * unchanged — no backend modifications required.
 *
 * Props
 * -----
 *   trigger        — the JSX element that opens the sheet when clicked.
 *                     The component injects the click handler.
 *   onConfirm      — ``(files: File[]) => void``; called with the
 *                     combined File array after the user confirms.
 *   maxItems       — total cap (uploads + closet picks). Default 7
 *                     matches the existing Stylist composer limit.
 *   currentCount   — how many attachments are ALREADY in the composer.
 *                     The picker subtracts this from ``maxItems`` so the
 *                     user never picks more than will fit.
 *   disabled       — when true, the trigger is rendered but does not open.
 */
export function AttachmentPicker({
  trigger,
  onConfirm,
  maxItems = 7,
  currentCount = 0,
  disabled = false,
}) {
  const { t } = useTranslation();
  const closet = useClosetStore({ prewarm: true });
  const closetItems = closet.items || [];

  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState('upload');
  const [uploadFiles, setUploadFiles] = useState([]);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [query, setQuery] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const remaining = Math.max(0, maxItems - currentCount);
  const pickedCount = uploadFiles.length + selectedIds.size;
  const overLimit = pickedCount > remaining;

  // Reset state when the sheet closes so the next open starts fresh.
  // (We deliberately do NOT reset on confirm — the close-and-reset path
  // is what runs after confirm too.)
  useEffect(() => {
    if (!open) {
      setUploadFiles([]);
      setSelectedIds(new Set());
      setQuery('');
      setTab('upload');
      setDragOver(false);
      setConfirming(false);
    }
  }, [open]);

  // ---- Upload tab handlers ----------------------------------------
  const addUploadFiles = (incoming) => {
    if (!incoming?.length) return;
    const accepted = Array.from(incoming).filter(
      (f) => f && f.type?.startsWith('image/'),
    );
    if (!accepted.length) {
      toast.error(t('attachmentPicker.imageOnly', 'Only image files are supported.'));
      return;
    }
    setUploadFiles((prev) => [...prev, ...accepted]);
  };

  const onFileInputChange = (e) => {
    addUploadFiles(e.target.files);
    // Allow re-selecting the same file by clearing the input.
    e.target.value = '';
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    addUploadFiles(e.dataTransfer?.files);
  };

  const removeUploadAt = (idx) => {
    setUploadFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  // ---- Closet tab handlers ----------------------------------------
  const filteredCloset = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return closetItems;
    return closetItems.filter((it) => {
      const hay = `${it.name || ''} ${it.category || ''} ${it.sub_category || ''} ${it.color || ''} ${it.brand || ''}`.toLowerCase();
      return hay.includes(q);
    });
  }, [closetItems, query]);

  const toggleClosetId = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  // ---- Confirm: materialise closet picks into File[] --------------
  const fetchClosetImageAsFile = async (item) => {
    // Use the canonical resolver so we honour the same field-priority
    // chain (incl. ``thumbnail_data_url``) the rest of the closet UI
    // uses. Without this, items whose only image lives in
    // ``thumbnail_data_url`` render — and pick up — as empty tiles.
    const url = bestImageUrl(item);
    if (!url) {
      throw new Error(`No image URL for closet item ${item.id}`);
    }
    // ``thumbnail_data_url`` is a base64 data URL — ``fetch`` handles
    // that natively (no network), so the same code path works for both
    // remote URLs and inline data URLs.
    const resp = await fetch(url, {
      credentials: url.startsWith('data:') ? 'omit' : 'include',
    });
    if (!resp.ok) {
      throw new Error(`Failed to fetch ${url.slice(0, 60)}…: ${resp.status}`);
    }
    const blob = await resp.blob();
    // Pick an extension that matches the Content-Type when possible.
    const ct = blob.type || 'image/jpeg';
    const ext = ct.split('/')[1]?.split(';')[0] || 'jpg';
    const safeName = (item.name || item.category || 'closet-item')
      .toLowerCase()
      .replace(/[^a-z0-9-]+/g, '-')
      .slice(0, 40);
    return new File([blob], `closet-${safeName}.${ext}`, { type: ct });
  };

  const handleConfirm = async () => {
    if (pickedCount === 0) return;
    if (overLimit) {
      toast.error(
        t(
          'attachmentPicker.overLimit',
          'Too many attachments — max {{max}} per turn.',
          { max: maxItems },
        ),
      );
      return;
    }
    setConfirming(true);
    try {
      // Materialise closet picks in parallel; uploads are already File objects.
      const idsArr = Array.from(selectedIds);
      const closetFiles = await Promise.all(
        idsArr.map((id) => {
          const item = closetItems.find((x) => x.id === id);
          if (!item) {
            return Promise.reject(new Error(`Item ${id} not in closet snapshot`));
          }
          return fetchClosetImageAsFile(item);
        }),
      );
      // Order: closet picks first, uploads second. This is arbitrary; the
      // backend treats all attachments equivalently.
      const combined = [...closetFiles, ...uploadFiles];
      onConfirm?.(combined);
      setOpen(false);
    } catch (exc) {
      console.error('AttachmentPicker.handleConfirm failed', exc);
      toast.error(
        t(
          'attachmentPicker.fetchFailed',
          'Could not load one of the closet images. Try again.',
        ),
      );
    } finally {
      setConfirming(false);
    }
  };

  // ---- Trigger wiring ---------------------------------------------
  // We clone the parent-supplied trigger to inject our onClick. If they
  // don't supply one, we render a sensible default.
  const triggerEl = trigger ? (
    <span
      role="button"
      tabIndex={0}
      onClick={() => !disabled && setOpen(true)}
      onKeyDown={(e) => {
        if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          setOpen(true);
        }
      }}
      className="inline-flex"
      data-testid="attachment-picker-trigger"
      aria-label={t('attachmentPicker.openLabel', 'Add attachments')}
      aria-disabled={disabled || undefined}
    >
      {trigger}
    </span>
  ) : (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="h-11 w-11 rounded-xl border border-border bg-card"
      onClick={() => !disabled && setOpen(true)}
      disabled={disabled}
      data-testid="attachment-picker-trigger"
      aria-label={t('attachmentPicker.openLabel', 'Add attachments')}
    >
      <ImgIcon className="h-5 w-5" />
    </Button>
  );

  return (
    <>
      {triggerEl}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-md p-0 flex flex-col"
          data-testid="attachment-picker-sheet"
        >
          <SheetHeader className="px-5 py-4 border-b border-border shrink-0">
            <SheetTitle className="font-display text-lg">
              {t('attachmentPicker.title', 'Add attachments')}
            </SheetTitle>
            <SheetDescription className="text-xs">
              {t(
                'attachmentPicker.subtitle',
                'Upload new photos or pick from your closet.',
              )}
            </SheetDescription>
          </SheetHeader>

          <Tabs
            value={tab}
            onValueChange={setTab}
            className="flex-1 flex flex-col overflow-hidden"
          >
            <TabsList className="grid grid-cols-2 mx-5 mt-3 shrink-0">
              <TabsTrigger
                value="upload"
                data-testid="attachment-picker-tab-upload"
              >
                <UploadCloud className="h-4 w-4 me-1.5" />
                {t('attachmentPicker.uploadTab', 'Upload')}
              </TabsTrigger>
              <TabsTrigger
                value="closet"
                data-testid="attachment-picker-tab-closet"
              >
                <ImgIcon className="h-4 w-4 me-1.5" />
                {t('attachmentPicker.closetTab', 'From Closet')}
              </TabsTrigger>
            </TabsList>

            {/* -------- Upload tab -------- */}
            <TabsContent
              value="upload"
              className="flex-1 m-0 p-5 overflow-y-auto"
            >
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                className={cn(
                  'w-full rounded-xl border-2 border-dashed transition-colors',
                  'px-4 py-10 flex flex-col items-center justify-center gap-2',
                  'text-sm text-muted-foreground',
                  dragOver
                    ? 'border-[hsl(var(--accent))] bg-[hsl(var(--accent))]/5'
                    : 'border-border bg-secondary/40 hover:bg-secondary/60',
                )}
                data-testid="attachment-picker-upload-dropzone"
              >
                <UploadCloud className="h-7 w-7 opacity-70" />
                <span>
                  {t('attachmentPicker.dropHere', 'Drop images here or click to browse')}
                </span>
                <span className="text-[10px] opacity-70">
                  {t('attachmentPicker.upTo', 'Up to {{n}} per turn', {
                    n: maxItems,
                  })}
                </span>
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={onFileInputChange}
                data-testid="attachment-picker-upload-input"
              />
              {uploadFiles.length > 0 ? (
                <div
                  className="mt-4 grid grid-cols-3 gap-2"
                  data-testid="attachment-picker-upload-preview-grid"
                >
                  {uploadFiles.map((f, i) => (
                    <div
                      key={`${f.name}-${i}`}
                      className="relative aspect-square rounded-lg overflow-hidden border border-border bg-background"
                    >
                      <img
                        src={URL.createObjectURL(f)}
                        alt={f.name}
                        className="h-full w-full object-cover"
                      />
                      <button
                        type="button"
                        onClick={() => removeUploadAt(i)}
                        className="absolute top-1 end-1 h-6 w-6 rounded-full bg-background/90 backdrop-blur flex items-center justify-center text-xs border border-border hover:bg-background"
                        aria-label={t('common.remove', 'Remove')}
                        data-testid={`attachment-picker-upload-remove-${i}`}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
            </TabsContent>

            {/* -------- Closet tab -------- */}
            <TabsContent
              value="closet"
              className="flex-1 m-0 flex flex-col overflow-hidden"
            >
              <div className="px-5 pt-3 pb-2 shrink-0">
                <div className="relative">
                  <Search className="absolute start-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={t(
                      'attachmentPicker.searchPlaceholder',
                      'Search closet…',
                    )}
                    className="ps-8"
                    data-testid="attachment-picker-search"
                  />
                </div>
              </div>
              <ScrollArea className="flex-1 px-5 pb-3">
                {closet.loading && closetItems.length === 0 ? (
                  <div
                    className="grid grid-cols-3 gap-2"
                    data-testid="attachment-picker-closet-loading"
                  >
                    {Array.from({ length: 9 }).map((_, i) => (
                      <Skeleton key={i} className="aspect-square rounded-lg" />
                    ))}
                  </div>
                ) : filteredCloset.length === 0 ? (
                  <div
                    className="py-10 text-center text-sm text-muted-foreground"
                    data-testid="attachment-picker-closet-empty"
                  >
                    {query
                      ? t('attachmentPicker.noMatches', 'No closet items match.')
                      : t('attachmentPicker.emptyCloset', 'Your closet is empty.')}
                  </div>
                ) : (
                  <div
                    className="grid grid-cols-3 gap-2 pb-2"
                    data-testid="attachment-picker-closet-grid"
                  >
                    {filteredCloset.map((it) => {
                      const isSel = selectedIds.has(it.id);
                      // Canonical resolver — matches the priority chain
                      // used by every other closet surface, including
                      // ``thumbnail_data_url`` which the inline chain
                      // here previously missed and which manifested as
                      // empty tiles showing only the category label.
                      const src = bestImageUrl(it);
                      return (
                        <button
                          type="button"
                          key={it.id}
                          onClick={() => toggleClosetId(it.id)}
                          className={cn(
                            'relative aspect-square rounded-lg overflow-hidden border bg-background',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--accent))]',
                            'transition',
                            isSel
                              ? 'border-[hsl(var(--accent))] ring-2 ring-[hsl(var(--accent))]'
                              : 'border-border hover:border-foreground/30',
                          )}
                          data-testid={`attachment-picker-item-${it.id}`}
                          aria-pressed={isSel}
                          aria-label={it.name || it.category || 'item'}
                        >
                          {src ? (
                            <img
                              src={src}
                              alt={it.name || ''}
                              loading="lazy"
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <div className="h-full w-full flex items-center justify-center text-[10px] text-muted-foreground">
                              {it.category || '—'}
                            </div>
                          )}
                          {isSel ? (
                            <div
                              className="absolute inset-0 bg-[hsl(var(--accent))]/15 flex items-center justify-center"
                              aria-hidden="true"
                            >
                              <span className="h-6 w-6 rounded-full bg-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))] flex items-center justify-center">
                                <Check className="h-3.5 w-3.5" />
                              </span>
                            </div>
                          ) : null}
                        </button>
                      );
                    })}
                  </div>
                )}
              </ScrollArea>
            </TabsContent>
          </Tabs>

          {/* Footer — selection counter + cancel/confirm */}
          <div className="px-5 py-3 border-t border-border shrink-0 flex items-center justify-between gap-2">
            <div className="text-xs text-muted-foreground flex items-center gap-1.5">
              {overLimit ? (
                <>
                  <AlertCircle className="h-3.5 w-3.5 text-destructive" />
                  <span className="text-destructive">
                    {t(
                      'attachmentPicker.tooMany',
                      '{{n}} over limit ({{max}})',
                      { n: pickedCount - remaining, max: maxItems },
                    )}
                  </span>
                </>
              ) : (
                <span data-testid="attachment-picker-count">
                  {t('attachmentPicker.selected', '{{n}} selected', {
                    n: pickedCount,
                  })}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setOpen(false)}
                data-testid="attachment-picker-cancel"
              >
                {t('common.cancel', 'Cancel')}
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={handleConfirm}
                disabled={confirming || pickedCount === 0 || overLimit}
                data-testid="attachment-picker-confirm"
              >
                {confirming ? (
                  <Loader2 className="h-4 w-4 me-1.5 animate-spin" />
                ) : null}
                {t('attachmentPicker.attachN', 'Attach {{n}}', {
                  n: pickedCount,
                })}
              </Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
