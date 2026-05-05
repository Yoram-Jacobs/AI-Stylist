import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { toast } from 'sonner';
import { Loader2, Sparkles } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { GoogleAuthButton } from '@/components/GoogleAuthButton';
import { BrandLogo } from '@/components/BrandLogo';
import { LanguagePicker } from '@/components/LanguagePicker';

export default function Login() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const { login, devBypass } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [withCalendar, setWithCalendar] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await login(email, password);
      nav('/home');
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('auth.signInFailed'));
    } finally { setBusy(false); }
  };

  const dev = async () => {
    setBusy(true);
    try {
      await devBypass();
      toast.success(t('auth.signedInAsDev'));
      nav('/home');
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('auth.devDisabled'));
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-[100dvh] grid md:grid-cols-2 relative">
      {/* Floating language "bulb" — fixed to the top-end so guests can
          flip the UI to their language *before* signing in. ``z-20`` so
          it stays above the editorial wash on desktop and the form
          card on mobile. */}
      <div className="absolute top-4 end-4 z-20">
        <LanguagePicker
          className="rounded-full bg-card/80 backdrop-blur-sm border-border shadow-sm hover:bg-card"
          testIdSuffix="login"
        />
      </div>
      {/* Editorial panel */}
      <div className="relative hidden md:flex flex-col justify-between p-10 hero-wash-light noise">
        <div>
          <BrandLogo size="lg" testId="brand-logo" />
          <div className="caps-label text-muted-foreground mt-2">{t('auth.tagline')}</div>
        </div>
        <figure className="relative overflow-hidden rounded-[calc(var(--radius)+6px)] border border-border shadow-editorial">
          <img
            src="https://images.unsplash.com/photo-1646105659698-1389145bf6a0?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85"
            alt="Editorial street style"
            className="w-full h-[52vh] object-cover"
          />
        </figure>
        <p className="text-sm text-muted-foreground max-w-md">{t('auth.editorial')}</p>
      </div>

      {/* Form panel */}
      <div className="flex flex-col justify-center p-6 md:p-16">
        <div className="md:hidden mb-8">
          <BrandLogo size="lg" testId="brand-logo-mobile" />
          <div className="caps-label text-muted-foreground mt-1">{t('auth.signIn')}</div>
        </div>
        <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
          <CardContent className="p-6 md:p-8">
            <h1 className="font-display text-3xl md:text-4xl leading-[1.02] mb-2">{t('auth.welcomeBack')}</h1>
            <p className="text-sm text-muted-foreground mb-6">{t('auth.signInSub')}</p>

            <div className="space-y-3 mb-6" data-testid="google-signin-block">
              <GoogleAuthButton
                withCalendar={withCalendar}
                next="/home"
                label={t('auth.continueWithGoogle')}
                testId="login-google-button"
              />
              <label
                className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer select-none"
                data-testid="login-with-calendar-row"
              >
                <Checkbox
                  checked={withCalendar}
                  onCheckedChange={(v) => setWithCalendar(Boolean(v))}
                  data-testid="login-with-calendar-checkbox"
                />
                <span>{t('auth.alsoConnectCalendar')}</span>
              </label>
            </div>

            <div className="flex items-center gap-3 mb-6">
              <div className="h-px bg-border flex-1" />
              <div className="caps-label text-muted-foreground">{t('common.or')}</div>
              <div className="h-px bg-border flex-1" />
            </div>

            <form onSubmit={submit} className="space-y-4" data-testid="login-form">
              <div>
                <Label htmlFor="email">{t('auth.email')}</Label>
                <Input id="email" type="email" autoComplete="email" required
                  value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder={t('auth.emailPlaceholder')} data-testid="login-email-input" />
              </div>
              <div>
                <Label htmlFor="password">{t('auth.password')}</Label>
                <Input id="password" type="password" autoComplete="current-password" required
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  data-testid="login-password-input" />
              </div>
              <Button type="submit" disabled={busy} className="w-full rounded-xl" data-testid="login-submit-button">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : t('auth.signIn')}
              </Button>
            </form>

            <Button type="button" variant="ghost" onClick={dev} disabled={busy}
              className="w-full rounded-xl mt-4 text-muted-foreground hover:text-foreground" data-testid="login-dev-bypass-button">
              <Sparkles className="h-4 w-4 me-2" /> {t('auth.continueAsDev')}
            </Button>

            <p className="mt-6 text-sm text-muted-foreground text-center">
              {t('auth.noAccount')}{' '}
              <Link to="/register" className="text-[hsl(var(--accent))] underline underline-offset-4" data-testid="login-register-link">
                {t('auth.createOne')}
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
