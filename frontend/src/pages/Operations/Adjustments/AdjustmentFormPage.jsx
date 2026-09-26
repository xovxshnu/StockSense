import OperationEditorPage from '../OperationEditorPage';
import { OPERATIONS } from '../../../components/operations/operationConfig';
import { adjustmentModel } from './adjustmentForm';
import AdjustmentFormFields from './AdjustmentFormFields';

export default function AdjustmentFormPage() {
  return <OperationEditorPage config={OPERATIONS.adjustments} model={adjustmentModel} Fields={AdjustmentFormFields} />;
}
