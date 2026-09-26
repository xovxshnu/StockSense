import OperationField from './OperationField';

export default function ScheduleDateField({ value, error, readOnly, onChange }) {
  return (
    <OperationField label="Schedule date" htmlFor="schedule-date" required error={error}>
      <input id="schedule-date" type="date" className={`input${error ? ' input--error' : ''}`}
        value={value} disabled={readOnly} required onChange={(e) => onChange(e.target.value)} />
    </OperationField>
  );
}
