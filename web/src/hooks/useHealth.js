import api from '../api.js';
import { useApi } from './useApi.js';

/** Backend connection status derived from the real /health endpoint. */
export function useHealth(version) {
  const { data, loading, error, refetch } = useApi(
    (signal) => api.getHealth(signal),
    [version]
  );

  let status = 'unknown';
  if (loading) status = 'checking';
  else if (error) status = 'offline';
  else if (data?.status === 'ok') status = 'online';

  return { status, refetch };
}

export default useHealth;
