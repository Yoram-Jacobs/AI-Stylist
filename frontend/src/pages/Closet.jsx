import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Plus, Search, Trash2, CheckCircle2, Circle, X, CheckSquare,
  Square, Loader2, ListChecks, Sparkles, Wand2, QrCode, Star,
  AlertTriangle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { AspectRatio } from '@/components/ui/aspect-ratio';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { SourceTagBadge } from '@/components/SourceTagBadge';
import { OutfitCompletionSheet } from '@/components/OutfitCompletionSheet';
import { api } from '@/lib/api';
import { bestImageUrl, isCleanImagePending } from '@/lib/itemImage';
import { labelForCategory, labelForSource, labelForIntent } from '@/lib/taxonomy';
import { useClosetStore } from '@/lib/useClosetStore';
import { closetStore } from '@/lib/closetStore';
import { toast } from 'sonner';

const CATEGORIES = ['all', 'top', 'bottom', 'outerwear', 'shoes', 'accessory', 'dress'];
// Filter dropdown options. We replaced the catch-all "Shared" with the
// three concrete marketplace intents so users can drill straight to
// items by their actual marketplace decision.
//
// Values in {Private, Retail} key on the closet item's ``source`` field;
// values in {for_sale, swap, donate} key on ``marketplace_intent``.
// "all" means no filter.
const SOURCES = ['all', 'Private', 'for_sale', 'swap', 'donate', 'Retail'];
const _SOURCE_VALUES = new Set(['Private', 'Shared', 'Retail']);
const _INTENT_VALUES = new Set(['for_sale', 'swap', 'donate']);

// Category synonyms — keep parity with the backend's matcher in
// closet.list_items so client-side filtering yields the same set of
// items as a server-side ``?category=`` would. This matters because
// we now filter the in-memory store rather than re-fetching.
const _CATEGORY_SYNONYMS = {
  top:        new Set(['top', 'tops']),
  bottom:     new Set(['bottom', 'bottoms']),
  outerwear:  new Set(['outerwear']),
  shoes:      new Set(['shoes', 'footwear']),
  accessory:  new Set(['accessory', 'accessories']),
  dress:      new Set(['dress', 'dresses', 'full body']),
};

function _matchesCategory(item, requested) {
  if (!requested || requested === 'all') return true;
  const synonyms = _CATEGORY_SYNONYMS[requested] || new Set([requested]);
  const cat = (item?.category || '').toLowerCase();
  return synonyms.has(cat);
}

function _matchesSource(item, requested) {
  if (!requested || requested === 'all') return true;
  if (_SOURCE_VALUES.has(requested)) return item?.source === requested;
  if (_INTENT_VALUES.has(requested)) return item?.marketplace_intent === requested;
  return true;
}

function _matchesSearch(item, q) {
  if (!q) return true;
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  // Mirror backend $text loosely: match any substring across the
  // user-visible string fields. Cheap on a 300-item closet.
  const haystack = [
    item?.title, item?.name, item?.category, item?.sub_category,
    item?.color, item?.brand, item?.material,
  ].filter(Boolean).join(' ').toLowerCase();
  return haystack.includes(needle);
}

export default function Closet() {
  const { t } = useTranslation();
  // Single source of truth: the global closet store. Reading from it
  // means navigating to /closet paints **instantly** (no network) —
  // the prewarm in AppLayout has already populated the snapshot.
  const store = useClosetStore();
  const initialFilters = { category: 'all', source: 'all', search: '' };
  const [filters, setFilters] = useState(initialFilters);
  // Search mode: 'keyword' uses Mongo text search, 'meaning' calls FashionCLIP.
  const [searchMode, setSearchMode] = useState('keyword');
  const [semanticActive, setSemanticActive] = useState(false);
  const [semanticItems, setSemanticItems] = useState([]);
  const [semanticIndexed, setSemanticIndexed] = useState(0);
  const [semanticLoading, setSemanticLoading] = useState(false);

  // Apply filters client-side over the store snapshot. Wrapped in a
  // memo so re-renders triggered by other state (selection, etc.)
  // don't re-walk a 300-item list unnecessarily.
  const filteredItems = useMemo(() => {
    if (semanticActive) return semanticItems;
    return (store.items || []).filter(
      (it) =>
        _matchesCategory(it, filters.category) &&
        _matchesSource(it, filters.source) &&
        _matchesSearch(it, filters.search),
    );
  }, [store.items, filters.category, filters.source, filters.search, semanticActive, semanticItems]);

  const items = filteredItems;
  const total = semanticActive
    ? semanticItems.length
    : (filters.category === 'all' && filters.source === 'all' && !filters.search
      ? store.total
      : filteredItems.length);
  // Show the skeleton in either of two cases:
  //   * the store is mid-prewarm and we have no cached items yet
  //     (very first visit after sign-in), OR
  //   * a semantic search is in flight (those override ``items``).
  const loading =
    (store.loading && (store.items?.length || 0) === 0) || semanticLoading;

  // Selection state
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // Outfit completion sheet (Phase P)
  const [completionOpen, setCompletionOpen] = useState(false);
  const [completionAnchors, setCompletionAnchors] = useState([]);

  // No-op compat shim. Some downstream code (e.g. the delete handler)
  // calls ``fetchItems`` after a mutation to refresh the grid; with
  // the store-based design we instead call ``store.remove`` /
  // ``store.upsert`` and let React re-render. The shim lets us leave
  // those code paths untouched while we land this refactor.
  const fetchItems = useCallback(async () => {
    return store.incrementalSync();
  }, [store]);

  // ──────────────────────────────────────────────────────────────────
  // Phase O.6 — poll for background-rembg completion.
  //
  // After ``POST /closet`` with ``from_one_pass=true`` the server
  // immediately returns the document with ``clean_image_status:
  // "pending"`` and queues rembg as a fire-and-forget BackgroundTask.
  // The closet grid initially renders the bbox-cropped JPEG; we poll
  // ``GET /closet/{id}`` here on a gentle backoff so the moment the
  // alpha-PNG cutout is ready we ``store.upsert(updated)`` and the
  // thumbnail swaps in-place \u2014 no full grid refetch, no flash.
  //
  // We do NOT poll for every single ``pending`` item every cycle:
  // ``polishingIds`` is recomputed against the LIVE store snapshot
  // and only items whose status is still ``pending`` get a fresh GET.
  // The cycle stops itself when none remain.
  // ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    const pendingIds = (store.items || [])
      .filter((it) => it && it.clean_image_status === 'pending')
      .map((it) => it.id);
    if (pendingIds.length === 0) return undefined;
    let cancelled = false;
    let attempt = 0;
    const POLL_STEPS_MS = [3000, 4000, 6000, 9000, 12000, 18000]; // ~52s total
    const tick = async () => {
      if (cancelled) return;
      // Refetch each still-pending item in parallel; bail out as soon
      // as any one of them flips to a terminal state so the grid
      // updates on the first available result rather than waiting
      // for the slowest. ``store.upsert`` is a no-op for unchanged
      // docs so duplicate cycles cost nothing.
      const live = store.items || [];
      const stillPending = pendingIds.filter((id) =>
        live.find((it) => it.id === id && it.clean_image_status === 'pending'),
      );
      if (stillPending.length === 0) return; // we're done
      try {
        const results = await Promise.all(
          stillPending.map((id) => api.getItem(id).catch(() => null)),
        );
        if (cancelled) return;
        results.forEach((it) => {
          if (it && it.id) store.upsert(it);
        });
      } catch {
        /* swallow \u2014 polling is best-effort */
      }
      attempt += 1;
      const delay =
        POLL_STEPS_MS[Math.min(attempt, POLL_STEPS_MS.length - 1)];
      timer = setTimeout(tick, delay);
    };
    let timer = setTimeout(tick, POLL_STEPS_MS[0]);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store.items]);

  const fetchSemantic = useCallback(async (text) => {
    setSemanticLoading(true);
    try {
      const res = await api.searchCloset({ text, limit: 48, min_score: 0.18 });
      const sItems = res.items || [];
      setSemanticItems(sItems);
      setSemanticIndexed(res.indexed || 0);
      setSemanticActive(true);
      if (sItems.length === 0) {
        toast.message(t('pages.closet.no_meaningful_matches_found_u2014'));
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Semantic search failed.');
      setSemanticActive(false);
    } finally { setSemanticLoading(false); }
  }, []);

  // Mount: incremental sync only (the eager prewarm in AppLayout
  // already populated the store). Filter changes no longer trigger
  // any network — they re-filter the in-memory list. This is the
  // core of the "don't fully reload on navigation" UX win.
  useEffect(() => {
    store.incrementalSync().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Refresh on focus / visibility — picks up changes the user made
  // in another tab. Throttled inside the store itself.
  useEffect(() => {
    const onFocus = () => { store.incrementalSync().catch(() => {}); };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') onFocus();
    });
    return () => {
      window.removeEventListener('focus', onFocus);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced semantic-search trigger; keyword search is now purely
  // client-side over the store snapshot, so no network involvement.
  useEffect(() => {
    if (searchMode !== 'meaning') return undefined;
    const q = filters.search.trim();
    if (!q) return undefined;
    const handle = setTimeout(() => { fetchSemantic(q); }, 300);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.search, searchMode]);

  const onSearch = (e) => {
    e.preventDefault();
    const q = filters.search.trim();
    if (searchMode === 'meaning' && q) {
      fetchSemantic(q);
    } else {
      fetchItems();
    }
  };

  // "x" button inside the search input — clears the query and
  // re-fetches without needing an extra trip through Enter / Search.
  const clearSearch = () => {
    setSemanticActive(false);
    setFilters((f) => ({ ...f, search: '' }));
    // Let the debounced effect handle the actual re-fetch on the
    // next tick so we don't double-fire.
  };

  const clearSemantic = () => {
    setSemanticActive(false);
    setFilters((f) => ({ ...f, search: '' }));
    fetchItems();
  };

  const empty = !loading && items.length === 0;

  // ------- selection helpers -------
  const enterSelect = () => { setSelectMode(true); setSelected(new Set()); };
  const cancelSelect = () => { setSelectMode(false); setSelected(new Set()); };

  const toggleOne = useCallback((id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const selectAllVisible = () => {
    setSelected(new Set(items.map((i) => i.id)));
  };
  const clearSelection = () => setSelected(new Set());

  const allVisibleSelected = items.length > 0 && selected.size >= items.length
    && items.every((i) => selected.has(i.id));

  const handleDelete = async () => {
    if (selected.size === 0) return;
    setDeleting(true);
    const ids = Array.from(selected);
    const results = await Promise.allSettled(ids.map((id) => api.deleteItem(id)));
    const ok = results.filter((r) => r.status === 'fulfilled').length;
    const fail = results.length - ok;
    setDeleting(false);
    setConfirmOpen(false);
    if (ok && !fail) {
      toast.success(`${ok} item${ok === 1 ? '' : 's'} deleted`);
    } else if (ok && fail) {
      toast.message(`Deleted ${ok}, failed ${fail}`);
    } else {
      toast.error(t('pages.closet.could_not_delete_the_selected'));
    }
    // Drop deleted items from the global store so every page sees
    // the change immediately (Closet, AddItem duplicate-check,
    // Stylist picker). We let the periodic incremental sync reconcile
    // ``total`` rather than firing a full refetch.
    const okIds = new Set(
      ids.filter((_, idx) => results[idx].status === 'fulfilled'),
    );
    okIds.forEach((id) => store.remove(id));
    setSelected(new Set());
    setSelectMode(false);
  };

  const onCardClick = (e, item) => {
    if (!selectMode) return; // let the <Link> navigate normally
    e.preventDefault();
    e.stopPropagation();
    toggleOne(item.id);
  };

  // Keyboard shortcut: Esc exits selection mode
  useEffect(() => {
    if (!selectMode) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') cancelSelect(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectMode]);

  return (
    <div className="container-px max-w-6xl mx-auto pt-6 md:pt-10">
      <header className="flex items-end justify-between mb-6">
        <div>
          <div className="caps-label text-muted-foreground">{t('closet.subtitle')}</div>
          <h1 className="font-display text-3xl sm:text-4xl mt-1">
            {t('closet.title')}{' '}
            <span
              className="text-muted-foreground font-body text-base align-middle ms-2"
              data-testid="closet-total"
            >
              ({total})
            </span>
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {!selectMode ? (
            <>
              <Button
                variant="outline"
                className="rounded-xl"
                onClick={enterSelect}
                disabled={items.length === 0}
                data-testid="closet-select-mode-button"
              >
                <ListChecks className="h-4 w-4 me-2" /> {t('closet.bulkSelect')}
              </Button>
              <Button
                asChild
                className="rounded-xl hidden md:inline-flex"
                data-testid="closet-add-item-button"
              >
                <Link to="/closet/add"><Plus className="h-4 w-4 me-2" /> {t('closet.addItem')}</Link>
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              className="rounded-xl"
              onClick={cancelSelect}
              data-testid="closet-select-cancel-button"
            >
              <X className="h-4 w-4 me-2" /> {t('common.cancel')}
            </Button>
          )}
        </div>
      </header>

      <form
        onSubmit={onSearch}
        className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border -mx-4 px-4 py-3 md:mx-0 md:px-0 md:py-4"
        data-testid="closet-filter-bar"
      >
        <div className="flex flex-wrap gap-2 items-center">
          <div className="relative flex-1 min-w-[220px]">
            {searchMode === 'meaning' ? (
              <Sparkles className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[hsl(var(--accent))]" />
            ) : (
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            )}
            <Input
              value={filters.search}
              onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
              placeholder={
                searchMode === 'meaning'
                  ? t('closet.semanticHint')
                  : t('closet.searchPlaceholder')
              }
              className={`pl-9 ${filters.search ? 'pr-40' : 'pr-24'} rounded-xl`}
              data-testid="closet-search-input"
            />
            {/* Clear (x) button — only appears when there's text, so
                the in-input mode switch stays visible when the field
                is empty. Sits to the left of the Keyword/Meaning pill. */}
            {filters.search && (
              <button
                type="button"
                onClick={clearSearch}
                aria-label={t('closet.clearSearch', { defaultValue: 'Clear search' })}
                data-testid="closet-search-clear"
                className="absolute right-[9.25rem] top-1/2 -translate-y-1/2 h-5 w-5 rounded-full bg-muted text-muted-foreground hover:bg-foreground/15 hover:text-foreground flex items-center justify-center transition-colors"
              >
                <X className="h-3 w-3" />
              </button>
            )}
            {/* In-input mode switch */}
            <div
              className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center rounded-lg bg-secondary/70 p-0.5"
              role="radiogroup"
              aria-label={t('common.search')}
            >
              <button
                type="button"
                onClick={() => setSearchMode('keyword')}
                aria-pressed={searchMode === 'keyword'}
                data-testid="closet-search-mode-keyword"
                className={`text-[11px] px-2 py-1 rounded-md transition-colors ${
                  searchMode === 'keyword'
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t('closet.keywordSearch')}
              </button>
              <button
                type="button"
                onClick={() => setSearchMode('meaning')}
                aria-pressed={searchMode === 'meaning'}
                data-testid="closet-search-mode-meaning"
                className={`text-[11px] px-2 py-1 rounded-md transition-colors flex items-center gap-1 ${
                  searchMode === 'meaning'
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <Sparkles className="h-3 w-3" /> {t('closet.meaningSearch')}
              </button>
            </div>
          </div>
          <Select value={filters.category} onValueChange={(v) => setFilters((f) => ({ ...f, category: v }))}>
            <SelectTrigger className="w-[140px] rounded-xl" data-testid="closet-category-select">
              <SelectValue placeholder={t('closet.category')} />
            </SelectTrigger>
            <SelectContent>
              {CATEGORIES.map((c) => (
                <SelectItem key={c} value={c}>{labelForCategory(c, t)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={filters.source} onValueChange={(v) => setFilters((f) => ({ ...f, source: v }))}>
            <SelectTrigger className="w-[140px] rounded-xl" data-testid="closet-source-select">
              <SelectValue placeholder={labelForSource('all', t)} />
            </SelectTrigger>
            <SelectContent>
              {SOURCES.map((s) => (
                <SelectItem key={s} value={s}>
                  {/* Intent values get the marketplace-intent label
                      (e.g. "For sale"); source values use the
                      Private/Shared/Retail labels. */}
                  {_INTENT_VALUES.has(s) ? labelForIntent(s, t) : labelForSource(s, t)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="submit"
            variant={searchMode === 'meaning' ? 'default' : 'secondary'}
            className="rounded-xl"
            data-testid="closet-search-button"
          >
            {searchMode === 'meaning' ? <Sparkles className="h-4 w-4 me-1.5" /> : null}
            {t('common.search')}
          </Button>
        </div>
      </form>

      {/* Semantic-results banner \u2014 only shown after a successful meaning search */}
      {semanticActive && (
        <div
          className="mt-4 flex flex-wrap items-center justify-between gap-3 px-4 py-3 rounded-2xl border border-border bg-[hsl(var(--accent))]/10"
          data-testid="closet-semantic-banner"
        >
          <div className="flex items-center gap-2 text-sm">
            <Sparkles className="h-4 w-4 text-[hsl(var(--accent))]" />
            <span>
              {t('pages.closet.showing')} <span className="font-medium">{items.length}</span> semantic match
              {items.length === 1 ? '' : 'es'} across <span className="font-medium">{semanticIndexed}</span> {t('pages.closet.indexed_items')}
            </span>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={clearSemantic}
            className="rounded-lg"
            data-testid="closet-semantic-clear"
          >
            <X className="h-4 w-4 mr-1.5" /> {t('pages.closet.back_to_full_closet')}
          </Button>
        </div>
      )}

      {/* Selection action bar */}
      {selectMode && (
        <div
          // Sticky toolbar — stays pinned just under TopNav (h-16 on
          // md+) as the user scrolls through long closets, so the
          // selection count + Delete/Complete-Outfit actions are
          // always one tap away. Mobile pins to top-0 since there's
          // no TopNav. Bumped opacity + backdrop-blur + shadow so it
          // reads cleanly over the grid below.
          className="sticky top-0 md:top-16 z-20 mt-4 flex flex-wrap items-center justify-between gap-3 px-4 py-3 rounded-2xl border border-border bg-secondary/95 supports-[backdrop-filter]:bg-secondary/80 supports-[backdrop-filter]:backdrop-blur shadow-editorial"
          data-testid="closet-selection-bar"
          role="toolbar"
          aria-label={t('pages.closet.selection_actions')}
        >
          <div className="flex items-center gap-3 text-sm">
            <CheckCircle2 className="h-4 w-4 text-[hsl(var(--accent))]" />
            <span data-testid="closet-selected-count">
              <span className="font-medium">{selected.size}</span>{' '}
              of {items.length} selected
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={allVisibleSelected ? clearSelection : selectAllVisible}
              data-testid="closet-select-all-button"
              className="rounded-lg"
            >
              {allVisibleSelected ? (
                <><Square className="h-4 w-4 mr-1.5" /> {t('common.clear')}</>
              ) : (
                <><CheckSquare className="h-4 w-4 mr-1.5" /> {t('common.selectAll')}</>
              )}
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="rounded-lg"
              disabled={selected.size === 0}
              onClick={() => {
                const ids = Array.from(selected);
                const hints = items.filter((i) => selected.has(i.id));
                setCompletionAnchors(hints);
                setCompletionOpen(true);
              }}
              data-testid="closet-complete-outfit-button"
            >
              <Wand2 className="h-4 w-4 mr-1.5" />
              {t('outfitCompletion.cta')}
              {selected.size > 0 ? ` (${selected.size})` : ''}
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              className="rounded-lg"
              disabled={selected.size === 0 || deleting}
              onClick={() => setConfirmOpen(true)}
              data-testid="closet-delete-selected-button"
            >
              {deleting ? (
                <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4 mr-1.5" />
              )}
              Delete{selected.size > 0 ? ` (${selected.size})` : ''}
            </Button>
          </div>
        </div>
      )}

      {loading && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mt-5">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="rounded-[calc(var(--radius)+6px)] overflow-hidden">
              <Skeleton className="aspect-[3/4] w-full" />
              <Skeleton className="h-4 w-3/4 mt-3" />
              <Skeleton className="h-3 w-1/2 mt-2" />
            </div>
          ))}
        </div>
      )}

      {empty && (
        <div className="mt-10 text-center max-w-md mx-auto" data-testid="closet-empty-state">
          <div className="mx-auto w-40 h-40 rounded-full bg-secondary/70 mb-6 overflow-hidden">
            <img
              src="https://images.unsplash.com/photo-1654773125909-6d73f0c12407?w=600&q=80"
              alt={t('pages.closet.flat_lay_empty_state')}
              className="w-full h-full object-cover"
            />
          </div>
          <h2 className="font-display text-2xl">{t('closet.emptyTitle')}</h2>
          <p className="text-sm text-muted-foreground mt-2">
            {t('closet.emptySub')}
          </p>
          <Button asChild className="mt-5 rounded-xl" data-testid="closet-empty-add-button">
            <Link to="/closet/add"><Plus className="h-4 w-4 me-2" /> {t('closet.addItem')}</Link>
          </Button>
        </div>
      )}

      {!loading && items.length > 0 && (
        <div
          className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mt-5"
          data-testid="closet-grid"
        >
          {items.map((it) => {
            const isSelected = selected.has(it.id);
            // In selection mode we render a <button> so clicks toggle
            // without navigating; otherwise a normal <Link>.
            if (selectMode) {
              return (
                <button
                  key={it.id}
                  type="button"
                  onClick={(e) => onCardClick(e, it)}
                  aria-pressed={isSelected}
                  aria-label={`${isSelected ? 'Deselect' : 'Select'} ${it.title || 'item'}`}
                  data-testid="closet-item-card"
                  data-selected={isSelected}
                  className={`relative block text-left group rounded-[calc(var(--radius)+6px)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--accent))] ring-offset-2 ring-offset-background ${
                    isSelected ? 'ring-2 ring-[hsl(var(--accent))]' : ''
                  }`}
                >
                  <ItemCardInner item={it} isSelected={isSelected} showCheckbox score={it._score} />
                </button>
              );
            }
            return (
              <Link
                key={it.id}
                to={`/closet/${it.id}`}
                className="block group"
                data-testid="closet-item-card"
              >
                <ItemCardInner item={it} score={it._score} />
              </Link>
            );
          })}
        </div>
      )}

      {/* Mobile FAB */}
      <Link
        to="/closet/add"
        className="md:hidden fixed right-4 bottom-[104px] z-40 inline-flex items-center justify-center h-14 w-14 rounded-full bg-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))] shadow-editorial-md"
        data-testid="closet-add-item-fab"
        aria-label="Add item"
      >
        <Plus className="h-6 w-6" />
      </Link>

      {/* Confirm delete dialog */}
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent data-testid="closet-delete-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('closet.confirmDeleteTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('closet.confirmDeleteBody', { count: selected.size })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="closet-delete-cancel">{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleting}
              data-testid="closet-delete-confirm"
              className="bg-[hsl(var(--destructive,0_84%_60%))] text-white hover:opacity-90"
            >
              {deleting ? (
                <Loader2 className="h-4 w-4 me-1.5 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4 me-1.5" />
              )}
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Phase Z4 — post-"Save all" failures dialog. Reads
          ``store.lastSaveFailures`` (populated by AddItem.saveAll's
          background-sync reconciler when one or more parallel
          createItem calls reject). Shows the user a single warning
          with every failed photo's thumbnail + filename so they
          know exactly what didn't make it into the cloud closet. */}
      <SaveFailuresDialog
        failures={store.lastSaveFailures || []}
        onDismiss={() => closetStore.dismissSaveFailures()}
      />

      {/* Phase P: Outfit Completion sheet */}
      <OutfitCompletionSheet
        open={completionOpen}
        onOpenChange={setCompletionOpen}
        anchorIds={Array.from(selected)}
        anchorsHint={completionAnchors}
      />
    </div>
  );
}

/* -------------------- shared card body -------------------- */
function ItemCardInner({ item, isSelected, showCheckbox, score }) {
  const { t } = useTranslation();
  return (
    <Card
      className={`rounded-[calc(var(--radius)+6px)] overflow-hidden border-border shadow-editorial group-hover:shadow-editorial-md transition-shadow ${
        isSelected ? 'border-[hsl(var(--accent))]' : ''
      }`}
    >
      <AspectRatio ratio={3 / 4} className="bg-secondary relative">
        {(() => {
          const thumbUrl = bestImageUrl(item);
          const polishing = isCleanImagePending(item);
          if (thumbUrl) {
            return (
              <>
                <img
                  src={thumbUrl}
                  alt={item.title}
                  loading="lazy"
                  decoding="async"
                  className="w-full h-full object-cover"
                  data-testid="closet-item-thumb"
                />
                {polishing && (
                  // Phase O.6 — subtle "polishing photo…" affordance
                  // while the backend's background rembg matte is
                  // running. The closet poll (Closet.jsx top-level)
                  // will swap the image in-place when status flips
                  // to "ready".
                  <div
                    className="absolute inset-0 flex items-end justify-start p-2 pointer-events-none"
                    data-testid="closet-item-polishing"
                  >
                    <Badge
                      variant="outline"
                      className="bg-background/85 backdrop-blur text-[10px] border-[hsl(var(--accent))]/40 animate-pulse"
                    >
                      {t('item.polishingPhoto', { defaultValue: 'Polishing photo…' })}
                    </Badge>
                  </div>
                )}
              </>
            );
          }
          if (item.dpp_data) {
            return (
              <div
                className="w-full h-full flex flex-col items-center justify-center gap-1.5 bg-gradient-to-br from-[hsl(var(--accent))]/10 to-muted text-muted-foreground"
                data-testid="closet-item-dpp-placeholder"
              >
                <QrCode className="h-7 w-7 text-[hsl(var(--accent))]/70" />
                <span className="caps-label text-[10px]">DPP</span>
              </div>
            );
          }
          return (
            <div className="w-full h-full flex items-center justify-center text-muted-foreground caps-label">
              {t('market.noImage')}
            </div>
          );
        })()}
        {typeof score === 'number' && (
          <Badge
            variant="outline"
            className="absolute top-2 right-2 bg-background/85 backdrop-blur text-[10px] border-[hsl(var(--accent))]/50 flex items-center gap-1"
            data-testid="closet-item-score"
          >
            <Sparkles className="h-2.5 w-2.5 text-[hsl(var(--accent))]" />
            {Math.round(score * 100)}%
          </Badge>
        )}
        {showCheckbox && (
          <div
            className={`absolute top-2 left-2 h-6 w-6 rounded-full flex items-center justify-center border-2 transition-colors ${
              isSelected
                ? 'bg-[hsl(var(--accent))] border-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))]'
                : 'bg-background/80 border-border backdrop-blur'
            }`}
            aria-hidden="true"
            data-testid={isSelected ? 'closet-item-selected-mark' : 'closet-item-unselected-mark'}
          >
            {isSelected ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : (
              <Circle className="h-4 w-4 text-muted-foreground opacity-0" />
            )}
          </div>
        )}
        {showCheckbox && isSelected && (
          <div className="absolute inset-0 bg-[hsl(var(--accent))]/10 pointer-events-none" />
        )}
        {/* Phase Z2 — red ⭐ overlay marks items the user explicitly
            kept as duplicates of an existing closet entry. The
            Stylist Brain filters these out of recommendations, so
            this badge tells the user "yes, I have this twice, but
            outfit suggestions won't double-count it." */}
        {item.is_duplicate && (
          <div
            className={`absolute ${typeof score === 'number' ? 'top-10' : 'top-2'} right-2 h-7 w-7 rounded-full bg-rose-600 text-white flex items-center justify-center shadow-md ring-2 ring-background`}
            title={t('closet.duplicateBadge', {
              defaultValue:
                'Marked as a duplicate — kept on purpose, hidden from outfit suggestions.',
            })}
            data-testid="closet-item-duplicate-star"
          >
            <Star className="h-3.5 w-3.5 fill-white" />
          </div>
        )}
        {/* Phase Z4 — pulsing sparkle marks items that were just
            saved optimistically and are still syncing to the server.
            Disappears the moment the canonical server item replaces
            the ghost in ``closetStore``. The animation is a soft
            opacity/scale pulse (not a spin, which reads as "error"
            in fashion-app context); pointer-events-none so it never
            blocks the card's link. */}
        {item._pendingSync && (
          <div
            className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-1.5 px-2 py-1.5 pointer-events-none bg-gradient-to-t from-background/95 via-background/80 to-transparent"
            data-testid="closet-item-pending-sync"
            aria-live="polite"
            aria-label={t('closet.pendingSync', { defaultValue: 'Syncing…' })}
          >
            <span className="relative inline-flex h-3 w-3">
              <span className="absolute inset-0 rounded-full bg-[hsl(var(--accent))] opacity-60 animate-ping" />
              <Sparkles className="relative h-3 w-3 text-[hsl(var(--accent))] animate-pulse" />
            </span>
            <span className="text-[10px] font-medium uppercase tracking-wider text-[hsl(var(--accent))]">
              {t('closet.pendingSync', { defaultValue: 'Syncing' })}
            </span>
          </div>
        )}
      </AspectRatio>
      <CardContent className="p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="font-medium text-sm truncate">{item.title}</div>
          <SourceTagBadge source={item.source} intent={item.marketplace_intent} />
        </div>
        <div className="text-xs text-muted-foreground mt-1">
          {[labelForCategory(item.category, t), item.color].filter(Boolean).join(' · ')}
        </div>
        {/* Auto-list "Complete listing" CTA — appears when an item
            has been auto-listed (Private→Shared toggle) and the user
            hasn't yet refined the listing's price / mode / description.
            One tap takes them to the edit-listing form. */}
        {item.auto_listing_needs_completion && item.auto_listing_id && (
          <Link
            to={`/marketplace/listing/${item.auto_listing_id}/edit`}
            data-testid="closet-item-complete-listing-cta"
            className="mt-2 flex items-center justify-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold py-1.5 rounded-md bg-[hsl(var(--accent))]/12 text-[hsl(var(--accent))] hover:bg-[hsl(var(--accent))]/20 transition-colors"
          >
            <Sparkles className="h-3 w-3" />
            {t('closet.completeListingCta', { defaultValue: 'Complete listing' })}
          </Link>
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------- Save-all failures dialog (Phase Z4) -------------------- */
/**
 * One-shot warning surfaced on the Closet page when one or more
 * items from the most recent "Save all" batch couldn't be persisted
 * to the server. The optimistic ghosts have already been pulled
 * from ``closetStore`` by the reconciler; this dialog is the
 * acknowledgement step that tells the user *which* photos didn't
 * make it, with thumbnails so they recognise them at a glance.
 *
 * Closes on dismiss; the underlying ``lastSaveFailures`` array on
 * the store is then cleared. Idempotent — re-rendering with an
 * empty array no-ops.
 */
function SaveFailuresDialog({ failures, onDismiss }) {
  const { t } = useTranslation();
  const open = Array.isArray(failures) && failures.length > 0;
  return (
    <AlertDialog
      open={open}
      onOpenChange={(o) => { if (!o) onDismiss(); }}
    >
      <AlertDialogContent
        className="max-w-md"
        data-testid="closet-save-failures-dialog"
      >
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" aria-hidden />
            {t('closet.saveFailuresTitle', {
              count: failures.length,
              defaultValue:
                failures.length === 1
                  ? "1 photo didn't make it"
                  : `${failures.length} photos didn't make it`,
            })}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {t('closet.saveFailuresBody', {
              defaultValue:
                'These items couldn\u2019t be saved to your closet. Please try uploading them again.',
            })}
          </AlertDialogDescription>
        </AlertDialogHeader>

        <ul
          className="max-h-72 overflow-y-auto -mx-2 px-2 space-y-2 py-1"
          data-testid="closet-save-failures-list"
        >
          {failures.map((f) => (
            <li
              key={f.id}
              className="flex items-center gap-3 rounded-lg border border-border bg-card/50 p-2"
            >
              <div className="relative shrink-0 h-14 w-14 overflow-hidden rounded-md bg-muted">
                {f.thumbnail ? (
                  <img
                    src={f.thumbnail}
                    alt=""
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="h-full w-full flex items-center justify-center text-muted-foreground">
                    <AlertTriangle className="h-5 w-5" aria-hidden />
                  </div>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div
                  className="truncate text-sm font-medium"
                  title={f.title}
                >
                  {f.title || t('closet.saveFailuresUnnamed', { defaultValue: 'Untitled item' })}
                </div>
                {f.filename && (
                  <div
                    className="truncate text-[11px] text-muted-foreground"
                    title={f.filename}
                  >
                    {f.filename}
                  </div>
                )}
                {f.error && (
                  <div
                    className="truncate text-[11px] text-amber-600 dark:text-amber-400"
                    title={f.error}
                  >
                    {f.error}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>

        <AlertDialogFooter>
          <AlertDialogAction
            onClick={onDismiss}
            data-testid="closet-save-failures-dismiss"
          >
            {t('common.gotIt', { defaultValue: 'Got it' })}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

