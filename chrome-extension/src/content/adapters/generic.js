/**
 * Generic size-chart detector.
 *
 * Used as the fallback adapter when the URL doesn't match a
 * site-specific one. Strategy:
 *   1. Look for any `<table>` whose surrounding text or own header
 *      cells contain words like 'size', 'chest', 'bust', 'waist',
 *      'hip', 'inseam'. Pick the one with the largest text payload.
 *   2. Look for size dropdowns (`select[name*=size]`,
 *      `[data-testid*=size]`, etc.) so the overlay button has
 *      something to anchor to.
 *
 * Returns ``{ chartElement, anchorElement, garmentType }`` — any of
 * which may be null. The content script handles the null cases by
 * falling back to a screenshot or a no-chart message.
 */
const HINT_KEYWORDS = ['size', 'chest', 'bust', 'waist', 'hip', 'inseam', 'shoulders', 'sleeve'];

export function detectChart(_doc = document) {
  let best = null;
  let bestScore = 0;
  const tables = _doc.querySelectorAll('table');
  tables.forEach((tbl) => {
    const txt = (tbl.innerText || '').toLowerCase();
    let score = 0;
    HINT_KEYWORDS.forEach((k) => { if (txt.includes(k)) score += 10; });
    score += Math.min(50, tbl.querySelectorAll('tr').length * 5);
    if (txt.length < 40) score = 0; // tiny tables are probably not size charts
    if (score > bestScore) {
      bestScore = score;
      best = tbl;
    }
  });
  return best && bestScore >= 30 ? best : null;
}

export function detectAnchor(_doc = document) {
  return (
    _doc.querySelector('select[name*=size i]') ||
    _doc.querySelector('select[id*=size i]') ||
    _doc.querySelector('[data-testid*=size i]') ||
    _doc.querySelector('[aria-label*=size i]') ||
    _doc.querySelector('[class*=size-selector i]') ||
    _doc.querySelector('label[for*=size i]') ||
    null
  );
}

export function detectGarmentType(_doc = document) {
  // Heuristic: parse the page H1 / breadcrumb / og:title for clothing
  // category words. Helps the LLM resolve sizing for ambiguous charts
  // (e.g. the same EU 38 means different cm depending on garment).
  const sources = [
    _doc.querySelector('meta[property="og:title"]')?.content,
    _doc.querySelector('h1')?.innerText,
    _doc.title,
  ].filter(Boolean).join(' ').toLowerCase();

  const dict = ['shirt','t-shirt','tshirt','blouse','dress','skirt','pants','trousers','jeans','shorts','jacket','coat','hoodie','sweater','jumper','suit','blazer','cardigan','swimwear','bra','underwear','briefs','bralette','socks'];
  for (const word of dict) {
    if (sources.includes(word)) return word;
  }
  return null;
}

export default { detectChart, detectAnchor, detectGarmentType };
