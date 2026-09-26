import { useParams } from 'react-router-dom';
import { EmptyState, ErrorState, LoadingState } from '../../components/operations/AsyncState';
import { describeError } from '../../components/operations/errorMessage';
import useOperationResource from './useOperationResource';
import buildOperationActions from './buildOperationActions';
import OperationEditor from './OperationEditor';

// Existing operation: fetch from the backend, then hand the server state to the editor.
function ExistingOperation({ id, config, model, Fields }) {
  const { data, setData, loading, error, reload, refresh } = useOperationResource(
    (signal) => config.api.get(id, { signal }),
    [config, id],
  );

  if (loading) return <LoadingState />;
  if (error?.isNotFound) return <EmptyState message={`${config.singular} not found.`} />;
  if (error) return <ErrorState message={describeError(error)} onRetry={reload} />;
  if (!data) return null;

  return (
    <OperationEditor
      config={config}
      model={model}
      Fields={Fields}
      operation={data}
      onOperationChange={setData}
      refresh={refresh}
      actions={buildOperationActions(config, id, { setData, refresh })}
    />
  );
}

// Serves both /operations/<type>/new (no id) and /operations/<type>/:id.
export default function OperationEditorPage({ config, model, Fields }) {
  const { id } = useParams();
  return id ? (
    <ExistingOperation key={id} id={id} config={config} model={model} Fields={Fields} />
  ) : (
    <OperationEditor config={config} model={model} Fields={Fields} operation={null} />
  );
}
