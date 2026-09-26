import { newLine } from '../../../components/operations/OperationLineTable';
import {
  asDateInput, isBlank, linesFromServer, linesPayload, orEmpty, preserveFields, scheduleDatePayload, validateLines,
} from '../operationFormModel';

// Transfer form model. responsible_user_id is NOT a form field (no lookup endpoint), so an
// existing backend value is carried through unchanged. No stock, availability or
// executability logic lives here: only the backend can decide whether a transfer can run.

export const emptyTransferForm = () => ({
  fromLocationId: '',
  toLocationId: '',
  scheduleDate: '',
  lines: [newLine()],
});

export const fromTransfer = (transfer) => ({
  fromLocationId: orEmpty(transfer.from_location_id),
  toLocationId: orEmpty(transfer.to_location_id),
  scheduleDate: asDateInput(transfer.schedule_date),
  lines: linesFromServer(transfer),
});

export function validateTransfer(form) {
  const errors = {};
  if (isBlank(form.fromLocationId)) errors.fromLocationId = 'From location is required.';
  if (isBlank(form.toLocationId)) errors.toLocationId = 'To location is required.';
  // Equality only (String() is just for comparison; the values themselves are never converted).
  else if (!isBlank(form.fromLocationId) && String(form.fromLocationId) === String(form.toLocationId)) {
    errors.toLocationId = 'To location must be different from the from location.';
  }
  if (!form.scheduleDate) errors.scheduleDate = 'Schedule date is required.';
  const lines = validateLines(form.lines);
  if (lines) errors.lines = lines;
  return errors;
}

// Domain fields only: no id, reference, status or timestamps (backend-owned).
export function toPayload(form, existing = null) {
  return preserveFields(
    {
      from_location_id: form.fromLocationId,
      to_location_id: form.toLocationId,
      schedule_date: scheduleDatePayload(form.scheduleDate, existing),
      lines: linesPayload(form.lines),
    },
    existing,
    ['responsible_user_id'],
  );
}

export const transferModel = {
  empty: emptyTransferForm,
  fromServer: fromTransfer,
  validate: validateTransfer,
  toPayload,
};
