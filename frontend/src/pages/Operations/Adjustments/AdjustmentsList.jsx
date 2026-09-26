import OperationListPage from '../OperationListPage';
import { OPERATIONS } from '../../../components/operations/operationConfig';

export default function AdjustmentsList() {
  return <OperationListPage config={OPERATIONS.adjustments} />;
}
