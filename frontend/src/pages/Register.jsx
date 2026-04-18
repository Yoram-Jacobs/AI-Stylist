import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/lib/auth';

export default function Register() {
  const nav = useNavigate();
  const { register } = useAuth();
  const [form, setForm] = useState({ email: '', password: '', display_name: '' });
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (form.password.length < 8) {
      toast.error('Password must be at least 8 characters.');
      return;
    }
    setBusy(true);
    try {
      await register(form);
      toast.success('Welcome to DressApp');
      nav('/home');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Registration failed');
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-[100dvh] grid md:grid-cols-2">
      <div className="hidden md:block relative hero-wash-light noise" />
      <div className="flex items-center justify-center p-6 md:p-16">
        <Card className="w-full max-w-md rounded-[calc(var(--radius)+6px)] shadow-editorial">
          <CardContent className="p-6 md:p-8">
            <h1 className="font-display text-3xl md:text-4xl leading-[1.02] mb-2">Create your account</h1>
            <p className="text-sm text-muted-foreground mb-6">Three fields and you're in.</p>
            <form onSubmit={submit} className="space-y-4" data-testid="register-form">
              <div>
                <Label htmlFor="name">Display name</Label>
                <Input id="name" value={form.display_name}
                  onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                  data-testid="register-name-input" placeholder="Alex" />
              </div>
              <div>
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" required value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  data-testid="register-email-input" placeholder="alex@domain.com" />
              </div>
              <div>
                <Label htmlFor="pw">Password</Label>
                <Input id="pw" type="password" required minLength={8} value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  data-testid="register-password-input" />
                <p className="text-xs text-muted-foreground mt-1">At least 8 characters.</p>
              </div>
              <Button type="submit" disabled={busy} className="w-full rounded-xl" data-testid="register-submit-button">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create account'}
              </Button>
            </form>
            <p className="mt-6 text-sm text-muted-foreground text-center">
              Already have an account?{' '}
              <Link to="/login" className="text-[hsl(var(--accent))] underline underline-offset-4" data-testid="register-login-link">
                Sign in
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
