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
const PICK_BANNER_ID = 'dressapp-pick-banner';
const PICK_HOVER_ID = 'dressapp-pick-hover';
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
      // No automatic match — invite the user to pick it manually.
      dismissOverlay();
      enterPickMode({ reason: 'auto-failed' });
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

async function _sendForAnalysis({ chart_html, chart_screenshot_b64, garment_type }) {
  mountSpinner();
  const payload = {
    chart_html,
    chart_screenshot_b64,
    garment_type: garment_type ?? generic.detectGarmentType(document),
    store: HOST.replace(/^www\./, ''),
    page_url: location.href,
    page_title: document.title,
  };
  log('analyze payload (preview)', {
    chart_html_len: payload.chart_html?.length || 0,
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
// Pick mode — user clicks the chart manually
// ---------------------------------------------------------------------
let _pickActive = false;

function enterPickMode({ reason = 'manual' } = {}) {
  if (_pickActive) return;
  _pickActive = true;
  hideFab();
  dismissOverlay();

  const banner = document.createElement('div');
  banner.id = PICK_BANNER_ID;
  banner.className = 'dressapp-pick-banner';
  banner.setAttribute('role', 'status');
  banner.setAttribute('data-testid', 'dressapp-pick-banner');
  banner.innerHTML = `
    <div class="dressapp-pick-text">
      <strong>Click the size chart</strong>
      <span>${reason === 'auto-failed' ? "We couldn't find it automatically — point at it." : 'Click the chart image or table you want to analyze.'}</span>
    </div>
    <button type="button" class="dressapp-pick-cancel" data-testid="dressapp-pick-cancel">Cancel</button>
  `;
  document.body.appendChild(banner);

  const hover = document.createElement('div');
  hover.id = PICK_HOVER_ID;
  hover.className = 'dressapp-pick-hover';
  hover.setAttribute('aria-hidden', 'true');
  document.body.appendChild(hover);

  function isOurChrome(t) {
    return t === banner || banner.contains(t) || t === hover || hover.contains(t);
  }

  function onMove(e) {
    if (isOurChrome(e.target)) { hover.style.display = 'none'; return; }
    const r = e.target.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) { hover.style.display = 'none'; return; }
    hover.style.display = 'block';
    hover.style.left = `${Math.max(0, r.left - 2)}px`;
    hover.style.top = `${Math.max(0, r.top - 2)}px`;
    hover.style.width = `${r.width + 4}px`;
    hover.style.height = `${r.height + 4}px`;
  }

  function onClick(e) {
    if (isOurChrome(e.target)) return;
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    const target = e.target;
    const x = e.clientX, y = e.clientY;
    cleanup();
    void handlePickedElement(target, x, y);
  }

  function onKey(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      cleanup();
      showFab();
    }
  }

  function cleanup() {
    _pickActive = false;
    document.removeEventListener('mousemove', onMove, true);
    document.removeEventListener('click', onClick, true);
    document.removeEventListener('keydown', onKey, true);
    banner.remove();
    hover.remove();
  }

  banner.querySelector('[data-testid="dressapp-pick-cancel"]')
    .addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      cleanup();
      showFab();
    });

  document.addEventListener('mousemove', onMove, true);
  document.addEventListener('click', onClick, true);
  document.addEventListener('keydown', onKey, true);
}

async function handlePickedElement(el, _x, _y) {
  mountSpinner();
  try {
    let chart_html = null;
    let chart_screenshot_b64 = null;

    // 1. <img> directly clicked, or contains an <img>.
    let img = null;
    if (el.tagName === 'IMG') img = el;
    else if (typeof el.querySelector === 'function') img = el.querySelector('img');
    if (!img && el.parentElement) {
      // Walk up a couple of levels — the user might have clicked a wrapper.
      let cur = el;
      for (let i = 0; i < 3 && cur && !img; i += 1) {
        if (cur.tagName === 'IMG') { img = cur; break; }
        cur = cur.parentElement;
      }
    }
    if (img) {
      chart_screenshot_b64 = await imageToB64Jpeg(img);
    }

    // 2. <table> in or around the click target.
    if (!chart_screenshot_b64) {
      const table = el.closest?.('table') || el.querySelector?.('table');
      if (table) chart_html = table.outerHTML.slice(0, 60_000);
    }

    // 3. Iframe — capture viewport (the iframe content lives elsewhere).
    if (!chart_html && !chart_screenshot_b64) {
      chart_screenshot_b64 = await _captureViewportWithPermission();
    }

    if (!chart_html && !chart_screenshot_b64) {
      mountOverlay({
        kind: 'warn',
        title: 'Couldn\'t capture that element',
        message: 'Try clicking directly on the size chart image or its table. If the chart is inside an iframe and screenshots are blocked, allow the optional permission and try again.',
        retry: () => enterPickMode({ reason: 'manual' }),
        onDismiss: showFab,
      });
      return;
    }

    await _sendForAnalysis({ chart_html, chart_screenshot_b64 });
  } catch (e) {
    mountOverlay({
      kind: 'error',
      title: 'Analysis failed',
      message: e?.message || String(e),
      retry: () => enterPickMode({ reason: 'manual' }),
      onDismiss: showFab,
    });
  }
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
  if (e.key === 'Escape' && !_pickActive) {
    dismissOverlay();
    showFab();
  }
}, true);
