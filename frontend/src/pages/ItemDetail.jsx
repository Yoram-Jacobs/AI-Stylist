import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft,
  Sparkles,
  Trash2,
  Store,
  Loader2,
  Wand2,
  Mic,
  Square,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AspectRatio } from '@/components/ui/aspect-ratio';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { SourceTagBadge } from '@/components/SourceTagBadge';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';
import { isSTTSupported, createRecognition } from '@/lib/speech';

export default function ItemDetail() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { id } = useParams();
  const nav = useNavigate();
  const [item, setItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editPrompt, setEditPrompt] = useState('');
  const [editing, setEditing] = useState(false);
  // Phase Q — Repair state
  const [repairHint, setRepairHint] = useState('');
  const [repairing, setRepairing] = useState(false);
  const [dictating, setDictating] = useState(false);
  const [dictationInterim, setDictationInterim] = useState('');
  const [showingOriginal, setShowingOriginal] = useState(false);
  const recognitionRef = useRef(null);
  const sttSupported = useRef(isSTTSupported());

  const load = async () => {
    try {
      setItem(await api.getItem(id));
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('itemDetail.notFound'));
      nav('/closet');
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    load();
  }, [id]);

  useEffect(
    () => () => {
      try {
        recognitionRef.current?.abort?.();
      } catch {
        /* ignore */
      }
    },
    [],
  );

  const onEdit = async () => {
    if (!editPrompt.trim()) return;
    setEditing(true);
    try {
      const res = await api.editItemImage(id, editPrompt.trim());
      toast.success(t('itemDetail.variantGenerated'));
      setItem((it) => ({ ...it, variants: res.variants }));
      setEditPrompt('');
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('itemDetail.editUnavailable'));
    } finally {
      setEditing(false);
    }
  };

  /* ---------- Phase Q: repair flow ---------- */
  const onRepair = async () => {
    if (repairing) return;
    setRepairing(true);
    setShowingOriginal(false);
    try {
      const res = await api.repairItemImage(id, {
        userHint: repairHint.trim() || null,
      });
      if (res.applied) {
        toast.success(t('itemDetail.repair.success'));
        setItem(res.item);
        setRepairHint('');
      } else {
        // Validation rejected — category drifted or HF hiccup.
        toast.warning(
          res.detail || t('itemDetail.repair.rejected'),
        );
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('itemDetail.repair.error'));
    } finally {
      setRepairing(false);
    }
  };

  const startDictation = () => {
    if (!sttSupported.current) return;
    const rec = createRecognition({
      lang: user?.preferred_language || 'en',
      onInterim: (txt) => setDictationInterim(txt || ''),
      onFinal: (finalText) => {
        if (finalText) {
          setRepairHint((prev) =>
            prev ? `${prev} ${finalText}`.slice(0, 240) : finalText.slice(0, 240),
          );
        }
      },
      onEnd: () => {
        setDictating(false);
        setDictationInterim('');
        recognitionRef.current = null;
      },
      onError: () => {
        toast.error(t('stylist.micDenied'));
      },
    });
    if (!rec) return;
    recognitionRef.current = rec;
    rec.start();
    setDictating(true);
  };

  const stopDictation = () => {
    try {
      recognitionRef.current?.stop?.();
    } catch {
      /* ignore */
    }
  };

  const onDelete = async () => {
    try {
      await api.deleteItem(id);
      toast.success(t('itemDetail.deleted'));
      nav('/closet');
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('closet.deleteFailed'));
    }
  };

  if (loading || !item) {
    return (
      <div className="container-px max-w-4xl mx-auto pt-6">
        <div className="aspect-[3/4] w-full rounded-[calc(var(--radius)+6px)] shimmer" />
      </div>
    );
  }

  const hasReconstruction = !!item.reconstructed_image_url;
  // Precedence: reconstructed (Phase Q) > segmented > original.
  const preferredImage =
    (!showingOriginal && item.reconstructed_image_url) ||
    item.segmented_image_url ||
    item.original_image_url;
  const reconstructionReasons =
    (item.reconstruction_metadata && item.reconstruction_metadata.reasons) || [];

  return (
    <div className="container-px max-w-4xl mx-auto pt-4 md:pt-10">
      <button
        onClick={() => nav(-1)}
        className="inline-flex items-center text-sm text-muted-foreground mb-4"
        data-testid="item-back"
      >
        <ArrowLeft className="h-4 w-4 me-1 rtl:rotate-180" /> {t('common.back')}
      </button>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
        <div className="md:col-span-3">
          <Card className="rounded-[calc(var(--radius)+6px)] overflow-hidden shadow-editorial relative">
            <AspectRatio ratio={3 / 4} className="bg-secondary">
              {preferredImage ? (
                <img
                  src={preferredImage}
                  alt={item.title}
                  className="w-full h-full object-cover"
                  data-testid="item-detail-main-image"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-muted-foreground">
                  {t('itemDetail.noImage')}
                </div>
              )}
            </AspectRatio>
            {hasReconstruction && (
              <>
                <div
                  className="absolute top-3 start-3 inline-flex items-center gap-1.5 rounded-full bg-background/90 backdrop-blur border border-border px-2.5 py-1 text-[11px] font-semibold"
                  data-testid="item-detail-repaired-badge"
                >
                  <Wand2 className="h-3 w-3 text-[hsl(var(--accent))]" />
                  {showingOriginal
                    ? t('itemDetail.repair.showingOriginal')
                    : t('itemDetail.repair.showingRepaired')}
                </div>
                <button
                  type="button"
                  onClick={() => setShowingOriginal((s) => !s)}
                  className="absolute top-3 end-3 inline-flex items-center gap-1.5 rounded-full bg-background/90 backdrop-blur border border-border px-2.5 py-1 text-[11px] font-medium hover:bg-secondary transition-colors"
                  data-testid="item-detail-toggle-reconstruction"
                  aria-label={
                    showingOriginal
                      ? t('itemDetail.repair.showRepaired')
                      : t('itemDetail.repair.showOriginal')
                  }
                >
                  <RefreshCw className="h-3 w-3" />
                  {showingOriginal
                    ? t('itemDetail.repair.showRepaired')
                    : t('itemDetail.repair.showOriginal')}
                </button>
              </>
            )}
          </Card>

          {item.variants && item.variants.length > 0 && (
            <div className="mt-4">
              <div className="caps-label text-muted-foreground mb-2">
                {t('itemDetail.variants')}
              </div>
              <div className="flex gap-3 overflow-x-auto pb-2" data-testid="item-variant-carousel">
                {item.variants.map((v, i) => (
                  <a
                    key={i}
                    href={v.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex-shrink-0 w-32"
                  >
                    <div className="aspect-[3/4] rounded-xl overflow-hidden border border-border">
                      <img src={v.url} alt={v.prompt} className="w-full h-full object-cover" />
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1 truncate">
                      {v.prompt}
                    </div>
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
                  <div className="text-sm text-muted-foreground mt-1">
                    {[item.brand, item.category, item.color].filter(Boolean).join(' · ')}
                  </div>
                </div>
                <SourceTagBadge source={item.source} />
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {item.formality && (
                  <Badge variant="outline" className="caps-label rounded-full">
                    {item.formality}
                  </Badge>
                )}
                {(item.tags || []).map((tag) => (
                  <Badge key={tag} variant="secondary" className="rounded-full">
                    {tag}
                  </Badge>
                ))}
              </div>
              {item.notes && <p className="text-sm text-muted-foreground mt-4">{item.notes}</p>}
            </CardContent>
          </Card>

          {/* Phase Q — Repair Image Card */}
          <Card
            className="rounded-[calc(var(--radius)+6px)] shadow-editorial"
            data-testid="item-repair-card"
          >
            <CardContent className="p-5 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="caps-label text-muted-foreground">
                  {t('itemDetail.repair.label')}
                </div>
                {reconstructionReasons.length > 0 && (
                  <Badge
                    variant="outline"
                    className="text-[10px] py-0 h-5 rounded-full"
                    data-testid="item-repair-reasons-badge"
                  >
                    {reconstructionReasons.join(', ')}
                  </Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                {t('itemDetail.repair.subtitle')}
              </p>

              <div className="relative">
                <Textarea
                  value={dictating ? dictationInterim || repairHint : repairHint}
                  onChange={(e) => setRepairHint(e.target.value.slice(0, 240))}
                  placeholder={t('itemDetail.repair.hintPlaceholder')}
                  rows={2}
                  className="rounded-xl resize-none pe-12"
                  data-testid="item-repair-hint-input"
                  disabled={repairing}
                />
                {sttSupported.current && (
                  <button
                    type="button"
                    onClick={dictating ? stopDictation : startDictation}
                    disabled={repairing}
                    className={`absolute end-2 bottom-2 inline-flex h-8 w-8 items-center justify-center rounded-full border border-border transition-colors ${
                      dictating
                        ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
                        : 'bg-card hover:bg-secondary'
                    }`}
                    data-testid="item-repair-mic-button"
                    aria-label={
                      dictating ? t('stylist.tapToStop') : t('stylist.recordVoice')
                    }
                  >
                    {dictating ? (
                      <Square className="h-3.5 w-3.5" />
                    ) : (
                      <Mic className="h-3.5 w-3.5" />
                    )}
                  </button>
                )}
              </div>

              <Button
                onClick={onRepair}
                disabled={repairing}
                className="w-full rounded-xl"
                data-testid="item-repair-button"
              >
                {repairing ? (
                  <>
                    <Loader2 className="h-4 w-4 me-2 animate-spin" />
                    {t('itemDetail.repair.running')}
                  </>
                ) : (
                  <>
                    <Wand2 className="h-4 w-4 me-2" />
                    {hasReconstruction
                      ? t('itemDetail.repair.retryCta')
                      : t('itemDetail.repair.cta')}
                  </>
                )}
              </Button>

              {repairing && (
                <div className="space-y-2" data-testid="item-repair-progress">
                  <div className="h-2 rounded shimmer w-full" />
                  <p className="text-[11px] text-muted-foreground italic">
                    {t('itemDetail.repair.progressHint')}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card
            className="rounded-[calc(var(--radius)+6px)] shadow-editorial"
            data-testid="item-edit-image-card"
          >
            <CardContent className="p-5 space-y-3">
              <div className="caps-label text-muted-foreground">
                {t('itemDetail.generateVariant')}
              </div>
              <p className="text-sm text-muted-foreground">
                {t('itemDetail.generateVariantSub')}
              </p>
              <Input
                value={editPrompt}
                onChange={(e) => setEditPrompt(e.target.value)}
                placeholder={t('itemDetail.variantPlaceholder')}
                className="rounded-xl"
                data-testid="item-edit-prompt-input"
              />
              <Button
                onClick={onEdit}
                disabled={editing || !editPrompt.trim()}
                className="w-full rounded-xl"
                data-testid="item-generate-variant-button"
              >
                {editing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 me-2" /> {t('itemDetail.generateVariant')}
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-3">
            <Button
              asChild
              variant="secondary"
              className="rounded-xl"
              data-testid="item-list-for-sale"
            >
              <Link to={`/market/create?itemId=${item.id}`}>
                <Store className="h-4 w-4 me-2" /> {t('itemDetail.listForSale')}
              </Link>
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  variant="destructive"
                  className="rounded-xl"
                  data-testid="item-delete-button"
                >
                  <Trash2 className="h-4 w-4 me-2" /> {t('common.delete')}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t('itemDetail.removeTitle')}</AlertDialogTitle>
                  <AlertDialogDescription>{t('itemDetail.removeBody')}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                  <AlertDialogAction onClick={onDelete} data-testid="item-delete-confirm">
                    {t('common.delete')}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </div>
    </div>
  );
}
