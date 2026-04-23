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

export const api = {
  // auth
  register: (body) => client.post('/auth/register', body).then((r) => r.data),
  login: (body) => client.post('/auth/login', body).then((r) => r.data),
  devBypass: () => client.post('/auth/dev-bypass').then((r) => r.data),
  me: () => client.get('/auth/me').then((r) => r.data),

  // users
  getMe: () => client.get('/users/me').then((r) => r.data),
  patchMe: (body) => client.patch('/users/me', body).then((r) => r.data),

  // closet
  listCloset: (params = {}) =>
    client.get('/closet', { params }).then((r) => r.data),
  getItem: (id) => client.get(`/closet/${id}`).then((r) => r.data),
  createItem: (body) => client.post('/closet', body).then((r) => r.data),
  analyzeItemImage: (body) =>
    client.post('/closet/analyze', body, { timeout: 90000 }).then((r) => r.data),
  searchCloset: (body) =>
    client.post('/closet/search', body, { timeout: 30000 }).then((r) => r.data),
  patchItem: (id, body) => client.patch(`/closet/${id}`, body).then((r) => r.data),
  updateItem: (id, body) => client.patch(`/closet/${id}`, body).then((r) => r.data),
  deleteItem: (id) => client.delete(`/closet/${id}`).then((r) => r.data),
  editItemImage: (id, prompt) =>
    client
      .post(`/closet/${id}/edit-image`, null, { params: { prompt } })
      .then((r) => r.data),

  // listings
  listListings: (params = {}) =>
    client.get('/listings', { params }).then((r) => r.data),
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

  // wardrobe reconstructor (Phase Q)
  repairItemImage: (itemId, { userHint = null, force = false } = {}) =>
    client
      .post(`/closet/${itemId}/repair`, {
        user_hint: userHint || null,
        force,
      })
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
    client.get('/ads/campaigns').then((r) => r.data),
  getAdCampaign: (id) =>
    client.get(`/ads/campaigns/${id}`).then((r) => r.data),
  createAdCampaign: (body) =>
    client.post('/ads/campaigns', body).then((r) => r.data),
  patchAdCampaign: (id, body) =>
    client.patch(`/ads/campaigns/${id}`, body).then((r) => r.data),
  deleteAdCampaign: (id) =>
    client.delete(`/ads/campaigns/${id}`).then((r) => r.data),
  adTicker: (params = {}) =>
    client.get('/ads/ticker', { params }).then((r) => r.data),
  trackAdImpression: (id) =>
    client.post(`/ads/impression/${id}`).then((r) => r.data).catch(() => null),
  trackAdClick: (id) =>
    client.post(`/ads/click/${id}`).then((r) => r.data).catch(() => null),

  // --- Phase U: admin professionals + ads ---
  adminProfessionals: (params = {}) =>
    client.get('/admin/professionals', { params }).then((r) => r.data),
  adminHideProfessional: (userId) =>
    client.post(`/admin/professionals/${userId}/hide`).then((r) => r.data),
  adminUnhideProfessional: (userId) =>
    client.post(`/admin/professionals/${userId}/unhide`).then((r) => r.data),
  adminAdCampaigns: (params = {}) =>
    client.get('/admin/ads/campaigns', { params }).then((r) => r.data),
  adminDisableCampaign: (id) =>
    client.post(`/admin/ads/campaigns/${id}/disable`).then((r) => r.data),
  adminEnableCampaign: (id) =>
    client.post(`/admin/ads/campaigns/${id}/enable`).then((r) => r.data),

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
