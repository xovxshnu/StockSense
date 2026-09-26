import { Link } from 'react-router-dom';
import OperationStatusBadge from './OperationStatusBadge';

// `reference` is backend-generated; it is never fabricated here.
export default function OperationHeader({ title, reference, status, backTo, backLabel, children }) {
  return (
    <header className="op-header">
      <div className="op-header__main">
        {backTo && (
          <Link to={backTo} className="op-header__back">
            ← {backLabel || 'Back'}
          </Link>
        )}
        <h1 className="op-header__title">
          {title}
          {reference && <span className="op-header__ref">{reference}</span>}
        </h1>
        <OperationStatusBadge status={status} />
      </div>
      {children && <div className="op-header__side">{children}</div>}
    </header>
  );
}
