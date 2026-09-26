import OperationEditorPage from '../OperationEditorPage';
import { OPERATIONS } from '../../../components/operations/operationConfig';
import { receiptModel } from './receiptForm';
import ReceiptFormFields from './ReceiptFormFields';

export default function ReceiptFormPage() {
  return <OperationEditorPage config={OPERATIONS.receipts} model={receiptModel} Fields={ReceiptFormFields} />;
}
