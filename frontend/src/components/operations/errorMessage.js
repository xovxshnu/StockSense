// Thrown when a mutation SUCCEEDED (the backend answered 2xx) but re-reading the record afterwards
// failed. It is deliberately not an ApiError from the mutation: the action is not reported as failed,
// and no new status is invented.
export class RefreshAfterMutationError extends Error {
  constructor(cause) {
    super('Refresh failed after a successful change.');
    this.name = 'RefreshAfterMutationError';
    this.cause = cause;
  }
}

// Turns an error into user-facing text, keeping the backend's own message when it sent one.
export function describeError(err) {
  if (!err) return '';
  if (err instanceof RefreshAfterMutationError) {
    const why = err.cause?.message ? ` (${err.cause.message})` : '';
    return `The backend accepted your change, but reloading the latest data failed${why}. What is shown may be out of date. Reload the page to confirm the current status.`;
  }
  const backend = err.details ? err.message : ''; // details is set only when the backend returned a body
  if (err.isUnauthorized) return `You are not signed in, or your session has expired.${backend ? ` (${backend})` : ''}`;
  if (err.isForbidden) return `You do not have permission to do this.${backend ? ` (${backend})` : ''}`;
  return err.message || 'Something went wrong.';
}
