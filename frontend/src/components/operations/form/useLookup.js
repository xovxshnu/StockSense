import { useCallback, useEffect, useState } from 'react';

// Loads a read-only option list from a service call.
export default function useLookup(loader) {
  const [state, setState] = useState({ options: [], loading: true, error: null });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    loader({ signal: controller.signal })
      .then((options) => !controller.signal.aborted && setState({ options, loading: false, error: null }))
      .catch((err) => err.name !== 'AbortError' && setState({ options: [], loading: false, error: err }));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}
