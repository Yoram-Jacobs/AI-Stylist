import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Home, Shirt, Sparkles, Store, LogOut, Settings, Receipt, Shield, UserRound, Megaphone } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { cn } from '@/lib/utils';

export const TopNav = () => {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const initials = (user?.display_name || user?.email || 'U').slice(0, 1).toUpperCase();
  const isPro = !!user?.professional?.is_professional;

  const LINKS = [
    { to: '/home', icon: Home, key: 'home', label: t('nav.home') },
    { to: '/closet', icon: Shirt, key: 'closet', label: t('nav.closet') },
    { to: '/stylist', icon: Sparkles, key: 'stylist', label: t('nav.stylist') },
    { to: '/market', icon: Store, key: 'market', label: t('nav.market') },
    { to: '/experts', icon: UserRound, key: 'experts', label: t('nav.experts') },
  ];

  return (
    <header
      data-testid="top-nav"
      className="hidden md:block sticky top-0 z-30 bg-background/85 backdrop-blur border-b border-border"
    >
      <div className="mx-auto max-w-6xl px-6 h-16 flex items-center gap-8">
        <Link to="/home" className="font-display text-2xl" data-testid="brand-logo">
          {t('brand')}
        </Link>
        <nav aria-label={t('nav.primary')} className="flex items-center gap-1">
          {LINKS.map(({ to, icon: Icon, key, label }) => (
            <NavLink
              key={to}
              to={to}
              data-testid={`topnav-link-${key}`}
              className={({ isActive }) =>
                cn(
                  'inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm',
                  isActive
                    ? 'text-foreground bg-secondary'
                    : 'text-muted-foreground hover:text-foreground hover:bg-secondary/60'
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="ms-auto">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" aria-label={t('nav.openUserMenu')} className="rounded-full h-10 w-10 p-0" data-testid="topnav-avatar-button">
                <span className="h-9 w-9 inline-flex items-center justify-center rounded-full bg-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))] font-medium">
                  {initials}
                </span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <div className="px-2 py-1.5 text-sm">
                <div className="font-medium truncate">{user?.display_name || t('nav.guest')}</div>
                <div className="text-xs text-muted-foreground truncate">{user?.email}</div>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => nav('/transactions')} data-testid="topnav-menu-transactions">
                <Receipt className="h-4 w-4 me-2" /> {t('nav.transactions')}
              </DropdownMenuItem>
              {isPro && (
                <DropdownMenuItem onClick={() => nav('/ads')} data-testid="topnav-menu-ads">
                  <Megaphone className="h-4 w-4 me-2" /> {t('nav.ads')}
                </DropdownMenuItem>
              )}
              {(user.roles || []).includes('admin') && (
                <DropdownMenuItem onClick={() => nav('/admin')} data-testid="topnav-menu-admin">
                  <Shield className="h-4 w-4 me-2" /> {t('nav.admin')}
                </DropdownMenuItem>
              )}
              <DropdownMenuItem onClick={() => nav('/me')} data-testid="topnav-menu-settings">
                <Settings className="h-4 w-4 me-2" /> {t('nav.settings')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => { logout(); nav('/login'); }} data-testid="topnav-menu-logout">
                <LogOut className="h-4 w-4 me-2" /> {t('nav.signOut')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
};
