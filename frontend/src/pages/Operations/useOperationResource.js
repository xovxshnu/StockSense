import { useCallback, useEffect, useRef, useState } from 'react';

// Loads a resource from the backend. `setData` lets action responses replace it, and
// `refresh` re-reads it without flipping back to the loading state (used after
// mutations so the page does not unmount). Errors are kept as objects so callers can
// distinguish e.g. not-found (`error.isNotFound`).
export default function useOperationResource(loader, deps) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setData(null);
    loaderRef.current(controller.signal)
      .then((result) => !controller.signal.aborted && setData(result))
      .catch((err) => err.name !== 'AbortError' && setError(err))
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  const refresh = useCallback(async () => {
    const fresh = await loaderRef.current();
    setData(fresh);
    return fresh;
  }, []);

  return { data, setData, loading, error, reload, refresh };
}
