/**
 * LanguageSwitchOverlay — full-screen, backdrop-blurred toast shown while
 * a language change is in flight.
 *
 * The PATCH /me round-trip + i18n.changeLanguage + LanguageSync's
 * <html lang/dir> re-paint can take ~20 seconds on slow networks; without
 * a visible affordance the user clicks the picker, sees nothing, and
 * concludes nothing happened. This overlay gives that wait an explicit,
 * branded affordance.
 *
 * How it talks to the picker
 * --------------------------
 * The picker dispatches two custom DOM events:
 *   • ``dressapp:lang-switch-start`` with detail { code, nativeName }
 *   • ``dressapp:lang-switch-done``  with detail { code }
 *
 * The overlay listens for both. Custom DOM events are used (rather than a
 * React context) so the overlay can be mounted once at the app shell and
 * doesn't need a provider wrapping every route.
 *
 * Behaviour
 * ---------
 *   • Opens on `…-start`, closes on `…-done`.
 *   • Auto-closes after 30 s as a safety net if the picker forgets to
 *     emit `…-done` (e.g. network failure mid-PATCH).
 *   • Escape key closes immediately (a11y).
 *   • aria-live="polite" so screen readers announce the in-flight state.
 *   • Locked behind z-index 200 (modal layer in our design tokens).
 */
import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const EVT_START = 'dressapp:lang-switch-start';
const EVT_DONE  = 'dressapp:lang-switch-done';
const SAFETY_MS = 30000;

export const LanguageSwitchOverlay = () => {
  const { t } = useTranslation();
  const [active, setActive] = useState(false);
  const [target, setTarget] = useState({ code: '', nativeName: '' });

  useEffect(() => {
    let safetyTimer = null;

    const onStart = (e) => {
      const detail = e?.detail || {};
      setTarget({
        code: detail.code || '',
        nativeName: detail.nativeName || detail.code || '',
      });
      setActive(true);
      if (safetyTimer) clearTimeout(safetyTimer);
      safetyTimer = setTimeout(() => setActive(false), SAFETY_MS);
    };
    const onDone = () => {
      if (safetyTimer) clearTimeout(safetyTimer);
      // Keep the overlay visible for a heartbeat so the user sees the
      // transition complete cleanly instead of a snap-cut.
      setTimeout(() => setActive(false), 250);
    };
    const onKey = (e) => { if (e.key === 'Escape') setActive(false); };

    window.addEventListener(EVT_START, onStart);
    window.addEventListener(EVT_DONE, onDone);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener(EVT_START, onStart);
      window.removeEventListener(EVT_DONE, onDone);
      window.removeEventListener('keydown', onKey);
      if (safetyTimer) clearTimeout(safetyTimer);
    };
  }, []);

  if (!active) return null;

  const title = target.nativeName
    ? t('language.switchingTo', {
        language: target.nativeName,
        defaultValue: 'Switching to {{language}}…',
      })
    : t('language.switching', { defaultValue: 'Switching language…' });

  const hint = t('language.switchingHint', {
    defaultValue: 'This usually takes a few seconds.',
  });

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      data-testid="language-switch-overlay"
      className="fixed inset-0 z-[200] flex items-center justify-center
                 bg-background/60 backdrop-blur-md
                 animate-in fade-in duration-200"
    >
      <div
        className="flex flex-col items-center gap-4 rounded-2xl border
                   border-border bg-card/95 px-8 py-7 shadow-2xl
                   max-w-[min(92vw,380px)] text-center
                   animate-in zoom-in-95 duration-200"
      >
        <Loader2
          className="h-9 w-9 animate-spin text-[hsl(var(--accent))]"
          aria-hidden="true"
        />
        <div className="space-y-1">
          <p
            className="text-base font-medium text-foreground"
            data-testid="language-switch-overlay-title"
          >
            {title}
          </p>
          <p
            className="text-sm text-muted-foreground"
            data-testid="language-switch-overlay-hint"
          >
            {hint}
          </p>
        </div>
      </div>
    </div>
  );
};

export default LanguageSwitchOverlay;
