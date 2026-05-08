/**
 * Content script entry point — runs on every shopping site listed
 * in manifest.json. Two surfaces:
 *
 *   * **Persistent FAB** (bottom-right) that's always available so
 *     the user can open the size-guide modal / Description tab
 *     *first* and then ask DressApp to recommend a size. This is the
 *     primary trigger now that we know charts are usually behind a
 *     click.
 *   * Inline **anchor button** mounted next to the size picker as a
 *     secondary affordance (best-effort; harmless if it can't find a
 *     home).
 *
 * On click, we run `analyze` against whatever is *currently visible*:
 *   1. open modal / dialog
 *   2. visible tab panel / active accordion
 *   3. site adapter HTML chart
 *   4. generic HTML chart
 *   5. image-based chart
 *   6. visible-tab screenshot fallback (SW captureVisibleTab)
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

function log(...args) {
  if (window.localStorage.getItem('dressapp_debug')) console.info(LOG_PREFIX, ...args);
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
// Persistent FAB (bottom-right corner)
// ---------------------------------------------------------------------
function ensureFab() {
  let fab = document.getElementById(FAB_ID);
  if (fab) return fab;
  fab = document.createElement('button');
  fab.id = FAB_ID;
  fab.type = 'button';
  fab.className = 'dressapp-fab';
  fab.setAttribute('aria-label', 'Get DressApp size recommendation');
  fab.setAttribute('data-testid', 'dressapp-fab');
  fab.title = 'Open the size chart, then click here for a DressApp size recommendation.';
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
// Image -> base64 helper
// ---------------------------------------------------------------------
async function imageToB64Jpeg(img) {
  const src = img.currentSrc || img.src;
  if (!src) return null;
  try {
    const resp = await fetch(src, { credentials: 'omit', cache: 'force-cache' });
    if (resp.ok) {
      const blob = await resp.blob();
      const dataUrl = await new Promise((resolve, reject) => {
        const fr = new FileReader();
        fr.onloadend = () => resolve(fr.result);
        fr.onerror = () => reject(fr.error);
        fr.readAsDataURL(blob);
      });
      return _stripDataPrefix(dataUrl);
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

function _stripDataPrefix(dataUrl) {
  if (typeof dataUrl !== 'string') return null;
  const i = dataUrl.indexOf(',');
  return i >= 0 ? dataUrl.slice(i + 1) : dataUrl;
}

// ---------------------------------------------------------------------
// Visible-region prioritisation: prefer open modals & active panels
// ---------------------------------------------------------------------
function findVisibleScopes() {
  const scopes = [];
  // Highest priority: open modals / dialogs.
  document.querySelectorAll(
    '[role="dialog"], [aria-modal="true"], dialog[open], [class*=modal i][class*=open i], [class*=Modal i]:not([aria-hidden="true"])'
  ).forEach((el) => {
    if (_isVisible(el)) scopes.push(el);
  });
  // Next: visible tab panels (Description, Sizing, etc.).
  document.querySelectorAll(
    '[role="tabpanel"]:not([hidden]):not([aria-hidden="true"]), [class*=tab-panel i]:not([aria-hidden="true"])'
  ).forEach((el) => {
    if (_isVisible(el) && _intersectsViewport(el)) scopes.push(el);
  });
  // Finally: any element with size-guide-ish class that's visible.
  document.querySelectorAll('[class*=size-guide i], [class*=sizeGuide], [class*=size-chart i], [id*=size-guide i], [id*=sizeChart i]').forEach((el) => {
    if (_isVisible(el)) scopes.push(el);
  });
  // Deduplicate while preserving priority.
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

// Run a detector against an ordered list of scopes, then full document.
function findInScopes(detector) {
  const scopes = findVisibleScopes();
  for (const s of scopes) {
    const found = detector(s);
    if (found) return { node: found, scope: s };
  }
  const fallback = detector(document);
  return fallback ? { node: fallback, scope: document } : null;
}

// ---------------------------------------------------------------------
// Analyze flow
// ---------------------------------------------------------------------
async function onAnalyze(ev) {
  ev?.preventDefault?.();
  ev?.stopPropagation?.();
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

    // 1. HTML chart inside a visible scope (modal / tab panel / size-guide-ish container).
    let hit = findInScopes((doc) => adapter.detectChart(doc) || generic.detectChart(doc));
    let chartEl = hit?.node || null;

    // 2. Image-based chart inside a visible scope.
    let chartImg = null;
    if (!chartEl) {
      hit = findInScopes((doc) => generic.detectChartImage(doc));
      chartImg = hit?.node || null;
    }

    // 3. Visible-tab screenshot fallback.
    let chart_screenshot_b64 = null;
    if (chartImg) {
      chart_screenshot_b64 = await imageToB64Jpeg(chartImg);
      if (!chart_screenshot_b64) {
        const cap = await sendToBackground({ type: messages.CAPTURE_VISIBLE_TAB });
        if (cap?.ok && cap.image_b64) chart_screenshot_b64 = cap.image_b64;
      }
    } else if (!chartEl) {
      const cap = await sendToBackground({ type: messages.CAPTURE_VISIBLE_TAB });
      if (cap?.ok && cap.image_b64) {
        chart_screenshot_b64 = cap.image_b64;
      } else {
        mountOverlay({
          kind: 'warn',
          title: 'No size chart visible',
          message: 'Open the store\'s size-guide modal (or Description tab) so the chart is on-screen, then click the DressApp button again.',
          retry: () => onAnalyze(),
          onDismiss: showFab,
        });
        return;
      }
    }

    const payload = {
      chart_html: chartEl ? chartEl.outerHTML.slice(0, 60_000) : null,
      chart_screenshot_b64,
      garment_type: generic.detectGarmentType(document),
      store: HOST.replace(/^www\./, ''),
      page_url: location.href,
      page_title: document.title,
    };
    log('analyze payload (preview)', {
      ...payload,
      chart_html_len: payload.chart_html?.length || 0,
      chart_screenshot_len: payload.chart_screenshot_b64?.length || 0,
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
  if (e.key === 'Escape') {
    dismissOverlay();
    showFab();
  }
}, true);
