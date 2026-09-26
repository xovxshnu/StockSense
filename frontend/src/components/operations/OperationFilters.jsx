import { STATUS_META } from './operationConfig';
import { LIST_FILTER_KEYS } from '../../services/operationsApi';

// Renders only the filters the API layer actually sends (LIST_FILTER_KEYS), so the UI
// never offers a filter the backend contract has not defined. To add warehouse/location/
// category: extend LIST_FILTER_KEYS in operationsApi.js and add a control below.
export default function OperationFilters({ config, value, onChange }) {
  const set = (key) => (e) => onChange({ ...value, [key]: e.target.value });
  return (
    <div className="filters">
      {LIST_FILTER_KEYS.includes('search') && (
        <input
          type="search"
          className="input"
          placeholder="Search…"
          aria-label="Search"
          value={value.search}
          onChange={set('search')}
        />
      )}
      {LIST_FILTER_KEYS.includes('status') && (
        <select className="input" aria-label="Status" value={value.status} onChange={set('status')}>
          <option value="">All statuses</option>
          {config.statuses.map((s) => (
            <option key={s} value={s}>{STATUS_META[s].label}</option>
          ))}
        </select>
      )}
    </div>
  );
}
