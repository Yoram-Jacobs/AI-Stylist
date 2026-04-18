import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { AspectRatio } from '@/components/ui/aspect-ratio';
import { SourceTagBadge } from '@/components/SourceTagBadge';
import { api } from '@/lib/api';
import { toast } from 'sonner';

const CATEGORIES = ['all', 'top', 'bottom', 'outerwear', 'shoes', 'accessory', 'dress'];
const SOURCES = ['all', 'Private', 'Shared', 'Retail'];

export default function Closet() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ category: 'all', source: 'all', search: '' });

  const fetchItems = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.category !== 'all') params.category = filters.category;
      if (filters.source !== 'all') params.source = filters.source;
      if (filters.search) params.search = filters.search;
      const res = await api.listCloset(params);
      setItems(res.items || []);
      setTotal(res.total || 0);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load closet');
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchItems(); /* eslint-disable-next-line */ }, [filters.category, filters.source]);

  const onSearch = (e) => {
    e.preventDefault();
    fetchItems();
  };

  const empty = !loading && items.length === 0;

  return (
    <div className="container-px max-w-6xl mx-auto pt-6 md:pt-10">
      <header className="flex items-end justify-between mb-6">
        <div>
          <div className="caps-label text-muted-foreground">Your wardrobe</div>
          <h1 className="font-display text-3xl sm:text-4xl mt-1">Closet <span className="text-muted-foreground font-body text-base align-middle ml-2" data-testid="closet-total">({total})</span></h1>
        </div>
        <Button asChild className="rounded-xl hidden md:inline-flex" data-testid="closet-add-item-button">
          <Link to="/closet/add"><Plus className="h-4 w-4 mr-2" /> Add item</Link>
        </Button>
      </header>

      <form onSubmit={onSearch} className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border -mx-4 px-4 py-3 md:mx-0 md:px-0 md:py-4" data-testid="closet-filter-bar">
        <div className="flex flex-wrap gap-2 items-center">
          <div className="relative flex-1 min-w-[180px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input value={filters.search}
              onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
              placeholder="Search by title, brand, tag" className="pl-9 rounded-xl"
              data-testid="closet-search-input" />
          </div>
          <Select value={filters.category} onValueChange={(v) => setFilters((f) => ({ ...f, category: v }))}>
            <SelectTrigger className="w-[140px] rounded-xl" data-testid="closet-category-select">
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={filters.source} onValueChange={(v) => setFilters((f) => ({ ...f, source: v }))}>
            <SelectTrigger className="w-[120px] rounded-xl" data-testid="closet-source-select">
              <SelectValue placeholder="Source" />
            </SelectTrigger>
            <SelectContent>{SOURCES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
          </Select>
          <Button type="submit" variant="secondary" className="rounded-xl" data-testid="closet-search-button">Search</Button>
        </div>
      </form>

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
            <img src="https://images.unsplash.com/photo-1654773125909-6d73f0c12407?w=600&q=80"
              alt="Flat lay empty state" className="w-full h-full object-cover" />
          </div>
          <h2 className="font-display text-2xl">Your closet starts here</h2>
          <p className="text-sm text-muted-foreground mt-2">Add your first piece — DressApp will tag it and keep it ready for styling, sharing, or listing.</p>
          <Button asChild className="mt-5 rounded-xl" data-testid="closet-empty-add-button">
            <Link to="/closet/add"><Plus className="h-4 w-4 mr-2" /> Add an item</Link>
          </Button>
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mt-5" data-testid="closet-grid">
          {items.map((it) => (
            <Link key={it.id} to={`/closet/${it.id}`} className="block group" data-testid="closet-item-card">
              <Card className="rounded-[calc(var(--radius)+6px)] overflow-hidden border-border shadow-editorial group-hover:shadow-editorial-md transition-shadow">
                <AspectRatio ratio={3 / 4} className="bg-secondary">
                  {(it.segmented_image_url || it.original_image_url) ? (
                    <img src={it.segmented_image_url || it.original_image_url}
                      alt={it.title} className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-muted-foreground caps-label">No image</div>
                  )}
                </AspectRatio>
                <CardContent className="p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-sm truncate">{it.title}</div>
                    <SourceTagBadge source={it.source} />
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {[it.category, it.color].filter(Boolean).join(' · ')}
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {/* Mobile FAB */}
      <Link to="/closet/add"
        className="md:hidden fixed right-4 bottom-[104px] z-40 inline-flex items-center justify-center h-14 w-14 rounded-full bg-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))] shadow-editorial-md"
        data-testid="closet-add-item-fab"
        aria-label="Add item">
        <Plus className="h-6 w-6" />
      </Link>
    </div>
  );
}
