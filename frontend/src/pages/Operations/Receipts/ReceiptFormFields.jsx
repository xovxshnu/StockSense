import OperationField from '../../../components/operations/form/OperationField';
import OperationFormSection from '../../../components/operations/form/OperationFormSection';
import UnavailableLookupValue from '../../../components/operations/form/UnavailableLookupValue';
import WarehouseLocationFields from '../../../components/operations/form/WarehouseLocationFields';
import ScheduleDateField from '../../../components/operations/form/ScheduleDateField';

// "Receipt information" card. Supplier and responsible user have no lookup endpoint yet, so
// they are shown read-only (existing backend value, or an "unavailable" note).
export default function ReceiptFormFields({ operation, form, errors, onChange, readOnly }) {
  return (
    <OperationFormSection title="Receipt information">
      <OperationField label="Supplier">
        <UnavailableLookupValue
          value={operation?.supplier_id}
          label={operation?.supplier?.name}
          unavailableMessage="Supplier lookup unavailable — backend endpoint required."
        />
      </OperationField>
      <WarehouseLocationFields form={form} errors={errors} readOnly={readOnly} onChange={onChange}
        locationKey="destinationLocationId" locationLabel="Destination location" />
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
