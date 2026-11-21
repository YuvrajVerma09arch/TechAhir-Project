/**
 * Single place where the dashboard talks to the FastAPI backend.
 * The base URL is configurable at build time:
 *   VITE_API_BASE_URL=https://api.example.com npm run build
 * Defaults to a local backend for development.
 */
const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

function toQuery(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value));
  });
  const serialized = query.toString();
  return serialized ? `?${serialized}` : '';
}

async function request(path, options = {}) {
  const { method = 'GET', body, headers = {}, signal } = options;
  const config = { method, headers: { ...headers }, signal };

  let payload = body;
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  if (body !== undefined && body !== null && !isForm && typeof body !== 'string') {
    config.headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  if (payload !== undefined && payload !== null) config.body = payload;

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, config);
  } catch (error) {
    const wrapped = new Error('Could not reach the backend service. Check that the API is running.');
    wrapped.code = 'NETWORK_ERROR';
    wrapped.cause = error;
    throw wrapped;
  }

  const contentType = response.headers.get('content-type') || '';
  let data = null;
  try {
    data = contentType.includes('application/json')
      ? await response.json()
      : await response.text();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const detail = data?.detail || data?.message || data?.error;
    const message = typeof detail === 'string' ? detail : `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

async function fetchAllPages(fetchPage, signal, pageSize = 200) {
  const records = [];
  let page = 1;
  let totalPages = 1;
  const maxPages = 100;

  while (page <= totalPages && page <= maxPages) {
    const response = await fetchPage({ page, page_size: pageSize }, signal);
    const rows = Array.isArray(response?.data)
      ? response.data
      : Array.isArray(response)
        ? response
        : [];
    records.push(...rows);
    totalPages = Math.max(
      1,
      Number(response?.pagination?.totalPages || response?.pagination?.total_pages || 1) || 1
    );
    page += 1;
  }
  return records;
}

export const api = {
  baseUrl: BASE_URL,

  getHealth: (signal) => request('/health', { signal }),

  seed: () => request('/api/triage/seed', { method: 'POST' }),

  submitBatch: (ticketsOrFormData) =>
    request('/api/triage/batch', { method: 'POST', body: ticketsOrFormData }),

  listTickets: (params = {}, signal) => request(`/api/tickets${toQuery(params)}`, { signal }),

  getTicket: (ticketId, signal) =>
    request(`/api/tickets/${encodeURIComponent(ticketId)}`, { signal }),

  getReviewQueue: (params = {}, signal) =>
    request(`/api/review-queue${toQuery(params)}`, { signal }),

  submitReview: (ticketId, payload) =>
    request(`/api/review/${encodeURIComponent(ticketId)}`, { method: 'POST', body: payload }),

  getReport: (signal) => request('/api/report', { signal }),

  // Convenience helpers used by the analytics, review and reports sections.
  getAllTickets: (signal) => fetchAllPages((params, sig) => api.listTickets(params, sig), signal),
  getAllReviewQueue: (signal) => fetchAllPages((params, sig) => api.getReviewQueue(params, sig), signal),
};

export default api;
