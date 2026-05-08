/**
 * Content script entry point — runs on every shopping site listed
 * in manifest.json. Lifecycle:
 *   1. Wait for first paint to settle (run_at=document_idle handles
 *      most of this; we additionally use a MutationObserver to catch
 *      late-mounted size dropdowns on SPAs like Zara/ASOS).
 *   2. Once we find a size dropdown, mount a small DressApp button
 *      next to it. Idempotent — won't double-mount on re-renders.
 *   3. On click, scrape the size chart (site adapter -> generic
 *      fallback), package the data, and ask the SW to call the
 *      backend. Show the result as a floating overlay.
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
  btn.innerHTML = `<span class="dressapp-dot"></span>DressApp size`;
  btn.addEventListener('click', onAnalyze);
  return btn;
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

    // Try the site adapter first; fall back to generic.
    let chartEl = adapter.detectChart(document);
    if (!chartEl) chartEl = generic.detectChart(document);
    if (!chartEl) {
      mountOverlay({
        kind: 'warn',
        title: 'No size chart found',
        message: 'We couldn\'t locate a size chart on this page. Open the store\'s size-guide modal and click DressApp again.',
      });
      return;
    }

    const payload = {
      chart_html: chartEl.outerHTML.slice(0, 60_000),
      garment_type: generic.detectGarmentType(document),
      store: HOST.replace(/^www\./, ''),
      page_url: location.href,
      page_title: document.title,
    };
    log('analyze payload (preview)', { ...payload, chart_html_len: payload.chart_html.length });

    const r = await sendToBackground({ type: messages.ANALYZE_CHART, payload });
    if (!r?.ok) {
      mountOverlay({
        kind: 'error',
        title: 'Analysis failed',
        message: r?.error || 'Unknown error',
      });
      return;
    }
    mountOverlay({ kind: 'recommendation', result: r.result, store: payload.store });
  } catch (e) {
    mountOverlay({ kind: 'error', title: 'Analysis failed', message: e?.message || String(e) });
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
