import OperationEditorPage from '../OperationEditorPage';
import { OPERATIONS } from '../../../components/operations/operationConfig';
import { transferModel } from './transferForm';
import TransferFormFields from './TransferFormFields';

export default function TransferFormPage() {
  return <OperationEditorPage config={OPERATIONS.transfers} model={transferModel} Fields={TransferFormFields} />;
}
