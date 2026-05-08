/**
 * Generic size-chart + anchor detector.
 *
 * Layered strategy, cheapest first. The content script calls each
 * detector in turn; the first non-null wins.
 *
 *   * ``detectChart``         — table-shaped HTML chart (best signal)
 *   * ``detectChartImage``    — chart rendered as a single <img>
 *   * ``detectAnchor``        — where to mount the inline pill button
 *   * ``detectGarmentType``   — extract a noun for the LLM prompt
 *
 * The image detector is the workhorse on AliExpress / H&M / Amazon
 * sellers who publish their chart as a single uploaded JPG. We score
 * candidates by:
 *   1. Strong textual signal (alt / aria / heading mentions "size guide")
 *   2. Inside an open dialog or visible "size guide"-classed container
 *   3. Inside the active Description / Specifications tab
 *   4. Largest visible image with chart-like aspect ratio that ISN'T
 *      inside a product-photo carousel
 *
 * Returning ``null`` is allowed; the content script then falls back to
 * a viewport screenshot (when permitted) before giving up.
 */
const HINT_KEYWORDS = ['size', 'sizing', 'chest', 'bust', 'waist', 'hip', 'hips', 'inseam', 'shoulders', 'shoulder', 'sleeve', 'length', 'bottom'];
const STRONG_KEYWORDS = ['size guide', 'size chart', 'sizing chart', 'size table', 'jacket size', 'measurement chart'];
const GALLERY_HINTS = /(gallery|carousel|thumb|hero|slick|swiper|pdp-images|product-images|main-image|primary-image|image-list)/i;

export function detectChart(_doc = document) {
  let best = null;
  let bestScore = 0;
  const tables = _doc.querySelectorAll('table');
  tables.forEach((tbl) => {
    const txt = (tbl.innerText || '').toLowerCase();
    let score = 0;
    HINT_KEYWORDS.forEach((k) => { if (txt.includes(k)) score += 8; });
    score += Math.min(50, tbl.querySelectorAll('tr').length * 5);
    if (txt.length < 40) score = 0;
    if (!/\d/.test(txt)) score -= 20;
    if (score > bestScore) { bestScore = score; best = tbl; }
  });
  return best && bestScore >= 30 ? best : null;
}

/**
 * Returns the <img> element most likely to be a size chart, or null.
 *
 * We score every visible <img> on the page and pick the highest-scoring
 * one above a threshold. Scoring is permissive on purpose because many
 * legit chart images carry no semantic metadata at all (Aliexpress &
 * Amazon sellers upload a JPG that happens to contain the table).
 */
export function detectChartImage(_doc = document) {
  const imgs = Array.from(_doc.querySelectorAll('img')).filter(_isVisible);
  if (imgs.length === 0) return null;

  const scored = imgs.map((img) => ({ img, score: _scoreChartImage(img) }));
  scored.sort((a, b) => b.score - a.score);
  const top = scored[0];
  return top && top.score >= 6 ? top.img : null;
}

function _scoreChartImage(img) {
  let score = 0;

  // --- bail-out conditions -------------------------------------------
  const r = img.getBoundingClientRect();
  const area = Math.max(0, r.width) * Math.max(0, r.height);
  if (area < 30_000) return -1;            // too small to be a chart
  if (r.width < 160 || r.height < 120) return -1;
  const aspect = r.width / r.height;
  if (aspect < 0.4 || aspect > 4.0) return -1; // banners / vertical strips

  // --- positive signals ----------------------------------------------
  const alt = (img.alt || '').toLowerCase();
  const aria = (img.getAttribute('aria-label') || '').toLowerCase();
  const meta = `${alt} ${aria}`;
  if (STRONG_KEYWORDS.some((k) => meta.includes(k))) score += 30;
  HINT_KEYWORDS.forEach((k) => { if (meta.includes(k)) score += 2; });

  const src = (img.currentSrc || img.src || '').toLowerCase();
  if (/(size|sizing|chart|measure)/.test(src)) score += 8;

  // Boost for being inside an open modal / size-guide-named container.
  if (img.closest('[role="dialog"], [aria-modal="true"], dialog[open]')) score += 14;
  if (img.closest('[class*=size-guide i], [class*=sizeGuide], [class*=size-chart i], [id*=size-guide i], [id*=sizeChart i]')) score += 18;

  // Boost for being inside the visible Description / Specifications
  // tab — the most common home for chart-as-image listings.
  const descScope = img.closest('[id*=description i], [class*=description i], [id*=detail i], [class*=detail i], [role="tabpanel"]');
  if (descScope && _isVisible(descScope) && _intersectsViewport(descScope)) score += 10;

  // Surrounding text containing measurement keywords (cheap, very
  // effective on stores that publish chart-as-image but DO put the
  // word "size chart" in a heading near it).
  const ctx = _nearbyText(img, 1200).toLowerCase();
  let kwHits = 0;
  HINT_KEYWORDS.forEach((k) => { if (ctx.includes(k)) kwHits += 1; });
  score += Math.min(kwHits * 1.5, 9);
  if (STRONG_KEYWORDS.some((k) => ctx.includes(k))) score += 12;

  // Visible & in-viewport bonus (the user clicks the FAB while looking
  // at the chart, so it's almost always on screen).
  if (_intersectsViewport(img)) score += 6;

  // Penalise images that are obviously product photos.
  if (img.closest('a[href]')) score -= 4;
  if (img.closest('button')) score -= 4;
  let cur = img;
  for (let i = 0; i < 6 && cur; i += 1) {
    const cls = `${cur.className || ''} ${cur.id || ''}`;
    if (typeof cls === 'string' && GALLERY_HINTS.test(cls)) { score -= 14; break; }
    cur = cur.parentElement;
  }

  // Finally, a faint preference for larger images so that, all else
  // equal, we pick the bigger candidate.
  score += Math.min(area / 200_000, 4);
  return score;
}

function _nearbyText(el, maxChars) {
  // Pull text from the nearest "container" ancestor — a heading, a
  // figcaption, or an enclosing div with a manageable text payload.
  let cur = el.parentElement;
  let collected = '';
  for (let i = 0; i < 4 && cur; i += 1) {
    const t = (cur.innerText || '').slice(0, maxChars);
    if (t.length > collected.length) collected = t;
    if (collected.length >= maxChars) break;
    cur = cur.parentElement;
  }
  return collected;
}

function _isVisible(el) {
  if (!el || !el.isConnected) return false;
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return false;
  const cs = el.ownerDocument?.defaultView?.getComputedStyle?.(el);
  if (!cs) return true;
  return cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity || '1') > 0.05;
}
function _intersectsViewport(el) {
  const r = el.getBoundingClientRect();
  return r.bottom > 0 && r.top < (window.innerHeight || 1e6);
}

export function detectAnchor(_doc = document) {
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
  const all = _doc.querySelectorAll('label, h2, h3, span, div');
  for (const el of all) {
    const txt = (el.innerText || '').trim().toLowerCase();
    if (/^size\b/.test(txt) && txt.length < 24 && _isVisible(el)) return el;
  }
  return null;
}

export function detectGarmentType(_doc = document) {
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
