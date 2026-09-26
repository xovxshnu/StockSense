import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import OperationHeader from '../../components/operations/OperationHeader';
import OperationFilters from '../../components/operations/OperationFilters';
import OperationStatusBadge from '../../components/operations/OperationStatusBadge';
import { LoadingState, ErrorState, EmptyState } from '../../components/operations/AsyncState';
import { describeError } from '../../components/operations/errorMessage';
import useOperationResource from './useOperationResource';

const SEARCH_DEBOUNCE_MS = 300;

export default function OperationListPage({ config }) {
  const navigate = useNavigate();
  const [filters, setFilters] = useState({ search: '', status: '' });
  const [applied, setApplied] = useState(filters); // what has actually been sent to the backend

  // Debounce typing; status changes apply on the same tick.
  useEffect(() => {
    const timer = setTimeout(() => setApplied(filters), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [filters]);

  const { data, loading, error, reload } = useOperationResource(
    (signal) => config.api.list(applied, { signal }),
    [config, applied],
  );

  return (
    <>
      <OperationHeader title={config.plural}>
        <Link to={`${config.path}/new`} className="btn btn--primary">New {config.singular}</Link>
      </OperationHeader>
      <OperationFilters config={config} value={filters} onChange={setFilters} />
      {loading && <LoadingState />}
      {error && <ErrorState message={describeError(error)} onRetry={reload} />}
      {!loading && !error && data && data.length === 0 && (
        <EmptyState message={`No ${config.plural.toLowerCase()} found.`} />
      )}
      {!loading && !error && data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table table--clickable">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Schedule date</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.id} onClick={() => navigate(`${config.path}/${encodeURIComponent(row.id)}`)}>
                  <td><Link to={`${config.path}/${encodeURIComponent(row.id)}`} onClick={(e) => e.stopPropagation()}>{row.reference || `#${row.id}`}</Link></td>
                  <td>{row.schedule_date || '—'}</td>
                  <td><OperationStatusBadge status={row.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
