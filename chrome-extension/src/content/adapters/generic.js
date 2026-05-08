/**
 * Generic size-chart + anchor detector.
 *
 * Used as the fallback adapter when the URL doesn't match a
 * site-specific one. Strategy:
 *   * ``detectChart`` — find the most chart-like ``<table>`` in the
 *     document. We score on the presence of size keywords, row count,
 *     and overall text length.
 *   * ``detectChartImage`` — many shopping sites publish their size
 *     chart as a single image inside the size-guide modal (H&M,
 *     AliExpress, some Amazon listings). We look for ``<img>`` whose
 *     ``alt``, ``src``, or surrounding text contains size keywords.
 *   * ``detectAnchor`` — find a place to mount the DressApp button.
 *     The classic anchor is a ``<select>`` for size, but more and more
 *     sites use button "pill" groups; we cover both.
 *   * ``detectGarmentType`` — heuristic noun extraction from H1 / OG
 *     title so the LLM has more context.
 *
 * Returning ``null`` is allowed; the content script falls back to a
 * visible-tab screenshot when both ``detectChart`` and
 * ``detectChartImage`` fail.
 */
const HINT_KEYWORDS = ['size', 'sizing', 'chest', 'bust', 'waist', 'hip', 'hips', 'inseam', 'shoulders', 'sleeve', 'length'];
const STRONG_KEYWORDS = ['size guide', 'size chart', 'sizing chart', 'size table'];

export function detectChart(_doc = document) {
  let best = null;
  let bestScore = 0;
  const tables = _doc.querySelectorAll('table');
  tables.forEach((tbl) => {
    const txt = (tbl.innerText || '').toLowerCase();
    let score = 0;
    HINT_KEYWORDS.forEach((k) => { if (txt.includes(k)) score += 8; });
    score += Math.min(50, tbl.querySelectorAll('tr').length * 5);
    if (txt.length < 40) score = 0; // tiny tables are probably not size charts
    // Demote tables that are clearly not chart-shaped (e.g. detail
    // sheets) by penalising tables without numeric tokens.
    if (!/\d/.test(txt)) score -= 20;
    if (score > bestScore) {
      bestScore = score;
      best = tbl;
    }
  });
  return best && bestScore >= 30 ? best : null;
}

/**
 * Look for an image-based size chart. Returns an <img> element or null.
 *
 * Heuristics:
 *   1. Any image whose ``alt`` or ``aria-label`` contains "size chart"
 *      / "size guide" / "size table".
 *   2. Any image inside a container (modal/dialog/section) whose
 *      heading text contains those phrases.
 *   3. As a last resort, the largest visible image whose ``src``
 *      contains ``size`` / ``chart`` / ``sizing``.
 */
export function detectChartImage(_doc = document) {
  const allImgs = Array.from(_doc.querySelectorAll('img')).filter(_isVisible);
  if (allImgs.length === 0) return null;

  // Strategy 1: alt/aria
  for (const img of allImgs) {
    const meta = `${img.alt || ''} ${img.getAttribute('aria-label') || ''}`.toLowerCase();
    if (STRONG_KEYWORDS.some((k) => meta.includes(k))) return img;
  }

  // Strategy 2: nearest heading inside an enclosing modal/section.
  const containers = _doc.querySelectorAll(
    '[role="dialog"], [aria-modal="true"], [class*=size-guide i], [class*=sizeGuide], [id*=size-guide i], [class*=size-chart i]',
  );
  for (const container of containers) {
    const h = container.querySelector('h1, h2, h3, [class*=title]');
    const heading = (h?.innerText || '').toLowerCase();
    if (STRONG_KEYWORDS.some((k) => heading.includes(k))) {
      const img = container.querySelector('img');
      if (img && _isVisible(img)) return img;
    }
  }

  // Strategy 3: src-based + sizable.
  let best = null;
  let bestArea = 0;
  for (const img of allImgs) {
    const src = (img.currentSrc || img.src || '').toLowerCase();
    if (!/(size|chart|sizing)/.test(src)) continue;
    const r = img.getBoundingClientRect();
    const area = Math.max(0, r.width) * Math.max(0, r.height);
    if (area > bestArea) {
      bestArea = area;
      best = img;
    }
  }
  // Demand at least 200x150 to avoid icons.
  return bestArea >= 30_000 ? best : null;
}

function _isVisible(el) {
  if (!el || !el.isConnected) return false;
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return false;
  const cs = el.ownerDocument?.defaultView?.getComputedStyle?.(el);
  if (!cs) return true;
  return cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity || '1') > 0.05;
}

export function detectAnchor(_doc = document) {
  // Order matters: prefer the closest analog of a "pick your size"
  // control so the button shows up next to user attention.
  const candidates = [
    'select[name*=size i]',
    'select[id*=size i]',
    '[data-testid*=size i]',
    '[aria-label*=size i]:not(button)',
    '[role="radiogroup"][aria-label*=size i]',
    '[role="listbox"][aria-label*=size i]',
    '[class*=size-selector i]',
    '[class*=sizeSelector i]',
    '[class*=size-picker i]',
    'fieldset[aria-label*=size i]',
    'label[for*=size i]',
    'button[aria-label*="size" i]',
    'button[aria-haspopup="dialog"][aria-label*=size i]',
  ];
  for (const sel of candidates) {
    const el = _doc.querySelector(sel);
    if (el && _isVisible(el)) return el;
  }
  // Final fallback: any element on the page whose own innerText starts
  // with the word "Size" (the size label above the picker on Amazon /
  // Zara mobile).
  const all = _doc.querySelectorAll('label, h2, h3, span, div');
  for (const el of all) {
    const txt = (el.innerText || '').trim().toLowerCase();
    if (/^size\b/.test(txt) && txt.length < 24 && _isVisible(el)) return el;
  }
  return null;
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

  const dict = ['shirt','t-shirt','tshirt','blouse','dress','skirt','pants','trousers','jeans','shorts','jacket','coat','hoodie','sweater','jumper','suit','blazer','cardigan','swimwear','bra','underwear','briefs','bralette','socks','leggings','tights','tank','top'];
  for (const word of dict) {
    if (sources.includes(word)) return word;
  }
  return null;
}

export default { detectChart, detectChartImage, detectAnchor, detectGarmentType };
