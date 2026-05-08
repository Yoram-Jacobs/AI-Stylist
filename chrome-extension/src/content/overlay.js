/**
 * Floating overlay rendered on shopping sites by the content script.
 *
 * We deliberately don't ship React in the content bundle to keep the
 * inject footprint tiny (~1 KB gzipped vs ~140 KB for React). All
 * states are rendered with vanilla DOM + Tailwind-equivalent inline
 * styles via classes from content.css.
 */
const OVERLAY_ID = 'dressapp-overlay-root';
const SPINNER_ID = 'dressapp-overlay-spinner';

function ensureRoot() {
  let host = document.getElementById(OVERLAY_ID);
  if (host) return host;
  host = document.createElement('div');
  host.id = OVERLAY_ID;
  host.className = 'dressapp-overlay-host';
  document.body.appendChild(host);
  return host;
}

export function dismissOverlay() {
  document.getElementById(OVERLAY_ID)?.remove();
  document.getElementById(SPINNER_ID)?.remove();
}

export function mountSpinner() {
  dismissOverlay();
  const el = document.createElement('div');
  el.id = SPINNER_ID;
  el.className = 'dressapp-overlay-spinner';
  el.innerHTML = `<div class="dressapp-spinner"></div><span>DressApp is reading the size chart…</span>`;
  document.body.appendChild(el);
}

function sourceLabel(s) {
  return s === 'gemma' ? 'AI (Eyes)' : s === 'qwen' ? 'AI (cloud)' : s === 'heuristic' ? 'estimate' : 'engine';
}

export function mountOverlay(opts) {
  dismissOverlay();
  const root = ensureRoot();
  root.innerHTML = '';
  const card = document.createElement('div');
  card.className = 'dressapp-overlay-card';
  card.setAttribute('role', 'dialog');
  card.setAttribute('aria-live', 'polite');

  const close = document.createElement('button');
  close.className = 'dressapp-overlay-close';
  close.setAttribute('aria-label', 'Close DressApp recommendation');
  close.textContent = '×';
  close.addEventListener('click', dismissOverlay);
  card.appendChild(close);

  const title = document.createElement('div');
  title.className = 'dressapp-overlay-title';
  card.appendChild(title);

  const body = document.createElement('div');
  body.className = 'dressapp-overlay-body';
  card.appendChild(body);

  if (opts.kind === 'recommendation') {
    const r = opts.result || {};
    if (!r.has_measurements) {
      title.textContent = 'Add your measurements';
      body.innerHTML =
        `<p>DressApp couldn’t recommend a size because your profile has no measurements yet.</p>` +
        `<a class="dressapp-overlay-cta" href="https://dressapp.co/me" target="_blank" rel="noreferrer">Open DressApp profile</a>`;
    } else if (!r.recommended_size) {
      title.textContent = 'No clear match';
      body.innerHTML =
        `<p>${escapeHtml(r.reasoning || 'We couldn\'t determine a size from this chart.')}</p>` +
        `<small>via ${escapeHtml(sourceLabel(r.source))} · ${r.elapsed_ms ?? 0} ms</small>`;
    } else {
      title.innerHTML =
        `DressApp recommends size <strong>${escapeHtml(String(r.recommended_size))}</strong>` +
        (r.confidence ? ` <span class="dressapp-confidence">${Math.round(r.confidence * 100)}%</span>` : '');
      const matched = (r.matched_columns || []).join(' · ') || 'your stored measurements';
      body.innerHTML =
        `<p>${escapeHtml(r.reasoning || 'Based on your measurements.')}</p>` +
        `<small class="dressapp-meta">Matched on: ${escapeHtml(matched)} · via ${escapeHtml(sourceLabel(r.source))} · ${r.elapsed_ms ?? 0} ms</small>` +
        (r.alternatives?.length
          ? `<div class="dressapp-alts">Alternatives: ${r.alternatives.map((a) => `<span>${escapeHtml(a.size)} <em>(${escapeHtml(a.fit)})</em></span>`).join(', ')}</div>`
          : '');
    }
  } else {
    title.textContent = opts.title || 'DressApp';
    body.innerHTML = `<p>${escapeHtml(opts.message || '')}</p>`;
    if (opts.kind === 'auth') {
      body.innerHTML += `<small>Click the DressApp icon in the toolbar to connect.</small>`;
    }
  }

  root.appendChild(card);
}

function escapeHtml(str) {
  return String(str || '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
