import { newLine } from '../../../components/operations/OperationLineTable';
import {
  asDateInput, isBlank, linesFromServer, linesPayload, optionalTextPayload, orEmpty, preserveFields, scheduleDatePayload, validateLines,
} from '../operationFormModel';

// Delivery form model. customer_id and responsible_user_id are NOT form fields: no lookup
// endpoint exists for them, so existing backend values are carried through unchanged.
// No stock, availability or free_to_use logic lives here: the backend owns it.

export const emptyDeliveryForm = () => ({
  warehouseId: '',
  sourceLocationId: '',
  deliveryAddress: '',
  scheduleDate: '',
  lines: [newLine()],
});

export const fromDelivery = (delivery) => ({
  warehouseId: orEmpty(delivery.warehouse_id),
  sourceLocationId: orEmpty(delivery.source_location_id),
  deliveryAddress: String(orEmpty(delivery.delivery_address)),
  scheduleDate: asDateInput(delivery.schedule_date),
  lines: linesFromServer(delivery),
});

// delivery_address is not required: the contract does not say it is, so the backend decides.
export function validateDelivery(form) {
  const errors = {};
  if (isBlank(form.warehouseId)) errors.warehouseId = 'Warehouse is required.';
  if (isBlank(form.sourceLocationId)) errors.sourceLocationId = 'Source location is required.';
  if (!form.scheduleDate) errors.scheduleDate = 'Schedule date is required.';
  const lines = validateLines(form.lines);
  if (lines) errors.lines = lines;
  return errors;
}

// Domain fields only: no id, reference, status or timestamps (backend-owned).
export function toPayload(form, existing = null) {
  const payload = {
    warehouse_id: form.warehouseId,
    source_location_id: form.sourceLocationId,
    schedule_date: scheduleDatePayload(form.scheduleDate, existing),
    lines: linesPayload(form.lines),
  };
  optionalTextPayload(payload, 'delivery_address', form.deliveryAddress, existing);

  return preserveFields(payload, existing, ['customer_id', 'responsible_user_id']);
}

export const deliveryModel = {
  empty: emptyDeliveryForm,
  fromServer: fromDelivery,
  validate: validateDelivery,
  toPayload,
};
