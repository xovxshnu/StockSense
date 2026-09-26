import OperationListPage from '../OperationListPage';
import { OPERATIONS } from '../../../components/operations/operationConfig';

export default function ReceiptsList() {
  return <OperationListPage config={OPERATIONS.receipts} />;
}
