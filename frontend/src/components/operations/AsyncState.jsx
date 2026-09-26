// Shared loading / error / empty presentation.
export function LoadingState({ label = 'Loading…' }) {
  return <div className="state" role="status">{label}</div>;
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="state state--error" role="alert">
      <p>{message}</p>
      {onRetry && <button type="button" className="btn btn--secondary" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function EmptyState({ message, children }) {
  return (
    <div className="state">
      <p>{message}</p>
      {children}
    </div>
  );
}
