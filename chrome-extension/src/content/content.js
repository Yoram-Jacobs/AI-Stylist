/**
 * Content script entry point.
 *
 * UX (in order of preference, falling through automatically):
 *
 *   1. Inline anchor button next to the size picker (best-effort).
 *   2. Persistent FAB at bottom-left.
 *   3. On FAB click → AUTO detection (HTML chart → image chart).
 *   4. If AUTO finds nothing → automatically enter PICK MODE: a
 *      hover-highlight overlay invites the user to click the chart
 *      directly. We then use exactly that element.
 *   5. As a final last resort, the user can grant the optional
 *      `<all_urls>` permission to enable a full-viewport screenshot.
 *
 * Pick mode is the reliability win for sites where the chart lives
 * inside cross-origin iframes (AliExpress's localized hosts), shadow
 * roots, lazy-mounted tabs, or has otherwise-anonymous markup. The
 * user always has a manual way out.
 */
import { getAdapter } from './adapters/sites.js';
import generic from './adapters/generic.js';
import { messages, sendToBackground } from '@/lib/messages.js';
import { mountOverlay, mountSpinner, dismissOverlay } from './overlay.js';

const HOST = location.hostname;
const adapter = getAdapter(HOST);
const ANCHOR_MOUNTED_ATTR = 'data-dressapp-mounted';
const FAB_ID = 'dressapp-fab';
const LOG_PREFIX = `[DressApp/${adapter.name}]`;
const isTopFrame = window === window.top;

function log(...args) {
  if (window.localStorage?.getItem('dressapp_debug')) console.info(LOG_PREFIX, ...args);
}

// ---------------------------------------------------------------------
// Anchor button (inline, next to the size picker)
// ---------------------------------------------------------------------
function createAnchorButton() {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'dressapp-anchor-btn';
  btn.setAttribute('aria-label', 'DressApp size recommendation');
  btn.setAttribute('data-testid', 'dressapp-anchor-btn');
  btn.innerHTML = `<span class="dressapp-dot" aria-hidden="true"></span>DressApp size`;
  btn.addEventListener('click', onAnalyze);
  return btn;
}

function mountAnchorButton() {
  if (!isTopFrame) return false;
  const anchor = generic.detectAnchor(document);
  if (!anchor) return false;
  if (anchor.hasAttribute(ANCHOR_MOUNTED_ATTR)) return true;
  anchor.setAttribute(ANCHOR_MOUNTED_ATTR, '1');
  const btn = createAnchorButton();
  anchor.parentNode?.insertBefore(btn, anchor.nextSibling);
  log('anchor mounted next to', anchor);
  return true;
}

// ---------------------------------------------------------------------
// Persistent FAB (bottom-left corner) — top frame only
// ---------------------------------------------------------------------
function ensureFab() {
  if (!isTopFrame) return null;
  let fab = document.getElementById(FAB_ID);
  if (fab) return fab;
  fab = document.createElement('button');
  fab.id = FAB_ID;
  fab.type = 'button';
  fab.className = 'dressapp-fab';
  fab.setAttribute('aria-label', 'Get DressApp size recommendation');
  fab.setAttribute('data-testid', 'dressapp-fab');
  fab.title = 'Click for a DressApp size recommendation. If we can\'t find the chart automatically, you\'ll be asked to click it.';
  fab.innerHTML = `
    <span class="dressapp-fab-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2 9 8l-7 1 5 5-1 7 6-3 6 3-1-7 5-5-7-1z"></path>
      </svg>
    </span>
    <span class="dressapp-fab-label">DressApp</span>
  `;
  fab.addEventListener('click', onAnalyze);
  document.body.appendChild(fab);
  return fab;
}

function hideFab() {
  const fab = document.getElementById(FAB_ID);
  if (fab) fab.style.opacity = '0';
}
function showFab() {
  const fab = document.getElementById(FAB_ID);
  if (fab) fab.style.opacity = '';
}

// ---------------------------------------------------------------------
// Image -> base64 helpers
// ---------------------------------------------------------------------
async function imageToB64Jpeg(img) {
  const src = img.currentSrc || img.src;
  if (!src) return null;
  try {
    const resp = await fetch(src, { credentials: 'omit', cache: 'force-cache' });
    if (resp.ok) {
      const blob = await resp.blob();
      return await blobToB64(blob);
    }
  } catch (_) { /* try canvas */ }
  try {
    const canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth || img.width;
    canvas.height = img.naturalHeight || img.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return _stripDataPrefix(canvas.toDataURL('image/jpeg', 0.85));
  } catch (_) { return null; }
}

async function blobToB64(blob) {
  const dataUrl = await new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onloadend = () => resolve(fr.result);
    fr.onerror = () => reject(fr.error);
    fr.readAsDataURL(blob);
  });
  return _stripDataPrefix(dataUrl);
}

function _stripDataPrefix(dataUrl) {
  if (typeof dataUrl !== 'string') return null;
  const i = dataUrl.indexOf(',');
  return i >= 0 ? dataUrl.slice(i + 1) : dataUrl;
}

async function _captureViewportWithPermission() {
  let cap = await sendToBackground({ type: messages.CAPTURE_VISIBLE_TAB });
  if (cap?.ok && cap.image_b64) return cap.image_b64;
  if (cap?.needs_permission || /<all_urls>|activeTab/i.test(cap?.error || '')) {
    try {
      const granted = await chrome.permissions.request({ origins: ['<all_urls>'] });
      if (granted) {
        cap = await sendToBackground({ type: messages.CAPTURE_VISIBLE_TAB });
        if (cap?.ok && cap.image_b64) return cap.image_b64;
      }
    } catch (e) {
      log('permissions.request failed', e);
    }
  }
  log('captureVisibleTab unavailable', cap?.error);
  return null;
}

// ---------------------------------------------------------------------
// Visible-region scopes
// ---------------------------------------------------------------------
function findVisibleScopes() {
  const scopes = [];
  document.querySelectorAll(
    '[role="dialog"], [aria-modal="true"], dialog[open], [class*=modal i][class*=open i], [class*=Modal i]:not([aria-hidden="true"])'
  ).forEach((el) => { if (_isVisible(el)) scopes.push(el); });
  document.querySelectorAll(
    '[role="tabpanel"]:not([hidden]):not([aria-hidden="true"]), [class*=tab-panel i]:not([aria-hidden="true"])'
  ).forEach((el) => { if (_isVisible(el) && _intersectsViewport(el)) scopes.push(el); });
  document.querySelectorAll(
    '[id*=description i], [class*=description i], [id*=detail i], [class*=detail i], [class*=size-guide i], [class*=size-chart i]'
  ).forEach((el) => { if (_isVisible(el)) scopes.push(el); });
  return Array.from(new Set(scopes));
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

function findInScopes(detector) {
  const scopes = findVisibleScopes();
  for (const s of scopes) {
    const found = detector(s);
    if (found) return found;
  }
  return detector(document) || null;
}

// ---------------------------------------------------------------------
// Auto analyze flow
// ---------------------------------------------------------------------
async function onAnalyze(ev) {
  ev?.preventDefault?.();
  ev?.stopPropagation?.();
  if (!isTopFrame) return;
  hideFab();
  mountSpinner();
  try {
    const status = await sendToBackground({ type: messages.AUTH_STATUS });
    if (!status?.ok || !status.token) {
      mountOverlay({
        kind: 'auth',
        title: 'Connect DressApp first',
        message: 'Open the DressApp extension popup and click "Connect to DressApp" to enable size recommendations.',
        onDismiss: showFab,
      });
      return;
    }

    let chartEl = findInScopes((doc) => adapter.detectChart(doc) || generic.detectChart(doc));
    let chartImg = chartEl ? null : findInScopes((doc) => generic.detectChartImage(doc));

    if (!chartEl && !chartImg) {
      _logDetectionDiagnostics();
      // No automatic match — invite the user to crop the chart manually.
      dismissOverlay();
      enterCropMode({ reason: 'auto-failed' });
      return;
    }

    let chart_screenshot_b64 = null;
    if (chartImg) {
      chart_screenshot_b64 = await imageToB64Jpeg(chartImg);
      if (!chart_screenshot_b64) {
        chart_screenshot_b64 = await _captureViewportWithPermission();
      }
    }

    await _sendForAnalysis({
      chart_html: chartEl ? chartEl.outerHTML.slice(0, 60_000) : null,
      chart_text: chartEl ? (chartEl.innerText || '').slice(0, 8_000) : null,
      chart_screenshot_b64,
      garment_type: generic.detectGarmentType(document),
    });
  } catch (e) {
    mountOverlay({
      kind: 'error',
      title: 'Analysis failed',
      message: e?.message || String(e),
      retry: () => onAnalyze(),
      onDismiss: showFab,
    });
  }
}

async function _sendForAnalysis({ chart_html, chart_text, chart_screenshot_b64, garment_type }) {
  mountSpinner();
  const payload = {
    chart_html,
    chart_text,
    chart_screenshot_b64,
    garment_type: garment_type ?? generic.detectGarmentType(document),
    store: HOST.replace(/^www\./, ''),
    page_url: location.href,
    page_title: document.title,
  };
  log('analyze payload (preview)', {
    chart_html_len: payload.chart_html?.length || 0,
    chart_text_len: payload.chart_text?.length || 0,
    chart_screenshot_len: payload.chart_screenshot_b64?.length || 0,
    garment_type: payload.garment_type,
  });
  const r = await sendToBackground({ type: messages.ANALYZE_CHART, payload });
  if (!r?.ok) {
    mountOverlay({
      kind: 'error',
      title: 'Analysis failed',
      message: r?.error || 'Unknown error',
      retry: () => onAnalyze(),
      onDismiss: showFab,
    });
    return;
  }
  mountOverlay({
    kind: 'recommendation',
    result: r.result,
    store: payload.store,
    onDismiss: showFab,
    // If the recommendation came back without a size, give the user
    // a way to retry by picking the chart manually — the backend's
    // ``reasoning`` field already tells them *why* it couldn't pick.
    retry: r.result?.recommended_size ? null : () => enterCropMode({ reason: 'manual' }),
  });
}

function _logDetectionDiagnostics() {
  if (!window.localStorage?.getItem('dressapp_debug')) return;
  const imgs = Array.from(document.querySelectorAll('img'));
  const visImgs = imgs.filter(_isVisible);
  console.groupCollapsed(`${LOG_PREFIX} detection diagnostics`);
  console.log('total <img>:', imgs.length, 'visible:', visImgs.length);
  console.log('frames:', window.frames.length);
  visImgs.slice(0, 10).forEach((img, i) => {
    const r = img.getBoundingClientRect();
    console.log(`#${i}`, {
      area: Math.round(r.width * r.height),
      w: Math.round(r.width), h: Math.round(r.height),
      alt: img.alt?.slice(0, 60),
      src: (img.currentSrc || img.src || '').slice(0, 80),
    });
  });
  console.groupEnd();
}

// ---------------------------------------------------------------------
// Crop mode — user drags a rectangle around the chart, clicks Apply.
//
// Why crop:
//   * The chart is often a single <img> on the page that our heuristic
//     misses (e.g. AliExpress's seller-uploaded JPGs in cross-origin
//     iframes), and a viewport screenshot of the whole tab carries
//     too much noise (product photos, ads) for the OCR to focus.
//   * Letting the user define the exact rectangle gives the backend
//     the cleanest possible image to feed Gemma's chart-extraction
//     pass. It also works inside iframes, shadow roots, lazy-loaded
//     panels — anywhere a screenshot can reach.
// ---------------------------------------------------------------------
const CROP_BANNER_ID = 'dressapp-crop-banner';
const CROP_OVERLAY_ID = 'dressapp-crop-overlay';
const CROP_RECT_ID = 'dressapp-crop-rect';
let _cropActive = false;

function enterCropMode({ reason = 'manual' } = {}) {
  if (_cropActive) return;
  _cropActive = true;
  hideFab();
  dismissOverlay();

  // Banner with size readout + Apply / Cancel.
  const banner = document.createElement('div');
  banner.id = CROP_BANNER_ID;
  banner.className = 'dressapp-pick-banner';
  banner.setAttribute('role', 'status');
  banner.setAttribute('data-testid', 'dressapp-crop-banner');
  banner.innerHTML = `
    <div class="dressapp-pick-text">
      <strong>Drag a box around the size chart</strong>
      <span data-role="hint">${reason === 'auto-failed' ? "We couldn't find it automatically." : 'Drag to select. Drag the corners or edges to adjust. Click Apply.'}</span>
    </div>
    <span class="dressapp-crop-size" data-testid="dressapp-crop-size" hidden>0×0</span>
    <button type="button" class="dressapp-pick-cancel" data-testid="dressapp-crop-cancel">Cancel</button>
    <button type="button" class="dressapp-crop-apply" data-testid="dressapp-crop-apply" disabled>Apply</button>
  `;
  document.body.appendChild(banner);

  // Dim overlay covering the whole viewport.
  const dim = document.createElement('div');
  dim.id = CROP_OVERLAY_ID;
  dim.className = 'dressapp-crop-overlay';
  dim.setAttribute('aria-hidden', 'true');
  document.body.appendChild(dim);

  // The crop rectangle. Once the user has finished drawing it, we
  // mount 8 resize handles (NW/N/NE/E/SE/S/SW/W) inside it and let
  // them drag the rect around as a whole as well.
  const rectEl = document.createElement('div');
  rectEl.id = CROP_RECT_ID;
  rectEl.className = 'dressapp-crop-rect';
  rectEl.setAttribute('aria-hidden', 'true');
  rectEl.setAttribute('data-testid', 'dressapp-crop-rect');
  // Handles. Pointer-events:auto on each handle so they can be grabbed
  // even though the parent rect itself is non-interactive when idle.
  const HANDLE_KEYS = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
  HANDLE_KEYS.forEach((k) => {
    const h = document.createElement('div');
    h.className = `dressapp-crop-handle dressapp-crop-handle-${k}`;
    h.dataset.handle = k;
    rectEl.appendChild(h);
  });
  document.body.appendChild(rectEl);

  const applyBtn = banner.querySelector('[data-testid="dressapp-crop-apply"]');
  const cancelBtn = banner.querySelector('[data-testid="dressapp-crop-cancel"]');
  const sizeReadout = banner.querySelector('[data-testid="dressapp-crop-size"]');
  const hintEl = banner.querySelector('[data-role="hint"]');

  // Single rect-state object so each gesture mutates it in-place.
  let rect = null;            // { x, y, w, h } in CSS pixels
  let mode = 'idle';          // 'idle' | 'draw' | 'move' | 'resize-<handle>'
  let anchor = null;          // gesture-specific reference state

  function isOurChrome(t) { return banner === t || banner.contains(t); }
  function isOurRect(t)   { return rectEl === t || rectEl.contains(t); }

  function commitRect(next) {
    rect = _normaliseRect(next);
    rectEl.style.left = `${rect.x}px`;
    rectEl.style.top = `${rect.y}px`;
    rectEl.style.width = `${rect.w}px`;
    rectEl.style.height = `${rect.h}px`;
    rectEl.style.display = 'block';
    const big = rect.w >= 24 && rect.h >= 16;
    applyBtn.disabled = !big;
    sizeReadout.hidden = !big;
    sizeReadout.textContent = `${Math.round(rect.w)}×${Math.round(rect.h)}`;
    if (big && hintEl) hintEl.textContent = 'Drag corners or edges to refine. Click Apply.';
  }

  function onDown(e) {
    if (e.button !== 0) return;
    if (isOurChrome(e.target)) return;
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();

    // Resize handle?
    if (e.target?.classList?.contains('dressapp-crop-handle')) {
      mode = `resize-${e.target.dataset.handle}`;
      anchor = { startX: e.clientX, startY: e.clientY, base: { ...rect } };
      return;
    }
    // Inside the rect (drag-to-move)?
    if (rect && isOurRect(e.target)) {
      mode = 'move';
      anchor = { startX: e.clientX, startY: e.clientY, base: { ...rect } };
      return;
    }
    // Anywhere else: start drawing a fresh rectangle.
    mode = 'draw';
    anchor = { startX: e.clientX, startY: e.clientY };
    commitRect({ x: e.clientX, y: e.clientY, w: 0, h: 0 });
  }

  function onMove(e) {
    if (mode === 'idle') return;
    if (mode === 'draw') {
      const { startX, startY } = anchor;
      commitRect({
        x: Math.min(startX, e.clientX),
        y: Math.min(startY, e.clientY),
        w: Math.abs(e.clientX - startX),
        h: Math.abs(e.clientY - startY),
      });
      return;
    }
    if (mode === 'move') {
      const dx = e.clientX - anchor.startX;
      const dy = e.clientY - anchor.startY;
      const b = anchor.base;
      const x = Math.max(0, Math.min(window.innerWidth - b.w, b.x + dx));
      const y = Math.max(0, Math.min(window.innerHeight - b.h, b.y + dy));
      commitRect({ x, y, w: b.w, h: b.h });
      return;
    }
    if (mode.startsWith('resize-')) {
      const handle = mode.slice('resize-'.length);
      const dx = e.clientX - anchor.startX;
      const dy = e.clientY - anchor.startY;
      const b = anchor.base;
      let { x, y, w, h } = b;
      if (handle.includes('w')) { x = b.x + dx; w = b.w - dx; }
      if (handle.includes('e')) { w = b.w + dx; }
      if (handle.includes('n')) { y = b.y + dy; h = b.h - dy; }
      if (handle.includes('s')) { h = b.h + dy; }
      commitRect({ x, y, w, h });
    }
  }

  function onUp() {
    if (mode === 'idle') return;
    // If the user did a tiny click without dragging, treat it as a
    // false-start and reset the rect so the next drag starts fresh.
    if (mode === 'draw' && rect && (rect.w < 8 || rect.h < 8)) {
      rect = null;
      rectEl.style.display = 'none';
      applyBtn.disabled = true;
      sizeReadout.hidden = true;
    }
    mode = 'idle';
    anchor = null;
  }

  function onKey(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      cleanup();
      showFab();
    } else if (e.key === 'Enter' && rect && !applyBtn.disabled) {
      e.preventDefault();
      void doApply();
    }
  }

  function cleanup() {
    _cropActive = false;
    document.removeEventListener('mousedown', onDown, true);
    document.removeEventListener('mousemove', onMove, true);
    document.removeEventListener('mouseup', onUp, true);
    document.removeEventListener('keydown', onKey, true);
    banner.remove();
    dim.remove();
    rectEl.remove();
  }

  async function doApply() {
    if (!rect) return;
    const r = rect;
    cleanup();
    await cropAndAnalyze(r);
  }

  applyBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    void doApply();
  });
  cancelBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    cleanup();
    showFab();
  });

  document.addEventListener('mousedown', onDown, true);
  document.addEventListener('mousemove', onMove, true);
  document.addEventListener('mouseup', onUp, true);
  document.addEventListener('keydown', onKey, true);
}

/**
 * Clamp a rect to the viewport, keep w/h non-negative, and ensure
 * the rect always has positive dimensions so handle math stays sane
 * when the user drags one edge past its opposite (the rect "flips").
 */
function _normaliseRect({ x, y, w, h }) {
  if (w < 0) { x += w; w = -w; }
  if (h < 0) { y += h; h = -h; }
  x = Math.max(0, x);
  y = Math.max(0, y);
  w = Math.min(window.innerWidth - x, Math.max(0, w));
  h = Math.min(window.innerHeight - y, Math.max(0, h));
  return { x, y, w, h };
}

/**
 * Find the best HTML chart-shaped node whose bounding box overlaps
 * the crop rectangle. We score `<table>` elements by intersection
 * area + the existing `generic.detectChart` chart-likeness signal,
 * which lets us send the underlying structured HTML alongside the
 * cropped screenshot. The backend can then run its instant heuristic
 * on the text without waiting on the LLM.
 *
 * Returns the matching element's outerHTML (capped at 60 KB) or null.
 */
function _extractHtmlInRect(rect) {
  const cx2 = rect.x + rect.w;
  const cy2 = rect.y + rect.h;

  // Phase 1: classic <table>, [role="table"], [role="grid"] elements.
  // These are the "happy path" — semantic markup that the backend
  // heuristic understands directly.
  const SEMANTIC_SEL = 'table, [role="table"], [role="grid"]';
  const semantic = Array.from(document.querySelectorAll(SEMANTIC_SEL));
  let best = null;
  let bestScore = 0;
  for (const t of semantic) {
    if (!t.isConnected) continue;
    const r = t.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const ix = Math.max(0, Math.min(r.right, cx2) - Math.max(r.left, rect.x));
    const iy = Math.max(0, Math.min(r.bottom, cy2) - Math.max(r.top, rect.y));
    const inter = ix * iy;
    if (inter <= 0) continue;
    const txt = (t.innerText || '').toLowerCase();
    const looksChart = /\b(size|chest|bust|waist|hip|shoulder|sleeve|length)\b/.test(txt) && /\d/.test(txt);
    const score = inter * (looksChart ? 4 : 1);
    if (score > bestScore) {
      bestScore = score;
      best = t;
    }
  }
  if (best) {
    return {
      html: best.outerHTML.slice(0, 60_000),
      text: (best.innerText || '').slice(0, 8_000),
    };
  }

  // Phase 2: div-based grid layouts (AliExpress, Shein, many modern
  // SPAs). These render the chart as nested <div>s, sometimes with
  // CSS grid / flexbox, and there is no semantic table at all.
  //
  // Strategy: find the *smallest* element fully containing the user's
  // crop rectangle whose innerText looks like a size chart — i.e.
  // contains size-keyword headers AND multiple numeric tokens AND
  // multiple size-label tokens (S / M / L / XS / EU 38 / etc.).
  // We walk up from the deepest element at the rect's center to
  // avoid grabbing the entire <body>.
  return _extractDivChartHtml(rect, cx2, cy2);
}

/**
 * Look for a div-based size chart whose bounding rect overlaps the
 * user's crop box. Walks upward from the element at the crop's
 * center until we find one whose innerText scores as a chart.
 *
 * Capped at 60 KB outerHTML so we never blow past the backend
 * payload limit.
 */
function _extractDivChartHtml(rect, cx2, cy2) {
  const cx = rect.x + rect.w / 2;
  const cy = rect.y + rect.h / 2;
  let node = null;
  try {
    node = document.elementFromPoint(cx, cy);
  } catch {
    node = null;
  }
  if (!node) return null;

  const SIZE_LABEL_RE = /\b(?:XXS|XS|S|M|L|XL|XXL|XXXL|2XL|3XL|4XL|5XL|EU\s?\d{2}|US\s?\d{1,2}|UK\s?\d{1,2}|\d{2,3}\s?cm)\b/gi;
  const KEYWORD_RE = /\b(size|chest|bust|waist|hip|hips|shoulder|shoulders|sleeve|length|inseam|bottom)\b/gi;
  const NUM_RE = /\b\d{2,3}(?:[.,]\d)?\b/g;

  function _scoreText(txt) {
    if (!txt) return 0;
    const lower = txt.toLowerCase();
    const labels = (lower.match(SIZE_LABEL_RE) || []).length;
    const keywords = (lower.match(KEYWORD_RE) || []).length;
    const nums = (lower.match(NUM_RE) || []).length;
    // Need at least: 2 keyword headers, 2 size labels, 4 numbers.
    if (keywords < 2 || labels < 2 || nums < 4) return 0;
    // Score weighted toward numeric density (real charts have lots
    // of numbers vs. surrounding marketing copy).
    return keywords * 3 + labels * 2 + nums;
  }

  let cur = node;
  let bestEl = null;
  let bestScore = 0;
  let bestSize = Infinity;
  // Walk up at most 12 levels — enough to escape the leaf cell into
  // the chart container without ever reaching <body>.
  for (let depth = 0; depth < 12 && cur && cur !== document.body; depth++) {
    const r = cur.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) {
      // Must reasonably overlap the crop box (not just a single cell).
      const ix = Math.max(0, Math.min(r.right, cx2) - Math.max(r.left, rect.x));
      const iy = Math.max(0, Math.min(r.bottom, cy2) - Math.max(r.top, rect.y));
      const inter = ix * iy;
      const cropArea = Math.max(1, rect.w * rect.h);
      const overlapPct = inter / cropArea;
      if (overlapPct > 0.25) {
        const txt = cur.innerText || '';
        // Skip absurdly large containers (likely the whole page).
        if (txt.length < 12_000) {
          const sc = _scoreText(txt);
          if (sc > 0) {
            // Prefer the *smallest* container that still scores —
            // otherwise we'd always pick body. Score must beat the
            // current best by a clear margin to override size.
            const elArea = r.width * r.height;
            if (sc > bestScore || (sc >= bestScore && elArea < bestSize)) {
              bestEl = cur;
              bestScore = sc;
              bestSize = elArea;
            }
          }
        }
      }
    }
    cur = cur.parentElement;
  }
  if (!bestEl) return null;
  try {
    return {
      html: bestEl.outerHTML.slice(0, 60_000),
      text: (bestEl.innerText || '').slice(0, 8_000),
    };
  } catch {
    return null;
  }
}

/**
 * Capture the viewport, crop to the user's CSS-pixel rectangle, send
 * the result for analysis. The crop happens locally in a canvas so we
 * never ship the surrounding (potentially-sensitive) viewport content
 * to the backend — only the bounded chart region.
 */
async function cropAndAnalyze(rect) {
  mountSpinner();
  try {
    // 1) Try to also pull the HTML table the user just framed. When
    //    the chart is HTML (e.g. AliExpress Size Guide modal), this
    //    lets the backend's heuristic answer in <50 ms without
    //    waiting on the LLM stack. We also collect the chart's
    //    visual ``innerText`` — for div-based layouts the HTML
    //    flattens poorly server-side, but the rendered text
    //    preserves row structure, so the heuristic can parse it.
    const extracted = _extractHtmlInRect(rect);
    const chart_html = extracted?.html || null;
    const chart_text = extracted?.text || null;

    // 2) Capture and crop the viewport screenshot for the LLM path.
    const screenshot = await _captureViewportWithPermission();
    let cropped = null;
    if (screenshot) {
      try {
        const dataUrl = `data:image/jpeg;base64,${screenshot}`;
        const img = await _loadImage(dataUrl);
        const dpr = window.devicePixelRatio || 1;
        const sx = Math.max(0, Math.round(rect.x * dpr));
        const sy = Math.max(0, Math.round(rect.y * dpr));
        const sw = Math.min(img.width - sx, Math.round(rect.w * dpr));
        const sh = Math.min(img.height - sy, Math.round(rect.h * dpr));
        if (sw >= 8 && sh >= 8) {
          const canvas = document.createElement('canvas');
          canvas.width = sw;
          canvas.height = sh;
          const ctx = canvas.getContext('2d');
          if (ctx) {
            ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
            cropped = _stripDataPrefix(canvas.toDataURL('image/jpeg', 0.88));
          }
        }
        if (window.localStorage?.getItem('dressapp_debug')) {
          console.info(LOG_PREFIX, 'crop sent', {
            cssRect: rect,
            sourceImg: { w: img.width, h: img.height },
            cropPx: { sx, sy, sw, sh },
            dpr,
            b64Len: cropped?.length || 0,
            chartHtmlLen: chart_html?.length || 0,
          });
        }
      } catch (e) {
        log('crop canvas failed', e);
      }
    }

    if (!chart_html && !chart_text && !cropped) {
      mountOverlay({
        kind: 'warn',
        title: 'Couldn\'t capture this region',
        message: 'DressApp needs either a visible HTML table inside the box or the optional "all sites" permission for a screenshot. Click the DressApp toolbar icon, approve the permission, then try again.',
        retry: () => enterCropMode({ reason: 'manual' }),
        onDismiss: showFab,
      });
      return;
    }

    await _sendForAnalysis({
      chart_html,
      chart_text,
      chart_screenshot_b64: cropped,
      garment_type: generic.detectGarmentType(document),
    });
  } catch (e) {
    mountOverlay({
      kind: 'error',
      title: 'Couldn\'t process the crop',
      message: e?.message || String(e),
      retry: () => enterCropMode({ reason: 'manual' }),
      onDismiss: showFab,
    });
  }
}

function _loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = (e) => reject(e?.message || 'image load failed');
    img.src = src;
  });
}

// ---------------------------------------------------------------------
// Mount lifecycle
// ---------------------------------------------------------------------
let pending = false;
function scheduleMount() {
  if (pending) return;
  pending = true;
  requestAnimationFrame(() => {
    pending = false;
    mountAnchorButton();
    ensureFab();
  });
}

const observer = new MutationObserver(scheduleMount);
observer.observe(document.documentElement, { subtree: true, childList: true });
mountAnchorButton();
ensureFab();

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !_cropActive) {
    dismissOverlay();
    showFab();
  }
}, true);
