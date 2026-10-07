import { useEffect, useState } from "react";
import { get } from "./api";
import { useSavedView } from "./savedView";

export interface Loaded<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
}

// Fetch a JSON view; `path === null` skips the request.
export function useApi<T>(path: string | null): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [version, setVersion] = useState(0);
  // A change of the active saved view refetches (get() adds it to the request).
  const view = useSavedView();
  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    setLoading(true);
    get<T>(path)
      .then((value) => !cancelled && (setData(value), setError(null)))
      .catch((reason: Error) => !cancelled && setError(reason))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [path, version, view]);
  return { data, error, loading, reload: () => setVersion((v) => v + 1) };
}
