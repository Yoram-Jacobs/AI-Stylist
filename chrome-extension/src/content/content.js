/**
 * Content script entry point — runs on every shopping site listed
 * in manifest.json. Lifecycle:
 *   1. Wait for first paint to settle (run_at=document_idle handles
 *      most of this; we additionally use a MutationObserver to catch
 *      late-mounted size dropdowns on SPAs like Zara/ASOS).
 *   2. Once we find a size anchor, mount a small DressApp button
 *      next to it. Idempotent — won't double-mount on re-renders.
 *   3. On click, the analyzer tries (in order):
 *        a. site adapter HTML chart -> generic HTML chart
 *        b. generic image-based chart (alt/heading/src heuristics)
 *        c. visible-tab screenshot from the SW (last-resort OCR)
 *      and asks the SW to call the backend, then renders the
 *      recommendation as a floating overlay.
 */
import { getAdapter } from './adapters/sites.js';
import generic from './adapters/generic.js';
import { messages, sendToBackground } from '@/lib/messages.js';
import { mountOverlay, mountSpinner, dismissOverlay } from './overlay.js';

const HOST = location.hostname;
const adapter = getAdapter(HOST);
const BUTTON_MOUNTED_ATTR = 'data-dressapp-mounted';
const LOG_PREFIX = `[DressApp/${adapter.name}]`;

function log(...args) {
  if (window.localStorage.getItem('dressapp_debug')) console.info(LOG_PREFIX, ...args);
}

function createButton() {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'dressapp-anchor-btn';
  btn.setAttribute('aria-label', 'DressApp size recommendation');
  btn.setAttribute('data-testid', 'dressapp-anchor-btn');
  btn.innerHTML = `<span class="dressapp-dot" aria-hidden="true"></span>DressApp size`;
  btn.addEventListener('click', onAnalyze);
  return btn;
}

/**
 * Convert an <img> element on the host page to a base64 JPEG string
 * (no ``data:`` prefix). We try ``fetch`` first because it preserves
 * the original pixel data; we fall back to a same-origin canvas
 * pipeline when CORS prevents reading the image bytes.
 */
async function imageToB64Jpeg(img) {
  const src = img.currentSrc || img.src;
  if (!src) return null;
  // Path 1: fetch + FileReader. Works for same-origin and any CORS-
  // permissive image. Most shopping CDNs expose images this way.
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
  } catch (_) {
    // ignore — try canvas next
  }
  // Path 2: canvas. May taint the canvas if the image is hostile to
  // CORS; we accept the failure and let the caller try a tab capture.
  try {
    const canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth || img.width;
    canvas.height = img.naturalHeight || img.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
    return _stripDataPrefix(dataUrl);
  } catch (_) {
    return null;
  }
}

function _stripDataPrefix(dataUrl) {
  if (typeof dataUrl !== 'string') return null;
  const i = dataUrl.indexOf(',');
  return i >= 0 ? dataUrl.slice(i + 1) : dataUrl;
}

async function onAnalyze(ev) {
  ev.preventDefault();
  ev.stopPropagation();
  mountSpinner();
  try {
    const status = await sendToBackground({ type: messages.AUTH_STATUS });
    if (!status?.ok || !status.token) {
      mountOverlay({
        kind: 'auth',
        title: 'Connect DressApp first',
        message: 'Open the DressApp extension popup and click "Connect to DressApp" to enable size recommendations.',
      });
      return;
    }

    // Path 1 — site adapter HTML chart, then generic HTML.
    let chartEl = adapter.detectChart(document);
    if (!chartEl) chartEl = generic.detectChart(document);

    // Path 2 — image-based chart on the page.
    let chartImg = null;
    if (!chartEl) chartImg = generic.detectChartImage(document);

    // Path 3 — visible-tab screenshot (SW captures the active tab).
    let screenshotB64 = null;
    if (!chartEl && !chartImg) {
      const cap = await sendToBackground({ type: messages.CAPTURE_VISIBLE_TAB });
      if (cap?.ok && cap.image_b64) {
        screenshotB64 = cap.image_b64;
      } else {
        mountOverlay({
          kind: 'warn',
          title: 'No size chart found',
          message: 'We couldn\'t locate a size chart on this page. Open the store\'s size-guide modal and click DressApp again.',
          retry: () => onAnalyze(ev),
        });
        return;
      }
    }

    let chart_screenshot_b64 = null;
    if (chartImg) {
      chart_screenshot_b64 = await imageToB64Jpeg(chartImg);
      if (!chart_screenshot_b64) {
        // Image was hostile to CORS — fall back to tab capture.
        const cap = await sendToBackground({ type: messages.CAPTURE_VISIBLE_TAB });
        if (cap?.ok && cap.image_b64) chart_screenshot_b64 = cap.image_b64;
      }
    } else if (screenshotB64) {
      chart_screenshot_b64 = screenshotB64;
    }

    const payload = {
      chart_html: chartEl ? chartEl.outerHTML.slice(0, 60_000) : null,
      chart_screenshot_b64: chart_screenshot_b64,
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
        retry: () => onAnalyze(ev),
      });
      return;
    }
    mountOverlay({ kind: 'recommendation', result: r.result, store: payload.store });
  } catch (e) {
    mountOverlay({
      kind: 'error',
      title: 'Analysis failed',
      message: e?.message || String(e),
      retry: () => onAnalyze(ev),
    });
  }
}

function mountButton() {
  const anchor = generic.detectAnchor(document);
  if (!anchor) return false;
  if (anchor.hasAttribute(BUTTON_MOUNTED_ATTR)) return true;
  anchor.setAttribute(BUTTON_MOUNTED_ATTR, '1');
  const btn = createButton();
  // Insert the button right after the anchor, in its parent flow.
  // ``insertBefore`` with anchor.nextSibling handles "is last child"
  // correctly without needing a DOM-position polyfill.
  anchor.parentNode?.insertBefore(btn, anchor.nextSibling);
  log('button mounted next to', anchor);
  return true;
}

// Listen for the SPA navigation + late-mount cases. Throttle the
// observer callback so we don't burn CPU on heavy DOM churn (Zara,
// AliExpress).
let pending = false;
function scheduleMount() {
  if (pending) return;
  pending = true;
  requestAnimationFrame(() => {
    pending = false;
    mountButton();
  });
}

const observer = new MutationObserver(scheduleMount);
observer.observe(document.documentElement, { subtree: true, childList: true });
mountButton();

// Allow the user to dismiss the overlay with Escape.
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') dismissOverlay();
}, true);
