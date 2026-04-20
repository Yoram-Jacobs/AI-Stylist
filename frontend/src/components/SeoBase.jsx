import { Helmet } from 'react-helmet-async';
import { useLocation } from 'react-router-dom';

const SITE_URL = 'https://ai-stylist-api.preview.emergentagent.com';
const BRAND = 'DressApp';
const DEFAULT_DESCRIPTION =
  'DressApp is your closet, marketplace, and AI stylist in one — manage what you own, sell or swap pieces with a 7% community fee, and get outfit advice grounded in your real schedule and weather.';

const ROUTE_META = {
  '/login': { title: 'Sign in', description: 'Sign in to DressApp to manage your closet, browse the marketplace, and chat with the AI stylist.' },
  '/register': { title: 'Create account', description: 'Join DressApp \u2014 your closet, community marketplace, and AI stylist in one place.' },
  '/home': { title: 'Today', description: 'Your daily DressApp brief: trends, closet stats, and the latest stylist reads.' },
  '/closet': { title: 'My closet', description: 'Every piece you own \u2014 with smart segmentation, source tags, and one-tap edit-with-AI.' },
  '/closet/add': { title: 'Add to closet', description: 'Add a new item to your DressApp closet from a photo or URL.' },
  '/stylist': { title: 'Stylist', description: 'Multimodal AI stylist that understands your closet, calendar, and the weather.' },
  '/market': { title: 'Marketplace', description: 'Buy, sell, swap, or donate community pieces with full fee transparency.' },
  '/market/create': { title: 'List a piece', description: 'List one of your closet items on the DressApp marketplace.' },
  '/transactions': { title: 'Transactions', description: 'Your DressApp purchases and sales, with full 7% fee transparency.' },
  '/admin': { title: 'Admin dashboard', description: 'DressApp operations console for users, marketplace, AI providers, and the Trend-Scout agent.' },
  '/me': { title: 'Profile & settings', description: 'Manage your DressApp profile, voice, and Google Calendar connection.' },
};

function metaFor(pathname) {
  if (ROUTE_META[pathname]) return ROUTE_META[pathname];
  // Dynamic routes
  if (pathname.startsWith('/closet/')) return { title: 'Closet item', description: 'A piece in your DressApp closet.' };
  if (pathname.startsWith('/market/')) return { title: 'Marketplace listing', description: 'A piece for sale on DressApp.' };
  return { title: BRAND, description: DEFAULT_DESCRIPTION };
}

/** Per-route Helmet that updates <title>, description, OG, Twitter, canonical. */
export const SeoBase = () => {
  const { pathname } = useLocation();
  const { title, description } = metaFor(pathname);
  const fullTitle = pathname === '/home' ? `${BRAND} \u2014 ${title}` : `${title} | ${BRAND}`;
  const canonical = `${SITE_URL}${pathname}`;
  return (
    <Helmet defaultTitle={BRAND} prioritizeSeoTags>
      <html lang="en" />
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
      <meta name="robots" content={pathname.startsWith('/admin') || pathname.startsWith('/me') ? 'noindex,nofollow' : 'index,follow'} />
    </Helmet>
  );
};
