/**
 * LanguagePicker — a small floating icon-button ("bulb") that lets the user
 * switch the app language without opening the Profile page.
 *
 * Behaviour
 *   • Click → dropdown of all SUPPORTED_LANGUAGES (native names).
 *   • Selecting a language switches i18n immediately, persists the choice
 *     to localStorage, and (if logged in) mirrors it to the user's
 *     ``preferred_language`` via PATCH /me — silently, no toast spam.
 *   • Current language is marked with a check.
 *   • Falls back to localStorage-only when the user is signed out (no API
 *     call), so the picker also works on /login or unauthed pages.
 *
 * The component intentionally has zero layout — drop it inside any
 * absolute-positioned container or alongside other CTAs.
 */
import { useTranslation } from 'react-i18next';
import { Globe, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { SUPPORTED_LANGUAGES } from '@/lib/i18n';
import { useAuth } from '@/lib/auth';
import { api } from '@/lib/api';

export const LanguagePicker = ({
  size = 'icon',
  variant = 'outline',
  className,
  testIdSuffix = '',
}) => {
  const { i18n, t } = useTranslation();
  const { user, updateUserLocal } = useAuth();
  const current = (i18n.language || 'en').split('-')[0];

  const change = async (code) => {
    if (!code || code === current) return;
    // 1) Switch UI language synchronously so feedback is instant.
    try { await i18n.changeLanguage(code); } catch { /* ignore */ }
    // 2) Persist locally for the next page load (works for guests too).
    try { localStorage.setItem('dressapp.lang', code); } catch { /* ignore */ }
    // 3) Mirror to the user's profile if signed in. We fire-and-forget
    //    here — the picker is meant to feel like a quick toggle, not a
    //    "save profile" action. Errors are silent.
    if (user) {
      try {
        const updated = await api.patchMe({ preferred_language: code });
        updateUserLocal(updated);
      } catch { /* ignore — we'll just resync next session */ }
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant={variant}
          size={size}
          className={className}
          aria-label={t('language.change', { defaultValue: 'Change language' })}
          data-testid={`language-picker-trigger${testIdSuffix ? '-' + testIdSuffix : ''}`}
        >
          <Globe className="h-[18px] w-[18px]" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="w-56"
        data-testid="language-picker-menu"
      >
        <DropdownMenuLabel className="caps-label text-muted-foreground">
          {t('language.label', { defaultValue: 'Language' })}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {SUPPORTED_LANGUAGES.map((l) => {
          const active = l.code === current;
          return (
            <DropdownMenuItem
              key={l.code}
              onSelect={() => change(l.code)}
              className="flex items-center justify-between gap-2 cursor-pointer"
              data-testid={`language-picker-option-${l.code}`}
              data-active={active || undefined}
              dir={l.dir}
            >
              <span className="truncate">{l.nativeName}</span>
              {active ? (
                <Check className="h-4 w-4 text-[hsl(var(--accent))] shrink-0" />
              ) : null}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
