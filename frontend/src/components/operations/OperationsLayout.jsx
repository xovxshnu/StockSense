import { NavLink, Outlet } from 'react-router-dom';
import { OPERATIONS } from './operationConfig';

// Minimal frame so the Operations pages are usable standalone.
// Replace with the real app shell when it exists.
export default function OperationsLayout() {
  return (
    <div className="shell">
      <nav className="shell__nav" aria-label="Operations">
        <span className="shell__brand">StockSense</span>
        {Object.values(OPERATIONS).map((op) => (
          <NavLink key={op.key} to={op.path} className="shell__link">
            {op.plural}
          </NavLink>
        ))}
      </nav>
      <main className="shell__main">
        <Outlet />
      </main>
    </div>
  );
}
