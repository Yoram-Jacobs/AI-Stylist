import { Helmet } from 'react-helmet-async';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

const SITE_URL = 'https://ai-stylist-api.preview.emergentagent.com';
const BRAND = 'DressApp';

// Static path → i18n route key. Dynamic /closet/<id> and /market/<id> paths
// are handled by the ``startsWith`` checks below. Keys live under
// ``seo.routes.<key>.{title,description}`` in every locale JSON.
const ROUTE_KEYS = {
  '/login':           'login',
  '/register':        'register',
  '/home':            'home',
  '/closet':          'closet',
  '/closet/add':      'closet_add',
  '/stylist':         'stylist',
  '/market':          'market',
  '/market/create':   'market_create',
  '/transactions':    'transactions',
  '/admin':           'admin',
  '/me':              'me',
};

function routeKeyFor(pathname) {
  if (ROUTE_KEYS[pathname]) return ROUTE_KEYS[pathname];
  if (pathname.startsWith('/closet/')) return 'closet_item';
  if (pathname.startsWith('/market/')) return 'market_listing';
  return null;
}

/** Per-route Helmet that updates <title>, description, OG, Twitter, canonical. */
export const SeoBase = () => {
  const { pathname } = useLocation();
  const { t, i18n } = useTranslation();
  const key = routeKeyFor(pathname);

  // Resolve title + description from the active locale; fall back to
  // brand + global default-description when no route key applies (e.g.
  // unknown internal route).
  const title = key
    ? t(`seo.routes.${key}.title`, { defaultValue: BRAND })
    : t('seo.defaultTitle', { defaultValue: BRAND });
  const description = key
    ? t(`seo.routes.${key}.description`, {
        defaultValue: t('seo.defaultDescription'),
      })
    : t('seo.defaultDescription');

  const fullTitle = pathname === '/home' ? `${BRAND} — ${title}` : `${title} | ${BRAND}`;
  const canonical = `${SITE_URL}${pathname}`;
  // ``i18n.language`` looks like ``en`` / ``en-US`` / ``zh-CN`` —
  // strip any region suffix to hand the browser a valid two-letter
  // BCP-47 tag for the `<html lang>` attribute.
  const lang = (i18n.language || 'en').split('-')[0].toLowerCase();

  return (
    <Helmet defaultTitle={BRAND} prioritizeSeoTags>
      <html lang={lang} />
      <title>{fullTitle}</title>
      <meta name="description" content={description} />
      <meta name="theme-color" content="#1F6F6B" />
      <link rel="canonical" href={canonical} />
      {/* Open Graph */}
      <meta property="og:site_name" content={BRAND} />
      <meta property="og:type" content="website" />
      <meta property="og:url" content={canonical} />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={description} />
      <meta property="og:image" content={`${SITE_URL}/og-cover.png`} />
      {/* Twitter */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={description} />
      <meta name="twitter:image" content={`${SITE_URL}/og-cover.png`} />
      {/* Robots: keep admin pages out of indexes */}
      <meta
        name="robots"
        content={
          pathname.startsWith('/admin') || pathname.startsWith('/me')
            ? 'noindex,nofollow'
            : 'index,follow'
        }
      />
    </Helmet>
  );
};
