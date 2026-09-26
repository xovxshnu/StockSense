import OperationField from './OperationField';
import LookupSelect from './LookupSelect';

const nameOf = (o) => (o.short_code ? `${o.short_code} — ${o.name}` : o.name || `#${o.id}`);

// One location picker over an already-loaded lookup (`lookup` = result of useLookup(locationApi.list)),
// so a form with several location fields fetches locations once. `warehouseId`, when given,
// narrows the options to that warehouse, only if the backend returns warehouse_id on locations
// (presentation only). `warehouses` optionally prefixes labels with the warehouse code so
// same-named locations in different warehouses can be told apart. Values are raw ids.
export default function LocationField({
  id, label, lookup, value, onChange, error, readOnly, warehouseId = '', warehouses = [], placeholder, disabledHint,
}) {
  const hasWarehouse = warehouseId !== '';
  const options = hasWarehouse
    ? lookup.options.filter((l) => l.warehouse_id === undefined || String(l.warehouse_id) === String(warehouseId))
    : lookup.options;

  const getLabel = (o) => {
    const wh = warehouses.find((w) => String(w.id) === String(o.warehouse_id));
    return wh?.short_code ? `${wh.short_code} / ${nameOf(o)}` : nameOf(o);
  };

  return (
    <OperationField label={label} htmlFor={id} required error={error}>
      <LookupSelect
        id={id}
        value={value}
        disabled={readOnly || Boolean(disabledHint)}
        options={options}
        getLabel={getLabel}
        loading={lookup.loading}
        error={lookup.error}
        onRetry={lookup.reload}
        placeholder={disabledHint || placeholder || 'Select location'}
        onChange={onChange}
      />
    </OperationField>
  );
}
