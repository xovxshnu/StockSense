import { newLine, getLineErrors } from '../../components/operations/OperationLineTable';

// Helpers shared by operation form models (receipt, delivery, …). Mechanics only: no
// domain rules. Form state is unsaved local state. Ids are kept exactly as the backend
// (or a lookup option) provided them; they are never stringified or re-typed.

export const orEmpty = (v) => (v === null || v === undefined ? '' : v);
export const isBlank = (v) => v === '' || v === null || v === undefined;

// ASSUMPTION: schedule_date may come back as a date or a datetime; the date input needs YYYY-MM-DD.
export const asDateInput = (v) => (v ? String(v).slice(0, 10) : '');

// If the user did not change the date, send the backend's original value untouched
// (it may carry a time part the date input cannot show).
export const scheduleDatePayload = (formDate, existing) =>
  existing && formDate === asDateInput(existing.schedule_date) && existing.schedule_date
    ? existing.schedule_date
    : formDate;

// Product of an existing line. The line's own product_id is the authority (it is in the contract);
// a nested product object, if present, only supplies display fields. The id is kept exactly as
// received (never converted).
export function productFromLine(line) {
  const id = line.product_id ?? line.product?.id;
  if (line.product) return { ...line.product, id };
  return { id, sku: `#${id}`, name: '' };
}

// ASSUMPTION: operation lines carry product_id and quantity, optionally with a nested product {sku, name}.
// Quantity is held as a string because it is text-input state; it is converted once, in linesPayload.
export function linesFromServer(operation) {
  const lines = (operation.lines || []).map((l) => ({
    ...newLine(),
    product: productFromLine(l),
    quantity: String(orEmpty(l.quantity)),
  }));
  return lines.length ? lines : [newLine()];
}

// Comparable snapshot for dirty checking (drops client-only line keys).
export const snapshot = (form) =>
  JSON.stringify({
    ...form,
    lines: form.lines.map((l) => [l.product?.id ?? null, l.quantity]),
  });

// 'Add at least one product.' / 'Fix the highlighted product lines.' or undefined.
export function validateLines(lines, options) {
  if (lines.length === 0) return 'Add at least one product.';
  if (lines.some((l) => Object.values(getLineErrors(l, lines, options)).some(Boolean))) {
    return 'Fix the highlighted product lines.';
  }
  return undefined;
}

// Optional free-text field (delivery address, adjustment reason). Sent as typed (not trimmed).
// Blank: a cleared non-empty value is sent as null (ASSUMPTION: null clears it); an untouched
// empty value is sent back exactly as the backend returned it; with no existing record it is omitted.
export function optionalTextPayload(payload, key, value, existing) {
  if (value.trim()) payload[key] = value;
  else if (existing && existing[key]) payload[key] = null;
  else if (existing && existing[key] !== undefined) payload[key] = existing[key];
  return payload;
}

// Line ids are not sent: the contract's create payload has only product_id and quantity.
export const linesPayload = (lines) =>
  lines.map((l) => ({ product_id: l.product.id, quantity: Number(l.quantity) }));

// Relational fields that cannot be edited yet (no lookup endpoint) are carried through
// from the backend record exactly as received, so an update never drops or nulls them.
// A key is omitted only if the backend never returned it (null IS preserved as null).
export function preserveFields(payload, existing, keys) {
  keys.forEach((key) => {
    if (existing && existing[key] !== undefined) payload[key] = existing[key];
  });
  return payload;
}
