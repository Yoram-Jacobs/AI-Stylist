import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Share2, Copy, Users, Loader2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

/**
 * Invite-friends action — web-today, mobile-ready-tomorrow.
 *
 * The browser's `navigator.share` gives us the exact same sheet a native
 * app gets on iOS/Android (iMessage, WhatsApp, Mail, AirDrop…). When the
 * browser is desktop-Chromium without a share target, we fall back to
 * clipboard copy — still one tap away from any messaging app. When the
 * app is packaged with Capacitor later, `navigator.share` transparently
 * delegates to the native share sheet with zero code changes here.
 */
export function InviteFriendsButton() {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);

  const inviteUrl = `${window.location.origin}/?ref=invite`;

  const share = async () => {
    setBusy(true);
    const payload = {
      title: t('profile.inviteSubject'),
      text: t('profile.inviteBody'),
      url: inviteUrl,
    };
    try {
      if (navigator.share) {
        await navigator.share(payload);
      } else {
        await navigator.clipboard.writeText(`${payload.text} ${payload.url}`);
        toast.success(t('profile.inviteCopied'));
      }
    } catch (err) {
      if (err?.name !== 'AbortError') {
        // AbortError just means the user closed the share sheet.
        try {
          await navigator.clipboard.writeText(`${payload.text} ${payload.url}`);
          toast.success(t('profile.inviteCopied'));
        } catch {
          toast.error(t('common.error'));
        }
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      className="rounded-[calc(var(--radius)+6px)] shadow-editorial"
      data-testid="invite-friends-card"
    >
      <CardContent className="p-6">
        <div className="flex items-start gap-4">
          <div className="h-10 w-10 rounded-full bg-secondary flex items-center justify-center shrink-0">
            <Users className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="caps-label text-muted-foreground">
              {t('profile.inviteFriends')}
            </div>
            <h3 className="font-display text-xl mt-1">
              {t('profile.inviteSubject')}
            </h3>
            <p className="text-sm text-muted-foreground mt-1 max-w-xl">
              {t('profile.inviteBody')}
            </p>
          </div>
          <div className="shrink-0">
            <Button
              onClick={share}
              disabled={busy}
              className="rounded-xl"
              data-testid="invite-friends-btn"
            >
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  {navigator.share ? (
                    <Share2 className="h-4 w-4 me-2" />
                  ) : (
                    <Copy className="h-4 w-4 me-2" />
                  )}
                  {t('profile.inviteFriends')}
                </>
              )}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
