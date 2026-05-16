import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api/v1`;

const STORAGE_TOKEN = 'dressapp.token';
const STORAGE_USER = 'dressapp.user';

export const tokenStore = {
  get: () => localStorage.getItem(STORAGE_TOKEN) || null,
  set: (t) => localStorage.setItem(STORAGE_TOKEN, t),
  clear: () => {
    localStorage.removeItem(STORAGE_TOKEN);
    localStorage.removeItem(STORAGE_USER);
  },
};

export const userStore = {
  get: () => {
    try { return JSON.parse(localStorage.getItem(STORAGE_USER) || 'null'); }
    catch { return null; }
  },
  set: (u) => localStorage.setItem(STORAGE_USER, JSON.stringify(u)),
};

const client = axios.create({ baseURL: API_BASE, timeout: 180000 });

client.interceptors.request.use((cfg) => {
  const t = tokenStore.get();
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

client.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      tokenStore.clear();
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  }
);

/**
 * streamNdjson — open an `application/x-ndjson` POST stream from the
 * backend and invoke ``onLine`` once per JSON object as it arrives.
 *
 * Why this exists
 * ===============
 * axios doesn't expose the raw ReadableStream until the response is
 * complete, which defeats the entire purpose of NDJSON streaming.
 * We use the platform ``fetch`` directly so we can attach a reader
 * to ``response.body`` and dispatch events to the caller in real
 * time — that's what makes the closet hash-repair feel "alive"
 * rather than blocked-then-reveal.
 *
 * The function:
 *   1. Auth-injects the same Bearer token axios uses, so callers
 *      don't have to think about it.
 *   2. Splits the stream on ``\n``. Carry-over bytes between chunks
 *      are buffered so a JSON object that straddles a TCP boundary
 *      isn't accidentally cut in two.
 *   3. Calls ``onLine(obj)`` for every parsed event and resolves
 *      with the *last* parsed object (typically the ``done``
 *      summary) when the stream closes cleanly.
 *   4. Rejects on network errors, non-2xx status, or AbortSignal
 *      trip. The signal is honoured mid-stream too (the reader
 *      cancels promptly).
 *
 * @param {string} path        Path relative to API_BASE, e.g. ``/closet/repair-hashes``.
 * @param {object} [options]
 * @param {string} [options.method='POST']
 * @param {object} [options.params]   Query params (URLSearchParams-compatible).
 * @param {object} [options.body]     JSON body; serialised with JSON.stringify.
 * @param {Function} [options.onLine] ``(obj) => void`` invoked per event.
 * @param {AbortSignal} [options.signal]
 * @returns {Promise<object|null>} The final parsed event, or null on empty stream.
 */
export async function streamNdjson(path, {
  method = 'POST',
  params,
  body,
  onLine,
  signal,
} = {}) {
  const url = new URL(`${API_BASE}${path}`);
  if (params && typeof params === 'object') {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    });
  }
  const headers = {
    'Accept': 'application/x-ndjson',
  };
  const tok = tokenStore.get();
  if (tok) headers.Authorization = `Bearer ${tok}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const resp = await fetch(url.toString(), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
    // Match axios: cookies for same-site, no credentials cross-site.
    credentials: 'same-origin',
  });

  if (resp.status === 401) {
    tokenStore.clear();
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = '/login';
    }
    throw new Error(`stream 401`);
  }
  if (!resp.ok || !resp.body) {
    throw new Error(`stream ${resp.status}: ${resp.statusText || 'no body'}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buf = '';
  let last = null;

  try {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      // Drain every complete line we have so far. The leftover
      // (potentially-partial last line) stays in ``buf`` for the
      // next chunk.
      let nl = buf.indexOf('\n');
      while (nl !== -1) {
        const raw = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (raw) {
          try {
            const obj = JSON.parse(raw);
            last = obj;
            if (onLine) onLine(obj);
          } catch (parseErr) {
            // Soft-fail individual malformed lines. The server's
            // gen() never produces them, but proxies that munge
            // utf-8 boundaries occasionally inject a stray byte.
            // Throwing here would kill the whole repair pass.
            // eslint-disable-next-line no-console
            console.warn('streamNdjson: skipping malformed line', parseErr);
          }
        }
        nl = buf.indexOf('\n');
      }
    }
    // End-of-stream — drain any leftover that didn't end with \n.
    const tail = buf.trim();
    if (tail) {
      try {
        const obj = JSON.parse(tail);
        last = obj;
        if (onLine) onLine(obj);
      } catch {
        /* ignore tail parse error */
      }
    }
  } finally {
    try { reader.releaseLock(); } catch { /* already released */ }
  }
  return last;
}

export const api = {
  // auth
  register: (body) => client.post('/auth/register', body).then((r) => r.data),
  login: (body) => client.post('/auth/login', body).then((r) => r.data),
  devBypass: () => client.post('/auth/dev-bypass').then((r) => r.data),
  me: () => client.get('/auth/me').then((r) => r.data),

  /** Resolve the Google OAuth start URL for the *sign-in / sign-up* flow.
   * Returns ``{ authorization_url }``. The caller is expected to do a
   * full-page redirect to that URL (popup-less PKCE-style flow).
   */
  googleLoginStart: ({ withCalendar = false, next = null } = {}) => {
    const params = new URLSearchParams();
    if (withCalendar) params.set('with_calendar', 'true');
    if (next) params.set('next', next);
    const qs = params.toString();
    return client
      .get(`/auth/google/login/start${qs ? `?${qs}` : ''}`)
      .then((r) => r.data);
  },

  // users
  getMe: () => client.get('/users/me').then((r) => r.data),
  patchMe: (body) => client.patch('/users/me', body).then((r) => r.data),

  // closet
  listCloset: (params = {}) =>
    client.get('/closet', { params }).then((r) => r.data),
  getItem: (id) => client.get(`/closet/${id}`).then((r) => r.data),
  createItem: (body) => client.post('/closet', body).then((r) => r.data),
  // Phase Z2 — pre-flight duplicate check.
  // Pass an array of `{sha256, filename, size_bytes}` for the photos
  // the user just selected. Returns `{matches: [...]}` listing only
  // those that collide with an existing closet item. The frontend
  // either prompts (≤5 photos) or silently filters them out (>5).
  preflightDuplicates: (photos) =>
    client
      .post('/closet/preflight', { photos })
      .then((r) => r.data),
  /**
   * Phase Z2.3 — streaming hash-repair pass.
   *
   * Opens an ``application/x-ndjson`` POST stream against
   * ``/closet/repair-hashes`` and dispatches each event to ``onEvent``.
   * Resolves with the final ``{type:'done', ...}`` summary.
   *
   * Events the caller may receive (one per line, in this order):
   *
   *   * ``{type:'start', total, only_missing, dry_run}``
   *   * ``{type:'item', id, status, source_field, delta, patch, error}``
   *     where ``status ∈ {repaired, cleared, unchanged, skipped, failed}``
   *     and ``patch`` (when non-null) carries only the changed fields,
   *     ready to be shallow-merged into the closet store.
   *   * ``{type:'done', scanned, repaired, cleared, unchanged,
   *        skipped, failed, wrote_db}``
   *
   * Safe to call repeatedly; the endpoint is idempotent.
   */
  repairClosetHashes: ({ dryRun = false, onlyMissing = false, limit = 2000, onEvent, signal } = {}) =>
    streamNdjson('/closet/repair-hashes', {
      method: 'POST',
      params: {
        dry_run: dryRun ? 'true' : 'false',
        only_missing: onlyMissing ? 'true' : 'false',
        limit,
      },
      onLine: onEvent,
      signal,
    }),
  /**
   * Phase Z2.6 — streaming thumbnail-repair pass.
   *
   * Re-derives ``thumbnail_data_url`` for closet items whose cached
   * thumb is stale relative to the best available source (typically:
   * cached JPEG while the source is now a PNG cutout, because the
   * thumbnail was baked before Phase Z2.6 fixed
   * ``pick_source_data_url``'s priority chain). Idempotent — re-runs
   * report every row as ``unchanged``.
   *
   * Events:
   *   * ``{type:'start', total, only_stale}``
   *   * ``{type:'item', id, status, reason, thumb_mime, error}``
   *     where ``status ∈ {regenerated, unchanged, skipped, failed}``
   *   * ``{type:'done', scanned, regenerated, unchanged, skipped,
   *        failed, wrote_db}``
   *
   * Set ``onlyStale=false`` to force-regenerate every thumbnail
   * unconditionally (useful after a thumbnail-format bug ships).
   */
  repairClosetThumbnails: ({ onlyStale = true, limit = 2000, onEvent, signal } = {}) =>
    streamNdjson('/closet/repair-thumbnails', {
      method: 'POST',
      params: {
        only_stale: onlyStale ? 'true' : 'false',
        limit,
      },
      onLine: onEvent,
      signal,
    }),
  analyzeItemImage: (body) =>
    // Patch M17 (May 2026) — /analyze now returns a StreamingResponse
    // wrapping the legacy JSON body with keepalive whitespace bytes so
    // the Kubernetes / Cloudflare ingress 60 s idle timeout never
    // fires while Gemini chugs through the parallel per-crop calls.
    // JSON.parse strips leading whitespace, so axios handles the body
    // unchanged. On error the backend cannot set a non-200 status mid-
    // stream, so it puts the intended status in a top-level
    // ``_status`` field plus a human ``_error`` message; we translate
    // that back into a thrown error here so the existing rejection /
    // toast path works identically to the pre-M17 sync endpoint.
    client
      .post('/closet/analyze', body, { timeout: 180000 })
      .then((r) => {
        const data = r.data || {};
        if (data && data._status && Number(data._status) >= 400) {
          const err = new Error(data._error || 'Analyze failed');
          err.response = { status: Number(data._status), data };
          throw err;
        }
        return data;
      }),
  searchCloset: (body) =>
    client.post('/closet/search', body, { timeout: 30000 }).then((r) => r.data),
  patchItem: (id, body) => client.patch(`/closet/${id}`, body).then((r) => r.data),
  updateItem: (id, body) => client.patch(`/closet/${id}`, body).then((r) => r.data),
  deleteItem: (id) => client.delete(`/closet/${id}`).then((r) => r.data),
  editItemImage: (id, prompt) =>
    client
      .post(`/closet/${id}/edit-image`, null, { params: { prompt } })
      .then((r) => r.data),
  // One-shot helper that auto-creates marketplace listings for closet
  // items that already have ``marketplace_intent`` set but never made
  // it to the marketplace (legacy data / pre-pipeline items). Returns
  // a {candidates, created, skipped_existing, source_synced, failed}
  // summary so the caller can render a confirmation toast.
  backfillMarketplaceListings: () =>
    client.post('/closet/marketplace/backfill').then((r) => r.data),
  /**
   * Streaming variant of the marketplace backfill — same semantics,
   * but emits one NDJSON line per candidate so the UI can render
   * live progress ("Listed 5/12 · Skipped 2") instead of a blank
   * "Syncing…" spinner. The legacy non-streaming endpoint is left
   * in place for any caller depending on its exact summary shape;
   * the new streaming UI opts in by hitting this one.
   *
   * Resolves with the final ``{type:'done', candidates, created,
   * skipped, source_synced, failed}`` summary.
   */
  streamMarketplaceBackfill: ({ onEvent, signal } = {}) =>
    streamNdjson('/closet/marketplace/backfill/stream', {
      method: 'POST',
      onLine: onEvent,
      signal,
    }),

  // listings
  listListings: (params = {}) =>
    client.get('/listings', { params }).then((r) => r.data),
  /**
   * Streaming variant of ``GET /listings`` — same filters, but
   * each listing arrives on its own NDJSON line so the
   * Marketplace grid can paint cards progressively. Time-to-first
   * card on a cold geo browse drops from ~500 ms to ~150 ms.
   *
   * Resolves with the final ``{type:'done', emitted}`` summary.
   */
  streamListings: ({ params = {}, onEvent, signal } = {}) =>
    streamNdjson('/listings/stream', {
      method: 'GET',
      params,
      onLine: onEvent,
      signal,
    }),
  feePreview: (cents) =>
    client
      .get('/listings/fee-preview', { params: { list_price_cents: cents } })
      .then((r) => r.data),
  getListing: (id) => client.get(`/listings/${id}`).then((r) => r.data),
  getSimilarListings: (id, params = {}) =>
    client.get(`/listings/${id}/similar`, { params }).then((r) => r.data),
  createListing: (body) => client.post('/listings', body).then((r) => r.data),
  patchListing: (id, body) =>
    client.patch(`/listings/${id}`, body).then((r) => r.data),
  deleteListing: (id) => client.delete(`/listings/${id}`).then((r) => r.data),

  // transactions
  listTransactions: (params = {}) =>
    client.get('/transactions', { params }).then((r) => r.data),
  createTransaction: (body) =>
    client.post('/transactions', body).then((r) => r.data),
  getTransaction: (id) =>
    client.get(`/transactions/${id}`).then((r) => r.data),

  // Wave 2 — swap + donate marketplace flows
  proposeSwap: (listingId, offeredItemId) =>
    client
      .post('/transactions/swap', {
        listing_id: listingId,
        offered_item_id: offeredItemId,
      })
      .then((r) => r.data),
  claimDonation: (listingId, handlingFeeCents = 0) =>
    client
      .post('/transactions/donate', {
        listing_id: listingId,
        handling_fee_cents: handlingFeeCents,
      })
      .then((r) => r.data),
  // Wave 3 — capture PayPal shipping fee for a donation claim. Called
  // by the frontend right after the PayPal popup/button confirms the
  // order. On success the donor gets their accept/deny email.
  captureDonationShipping: (txId, orderId) =>
    client
      .post(`/transactions/donate/${txId}/capture`, null, {
        params: { order_id: orderId },
      })
      .then((r) => r.data),
  confirmReceipt: (txId) =>
    client
      .post(`/transactions/${txId}/confirm-receipt`)
      .then((r) => r.data),
  // Public (no auth) — used by the email-landing page so users who
  // click accept/deny from a logged-out browser can still see the
  // listing summary + status banner.
  getLandingSummary: (txId) =>
    client
      .get(`/transactions/${txId}/landing-summary`)
      .then((r) => r.data),

  // stylist — returns raw axios promise for multipart
  stylist: (formData) =>
    client.post('/stylist', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data),
  stylistHistory: (sessionId = null, limit = 200) =>
    client
      .get('/stylist/history', {
        params: sessionId ? { session_id: sessionId, limit } : { limit },
      })
      .then((r) => r.data),
  stylistSessions: () =>
    client.get('/stylist/sessions').then((r) => r.data),
  stylistCreateSession: () =>
    client.post('/stylist/sessions').then((r) => r.data),
  stylistDeleteSession: (sessionId) =>
    client.delete(`/stylist/sessions/${sessionId}`).then((r) => r.data),

  // Phase R — Stylist Power-Up: multi-image outfit composer
  composeOutfit: (formData) =>
    client.post('/stylist/compose-outfit', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 240000,  // composer can take 30-60s when N images need analysis
    }).then((r) => r.data),

  // outfit completion (Phase P)
  completeOutfit: ({ itemIds, includeMarketplace = false, occasion = null, limit = 6 }) =>
    client
      .post('/closet/complete-outfit', {
        item_ids: itemIds,
        include_marketplace: includeMarketplace,
        occasion: occasion || null,
        limit,
      })
      .then((r) => r.data),

  // wardrobe reconstructor (Phase Q — now used as fallback only)
  repairItemImage: (itemId, { userHint = null, force = false } = {}) =>
    client
      .post(`/closet/${itemId}/repair`, {
        user_hint: userHint || null,
        force,
      })
      .then((r) => r.data),
  // Clean background (Phase V Fix 2 — non-generative matting)
  cleanItemBackground: (itemId) =>
    client.post(`/closet/${itemId}/clean-background`).then((r) => r.data),
  // Re-run The Eyes on the item's stored image and patch the analysis
  // fields back onto the doc. Used by the "Analyze" action on the
  // edit page after a photo replace, or to recover from a bad first
  // analysis without re-uploading the image.
  reanalyzeItem: (itemId) =>
    client
      .post(`/closet/${itemId}/reanalyze`, null, { timeout: 90000 })
      .then((r) => r.data),
  // Phase V6 — EU Digital Product Passport (DPP) import via QR scan
  importDpp: (qrPayload) =>
    client
      .post('/closet/import-dpp', { qr_payload: qrPayload }, { timeout: 30000 })
      .then((r) => r.data),
  // Phase V6 — add or replace an item's photo (runs The Eyes single-item).
  // ``language`` (optional ISO-639-1 code) overrides the analyzer's output
  // language for this call — see ``AnalyzeIn.language`` on the backend.
  setItemPhoto: (itemId, { imageBase64, imageMime = 'image/jpeg', autoSegment = true, language }) =>
    client
      .post(
        `/closet/${itemId}/photo`,
        {
          image_base64: imageBase64,
          image_mime: imageMime,
          auto_segment: autoSegment,
          ...(language ? { language } : {}),
        },
        { timeout: 120000 },
      )
      .then((r) => r.data),

  // google calendar
  calendarStatus: () => client.get('/calendar/status').then((r) => r.data),
  calendarUpcoming: (hours = 48) =>
    client.get('/calendar/upcoming', { params: { hours_ahead: hours } }).then((r) => r.data),
  googleOAuthStart: () => client.get('/auth/google/start').then((r) => r.data),
  googleOAuthDisconnect: () =>
    client.post('/auth/google/disconnect').then((r) => r.data),

  // trend-scout
  trendsLatest: (perBucket = 1) =>
    client.get('/trends/latest', { params: { per_bucket: perBucket } }).then((r) => r.data),
  fashionScoutFeed: (limit = 12, params = {}) =>
    client
      .get('/trends/fashion-scout', {
        params: {
          limit,
          ...(params.language ? { language: params.language } : {}),
          ...(params.country ? { country: params.country } : {}),
        },
      })
      .then((r) => r.data),
  trendsRunNowDev: (force = true) =>
    client.post('/trends/run-now-dev', null, { params: { force } }).then((r) => r.data),
  // Admin-only force refresh — used by the 🔄 button next to "Daily edit"
  // on the Home page. Force=true so the run regenerates *today's* cards
  // even if they already exist (otherwise the dedupe in
  // ``run_trend_scout`` would skip).
  trendsRefreshAdmin: (force = true) =>
    client.post('/trends/run-now', null, { params: { force } }).then((r) => r.data),
  // Public-safe diagnostics: when did each bucket last refresh?
  trendsLastRefresh: () =>
    client.get('/trends/last_refresh').then((r) => r.data),

  // share — mint a read-only snapshot link for an outfit recommendation
  createSharedOutfit: (body) =>
    client.post('/share/outfit', body).then((r) => {
      const data = r.data;
      // Convenience: attach the fully-qualified share URL so callers can
      // drop it straight into `navigator.share`.
      if (data?.id && typeof window !== 'undefined') {
        data.share_url = `${window.location.origin}/shared/${data.id}`;
      }
      return data;
    }),
  getSharedOutfit: (id) =>
    client.get(`/share/outfit/${id}`).then((r) => r.data),

  // admin
  adminOverview: () => client.get('/admin/overview').then((r) => r.data),
  adminUsers: (params = {}) => client.get('/admin/users', { params }).then((r) => r.data),
  adminListings: (params = {}) => client.get('/admin/listings', { params }).then((r) => r.data),
  adminTransactions: (params = {}) => client.get('/admin/transactions', { params }).then((r) => r.data),
  adminProviders: () => client.get('/admin/providers').then((r) => r.data),
  adminProviderCalls: (provider, limit = 50) =>
    client.get(`/admin/providers/${provider}/calls`, { params: { limit } }).then((r) => r.data),
  adminTrendScout: (limit = 30) =>
    client.get('/admin/trend-scout', { params: { limit } }).then((r) => r.data),
  adminTrendScoutRun: (force = true) =>
    client.post('/admin/trend-scout/run', null, { params: { force } }).then((r) => r.data),
  adminLlmUsage: () => client.get('/admin/llm-usage').then((r) => r.data),
  adminSystem: () => client.get('/admin/system').then((r) => r.data),
  adminPromoteUser: (userId) =>
    client.post(`/admin/users/${userId}/promote`).then((r) => r.data),
  adminDemoteUser: (userId) =>
    client.post(`/admin/users/${userId}/demote`).then((r) => r.data),
  adminSetListingStatus: (listingId, status) =>
    client.post(`/admin/listings/${listingId}/status`, null, { params: { status } }).then((r) => r.data),

  // --- Phase U: professionals directory ---
  listProfessionals: (params = {}) =>
    client.get('/professionals', { params }).then((r) => r.data),
  getProfessional: (id) =>
    client.get(`/professionals/${id}`).then((r) => r.data),

  // --- Phase U: ad campaigns ---
  listMyAdCampaigns: () =>
    client.get('/promotions/campaigns').then((r) => r.data),
  getAdCampaign: (id) =>
    client.get(`/promotions/campaigns/${id}`).then((r) => r.data),
  createAdCampaign: (body) =>
    client.post('/promotions/campaigns', body).then((r) => r.data),
  patchAdCampaign: (id, body) =>
    client.patch(`/promotions/campaigns/${id}`, body).then((r) => r.data),
  deleteAdCampaign: (id) =>
    client.delete(`/promotions/campaigns/${id}`).then((r) => r.data),
  adTicker: (params = {}) =>
    client.get('/promotions/ticker', { params }).then((r) => r.data),
  trackAdImpression: (id) =>
    client.post(`/promotions/impression/${id}`).then((r) => r.data).catch(() => null),
  trackAdClick: (id) =>
    client.post(`/promotions/click/${id}`).then((r) => r.data).catch(() => null),

  // --- Phase U: admin professionals + ads ---
  adminProfessionals: (params = {}) =>
    client.get('/admin/professionals', { params }).then((r) => r.data),
  adminHideProfessional: (userId) =>
    client.post(`/admin/professionals/${userId}/hide`).then((r) => r.data),
  adminUnhideProfessional: (userId) =>
    client.post(`/admin/professionals/${userId}/unhide`).then((r) => r.data),
  adminAdCampaigns: (params = {}) =>
    client.get('/admin/promotions/campaigns', { params }).then((r) => r.data),
  adminDisableCampaign: (id) =>
    client.post(`/admin/promotions/campaigns/${id}/disable`).then((r) => r.data),
  adminEnableCampaign: (id) =>
    client.post(`/admin/promotions/campaigns/${id}/enable`).then((r) => r.data),

  // --- Phase O.3: Eyes provider runtime override ---
  // Snapshot of the currently-active vision provider on this pod
  // (Qwen-VL / Gemma-4 E2B), the source of truth (env vs DB),
  // wiring sanity flags, and the last analyse call recorded by
  // ``provider_activity`` for the closet pipeline. Called by the
  // admin-only Developer panel in Profile.
  adminEyesStatus: () => client.get('/admin/eyes').then((r) => r.data),
  // Persist (or clear) the runtime override. Pass ``provider``
  // as ``"gemma"`` / ``"qwen"`` to set, or ``null`` / undefined to
  // clear and revert to env-default.
  adminEyesSet: (provider) =>
    client.post('/admin/eyes', { provider: provider ?? null }).then((r) => r.data),

  // --- Phase 4P: PayPal / credits / marketplace buy ---
  paypalConfig: () => client.get('/paypal/config').then((r) => r.data),
  creditsBalance: (currency = 'USD') =>
    client.get('/credits/balance', { params: { currency } }).then((r) => r.data),
  creditsAllBalances: () =>
    client.get('/credits/balances').then((r) => r.data),
  creditsHistory: (limit = 30) =>
    client.get('/credits/history', { params: { limit } }).then((r) => r.data),
  creditsTopupCreate: (body) =>
    client.post('/credits/topup', body).then((r) => r.data),
  creditsTopupCapture: (topupId) =>
    client.post(`/credits/topup/${topupId}/capture`).then((r) => r.data),

  listingBuyCreate: (listingId) =>
    client.post(`/listings/${listingId}/buy`).then((r) => r.data),
  listingBuyCapture: (listingId, orderId) =>
    client
      .post(`/listings/${listingId}/buy/capture`, null, {
        params: { order_id: orderId },
      })
      .then((r) => r.data),
};

export default client;
