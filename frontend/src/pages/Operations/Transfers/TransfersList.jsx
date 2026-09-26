import OperationListPage from '../OperationListPage';
import { OPERATIONS } from '../../../components/operations/operationConfig';

export default function TransfersList() {
  return <OperationListPage config={OPERATIONS.transfers} />;
}
