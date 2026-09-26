import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import OperationHeader from '../../components/operations/OperationHeader';
import OperationActions from '../../components/operations/OperationActions';
import OperationLineTable from '../../components/operations/OperationLineTable';
import ConfirmDialog from '../../components/operations/ConfirmDialog';
import OperationFormSection from '../../components/operations/form/OperationFormSection';
import OperationFormFooter from '../../components/operations/form/OperationFormFooter';
import { RefreshAfterMutationError, describeError } from '../../components/operations/errorMessage';
import { STATUS_META } from '../../components/operations/operationConfig';
import { isOperation } from './buildOperationActions';
import useUnsavedChangesGuard from './useUnsavedChangesGuard';
import { snapshot } from './operationFormModel';

// Generic create/edit form for one operation (receipt, delivery, …).
//   operation: server state (null when creating). Replaced only by backend responses.
//   form:      unsaved local edits, reset whenever `operation` changes.
// Backend status decides editability: only DRAFT (or a new operation) is editable.
//
// model:  { empty(), fromServer(op), validate(form) -> errors, toPayload(form, existing),
//           lineTable? (extra OperationLineTable props: quantityLabel, allowZero, columns…) }
// Fields: component rendering the header-information card for this operation.
export default function OperationEditor({ config, model, Fields, operation, actions, onOperationChange, refresh }) {
  const navigate = useNavigate();
  const isNew = !operation;
  const readOnly = !isNew && !config.editableStatuses.includes(operation.status);
  const noun = config.singular.toLowerCase();

  const [form, setForm] = useState(() => (operation ? model.fromServer(operation) : model.empty()));
  const [baseline, setBaseline] = useState(() => snapshot(form));
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const submitting = useRef(false);

  // Server state changed (load, save, todo/validate/cancel): re-sync the form from it.
  useEffect(() => {
    if (!operation) return;
    const next = model.fromServer(operation);
    setForm(next);
    setBaseline(snapshot(next));
    setShowErrors(false);
  }, [operation, model]);

  const locked = saving || actionBusy; // no edits while a backend call is in flight
  const dirty = !readOnly && snapshot(form) !== baseline;
  const { blocker, release } = useUnsavedChangesGuard(dirty);
  const errors = showErrors ? model.validate(form) : {};

  const submit = async (e) => {
    e.preventDefault();
    if (submitting.current || readOnly || actionBusy) return;
    setShowErrors(true);
    if (Object.keys(model.validate(form)).length > 0) return;

    submitting.current = true;
    setSaving(true);
    setSaveError(null);
    try {
      const payload = model.toPayload(form, operation);
      if (isNew) {
        const created = await config.api.create(payload);
        if (created?.id === undefined || created?.id === null) {
          setSaveError(`The ${noun} was submitted but the server response did not include its ID. Check the ${config.plural.toLowerCase()} list before trying again.`);
          return;
        }
        release();
        navigate(`${config.path}/${encodeURIComponent(created.id)}`, { replace: true });
      } else {
        const saved = await config.api.update(operation.id, payload);
        if (isOperation(saved, operation.id)) onOperationChange(saved);
        else {
          try {
            await refresh();
          } catch (err) {
            throw new RefreshAfterMutationError(err); // saved, but could not re-read: not a failed save
          }
        }
      }
    } catch (err) {
      setSaveError(describeError(err));
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  };

  const discard = () => {
    setConfirmDiscard(false);
    const next = operation ? model.fromServer(operation) : model.empty();
    setForm(next);
    setBaseline(snapshot(next));
    setShowErrors(false);
    setSaveError(null);
  };

  const statusNote = operation && config.statusNotes?.[operation.status];

  return (
    <form className="form-stack" onSubmit={submit} noValidate>
      <OperationHeader
        title={isNew ? `New ${config.singular}` : config.singular}
        reference={operation?.reference}
        status={operation?.status}
        backTo={config.path}
        backLabel={config.plural}
      >
        {!isNew && (
          // Workflow actions are backend calls. They are disabled while there are unsaved
          // edits, because the form would otherwise be overwritten by the backend response.
          <OperationActions config={config} status={operation.status} handlers={actions} disabled={dirty || saving} onBusyChange={setActionBusy} />
        )}
      </OperationHeader>
      {dirty && !isNew && (
        <p className="form-summary">You have unsaved changes. Save them before moving this {noun} forward.</p>
      )}
      {statusNote && <p className="form-summary">{statusNote}</p>}
      {readOnly && (
        <p className="form-summary">
          This {noun} is {(STATUS_META[operation.status]?.label || operation.status).toLowerCase()}; editing is only available while it is a draft.
        </p>
      )}

      <Fields operation={operation} form={form} errors={errors} readOnly={readOnly || locked} onChange={setForm} />

      <OperationFormSection title="Products" grid={false}>
        <OperationLineTable
          lines={form.lines}
          readOnly={readOnly}
          disabled={locked}
          showErrors={showErrors}
          {...model.lineTable}
          onChange={(lines) => setForm({ ...form, lines })}
        />
        {errors.lines && form.lines.length > 0 && <p className="field__error">{errors.lines}</p>}
        <p className="form-summary">{form.lines.length} {form.lines.length === 1 ? 'line' : 'lines'}</p>
      </OperationFormSection>

      <OperationFormFooter error={saveError} note={dirty ? 'Unsaved changes' : null}>
        <Link to={config.path} className="btn btn--secondary">{readOnly ? 'Back' : 'Close'}</Link>
        {!readOnly && (
          <>
            {dirty && (
              <button type="button" className="btn btn--secondary" disabled={locked} onClick={() => setConfirmDiscard(true)}>
                Discard changes
              </button>
            )}
            <button type="submit" className="btn btn--primary" disabled={locked || (!isNew && !dirty)}>
              {saving ? 'Saving…' : isNew ? `Create ${noun}` : 'Save changes'}
            </button>
          </>
        )}
      </OperationFormFooter>

      <ConfirmDialog
        open={confirmDiscard}
        title="Discard changes?"
        message="Your unsaved edits will be lost."
        confirmLabel="Discard"
        onConfirm={discard}
        onClose={() => setConfirmDiscard(false)}
      />
      <ConfirmDialog
        open={blocker.state === 'blocked'}
        title="Leave without saving?"
        message={`You have unsaved changes on this ${noun}. If you leave, they will be lost.`}
        confirmLabel="Leave"
        cancelLabel="Stay"
        onConfirm={() => blocker.proceed()}
        onClose={() => blocker.reset()}
      />
    </form>
  );
}
