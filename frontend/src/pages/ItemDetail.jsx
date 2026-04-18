import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Sparkles, Trash2, Store, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AspectRatio } from '@/components/ui/aspect-ratio';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle, AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Input } from '@/components/ui/input';
import { SourceTagBadge } from '@/components/SourceTagBadge';
import { api } from '@/lib/api';
import { toast } from 'sonner';

export default function ItemDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [item, setItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editPrompt, setEditPrompt] = useState('');
  const [editing, setEditing] = useState(false);

  const load = async () => {
    try { setItem(await api.getItem(id)); }
    catch (err) { toast.error(err?.response?.data?.detail || 'Item not found'); nav('/closet'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const onEdit = async () => {
    if (!editPrompt.trim()) return;
    setEditing(true);
    try {
      const res = await api.editItemImage(id, editPrompt.trim());
      toast.success('New variant generated');
      setItem((it) => ({ ...it, variants: res.variants }));
      setEditPrompt('');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Image edit unavailable');
    } finally { setEditing(false); }
  };

  const onDelete = async () => {
    try {
      await api.deleteItem(id);
      toast.success('Item removed');
      nav('/closet');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Delete failed');
    }
  };

  if (loading || !item) {
    return (
      <div className="container-px max-w-4xl mx-auto pt-6">
        <div className="aspect-[3/4] w-full rounded-[calc(var(--radius)+6px)] shimmer" />
      </div>
    );
  }

  const mainImage = item.segmented_image_url || item.original_image_url;

  return (
    <div className="container-px max-w-4xl mx-auto pt-4 md:pt-10">
      <button onClick={() => nav(-1)} className="inline-flex items-center text-sm text-muted-foreground mb-4" data-testid="item-back">
        <ArrowLeft className="h-4 w-4 mr-1" /> Back
      </button>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
        <div className="md:col-span-3">
          <Card className="rounded-[calc(var(--radius)+6px)] overflow-hidden shadow-editorial">
            <AspectRatio ratio={3 / 4} className="bg-secondary">
              {mainImage
                ? <img src={mainImage} alt={item.title} className="w-full h-full object-cover" />
                : <div className="w-full h-full flex items-center justify-center text-muted-foreground">No image</div>}
            </AspectRatio>
          </Card>

          {item.variants && item.variants.length > 0 && (
            <div className="mt-4">
              <div className="caps-label text-muted-foreground mb-2">Variants</div>
              <div className="flex gap-3 overflow-x-auto pb-2" data-testid="item-variant-carousel">
                {item.variants.map((v, i) => (
                  <a key={i} href={v.url} target="_blank" rel="noreferrer" className="flex-shrink-0 w-32">
                    <div className="aspect-[3/4] rounded-xl overflow-hidden border border-border">
                      <img src={v.url} alt={v.prompt} className="w-full h-full object-cover" />
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1 truncate">{v.prompt}</div>
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="md:col-span-2 space-y-4">
          <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
            <CardContent className="p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h1 className="font-display text-2xl leading-tight">{item.title}</h1>
                  <div className="text-sm text-muted-foreground mt-1">{[item.brand, item.category, item.color].filter(Boolean).join(' · ')}</div>
                </div>
                <SourceTagBadge source={item.source} />
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {item.formality && <Badge variant="outline" className="caps-label rounded-full">{item.formality}</Badge>}
                {(item.tags || []).map((t) => (
                  <Badge key={t} variant="secondary" className="rounded-full">{t}</Badge>
                ))}
              </div>
              {item.notes && <p className="text-sm text-muted-foreground mt-4">{item.notes}</p>}
            </CardContent>
          </Card>

          <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial" data-testid="item-edit-image-card">
            <CardContent className="p-5 space-y-3">
              <div className="caps-label text-muted-foreground">Generate variant</div>
              <p className="text-sm text-muted-foreground">Describe a change: color, fabric, silhouette. We'll create a generative preview.</p>
              <Input value={editPrompt}
                onChange={(e) => setEditPrompt(e.target.value)}
                placeholder="same shirt in deep navy" className="rounded-xl" data-testid="item-edit-prompt-input" />
              <Button onClick={onEdit} disabled={editing || !editPrompt.trim()} className="w-full rounded-xl" data-testid="item-generate-variant-button">
                {editing ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Sparkles className="h-4 w-4 mr-2" /> Generate variant</>}
              </Button>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-3">
            <Button asChild variant="secondary" className="rounded-xl" data-testid="item-list-for-sale">
              <Link to={`/market/create?itemId=${item.id}`}><Store className="h-4 w-4 mr-2" /> List for sale</Link>
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" className="rounded-xl" data-testid="item-delete-button">
                  <Trash2 className="h-4 w-4 mr-2" /> Delete
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Remove from closet?</AlertDialogTitle>
                  <AlertDialogDescription>This can't be undone.</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={onDelete} data-testid="item-delete-confirm">Delete</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </div>
    </div>
  );
}
