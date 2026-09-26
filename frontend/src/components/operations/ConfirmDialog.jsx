import { useEffect } from 'react';

export default function ConfirmDialog({ open, title, message, confirmLabel = 'Confirm', cancelLabel = 'Keep', confirmVariant = 'danger', busy, onConfirm, onClose }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === 'Escape' && !busy && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, busy, onClose]);

  if (!open) return null;
  return (
    <div className="dialog-backdrop" onClick={busy ? undefined : onClose}>
      <div className="dialog" role="alertdialog" aria-modal="true" aria-labelledby="dlg-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="dlg-title" className="dialog__title">{title}</h2>
        <p className="dialog__message">{message}</p>
        <div className="dialog__actions">
          <button type="button" className="btn btn--secondary" disabled={busy} onClick={onClose}>
            {cancelLabel}
          </button>
          <button type="button" className={`btn btn--${confirmVariant}`} disabled={busy} onClick={onConfirm}>
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
