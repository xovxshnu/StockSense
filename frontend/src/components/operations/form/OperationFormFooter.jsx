// Bottom action bar for operation forms: status message on the left, buttons on the right.
export default function OperationFormFooter({ error, note, children }) {
  return (
    <footer className="form-footer">
      <div className="form-footer__msg">
        {error && <p className="alert alert--error" role="alert">{error}</p>}
        {!error && note && <p className="form-footer__note">{note}</p>}
      </div>
      <div className="form-footer__buttons">{children}</div>
    </footer>
  );
}
