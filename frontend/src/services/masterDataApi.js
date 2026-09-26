import { api } from './api';
import { unwrapList } from './operationsApi';

// Read-only master-data lookups. Endpoints are from the blueprint API contract (§8),
// owned by the master-data backend. There is deliberately NO supplier/contact or user
// lookup: the contract defines no endpoint for them.
export const warehouseApi = {
  list: (options) => api.get('/api/warehouses', options).then(unwrapList),
};

export const locationApi = {
  list: (options) => api.get('/api/locations', options).then(unwrapList),
};
