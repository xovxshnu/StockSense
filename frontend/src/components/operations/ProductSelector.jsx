import { useEffect, useRef, useState } from 'react';
import { productApi } from '../../services/operationsApi';
import { describeError } from './errorMessage';

// Searches GET /api/products?search=… and returns the chosen product to the parent.
// Displays only fields the backend returns; no stock is read or computed.
export default function ProductSelector({ value, onSelect, disabled, error }) {
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(null);
  const rootRef = useRef(null);

  useEffect(() => {
    setResults([]); // never show results from a previous term
    setFailed(null);
    if (!open || term.trim().length === 0) {
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        setResults(await productApi.search(term.trim(), { signal: controller.signal }));
      } catch (err) {
        if (err.name !== 'AbortError') setFailed(describeError(err));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [term, open]);

  useEffect(() => {
    const close = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const choose = (product) => {
    onSelect(product);
    setTerm('');
    setOpen(false);
  };

  return (
    <div className="field product-selector" ref={rootRef}>
      <input
        type="text"
        className={`input${error ? ' input--error' : ''}`}
        placeholder="Search by SKU or name"
        aria-label="Product"
        disabled={disabled}
        value={open ? term : value ? `${value.sku} — ${value.name}` : term}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => e.key === 'Enter' && e.preventDefault()} // Enter must not submit the surrounding form
        onChange={(e) => {
          setTerm(e.target.value);
          setOpen(true);
        }}
      />
      {error && <span className="field__error">{error}</span>}
      {open && term.trim() && (
        <ul className="product-selector__menu" role="listbox">
          {loading && <li className="product-selector__note">Searching…</li>}
          {failed && <li className="product-selector__note product-selector__note--error">{failed}</li>}
          {!loading && !failed && results.length === 0 && (
            <li className="product-selector__note">No products found</li>
          )}
          {!failed &&
            results.map((p) => (
              <li key={p.id}>
                <button type="button" role="option" className="product-selector__option" onClick={() => choose(p)}>
                  <strong>{p.sku}</strong> <span>{p.name}</span>
                </button>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
