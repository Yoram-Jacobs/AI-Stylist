import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { LogOut, Loader2, Languages } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useNavigate } from 'react-router-dom';
import { CalendarConnect } from '@/components/CalendarConnect';
import { LocationCard } from '@/components/LocationCard';
import { InviteFriendsButton } from '@/components/InviteFriendsButton';
import { SUPPORTED_LANGUAGES } from '@/lib/i18n';

const VOICES = [
  'aura-2-thalia-en', 'aura-2-hermes-en', 'aura-2-electra-en',
  'aura-2-apollo-en', 'aura-2-draco-en', 'aura-2-hyperion-en',
];

export default function Profile() {
  const { t, i18n } = useTranslation();
  const { user, updateUserLocal, logout } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({
    display_name: user?.display_name || '',
    preferred_language: user?.preferred_language || i18n.language || 'en',
    preferred_voice_id: user?.preferred_voice_id || 'aura-2-thalia-en',
    home_city: user?.home_location?.city || '',
    home_lat: user?.home_location?.lat ?? '',
    home_lng: user?.home_location?.lng ?? '',
    aesthetics: (user?.style_profile?.aesthetics || []).join(', '),
    color_palette: (user?.style_profile?.color_palette || []).join(', '),
    avoid: (user?.style_profile?.avoid || []).join(', '),
    region: user?.cultural_context?.region || '',
    dress_conservativeness: user?.cultural_context?.dress_conservativeness || 'moderate',
  });
  const [busy, setBusy] = useState(false);
  const [langBusy, setLangBusy] = useState(false);

  // Apply language immediately on selection + persist via API.
  const onLanguageChange = async (code) => {
    setForm((f) => ({ ...f, preferred_language: code }));
    setLangBusy(true);
    try {
      await i18n.changeLanguage(code);
      try { localStorage.setItem('dressapp.lang', code); } catch { /* ignore */ }
      const res = await api.patchMe({ preferred_language: code });
      updateUserLocal(res);
      toast.success(t('profile.languageUpdated'));
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('profile.saveFailed'));
    } finally {
      setLangBusy(false);
    }
  };

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const body = {
        display_name: form.display_name || null,
        preferred_language: form.preferred_language,
        preferred_voice_id: form.preferred_voice_id,
        style_profile: {
          aesthetics: form.aesthetics.split(',').map((s) => s.trim()).filter(Boolean),
          color_palette: form.color_palette.split(',').map((s) => s.trim()).filter(Boolean),
          avoid: form.avoid.split(',').map((s) => s.trim()).filter(Boolean),
        },
        cultural_context: {
          region: form.region || null,
          dress_conservativeness: form.dress_conservativeness,
        },
      };
      if (form.home_city || form.home_lat || form.home_lng) {
        body.home_location = {
          city: form.home_city || null,
          lat: form.home_lat === '' ? null : Number(form.home_lat),
          lng: form.home_lng === '' ? null : Number(form.home_lng),
        };
      }
      const res = await api.patchMe(body);
      updateUserLocal(res);
      toast.success(t('profile.profileSaved'));
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('profile.saveFailed'));
    } finally { setBusy(false); }
  };

  return (
    <div className="container-px max-w-3xl mx-auto pt-6 md:pt-10">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="caps-label text-muted-foreground">{t('profile.accountLabel')}</div>
          <h1 className="font-display text-3xl sm:text-4xl mt-1">{t('profile.title')}</h1>
        </div>
      </div>

      {/* Language selector surfaced up-front so users find it instantly */}
      <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial mb-6" data-testid="language-card">
        <CardContent className="p-6">
          <div className="flex flex-col md:flex-row md:items-center md:gap-6">
            <div className="flex items-center gap-3">
              <Languages className="h-5 w-5 text-[hsl(var(--accent))]" aria-hidden="true" />
              <div>
                <div className="caps-label text-muted-foreground">{t('profile.voiceLanguage')}</div>
                <div className="font-medium">{t('profile.language')}</div>
              </div>
            </div>
            <div className="mt-3 md:mt-0 md:ms-auto w-full md:w-72">
              <Select
                value={form.preferred_language}
                onValueChange={onLanguageChange}
                disabled={langBusy}
              >
                <SelectTrigger className="rounded-xl" data-testid="language-selector">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SUPPORTED_LANGUAGES.map((l) => (
                    <SelectItem
                      key={l.code}
                      value={l.code}
                      data-testid={`language-option-${l.code}`}
                    >
                      <span className="inline-flex items-center gap-2">
                        <span className="font-medium">{l.nativeName}</span>
                        <span className="text-xs text-muted-foreground">· {l.englishName}</span>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="mb-6">
        <CalendarConnect />
      </div>

      <div className="mb-6">
        <LocationCard />
      </div>

      <div className="mb-6">
        <InviteFriendsButton />
      </div>

      <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
        <CardContent className="p-6">
          <form onSubmit={save} className="space-y-6" data-testid="settings-form">
            <section className="space-y-3">
              <div className="caps-label text-muted-foreground">{t('profile.identity')}</div>
              <div>
                <Label>{t('profile.displayName')}</Label>
                <Input value={form.display_name}
                  onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                  className="rounded-xl" data-testid="settings-display-name" />
              </div>
              <div className="text-xs text-muted-foreground">
                {t('profile.emailReadonly')}: <span className="font-medium">{user?.email}</span>
              </div>
            </section>

            <Separator />

            <section className="space-y-3" data-testid="settings-style-profile">
              <div className="caps-label text-muted-foreground">{t('profile.styleProfile')}</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <Label>{t('profile.aesthetics')}</Label>
                  <Input value={form.aesthetics} onChange={(e) => setForm({ ...form, aesthetics: e.target.value })}
                    placeholder={t('profile.aestheticsPlaceholder')} className="rounded-xl" data-testid="settings-aesthetics" />
                </div>
                <div>
                  <Label>{t('profile.colorPalette')}</Label>
                  <Input value={form.color_palette} onChange={(e) => setForm({ ...form, color_palette: e.target.value })}
                    placeholder={t('profile.colorPalettePlaceholder')} className="rounded-xl" data-testid="settings-palette" />
                </div>
                <div className="md:col-span-2">
                  <Label>{t('profile.avoid')}</Label>
                  <Input value={form.avoid} onChange={(e) => setForm({ ...form, avoid: e.target.value })}
                    placeholder={t('profile.avoidPlaceholder')} className="rounded-xl" data-testid="settings-avoid" />
                </div>
              </div>
            </section>

            <Separator />

            <section className="space-y-3">
              <div className="caps-label text-muted-foreground">{t('profile.context')}</div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <Label>{t('profile.homeCity')}</Label>
                  <Input value={form.home_city} onChange={(e) => setForm({ ...form, home_city: e.target.value })}
                    className="rounded-xl" data-testid="settings-home-city" />
                </div>
                <div>
                  <Label>{t('profile.latitude')}</Label>
                  <Input value={form.home_lat} onChange={(e) => setForm({ ...form, home_lat: e.target.value })}
                    className="rounded-xl" data-testid="settings-home-lat" />
                </div>
                <div>
                  <Label>{t('profile.longitude')}</Label>
                  <Input value={form.home_lng} onChange={(e) => setForm({ ...form, home_lng: e.target.value })}
                    className="rounded-xl" data-testid="settings-home-lng" />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <Label>{t('profile.region')}</Label>
                  <Input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })}
                    className="rounded-xl" data-testid="settings-region" placeholder={t('profile.regionPlaceholder')} />
                </div>
                <div>
                  <Label>{t('profile.conservativeness')}</Label>
                  <Select value={form.dress_conservativeness} onValueChange={(v) => setForm({ ...form, dress_conservativeness: v })}>
                    <SelectTrigger className="rounded-xl" data-testid="settings-conservativeness"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">{t('profile.conservLow')}</SelectItem>
                      <SelectItem value="moderate">{t('profile.conservModerate')}</SelectItem>
                      <SelectItem value="high">{t('profile.conservHigh')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </section>

            <Separator />

            <section className="space-y-3">
              <div className="caps-label text-muted-foreground">{t('profile.voiceLanguage')}</div>
              <div>
                <Label>{t('profile.voice')}</Label>
                <Select value={form.preferred_voice_id} onValueChange={(v) => setForm({ ...form, preferred_voice_id: v })}>
                  <SelectTrigger className="rounded-xl" data-testid="settings-voice"><SelectValue /></SelectTrigger>
                  <SelectContent>{VOICES.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </section>

            <div className="flex gap-3">
              <Button type="submit" disabled={busy} className="rounded-xl" data-testid="settings-save-button">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : t('profile.saveChanges')}
              </Button>
              <Button type="button" variant="secondary" className="rounded-xl ms-auto"
                onClick={() => { logout(); nav('/login'); }} data-testid="settings-logout-button">
                <LogOut className="h-4 w-4 me-2" /> {t('profile.signOut')}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
