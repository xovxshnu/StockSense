import OperationField from '../../../components/operations/form/OperationField';
import OperationFormSection from '../../../components/operations/form/OperationFormSection';
import UnavailableLookupValue from '../../../components/operations/form/UnavailableLookupValue';
import LocationField from '../../../components/operations/form/LocationField';
import useLookup from '../../../components/operations/form/useLookup';
import { locationApi, warehouseApi } from '../../../services/masterDataApi';

// "Adjustment information" card. One location; no warehouse field, so no warehouse filtering.
// Responsible user has no lookup endpoint yet, so it is shown read-only.
export default function AdjustmentFormFields({ operation, form, errors, onChange, readOnly }) {
  const locations = useLookup(locationApi.list);
  const warehouses = useLookup(warehouseApi.list);

  return (
    <OperationFormSection title="Adjustment information">
      <LocationField id="location" label="Location" lookup={locations} warehouses={warehouses.options}
        value={form.locationId} error={errors.locationId} readOnly={readOnly}
        onChange={(locationId) => onChange({ ...form, locationId })} />
      <OperationField label="Responsible user">
        <UnavailableLookupValue
          value={operation?.responsible_user_id}
          label={operation?.responsible_user?.name}
          unavailableMessage="Responsible user lookup unavailable — backend endpoint required."
        />
      </OperationField>
      <OperationField label="Reason" htmlFor="reason">
        <textarea id="reason" className="input" rows={2} value={form.reason} disabled={readOnly}
          onChange={(e) => onChange({ ...form, reason: e.target.value })} />
      </OperationField>
    </OperationFormSection>
  );
}
