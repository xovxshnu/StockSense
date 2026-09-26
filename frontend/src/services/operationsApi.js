import { api, ApiError } from './api';

// Contract: StockSense_Technical_Blueprint_v1.md §8. This file is the only place
// that builds operation endpoint paths. Every mutation returns the backend
// response untouched; callers reconcile from it.

// ASSUMPTION: list endpoints return either a bare array or { items: [...] }.
// The shape is not specified in the contract. Anything else is an error, not an empty list.
export function unwrapList(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.items)) return data.items;
  throw new ApiError('The server returned an unexpected list format.', { kind: 'parse' });
}

// Query params sent to list endpoints. The contract does not define any for
// operation lists; `search` and `status` are assumed (blueprint §11) and UNCONFIRMED.
// Add warehouse_id / location_id / category_id here only once the backend defines them.
export const LIST_FILTER_KEYS = ['search', 'status'];

function pickListParams(filters = {}) {
  const params = {};
  LIST_FILTER_KEYS.forEach((key) => {
    const value = filters[key];
    if (value !== undefined && value !== null && value !== '') params[key] = value;
  });
  return params;
}

const seg = (id) => encodeURIComponent(id);

function createOperationApi(basePath, { todo = false, cancel = true } = {}) {
  const service = {
    list: (filters, options) =>
      api.get(basePath, { ...options, params: pickListParams(filters) }).then(unwrapList),
    get: (id, options) => api.get(`${basePath}/${seg(id)}`, options),
    create: (payload) => api.post(basePath, payload),
    update: (id, payload) => api.put(`${basePath}/${seg(id)}`, payload),
    validate: (id) => api.post(`${basePath}/${seg(id)}/validate`),
  };
  if (todo) service.todo = (id) => api.post(`${basePath}/${seg(id)}/todo`);
  if (cancel) service.cancel = (id) => api.post(`${basePath}/${seg(id)}/cancel`);
  return service;
}

export const receiptApi = createOperationApi('/api/receipts', { todo: true });
export const deliveryApi = createOperationApi('/api/deliveries', { todo: true });
// Transfers have no /todo endpoint in the contract.
export const transferApi = createOperationApi('/api/transfers');
// Adjustments have no /todo or /cancel endpoint in the contract.
export const adjustmentApi = createOperationApi('/api/adjustments', { cancel: false });

export const productApi = {
  search: (term, options) =>
    api.get('/api/products', { ...options, params: { search: term } }).then(unwrapList),
};
