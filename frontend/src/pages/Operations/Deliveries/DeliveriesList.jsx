import OperationListPage from '../OperationListPage';
import { OPERATIONS } from '../../../components/operations/operationConfig';

export default function DeliveriesList() {
  return <OperationListPage config={OPERATIONS.deliveries} />;
}
