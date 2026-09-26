import { STATUS_META } from './operationConfig';

export default function OperationStatusBadge({ status }) {
  if (!status) return null;
  // Unknown statuses are shown verbatim rather than invented or hidden.
  const meta = STATUS_META[status] || { label: status, tone: 'neutral' };
  return <span className={`badge badge--${meta.tone}`}>{meta.label}</span>;
}
