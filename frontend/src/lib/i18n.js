import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from '@/locales/en.json';
import he from '@/locales/he.json';
import ar from '@/locales/ar.json';
import es from '@/locales/es.json';
import fr from '@/locales/fr.json';
import de from '@/locales/de.json';
import it from '@/locales/it.json';
import pt from '@/locales/pt.json';
import ru from '@/locales/ru.json';
import zh from '@/locales/zh.json';
import ja from '@/locales/ja.json';
import hi from '@/locales/hi.json';

// Public metadata for the language selector (native names, RTL flag).
// Keep this list in sync with the resources below.
export const SUPPORTED_LANGUAGES = [
  { code: 'en', nativeName: 'English',    englishName: 'English',    dir: 'ltr' },
  { code: 'he', nativeName: 'עברית',     englishName: 'Hebrew',     dir: 'rtl' },
  { code: 'ar', nativeName: 'العربية',   englishName: 'Arabic',     dir: 'rtl' },
  { code: 'es', nativeName: 'Español',    englishName: 'Spanish',    dir: 'ltr' },
  { code: 'fr', nativeName: 'Français',    englishName: 'French',     dir: 'ltr' },
  { code: 'de', nativeName: 'Deutsch',     englishName: 'German',     dir: 'ltr' },
  { code: 'it', nativeName: 'Italiano',    englishName: 'Italian',    dir: 'ltr' },
  { code: 'pt', nativeName: 'Português',   englishName: 'Portuguese', dir: 'ltr' },
  { code: 'ru', nativeName: 'Русский',     englishName: 'Russian',    dir: 'ltr' },
  { code: 'zh', nativeName: '中文（简体）', englishName: 'Chinese (Simplified)', dir: 'ltr' },
  { code: 'ja', nativeName: '日本語',      englishName: 'Japanese',   dir: 'ltr' },
  { code: 'hi', nativeName: 'हिन्दी',     englishName: 'Hindi',      dir: 'ltr' },
];

export const RTL_LANGUAGES = new Set(
  SUPPORTED_LANGUAGES.filter((l) => l.dir === 'rtl').map((l) => l.code)
);

export const isRtl = (code) => RTL_LANGUAGES.has(code);

const resources = {
  en: { translation: en },
  he: { translation: he },
  ar: { translation: ar },
  es: { translation: es },
  fr: { translation: fr },
  de: { translation: de },
  it: { translation: it },
  pt: { translation: pt },
  ru: { translation: ru },
  zh: { translation: zh },
  ja: { translation: ja },
  hi: { translation: hi },
};

// Initial language pick order:
//   1. Persisted localStorage value (set by LanguageSync on user change / manual pick)
//   2. Browser navigator.language prefix (if supported)
//   3. Fallback to 'en'
function pickInitialLanguage() {
  try {
    const stored = localStorage.getItem('dressapp.lang');
    if (stored && resources[stored]) return stored;
    const nav = (navigator?.language || '').toLowerCase();
    const base = nav.split('-')[0];
    if (resources[base]) return base;
  } catch {
    /* ignore */
  }
  return 'en';
}

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: pickInitialLanguage(),
    fallbackLng: 'en',
    defaultNS: 'translation',
    interpolation: { escapeValue: false },
    returnEmptyString: false,
    react: { useSuspense: false },
  });

export default i18n;
