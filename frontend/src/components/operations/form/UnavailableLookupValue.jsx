// Read-only stand-in for a relational field whose lookup endpoint is not in the API
// contract. Shows the existing backend value if there is one (never editable, never
// dropped), otherwise a clear "unavailable" note. It offers no options and no free-text ID.
export default function UnavailableLookupValue({ value, label, unavailableMessage }) {
  if (value === undefined || value === null || value === '') {
    return <div className="readonly-value readonly-value--unavailable">{unavailableMessage}</div>;
  }
  return (
    <div className="readonly-value" title="Set by the backend; cannot be changed from this form yet.">
      {label ?? `#${value}`}
    </div>
  );
}
