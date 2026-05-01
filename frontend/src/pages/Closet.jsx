import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Plus, Search, Trash2, CheckCircle2, Circle, X, CheckSquare,
  Square, Loader2, ListChecks, Sparkles, Wand2, QrCode, Star,
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
import { labelForCategory, labelForSource } from '@/lib/taxonomy';
import { toast } from 'sonner';

const CATEGORIES = ['all', 'top', 'bottom', 'outerwear', 'shoes', 'accessory', 'dress'];
const SOURCES = ['all', 'Private', 'Shared', 'Retail'];

// --- Module-level cache (stale-while-revalidate) -----------------------
// Navigating away from /closet and back used to re-fetch the entire
// response (25+ MB once items have reconstructed images). With this
// cache the grid paints instantly from the last known snapshot and a
// background refresh replaces it when the server responds.
const CLOSET_CACHE = {
  // cache key -> { items, total, ts }
  entries: new Map(),
  key(filters) {
    return `${filters.category}|${filters.source}|${filters.search || ''}`;
  },
  get(filters) { return this.entries.get(this.key(filters)); },
  set(filters, items, total) {
    this.entries.set(this.key(filters), { items, total, ts: Date.now() });
  },
  patch(filters, updater) {
    const e = this.entries.get(this.key(filters));
    if (e) e.items = updater(e.items);
  },
  invalidate() { this.entries.clear(); },
};

export default function Closet() {
  const { t } = useTranslation();
  const initialFilters = { category: 'all', source: 'all', search: '' };
  const initialCached = CLOSET_CACHE.get(initialFilters);
  const [items, setItems] = useState(initialCached?.items || []);
  const [total, setTotal] = useState(initialCached?.total || 0);
  // Only show the big loading skeleton when we have no cached snapshot;
  // otherwise paint the cached grid immediately and revalidate silently.
  const [loading, setLoading] = useState(!initialCached);
  const [filters, setFilters] = useState(initialFilters);
  // Search mode: 'keyword' uses Mongo text search, 'meaning' calls FashionCLIP.
  const [searchMode, setSearchMode] = useState('keyword');
  const [semanticActive, setSemanticActive] = useState(false); // true while the current list is semantic results
  const [semanticIndexed, setSemanticIndexed] = useState(0);

  // Selection state
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // Outfit completion sheet (Phase P)
  const [completionOpen, setCompletionOpen] = useState(false);
  const [completionAnchors, setCompletionAnchors] = useState([]);

  const fetchItems = useCallback(async () => {
    // Only show the skeleton when we have no cached data to paint.
    const cached = CLOSET_CACHE.get(filters);
    if (!cached) setLoading(true);
    setSemanticActive(false);
    try {
      const params = {};
      if (filters.category !== 'all') params.category = filters.category;
      if (filters.source !== 'all') params.source = filters.source;
      if (filters.search) params.search = filters.search;
      const res = await api.listCloset(params);
      const nextItems = res.items || [];
      const nextTotal = res.total || 0;
      setItems(nextItems);
      setTotal(nextTotal);
      CLOSET_CACHE.set(filters, nextItems, nextTotal);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load closet');
    } finally { setLoading(false); }
  }, [filters]);

  const fetchSemantic = useCallback(async (text) => {
    setLoading(true);
    try {
      const res = await api.searchCloset({ text, limit: 48, min_score: 0.18 });
      setItems(res.items || []);
      setTotal(res.total || 0);
      setSemanticIndexed(res.indexed || 0);
      setSemanticActive(true);
      if ((res.items || []).length === 0) {
        toast.message('No meaningful matches found \u2014 try different words.');
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Semantic search failed.');
      setSemanticActive(false);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchItems(); }, [filters.category, filters.source, fetchItems]);

  // Debounced live-search for keyword mode — typing updates the
  // closet grid after ~300 ms of inactivity, matching standard
  // search-bar UX so the user doesn't have to hit Enter. We
  // deliberately skip this for ``meaning`` mode because the
  // semantic search hits an LLM-grade endpoint that's expensive to
  // call per keystroke; users still submit that one explicitly via
  // the Search button.
  useEffect(() => {
    if (searchMode !== 'keyword') return undefined;
    // Skip the initial mount fire for empty searches — the main
    // ``fetchItems`` effect above already runs on mount.
    const handle = setTimeout(() => { fetchItems(); }, 300);
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
      toast.error('Could not delete the selected items');
    }
    // Remove successfully deleted items from UI; refresh total to be safe.
    const okIds = new Set(
      ids.filter((_, idx) => results[idx].status === 'fulfilled')
    );
    setItems((prev) => prev.filter((it) => !okIds.has(it.id)));
    CLOSET_CACHE.patch(filters, (arr) => arr.filter((it) => !okIds.has(it.id)));
    setSelected(new Set());
    setSelectMode(false);
    // Reconcile total in the background.
    fetchItems();
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
                aria-label={t('common.clear', { defaultValue: 'Clear search' })}
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
            <SelectTrigger className="w-[120px] rounded-xl" data-testid="closet-source-select">
              <SelectValue placeholder={labelForSource('all', t)} />
            </SelectTrigger>
            <SelectContent>
              {SOURCES.map((s) => (
                <SelectItem key={s} value={s}>{labelForSource(s, t)}</SelectItem>
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
              Showing <span className="font-medium">{items.length}</span> semantic match
              {items.length === 1 ? '' : 'es'} across <span className="font-medium">{semanticIndexed}</span> indexed items.
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
            <X className="h-4 w-4 mr-1.5" /> Back to full closet
          </Button>
        </div>
      )}

      {/* Selection action bar */}
      {selectMode && (
        <div
          className="mt-4 flex flex-wrap items-center justify-between gap-3 px-4 py-3 rounded-2xl border border-border bg-secondary/60"
          data-testid="closet-selection-bar"
          role="toolbar"
          aria-label="Selection actions"
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
              alt="Flat lay empty state"
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
        {(item.thumbnail_data_url || item.reconstructed_image_url || item.segmented_image_url || item.original_image_url) ? (
          <img
            src={item.thumbnail_data_url || item.reconstructed_image_url || item.segmented_image_url || item.original_image_url}
            alt={item.title}
            loading="lazy"
            decoding="async"
            className="w-full h-full object-cover"
          />
        ) : item.dpp_data ? (
          <div
            className="w-full h-full flex flex-col items-center justify-center gap-1.5 bg-gradient-to-br from-[hsl(var(--accent))]/10 to-muted text-muted-foreground"
            data-testid="closet-item-dpp-placeholder"
          >
            <QrCode className="h-7 w-7 text-[hsl(var(--accent))]/70" />
            <span className="caps-label text-[10px]">DPP</span>
          </div>
        ) : (
          <div className="w-full h-full flex items-center justify-center text-muted-foreground caps-label">
            {t('market.noImage')}
          </div>
        )}
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
      </AspectRatio>
      <CardContent className="p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="font-medium text-sm truncate">{item.title}</div>
          <SourceTagBadge source={item.source} />
        </div>
        <div className="text-xs text-muted-foreground mt-1">
          {[labelForCategory(item.category, t), item.color].filter(Boolean).join(' · ')}
        </div>
      </CardContent>
    </Card>
  );
}
