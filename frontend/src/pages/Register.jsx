import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/lib/auth';

export default function Register() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const { register } = useAuth();
  const [form, setForm] = useState({ email: '', password: '', display_name: '' });
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (form.password.length < 8) {
      toast.error(t('auth.registerFailed'));
      return;
    }
    setBusy(true);
    try {
      await register(form);
      toast.success(t('brand'));
      nav('/home');
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('auth.registerFailed'));
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-[100dvh] grid md:grid-cols-2">
      <div className="hidden md:block relative hero-wash-light noise" />
      <div className="flex items-center justify-center p-6 md:p-16">
        <Card className="w-full max-w-md rounded-[calc(var(--radius)+6px)] shadow-editorial">
          <CardContent className="p-6 md:p-8">
            <h1 className="font-display text-3xl md:text-4xl leading-[1.02] mb-2">{t('auth.createAccount')}</h1>
            <p className="text-sm text-muted-foreground mb-6">{t('auth.registerSub')}</p>
            <form onSubmit={submit} className="space-y-4" data-testid="register-form">
              <div>
                <Label htmlFor="name">{t('auth.displayName')}</Label>
                <Input id="name" value={form.display_name}
                  onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                  data-testid="register-name-input" placeholder="Alex" />
              </div>
              <div>
                <Label htmlFor="email">{t('auth.email')}</Label>
                <Input id="email" type="email" required value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  data-testid="register-email-input" placeholder={t('auth.emailPlaceholder')} />
              </div>
              <div>
                <Label htmlFor="pw">{t('auth.password')}</Label>
                <Input id="pw" type="password" required minLength={8} value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  data-testid="register-password-input" />
              </div>
              <Button type="submit" disabled={busy} className="w-full rounded-xl" data-testid="register-submit-button">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : t('auth.register')}
              </Button>
            </form>
            <p className="mt-6 text-sm text-muted-foreground text-center">
              {t('auth.alreadyHaveAccount')}{' '}
              <Link to="/login" className="text-[hsl(var(--accent))] underline underline-offset-4" data-testid="register-login-link">
                {t('auth.signInLink')}
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
