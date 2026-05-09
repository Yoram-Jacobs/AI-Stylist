/**
 * Floating overlay rendered on shopping sites by the content script.
 *
 * We deliberately don't ship React in the content bundle to keep the
 * inject footprint tiny (~1 KB gzipped vs ~140 KB for React). All
 * states are rendered with vanilla DOM + Tailwind-equivalent inline
 * styles via classes from content.css.
 *
 * Every interactive element gets a stable ``data-testid`` so the
 * testing agent (and future Playwright suites) can drive the overlay
 * without relying on text or class selectors.
 */
const OVERLAY_ID = 'dressapp-overlay-root';
const SPINNER_ID = 'dressapp-overlay-spinner';

function ensureRoot() {
  let host = document.getElementById(OVERLAY_ID);
  if (host) return host;
  host = document.createElement('div');
  host.id = OVERLAY_ID;
  host.className = 'dressapp-overlay-host';
  host.setAttribute('data-testid', 'dressapp-overlay-host');
  document.body.appendChild(host);
  return host;
}

export function dismissOverlay() {
  document.getElementById(OVERLAY_ID)?.remove();
  document.getElementById(SPINNER_ID)?.remove();
}

let _onDismissCb = null;
function _runOnDismiss() {
  const cb = _onDismissCb;
  _onDismissCb = null;
  if (typeof cb === 'function') {
    try { cb(); } catch (_) { /* swallow */ }
  }
}

function _dismissAndCallback() {
  dismissOverlay();
  _runOnDismiss();
}

export function mountSpinner() {
  dismissOverlay();
  const el = document.createElement('div');
  el.id = SPINNER_ID;
  el.className = 'dressapp-overlay-spinner';
  el.setAttribute('data-testid', 'dressapp-overlay-spinner');
  el.innerHTML = `<div class="dressapp-spinner" aria-hidden="true"></div><span>DressApp is reading the size chart…</span>`;
  document.body.appendChild(el);
}

function sourceLabel(s) {
  return s === 'gemma'
    ? 'AI (Eyes)'
    : s === 'qwen'
      ? 'AI (cloud)'
      : s === 'heuristic'
        ? 'estimate'
        : s === 'none'
          ? 'no result'
          : 'engine';
}

export function mountOverlay(opts) {
  dismissOverlay();
  _onDismissCb = typeof opts.onDismiss === 'function' ? opts.onDismiss : null;
  const root = ensureRoot();
  root.innerHTML = '';
  const card = document.createElement('div');
  card.className = 'dressapp-overlay-card';
  card.setAttribute('role', 'dialog');
  card.setAttribute('aria-live', 'polite');
  card.setAttribute('data-testid', `dressapp-overlay-${opts.kind || 'info'}`);

  const close = document.createElement('button');
  close.className = 'dressapp-overlay-close';
  close.setAttribute('aria-label', 'Close DressApp recommendation');
  close.setAttribute('data-testid', 'dressapp-overlay-close');
  close.textContent = '×';
  close.addEventListener('click', _dismissAndCallback);
  card.appendChild(close);

  const title = document.createElement('div');
  title.className = 'dressapp-overlay-title';
  title.setAttribute('data-testid', 'dressapp-overlay-title');
  card.appendChild(title);

  const body = document.createElement('div');
  body.className = 'dressapp-overlay-body';
  body.setAttribute('data-testid', 'dressapp-overlay-body');
  card.appendChild(body);

  if (opts.kind === 'recommendation') {
    _renderRecommendation(title, body, opts.result || {});
  } else {
    title.textContent = opts.title || 'DressApp';
    const p = document.createElement('p');
    p.textContent = opts.message || '';
    body.appendChild(p);
    if (opts.kind === 'auth') {
      const small = document.createElement('small');
      small.textContent = 'Click the DressApp icon in the toolbar to connect.';
      body.appendChild(small);
    }
  }

  // Retry CTA — works for any non-recommendation overlay where the
  // caller passed a ``retry`` callback.
  if (typeof opts.retry === 'function') {
    const actions = document.createElement('div');
    actions.className = 'dressapp-overlay-actions';
    const retry = document.createElement('button');
    retry.className = 'dressapp-overlay-cta';
    retry.type = 'button';
    retry.textContent = 'Retry';
    retry.setAttribute('data-testid', 'dressapp-overlay-retry');
    retry.addEventListener('click', (e) => {
      e.preventDefault();
      try { opts.retry(); } catch (_) { /* swallow */ }
    });
    actions.appendChild(retry);
    card.appendChild(actions);
  }

  root.appendChild(card);
}

function _renderRecommendation(title, body, r) {
  if (!r.has_measurements) {
    title.textContent = 'Add your measurements';
    const p = document.createElement('p');
    p.textContent = 'DressApp couldn\'t recommend a size because your profile has no measurements yet.';
    body.appendChild(p);
    const cta = document.createElement('a');
    cta.className = 'dressapp-overlay-cta';
    cta.target = '_blank';
    cta.rel = 'noreferrer';
    cta.href = 'https://dressapp.co/me';
    cta.textContent = 'Open DressApp profile';
    cta.setAttribute('data-testid', 'dressapp-overlay-open-profile');
    body.appendChild(cta);
    return;
  }
  if (!r.recommended_size) {
    title.textContent = 'No clear match';
    const p = document.createElement('p');
    p.textContent = r.reasoning || 'We couldn\'t determine a size from this chart.';
    body.appendChild(p);
    const meta = document.createElement('small');
    meta.textContent = `via ${sourceLabel(r.source)} · ${r.elapsed_ms ?? 0} ms`;
    body.appendChild(meta);
    return;
  }
  title.innerHTML = '';
  const lead = document.createTextNode('DressApp recommends size ');
  const strong = document.createElement('strong');
  strong.textContent = String(r.recommended_size);
  strong.setAttribute('data-testid', 'dressapp-overlay-size');
  title.appendChild(lead);
  title.appendChild(strong);
  if (typeof r.confidence === 'number') {
    const conf = document.createElement('span');
    conf.className = 'dressapp-confidence';
    conf.textContent = `${Math.round(r.confidence * 100)}%`;
    conf.setAttribute('data-testid', 'dressapp-overlay-confidence');
    title.appendChild(document.createTextNode(' '));
    title.appendChild(conf);
  }

  const why = document.createElement('p');
  why.textContent = r.reasoning || 'Based on your measurements.';
  body.appendChild(why);

  // Soft data-quality warnings. The model surfaces these when one of
  // the user's stored measurements looks obviously implausible vs.
  // the chart's range (e.g. shoulders=75 cm on a chart that maxes
  // at 50 cm). Render them as a stack of yellow callouts above the
  // meta line so they're impossible to miss.
  if (Array.isArray(r.warnings) && r.warnings.length) {
    const warnBox = document.createElement('div');
    warnBox.className = 'dressapp-warnings';
    warnBox.setAttribute('data-testid', 'dressapp-overlay-warnings');
    warnBox.setAttribute('role', 'alert');
    r.warnings.forEach((w, idx) => {
      if (!w) return;
      const item = document.createElement('div');
      item.className = 'dressapp-warning-item';
      item.setAttribute('data-testid', `dressapp-overlay-warning-${idx}`);
      // Leading icon (vector, no emoji).
      const icon = document.createElement('span');
      icon.className = 'dressapp-warning-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = '!';
      item.appendChild(icon);
      const txt = document.createElement('span');
      txt.className = 'dressapp-warning-text';
      txt.textContent = String(w);
      item.appendChild(txt);
      warnBox.appendChild(item);
    });
    body.appendChild(warnBox);
  }

  const matched = (r.matched_columns || []).join(' · ') || 'your stored measurements';
  const meta = document.createElement('small');
  meta.className = 'dressapp-meta';
  meta.textContent = `Matched on: ${matched} · via ${sourceLabel(r.source)} · ${r.elapsed_ms ?? 0} ms`;
  body.appendChild(meta);

  if (Array.isArray(r.alternatives) && r.alternatives.length) {
    const alts = document.createElement('div');
    alts.className = 'dressapp-alts';
    alts.setAttribute('data-testid', 'dressapp-overlay-alternatives');
    alts.appendChild(document.createTextNode('Alternatives: '));
    r.alternatives.forEach((a, idx) => {
      const span = document.createElement('span');
      span.textContent = `${a.size} `;
      const em = document.createElement('em');
      em.textContent = `(${a.fit || 'alt'})`;
      span.appendChild(em);
      alts.appendChild(span);
      if (idx !== r.alternatives.length - 1) {
        alts.appendChild(document.createTextNode(', '));
      }
    });
    body.appendChild(alts);
  }
}
