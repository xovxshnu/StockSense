import OperationField from '../../../components/operations/form/OperationField';
import OperationFormSection from '../../../components/operations/form/OperationFormSection';
import UnavailableLookupValue from '../../../components/operations/form/UnavailableLookupValue';
import LocationField from '../../../components/operations/form/LocationField';
import ScheduleDateField from '../../../components/operations/form/ScheduleDateField';
import useLookup from '../../../components/operations/form/useLookup';
import { locationApi, warehouseApi } from '../../../services/masterDataApi';

// "Transfer information" card. A transfer has two independent locations and no warehouse
// field, so there is no warehouse filtering: both pickers list all locations (labelled with
// their warehouse code when the warehouse lookup is available). No stock is read.
export default function TransferFormFields({ operation, form, errors, onChange, readOnly }) {
  const locations = useLookup(locationApi.list);
  const warehouses = useLookup(warehouseApi.list);

  return (
    <OperationFormSection title="Transfer information">
      <LocationField id="from-location" label="From location (source)" lookup={locations}
        warehouses={warehouses.options} value={form.fromLocationId} error={errors.fromLocationId}
        readOnly={readOnly} placeholder="Select source location"
        onChange={(fromLocationId) => onChange({ ...form, fromLocationId })} />
      <LocationField id="to-location" label="To location (destination)" lookup={locations}
        warehouses={warehouses.options} value={form.toLocationId} error={errors.toLocationId}
        readOnly={readOnly} placeholder="Select destination location"
        onChange={(toLocationId) => onChange({ ...form, toLocationId })} />
      <ScheduleDateField value={form.scheduleDate} error={errors.scheduleDate} readOnly={readOnly}
        onChange={(scheduleDate) => onChange({ ...form, scheduleDate })} />
      <OperationField label="Responsible user">
        <UnavailableLookupValue
          value={operation?.responsible_user_id}
          label={operation?.responsible_user?.name}
          unavailableMessage="Responsible user lookup unavailable — backend endpoint required."
        />
      </OperationField>
    </OperationFormSection>
  );
}
