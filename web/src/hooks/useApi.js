import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Fetch remote data with cancellation, loading/error state and manual refetch.
 * `fetcher` receives an AbortSignal. `deps` controls when a fresh request is made.
 */
export function useApi(fetcher, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const mounted = useRef(true);
  const requestId = useRef(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = useCallback(() => {
    const id = ++requestId.current;
    const controller = new AbortController();
    setState((previous) => ({ ...previous, loading: true, error: null }));

    Promise.resolve()
      .then(() => fetcherRef.current(controller.signal))
      .then((data) => {
        if (mounted.current && id === requestId.current) {
          setState({ data, loading: false, error: null });
        }
      })
      .catch((error) => {
        if (mounted.current && id === requestId.current) {
          setState({ data: null, loading: false, error });
        }
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    mounted.current = true;
    const cancel = load();
    return () => {
      mounted.current = false;
      if (cancel) cancel();
    };
  }, [load]);

  return { ...state, refetch: load };
}

export default useApi;
