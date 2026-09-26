import { newLine } from '../../../components/operations/OperationLineTable';
import {
  asDateInput, isBlank, linesFromServer, linesPayload, orEmpty, preserveFields, scheduleDatePayload, validateLines,
} from '../operationFormModel';

// Receipt form model. supplier_id and responsible_user_id are NOT form fields: no lookup
// endpoint exists for them, so they are not editable here and existing backend values are
// carried through unchanged. Nothing is required of them, since the contract does not say.

export const emptyReceiptForm = () => ({
  warehouseId: '',
  destinationLocationId: '',
  scheduleDate: '',
  lines: [newLine()],
});

export const fromReceipt = (receipt) => ({
  warehouseId: orEmpty(receipt.warehouse_id),
  destinationLocationId: orEmpty(receipt.destination_location_id),
  scheduleDate: asDateInput(receipt.schedule_date),
  lines: linesFromServer(receipt),
});

export function validateReceipt(form) {
  const errors = {};
  if (isBlank(form.warehouseId)) errors.warehouseId = 'Warehouse is required.';
  if (isBlank(form.destinationLocationId)) errors.destinationLocationId = 'Destination location is required.';
  if (!form.scheduleDate) errors.scheduleDate = 'Schedule date is required.';
  const lines = validateLines(form.lines);
  if (lines) errors.lines = lines;
  return errors;
}

// Domain fields only: no id, reference, status or timestamps (backend-owned).
export function toPayload(form, existing = null) {
  return preserveFields(
    {
      warehouse_id: form.warehouseId,
      destination_location_id: form.destinationLocationId,
      schedule_date: scheduleDatePayload(form.scheduleDate, existing),
      lines: linesPayload(form.lines),
    },
    existing,
    ['supplier_id', 'responsible_user_id'],
  );
}

export const receiptModel = {
  empty: emptyReceiptForm,
  fromServer: fromReceipt,
  validate: validateReceipt,
  toPayload,
};
