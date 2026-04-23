import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Share2, Copy, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { api } from '@/lib/api';

/**
 * Share a single outfit recommendation. Mints a read-only snapshot on the
 * server, then calls the native share sheet (`navigator.share`) when
 * available. Falls back to clipboard copy so desktop-Chromium users can
 * still paste the link into any chat.
 */
export function ShareOutfitButton({ rec, sessionId, size = 'sm' }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);

  const share = async () => {
    setBusy(true);
    try {
      const snapshot = await api.createSharedOutfit({
        session_id: sessionId,
        outfit: rec,
      });
      const url = snapshot?.share_url || `${window.location.origin}/shared/${snapshot.id}`;
      const payload = {
        title: t('stylist.shareOutfitSubject'),
        text:
          rec?.name
            ? `${t('stylist.shareOutfitBody')}: ${rec.name}`
            : t('stylist.shareOutfitBody'),
        url,
      };
      if (navigator.share) {
        try {
          await navigator.share(payload);
        } catch (err) {
          if (err?.name !== 'AbortError') {
            await navigator.clipboard.writeText(`${payload.text} ${payload.url}`);
            toast.success(t('stylist.shareCopied'));
          }
        }
      } else {
        await navigator.clipboard.writeText(`${payload.text} ${payload.url}`);
        toast.success(t('stylist.shareCopied'));
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button
      size={size}
      variant="outline"
      onClick={share}
      disabled={busy}
      className="rounded-full h-8 gap-1"
      data-testid="share-outfit-btn"
    >
      {busy ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : navigator.share ? (
        <Share2 className="h-3.5 w-3.5" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
      <span className="text-xs">{t('stylist.shareOutfit')}</span>
    </Button>
  );
}
