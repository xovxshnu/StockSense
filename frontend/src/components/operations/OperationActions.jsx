import { useEffect, useRef, useState } from 'react';
import { describeError } from './errorMessage';
import ConfirmDialog from './ConfirmDialog';
import { ACTION_META, UNVERIFIED_ACTION_HINT, confirmFor, isUnverifiedAction } from './operationConfig';

// Renders the actions available for the backend-reported status.
// Each action calls `handlers[name]()` (a backend API call supplied by the parent);
// the parent replaces its state with the backend response. No status or stock is
// changed here, and no action is assumed to succeed before the backend answers.
export default function OperationActions({ config, status, handlers, disabled = false, onBusyChange }) {
  const [pending, setPending] = useState(null); // { name, confirm } awaiting confirmation (text captured when opened)
  const [busy, setBusy] = useState(null); // action in flight
  const [error, setError] = useState(null);
  const inFlight = useRef(false); // synchronous guard: state updates are too late for a fast double-click

  // Lets the parent lock its form while a backend action is running.
  useEffect(() => {
    onBusyChange?.(busy !== null);
  }, [busy, onBusyChange]);

  const names = (config.actionsByStatus[status] || []).filter((n) => handlers[n]);
  // Keep rendering while an error is showing: a failed action may have re-synced the status to
  // one with no actions, and the backend's message must still be visible.
  if (names.length === 0 && !error) return null;

  const run = async (name) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(name);
    setError(null);
    try {
      await handlers[name]();
    } catch (err) {
      setError(describeError(err));
    } finally {
      inFlight.current = false;
      setBusy(null);
      setPending(null);
    }
  };

  const click = (name) => {
    const confirmation = confirmFor(config, status, name);
    if (confirmation) setPending({ name, confirm: confirmation });
    else run(name);
  };
  const confirm = pending?.confirm ?? null;

  return (
    <div className="op-actions">
      <div className="op-actions__buttons">
        {names.map((name) => (
          <button
            key={name}
            type="button"
            className={`btn btn--${ACTION_META[name].variant}`}
            disabled={disabled || busy !== null}
            title={isUnverifiedAction(config, status, name) ? UNVERIFIED_ACTION_HINT : undefined}
            onClick={() => click(name)}
          >
            {busy === name ? ACTION_META[name].busyLabel : ACTION_META[name].label}
          </button>
        ))}
      </div>
      {error && <p className="alert alert--error" role="alert">{error}</p>}
      <ConfirmDialog
        open={Boolean(pending)}
        title={confirm?.title}
        message={confirm?.message}
        confirmLabel={confirm?.confirmLabel}
        confirmVariant={confirm?.confirmVariant}
        busy={busy !== null}
        onConfirm={() => run(pending.name)}
        onClose={() => setPending(null)}
      />
    </div>
  );
}
