import ProductSelector from './ProductSelector';
import QuantityInput, { getQuantityError } from './QuantityInput';

// Controlled by the parent form: `lines` in, `onChange(nextLines)` out.
// A line is { key, product, quantity } plus any operation-specific fields. `key` is a client-only
// React key, never sent to the backend.
//
// Optional extension points (defaults keep receipt/delivery/transfer unchanged):
//   columnsBeforeQuantity / columnsAfterQuantity: [{ key, label, className, render(line) }] read-only cells.
//   derivedFields: line fields the backend derives from the product (e.g. system quantity). They are
//     cleared when the product on a line changes, because the old values no longer apply.
let keyCounter = 0;
export const newLine = () => ({ key: `line-${++keyCounter}`, product: null, quantity: '' });

// Deterministic duplicate rule: the first line for a product is valid, every later
// line for the same product is flagged. (Whether the backend merges or rejects
// duplicates is not specified; forms should not submit them.)
export function getLineErrors(line, lines, { allowZero = false, label = 'Quantity' } = {}) {
  const productId = line.product?.id;
  const isDuplicate =
    productId !== undefined && lines.findIndex((l) => l.product?.id === productId) !== lines.indexOf(line);
  let product = null;
  if (!line.product || productId === undefined || productId === null) product = 'Select a product.';
  else if (isDuplicate) product = 'This product is already on another line.';
  return { product, quantity: getQuantityError(line.quantity, { allowZero, label }) };
}

export default function OperationLineTable({
  lines,
  onChange,
  readOnly = false,
  disabled = false, // temporarily locked (e.g. while saving); unlike readOnly the controls stay visible
  showErrors = false,
  quantityLabel = 'Quantity',
  allowZero = false,
  columnsBeforeQuantity = [],
  columnsAfterQuantity = [],
  derivedFields = [],
}) {
  const clearDerived = () => Object.fromEntries(derivedFields.map((f) => [f, undefined]));
  const colCount = 2 + columnsBeforeQuantity.length + columnsAfterQuantity.length + (readOnly ? 0 : 1);
  const update = (key, patch) => onChange(lines.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  const remove = (key) => onChange(lines.filter((l) => l.key !== key));

  return (
    <div className="line-table">
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Product</th>
              {columnsBeforeQuantity.map((c) => <th key={c.key} className={c.className}>{c.label}</th>)}
              <th className="col-qty">{quantityLabel}</th>
              {columnsAfterQuantity.map((c) => <th key={c.key} className={c.className}>{c.label}</th>)}
              {!readOnly && <th className="col-action" aria-label="Actions" />}
            </tr>
          </thead>
          <tbody>
            {lines.length === 0 && (
              <tr>
                <td colSpan={colCount} className="table__empty">
                  No lines yet.
                </td>
              </tr>
            )}
            {lines.map((line) => {
              const errors = showErrors ? getLineErrors(line, lines, { allowZero, label: quantityLabel }) : {};
              return (
                <tr key={line.key}>
                  <td>
                    {readOnly ? (
                      line.product ? `${line.product.sku} — ${line.product.name}` : '—'
                    ) : (
                      <ProductSelector
                        value={line.product}
                        error={errors.product}
                        disabled={disabled}
                        onSelect={(product) => update(line.key, { product, ...(product?.id !== line.product?.id ? clearDerived() : {}) })}
                      />
                    )}
                  </td>
                  {columnsBeforeQuantity.map((c) => <td key={c.key} className={c.className}>{c.render(line)}</td>)}
                  <td className="col-qty">
                    {readOnly ? (
                      line.quantity
                    ) : (
                      <QuantityInput
                        value={line.quantity}
                        error={errors.quantity}
                        disabled={disabled}
                        label={quantityLabel}
                        onChange={(quantity) => update(line.key, { quantity })}
                      />
                    )}
                  </td>
                  {columnsAfterQuantity.map((c) => <td key={c.key} className={c.className}>{c.render(line)}</td>)}
                  {!readOnly && (
                    <td className="col-action">
                      <button type="button" className="btn btn--ghost" disabled={disabled} onClick={() => remove(line.key)}>
                        Remove
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!readOnly && (
        <button type="button" className="btn btn--secondary" disabled={disabled} onClick={() => onChange([...lines, newLine()])}>
          + Add line
        </button>
      )}
      {showErrors && lines.length === 0 && <p className="field__error">Add at least one product.</p>}
    </div>
  );
}
