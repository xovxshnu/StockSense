export default function OperationField({ label, htmlFor, required, error, hint, children }) {
  return (
    <div className="form-field">
      <label className="form-field__label" htmlFor={htmlFor}>
        {label}
        {required && <span className="form-field__req" aria-hidden="true"> *</span>}
      </label>
      {children}
      {hint && !error && <span className="form-field__hint">{hint}</span>}
      {error && <span className="field__error" role="alert">{error}</span>}
    </div>
  );
}
