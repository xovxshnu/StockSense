import OperationField from '../../../components/operations/form/OperationField';
import OperationFormSection from '../../../components/operations/form/OperationFormSection';
import UnavailableLookupValue from '../../../components/operations/form/UnavailableLookupValue';
import WarehouseLocationFields from '../../../components/operations/form/WarehouseLocationFields';
import ScheduleDateField from '../../../components/operations/form/ScheduleDateField';

// "Delivery information" card. Customer and responsible user have no lookup endpoint yet, so
// they are shown read-only (existing backend value, or an "unavailable" note).
export default function DeliveryFormFields({ operation, form, errors, onChange, readOnly }) {
  return (
    <OperationFormSection title="Delivery information">
      <OperationField label="Customer">
        <UnavailableLookupValue
          value={operation?.customer_id}
          label={operation?.customer?.name}
          unavailableMessage="Customer lookup unavailable — backend endpoint required."
        />
      </OperationField>
      <WarehouseLocationFields form={form} errors={errors} readOnly={readOnly} onChange={onChange}
        locationKey="sourceLocationId" locationLabel="Source location" />
      <ScheduleDateField value={form.scheduleDate} error={errors.scheduleDate} readOnly={readOnly}
        onChange={(scheduleDate) => onChange({ ...form, scheduleDate })} />
      <OperationField label="Responsible user">
        <UnavailableLookupValue
          value={operation?.responsible_user_id}
          label={operation?.responsible_user?.name}
          unavailableMessage="Responsible user lookup unavailable — backend endpoint required."
        />
      </OperationField>
      <OperationField label="Delivery address" htmlFor="delivery-address">
        <textarea id="delivery-address" className="input" rows={2} value={form.deliveryAddress} disabled={readOnly}
          onChange={(e) => onChange({ ...form, deliveryAddress: e.target.value })} />
      </OperationField>
    </OperationFormSection>
  );
}
