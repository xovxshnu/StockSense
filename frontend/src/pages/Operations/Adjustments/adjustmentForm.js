import { newLine } from '../../../components/operations/OperationLineTable';
import {
  isBlank, optionalTextPayload, orEmpty, preserveFields, productFromLine, validateLines,
} from '../operationFormModel';
import { adjustmentLineTable } from './AdjustmentLineColumns';

// Adjustment form model. React never touches stock: this only prepares what is submitted to the
// backend, which performs the reconciliation. No stock lookup exists or is invented here.
//
// PAYLOAD DECISIONS (assumptions, isolated in this file):
//  - counted_quantity is the only line value the user enters, so it is always sent.
//  - system_quantity and difference are backend-derived and are NEVER sent (create or update).
//    They are kept in form state only so they can be displayed when the backend returns them.
//    (Whether the backend wants system_quantity on PUT is an open contract question; the safe
//    default is to let the backend own it, so a stale client copy can never influence a reconciliation.)
//  - responsible_user_id has no lookup; an existing backend value is carried through unchanged.

export const emptyAdjustmentForm = () => ({
  locationId: '',
  reason: '',
  lines: [newLine()],
});

export function fromAdjustment(adjustment) {
  const lines = (adjustment.lines || []).map((l) => ({
    ...newLine(),
    product: productFromLine(l),
    quantity: String(orEmpty(l.counted_quantity)),
    serverQuantity: String(orEmpty(l.counted_quantity)),
    systemQuantity: l.system_quantity,
    difference: l.difference,
  }));
  return {
    locationId: orEmpty(adjustment.location_id),
    reason: String(orEmpty(adjustment.reason)),
    lines: lines.length ? lines : [newLine()],
  };
}

// Reason is not required: the contract only names the field, so the backend decides.
export function validateAdjustment(form) {
  const errors = {};
  if (isBlank(form.locationId)) errors.locationId = 'Location is required.';
  const lines = validateLines(form.lines, { allowZero: adjustmentLineTable.allowZero, label: adjustmentLineTable.quantityLabel });
  if (lines) errors.lines = lines;
  return errors;
}

export function toPayload(form, existing = null) {
  const payload = {
    location_id: form.locationId,
    lines: form.lines.map((l) => ({ product_id: l.product.id, counted_quantity: Number(l.quantity) })),
  };
  optionalTextPayload(payload, 'reason', form.reason, existing);
  return preserveFields(payload, existing, ['responsible_user_id']);
}

export const adjustmentModel = {
  empty: emptyAdjustmentForm,
  fromServer: fromAdjustment,
  validate: validateAdjustment,
  toPayload,
  lineTable: adjustmentLineTable,
};
