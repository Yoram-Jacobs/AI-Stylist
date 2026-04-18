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
  patchItem: (id, body) => client.patch(`/closet/${id}`, body).then((r) => r.data),
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
  stylistHistory: (limit = 20) =>
    client.get('/stylist/history', { params: { limit } }).then((r) => r.data),
};

export default client;
