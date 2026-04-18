import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent } from '@/components/ui/card';
import { api } from '@/lib/api';
import { toast } from 'sonner';

const CATEGORIES = ['top', 'bottom', 'outerwear', 'shoes', 'accessory', 'dress'];
const FORMALITIES = ['casual', 'smart-casual', 'business', 'formal'];
const SOURCES = ['Private', 'Shared', 'Retail'];

const fileToBase64 = (file) =>
  new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onerror = reject;
    r.onload = () => {
      const s = String(r.result || '');
      const comma = s.indexOf(',');
      resolve(comma >= 0 ? s.slice(comma + 1) : s);
    };
    r.readAsDataURL(file);
  });

export default function AddItem() {
  const nav = useNavigate();
  const [form, setForm] = useState({
    title: '', category: 'top', color: '', brand: '', formality: 'smart-casual',
    source: 'Private', tags: '', notes: '', original_image_url: '',
  });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.title) { toast.error('Title is required'); return; }
    setBusy(true);
    try {
      const body = {
        source: form.source,
        category: form.category,
        title: form.title,
        brand: form.brand || null,
        color: form.color || null,
        formality: form.formality || null,
        notes: form.notes || null,
        tags: form.tags ? form.tags.split(',').map((t) => t.trim()).filter(Boolean) : [],
      };
      if (file) {
        body.image_base64 = await fileToBase64(file);
        body.image_mime = file.type || 'image/jpeg';
      } else if (form.original_image_url) {
        body.original_image_url = form.original_image_url;
      }
      const created = await api.createItem(body);
      toast.success(`Added “${created.title}”`);
      nav(`/closet/${created.id}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not save item');
    } finally { setBusy(false); }
  };

  return (
    <div className="container-px max-w-2xl mx-auto pt-4 md:pt-10">
      <button onClick={() => nav(-1)} className="inline-flex items-center text-sm text-muted-foreground mb-4" data-testid="additem-back">
        <ArrowLeft className="h-4 w-4 mr-1" /> Back
      </button>
      <h1 className="font-display text-3xl md:text-4xl">Add to closet</h1>
      <p className="text-sm text-muted-foreground mt-1">Upload a photo or paste a URL. Segmentation runs automatically.</p>

      <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial mt-6">
        <CardContent className="p-6">
          <form onSubmit={submit} className="space-y-5" data-testid="add-item-form">
            <div>
              <Label>Photo (optional)</Label>
              <label className="mt-2 flex flex-col items-center justify-center border-2 border-dashed border-border rounded-xl p-6 text-sm text-muted-foreground cursor-pointer hover:bg-secondary/50 transition-colors" data-testid="add-item-upload-button">
                <input type="file" accept="image/*" className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] || null)} />
                {file ? (
                  <span className="font-medium text-foreground truncate max-w-full">{file.name}</span>
                ) : (
                  <>
                    <Upload className="h-6 w-6 mb-1" />
                    <span>Click to select an image</span>
                  </>
                )}
              </label>
              <div className="caps-label text-muted-foreground mt-3">or paste a URL</div>
              <Input value={form.original_image_url}
                onChange={(e) => setForm({ ...form, original_image_url: e.target.value })}
                placeholder="https://..." className="mt-2 rounded-xl" data-testid="add-item-url-input" />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="title">Title</Label>
                <Input id="title" required value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="White Oxford Shirt" className="rounded-xl" data-testid="add-item-title-input" />
              </div>
              <div>
                <Label htmlFor="brand">Brand</Label>
                <Input id="brand" value={form.brand}
                  onChange={(e) => setForm({ ...form, brand: e.target.value })}
                  placeholder="Uniqlo" className="rounded-xl" data-testid="add-item-brand-input" />
              </div>
              <div>
                <Label>Category</Label>
                <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                  <SelectTrigger className="rounded-xl" data-testid="add-item-category-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label>Formality</Label>
                <Select value={form.formality} onValueChange={(v) => setForm({ ...form, formality: v })}>
                  <SelectTrigger className="rounded-xl" data-testid="add-item-formality-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{FORMALITIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="color">Color</Label>
                <Input id="color" value={form.color}
                  onChange={(e) => setForm({ ...form, color: e.target.value })}
                  placeholder="white" className="rounded-xl" data-testid="add-item-color-input" />
              </div>
              <div>
                <Label>Source</Label>
                <Select value={form.source} onValueChange={(v) => setForm({ ...form, source: v })}>
                  <SelectTrigger className="rounded-xl" data-testid="add-item-source-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{SOURCES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label htmlFor="tags">Tags</Label>
              <Input id="tags" value={form.tags}
                onChange={(e) => setForm({ ...form, tags: e.target.value })}
                placeholder="oxford, office, layerable" className="rounded-xl" data-testid="add-item-tags-input" />
              <p className="text-xs text-muted-foreground mt-1">Comma-separated.</p>
            </div>

            <div>
              <Label htmlFor="notes">Notes</Label>
              <Textarea id="notes" value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                rows={3} className="rounded-xl" data-testid="add-item-notes-input" />
            </div>

            <Button type="submit" disabled={busy} className="w-full rounded-xl" data-testid="add-item-save-button">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save to closet'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
