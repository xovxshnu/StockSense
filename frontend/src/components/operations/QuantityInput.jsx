// Controlled numeric input. Emits the raw string so the parent decides how to validate.
// `allowZero` is for quantities where 0 is meaningful (e.g. a counted quantity of 0).
export function getQuantityError(value, { allowZero = false, label = 'Quantity' } = {}) {
  if (value === '' || value === null || value === undefined) return `${label} is required.`;
  const n = Number(value);
  if (!Number.isFinite(n)) return `${label} must be a number.`;
  if (n < 0 || (n === 0 && !allowZero)) return allowZero ? `${label} cannot be negative.` : `${label} must be greater than 0.`;
  return null;
}

export default function QuantityInput({ value, onChange, error, disabled, min = 0, id, label = 'Quantity' }) {
  return (
    <div className="field">
      <input
        id={id}
        type="number"
        inputMode="decimal"
        className={`input input--num${error ? ' input--error' : ''}`}
        value={value ?? ''}
        min={min}
        step="any"
        disabled={disabled}
        aria-label={label}
        aria-invalid={Boolean(error)}
        onChange={(e) => onChange(e.target.value)}
      />
      {error && <span className="field__error">{error}</span>}
    </div>
  );
}
