import { describeError } from '../errorMessage';

// Select over backend-provided options ({ id, ... }). `value` and the emitted value are the
// option's raw id (never stringified), or '' for none. If the current value is not among the
// options (lookup failed, or the record was deactivated) it is still shown as "#id" so nothing
// is hidden or silently changed; picking it keeps the current value.
export default function LookupSelect({
  id, value, onChange, options, getLabel, loading, error, onRetry, disabled, placeholder = 'Select…',
}) {
  const current = value === '' || value === null || value === undefined ? '' : String(value);
  const known = options.some((o) => String(o.id) === current);

  const pick = (chosen) => {
    if (chosen === '') return onChange('');
    const match = options.find((o) => String(o.id) === chosen);
    return onChange(match ? match.id : value);
  };

  return (
    <div className="lookup">
      <select
        id={id}
        className={`input${error ? ' input--error' : ''}`}
        value={current}
        disabled={disabled || loading}
        onChange={(e) => pick(e.target.value)}
      >
        <option value="">{loading ? 'Loading…' : placeholder}</option>
        {current && !known && !loading && <option value={current}>#{current}</option>}
        {options.map((o) => (
          <option key={o.id} value={String(o.id)}>{getLabel(o)}</option>
        ))}
      </select>
      {error && !loading && (
        <span className="field__error">
          Could not load options: {describeError(error)}{' '}
          {onRetry && <button type="button" className="link-btn" onClick={onRetry}>Retry</button>}
        </span>
      )}
    </div>
  );
}
