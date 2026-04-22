import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/lib/auth';
import { isRtl, SUPPORTED_LANGUAGES } from '@/lib/i18n';

const SUPPORTED_CODES = new Set(SUPPORTED_LANGUAGES.map((l) => l.code));

/**
 * Applies the user's preferred language (or the already-selected i18n language)
 * to i18next, <html lang="..."> and <html dir="rtl|ltr">.
 *
 * Mount this once at the top of the authenticated app shell so every route
 * (including Admin) updates consistently.
 */
export const LanguageSync = () => {
  const { user } = useAuth();
  const { i18n } = useTranslation();

  // If the logged-in user has a preferred_language saved in the DB, adopt it.
  useEffect(() => {
    const lang = user?.preferred_language;
    if (lang && SUPPORTED_CODES.has(lang) && i18n.language !== lang) {
      i18n.changeLanguage(lang);
      try { localStorage.setItem('dressapp.lang', lang); } catch { /* ignore */ }
    }
  }, [user?.preferred_language, i18n]);

  // Keep <html lang/dir> in sync with the active i18n language.
  useEffect(() => {
    const apply = (lng) => {
      const code = SUPPORTED_CODES.has(lng) ? lng : 'en';
      const html = document.documentElement;
      html.setAttribute('lang', code);
      html.setAttribute('dir', isRtl(code) ? 'rtl' : 'ltr');
    };
    apply(i18n.language);
    i18n.on('languageChanged', apply);
    return () => { i18n.off('languageChanged', apply); };
  }, [i18n]);

  return null;
};
