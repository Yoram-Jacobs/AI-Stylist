import { NavLink } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Home, Shirt, Sparkles, Store, User } from 'lucide-react';
import { cn } from '@/lib/utils';

const TABS = [
  { to: '/home', icon: Home, label: 'Home', testid: 'bottom-tab-home' },
  { to: '/closet', icon: Shirt, label: 'Closet', testid: 'bottom-tab-closet' },
  { to: '/stylist', icon: Sparkles, label: 'Stylist', testid: 'bottom-tab-stylist' },
  { to: '/market', icon: Store, label: 'Market', testid: 'bottom-tab-market' },
  { to: '/me', icon: User, label: 'Me', testid: 'bottom-tab-me' },
];

export const BottomTabs = () => (
  <nav
    data-testid="bottom-tabs"
    className="md:hidden fixed bottom-0 inset-x-0 bg-background/95 backdrop-blur border-t border-border z-40"
    style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
  >
    <ul className="grid grid-cols-5 gap-1 px-2 py-2">
      {TABS.map(({ to, icon: Icon, label, testid }) => (
        <li key={to} className="flex">
          <NavLink
            to={to}
            data-testid={testid}
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
