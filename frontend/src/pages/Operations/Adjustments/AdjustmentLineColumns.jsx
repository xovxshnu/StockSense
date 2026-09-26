import { getQuantityError } from '../../../components/operations/QuantityInput';

// Extra read-only columns for adjustment lines. Line shape (in addition to product/quantity):
//   quantity        = counted quantity, the only value the user enters (string)
//   systemQuantity  = backend-provided; never computed or looked up here
//   difference      = backend-provided; never editable
//   serverQuantity  = the counted quantity as last loaded/saved from the backend

const isSet = (v) => v !== undefined && v !== null && v !== '';

// PRESENTATION ONLY: shown when the backend has supplied system_quantity but the counted value has
// been edited since, so the backend's stored difference is stale. Never sent to the backend and never
// used for validation or workflow. The backend recalculates and remains authoritative.
export function previewDifference(counted, system) {
  if (getQuantityError(counted, { allowZero: true }) || !isSet(system) || !Number.isFinite(Number(system))) return null;
  return Number(counted) - Number(system);
}

const signed = (n) => (n > 0 ? `+${n}` : String(n));

export const systemQuantityColumn = {
  key: 'system',
  label: 'System quantity',
  className: 'col-qty col-readonly',
  render: (line) =>
    isSet(line.systemQuantity)
      ? line.systemQuantity
      : <span className="muted" title="Provided by the backend; not available for this line yet.">—</span>,
};

export const differenceColumn = {
  key: 'difference',
  label: 'Difference',
  className: 'col-qty col-readonly',
  render: (line) => {
    // Backend value while the counted quantity is unchanged from what the backend has.
    if (isSet(line.difference) && String(line.quantity) === line.serverQuantity) {
      return Number.isFinite(Number(line.difference)) ? signed(Number(line.difference)) : String(line.difference);
    }
    const preview = previewDifference(line.quantity, line.systemQuantity);
    if (preview !== null) {
      return <span className="muted" title="Preview only. The backend calculates the difference when the adjustment is saved.">{signed(preview)} (preview)</span>;
    }
    return <span className="muted" title="Calculated by the backend.">—</span>;
  },
};

export const adjustmentLineTable = {
  quantityLabel: 'Counted quantity',
  allowZero: true, // a counted quantity of 0 is valid
  columnsBeforeQuantity: [systemQuantityColumn],
  columnsAfterQuantity: [differenceColumn],
  derivedFields: ['systemQuantity', 'difference', 'serverQuantity'],
};
