import { NavLink } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { Home, Shirt, Sparkles, Store, User } from 'lucide-react';
import { cn } from '@/lib/utils';

export const BottomTabs = () => {
  const { t } = useTranslation();
  const TABS = [
    { to: '/home', icon: Home, label: t('nav.home'), testid: 'bottom-tab-home' },
    { to: '/closet', icon: Shirt, label: t('nav.closet'), testid: 'bottom-tab-closet' },
    { to: '/stylist', icon: Sparkles, label: t('nav.stylist'), testid: 'bottom-tab-stylist' },
    { to: '/market', icon: Store, label: t('nav.market'), testid: 'bottom-tab-market' },
    { to: '/me', icon: User, label: t('nav.me'), testid: 'bottom-tab-me' },
  ];
  return (
    <nav
      data-testid="bottom-tabs"
      aria-label={t('nav.mobilePrimary')}
      className="md:hidden fixed bottom-0 inset-x-0 bg-background/95 backdrop-blur border-t border-border z-40"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <ul className="grid grid-cols-5 gap-1 px-2 py-2">
        {TABS.map(({ to, icon: Icon, label, testid }) => (
          <li key={to} className="flex">
            <NavLink
              to={to}
              data-testid={testid}
              aria-label={label}
              className={({ isActive }) =>
                cn(
                  'flex-1 flex flex-col items-center justify-center rounded-lg px-1 py-2 min-h-[52px]',
                  isActive
                    ? 'text-[hsl(var(--accent))]'
                    : 'text-muted-foreground hover:text-foreground'
                )
              }
            >
              {({ isActive }) => (
                <motion.span
                  whileTap={{ scale: 0.92 }}
                  className="flex flex-col items-center gap-1"
                >
                  <Icon className={cn('h-5 w-5', isActive && 'stroke-[2.2]')} />
                  <span className="text-[10px] tracking-wide">{label}</span>
                  {isActive && (
                    <motion.span
                      layoutId="active-tab-underline"
                      className="h-[2px] w-5 bg-[hsl(var(--accent))] rounded-full"
                    />
                  )}
                </motion.span>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
};
