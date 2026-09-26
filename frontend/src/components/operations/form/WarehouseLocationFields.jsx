import OperationField from './OperationField';
import LookupSelect from './LookupSelect';
import LocationField from './LocationField';
import useLookup from './useLookup';
import { warehouseApi, locationApi } from '../../../services/masterDataApi';

const optionLabel = (o) => (o.short_code ? `${o.short_code} — ${o.name}` : o.name || `#${o.id}`);

// Warehouse + one location, for operations that belong to a warehouse (receipt, delivery).
// `locationKey` is the form key for the location (e.g. 'destinationLocationId'); changing the
// warehouse clears it so a location from another warehouse is never kept. Presentation only:
// no stock is read or compared. (Transfers use two LocationFields directly instead.)
export default function WarehouseLocationFields({ form, errors, readOnly, onChange, locationKey, locationLabel }) {
  const warehouses = useLookup(warehouseApi.list);
  const locations = useLookup(locationApi.list);
  const hasWarehouse = form.warehouseId !== '';

  return (
    <>
      <OperationField label="Warehouse" htmlFor="warehouse" required error={errors.warehouseId}>
        <LookupSelect id="warehouse" value={form.warehouseId} disabled={readOnly}
          options={warehouses.options} getLabel={optionLabel} loading={warehouses.loading}
          error={warehouses.error} onRetry={warehouses.reload} placeholder="Select warehouse"
          onChange={(warehouseId) => onChange({ ...form, warehouseId, [locationKey]: '' })} />
      </OperationField>

      <LocationField id="location" label={locationLabel} lookup={locations}
        value={form[locationKey]} error={errors[locationKey]} readOnly={readOnly}
        warehouseId={form.warehouseId}
        disabledHint={hasWarehouse ? undefined : 'Select a warehouse first'}
        onChange={(value) => onChange({ ...form, [locationKey]: value })} />
    </>
  );
}
