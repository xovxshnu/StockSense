import { RefreshAfterMutationError } from '../../components/operations/errorMessage';

// Builds { todo, validate, cancel } handlers for OperationActions from the operation API.
// Each waits for the backend, then shows what the backend says: the returned operation if
// it looks like one, otherwise a re-read. On failure it re-reads (the status may have
// changed elsewhere) and re-throws so the caller can show the error.
// If the action succeeded but the follow-up re-read fails, that is reported as a refresh failure
// (RefreshAfterMutationError), not as a failed action; the data on screen is left as it was.
// A response is trusted as "the operation" only if it has the same id, a status and its lines.
// Anything thinner (e.g. { ok: true } or a header-only object) triggers a re-read instead,
// so the form never renders a partial record.
const isOperation = (value, id) =>
  Boolean(value) && typeof value === 'object' && Boolean(value.status)
  && String(value.id) === String(id) && Array.isArray(value.lines);

export default function buildOperationActions(config, id, { setData, refresh }) {
  return Object.fromEntries(
    ['todo', 'validate', 'cancel']
      .filter((name) => config.api[name])
      .map((name) => [
        name,
        async () => {
          let result;
          try {
            result = await config.api[name](id);
          } catch (err) {
            await refresh().catch(() => {});
            throw err;
          }
          if (isOperation(result, id)) setData(result);
          else {
            try {
              await refresh();
            } catch (err) {
              if (err.name === 'AbortError') throw err;
              throw new RefreshAfterMutationError(err);
            }
          }
        },
      ]),
  );
}

export { isOperation };
