import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { LogOut, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useNavigate } from 'react-router-dom';

const VOICES = [
  'aura-2-thalia-en', 'aura-2-hermes-en', 'aura-2-electra-en',
  'aura-2-apollo-en', 'aura-2-draco-en', 'aura-2-hyperion-en',
];
const LANGUAGES = ['en', 'es', 'fr', 'de', 'it', 'ja', 'nl'];

export default function Profile() {
  const { user, updateUserLocal, logout } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({
    display_name: user?.display_name || '',
    preferred_language: user?.preferred_language || 'en',
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
      toast.success('Profile saved');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Save failed');
    } finally { setBusy(false); }
  };

  return (
    <div className="container-px max-w-3xl mx-auto pt-6 md:pt-10">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="caps-label text-muted-foreground">Account</div>
          <h1 className="font-display text-3xl sm:text-4xl mt-1">Profile & settings</h1>
        </div>
      </div>

      <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
        <CardContent className="p-6">
          <form onSubmit={save} className="space-y-6" data-testid="settings-form">
            <section className="space-y-3">
              <div className="caps-label text-muted-foreground">Identity</div>
              <div>
                <Label>Display name</Label>
                <Input value={form.display_name}
                  onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                  className="rounded-xl" data-testid="settings-display-name" />
              </div>
              <div className="text-xs text-muted-foreground">Email: <span className="font-medium">{user?.email}</span></div>
            </section>

            <Separator />

            <section className="space-y-3" data-testid="settings-style-profile">
              <div className="caps-label text-muted-foreground">Style profile</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <Label>Aesthetics</Label>
                  <Input value={form.aesthetics} onChange={(e) => setForm({ ...form, aesthetics: e.target.value })}
                    placeholder="minimalist, smart-casual" className="rounded-xl" data-testid="settings-aesthetics" />
                </div>
                <div>
                  <Label>Color palette</Label>
                  <Input value={form.color_palette} onChange={(e) => setForm({ ...form, color_palette: e.target.value })}
                    placeholder="navy, ivory, olive" className="rounded-xl" data-testid="settings-palette" />
                </div>
                <div className="md:col-span-2">
                  <Label>Avoid</Label>
                  <Input value={form.avoid} onChange={(e) => setForm({ ...form, avoid: e.target.value })}
                    placeholder="neon, logos" className="rounded-xl" data-testid="settings-avoid" />
                </div>
              </div>
            </section>

            <Separator />

            <section className="space-y-3">
              <div className="caps-label text-muted-foreground">Context</div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <Label>Home city</Label>
                  <Input value={form.home_city} onChange={(e) => setForm({ ...form, home_city: e.target.value })}
                    className="rounded-xl" data-testid="settings-home-city" />
                </div>
                <div>
                  <Label>Latitude</Label>
                  <Input value={form.home_lat} onChange={(e) => setForm({ ...form, home_lat: e.target.value })}
                    className="rounded-xl" data-testid="settings-home-lat" />
                </div>
                <div>
                  <Label>Longitude</Label>
                  <Input value={form.home_lng} onChange={(e) => setForm({ ...form, home_lng: e.target.value })}
                    className="rounded-xl" data-testid="settings-home-lng" />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <Label>Region</Label>
                  <Input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })}
                    className="rounded-xl" data-testid="settings-region" placeholder="US / IN / SA ..." />
                </div>
                <div>
                  <Label>Dress conservativeness</Label>
                  <Select value={form.dress_conservativeness} onValueChange={(v) => setForm({ ...form, dress_conservativeness: v })}>
                    <SelectTrigger className="rounded-xl" data-testid="settings-conservativeness"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="moderate">Moderate</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </section>

            <Separator />

            <section className="space-y-3">
              <div className="caps-label text-muted-foreground">Voice & language</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <Label>Language</Label>
                  <Select value={form.preferred_language} onValueChange={(v) => setForm({ ...form, preferred_language: v })}>
                    <SelectTrigger className="rounded-xl" data-testid="settings-language"><SelectValue /></SelectTrigger>
                    <SelectContent>{LANGUAGES.map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Voice (Deepgram Aura-2)</Label>
                  <Select value={form.preferred_voice_id} onValueChange={(v) => setForm({ ...form, preferred_voice_id: v })}>
                    <SelectTrigger className="rounded-xl" data-testid="settings-voice"><SelectValue /></SelectTrigger>
                    <SelectContent>{VOICES.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
            </section>

            <div className="flex gap-3">
              <Button type="submit" disabled={busy} className="rounded-xl" data-testid="settings-save-button">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save changes'}
              </Button>
              <Button type="button" variant="secondary" className="rounded-xl ml-auto"
                onClick={() => { logout(); nav('/login'); }} data-testid="settings-logout-button">
                <LogOut className="h-4 w-4 mr-2" /> Sign out
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
