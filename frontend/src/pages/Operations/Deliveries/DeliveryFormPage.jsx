import OperationEditorPage from '../OperationEditorPage';
import { OPERATIONS } from '../../../components/operations/operationConfig';
import { deliveryModel } from './deliveryForm';
import DeliveryFormFields from './DeliveryFormFields';

export default function DeliveryFormPage() {
  return <OperationEditorPage config={OPERATIONS.deliveries} model={deliveryModel} Fields={DeliveryFormFields} />;
}
