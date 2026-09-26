import { useCallback, useEffect, useRef } from 'react';
import { useBlocker } from 'react-router-dom';

// Warns before leaving a form with unsaved edits: in-app navigation via useBlocker
// (returns a blocker to render a dialog from) and tab close/refresh via beforeunload.
// Call `release()` right before an intentional navigation (e.g. after a successful create).
export default function useUnsavedChangesGuard(isDirty) {
  const dirtyRef = useRef(isDirty);
  dirtyRef.current = isDirty;

  const blocker = useBlocker(
    useCallback(
      ({ currentLocation, nextLocation }) =>
        dirtyRef.current && currentLocation.pathname !== nextLocation.pathname,
      [],
    ),
  );

  useEffect(() => {
    if (!isDirty) return undefined;
    const onBeforeUnload = (e) => e.preventDefault();
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [isDirty]);

  const release = useCallback(() => {
    dirtyRef.current = false;
  }, []);

  return { blocker, release };
}
