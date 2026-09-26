import { Link, Navigate, Route, Routes } from 'react-router-dom';
import OperationsLayout from '../components/operations/OperationsLayout';
import ReceiptsList from '../pages/Operations/Receipts/ReceiptsList';
import ReceiptsForm from '../pages/Operations/Receipts/ReceiptsForm';
import ReceiptsDetail from '../pages/Operations/Receipts/ReceiptsDetail';
import DeliveriesList from '../pages/Operations/Deliveries/DeliveriesList';
import DeliveriesForm from '../pages/Operations/Deliveries/DeliveriesForm';
import DeliveriesDetail from '../pages/Operations/Deliveries/DeliveriesDetail';
import TransfersList from '../pages/Operations/Transfers/TransfersList';
import TransfersForm from '../pages/Operations/Transfers/TransfersForm';
import TransfersDetail from '../pages/Operations/Transfers/TransfersDetail';
import AdjustmentsList from '../pages/Operations/Adjustments/AdjustmentsList';
import AdjustmentsForm from '../pages/Operations/Adjustments/AdjustmentsForm';
import AdjustmentsDetail from '../pages/Operations/Adjustments/AdjustmentsDetail';

// Operations routes as a fragment of <Route>s. The integration owner's app shell can
// render `{operationsRoutes}` inside its own <Routes> (under its own layout) and add
// Dashboard/Stock/etc. alongside; nothing here assumes it owns the whole URL space.
export const operationsRoutes = (
  <>
    <Route path="/operations" element={<Navigate to="/operations/receipts" replace />} />
    <Route element={<OperationsLayout />}>
      <Route path="/operations/receipts" element={<ReceiptsList />} />
      <Route path="/operations/receipts/new" element={<ReceiptsForm />} />
      <Route path="/operations/receipts/:id" element={<ReceiptsDetail />} />
      <Route path="/operations/deliveries" element={<DeliveriesList />} />
      <Route path="/operations/deliveries/new" element={<DeliveriesForm />} />
      <Route path="/operations/deliveries/:id" element={<DeliveriesDetail />} />
      <Route path="/operations/transfers" element={<TransfersList />} />
      <Route path="/operations/transfers/new" element={<TransfersForm />} />
      <Route path="/operations/transfers/:id" element={<TransfersDetail />} />
      <Route path="/operations/adjustments" element={<AdjustmentsList />} />
      <Route path="/operations/adjustments/new" element={<AdjustmentsForm />} />
      <Route path="/operations/adjustments/:id" element={<AdjustmentsDetail />} />
    </Route>
  </>
);

// Standalone entry used until the real app shell exists.
export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/operations/receipts" replace />} />
      {operationsRoutes}
      <Route path="*" element={<p style={{ padding: 24 }}>Page not found. <Link to="/operations/receipts">Go to Receipts</Link></p>} />
    </Routes>
  );
}
