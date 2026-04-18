import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import { toast } from 'sonner';
import { Loader2, Sparkles } from 'lucide-react';
import { useAuth } from '@/lib/auth';

export default function Login() {
  const nav = useNavigate();
  const { login, devBypass } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await login(email, password);
      nav('/home');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Login failed');
    } finally { setBusy(false); }
  };

  const dev = async () => {
    setBusy(true);
    try {
      await devBypass();
      toast.success('Signed in as dev user');
      nav('/home');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Dev sign-in disabled');
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-[100dvh] grid md:grid-cols-2">
      {/* Editorial panel */}
      <div className="relative hidden md:flex flex-col justify-between p-10 hero-wash-light noise">
        <div>
          <div className="font-display text-3xl" data-testid="brand-logo">DressApp</div>
          <div className="caps-label text-muted-foreground mt-2">A fashion editor in your pocket</div>
        </div>
        <figure className="relative overflow-hidden rounded-[calc(var(--radius)+6px)] border border-border shadow-editorial">
          <img
            src="https://images.unsplash.com/photo-1646105659698-1389145bf6a0?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85"
            alt="Editorial street style"
            className="w-full h-[52vh] object-cover"
          />
        </figure>
        <p className="text-sm text-muted-foreground max-w-md">
          Catalog your wardrobe. Ask the AI stylist. Swap, sell or donate — with a tasteful 7% platform fee only when things sell.
        </p>
      </div>

      {/* Form panel */}
      <div className="flex flex-col justify-center p-6 md:p-16">
        <div className="md:hidden mb-8">
          <div className="font-display text-3xl" data-testid="brand-logo-mobile">DressApp</div>
          <div className="caps-label text-muted-foreground mt-1">Sign in</div>
        </div>
        <Card className="rounded-[calc(var(--radius)+6px)] shadow-editorial">
          <CardContent className="p-6 md:p-8">
            <h1 className="font-display text-3xl md:text-4xl leading-[1.02] mb-2">Welcome back</h1>
            <p className="text-sm text-muted-foreground mb-6">Sign in to your closet and stylist.</p>
            <form onSubmit={submit} className="space-y-4" data-testid="login-form">
              <div>
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" autoComplete="email" required
                  value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@domain.com" data-testid="login-email-input" />
              </div>
              <div>
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" autoComplete="current-password" required
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  data-testid="login-password-input" />
              </div>
              <Button type="submit" disabled={busy} className="w-full rounded-xl" data-testid="login-submit-button">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Sign in'}
              </Button>
            </form>

            <div className="flex items-center gap-3 my-6">
              <div className="h-px bg-border flex-1" />
              <div className="caps-label text-muted-foreground">or</div>
              <div className="h-px bg-border flex-1" />
            </div>

            <Button type="button" variant="secondary" onClick={dev} disabled={busy}
              className="w-full rounded-xl" data-testid="login-dev-bypass-button">
              <Sparkles className="h-4 w-4 mr-2" /> Continue as dev user
            </Button>

            <p className="mt-6 text-sm text-muted-foreground text-center">
              No account?{' '}
              <Link to="/register" className="text-[hsl(var(--accent))] underline underline-offset-4" data-testid="login-register-link">
                Create one
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
