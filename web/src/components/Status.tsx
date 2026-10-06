import type { Loaded } from "../useApi";

export function Status<T>({ state }: { state: Loaded<T> }) {
  if (state.loading && !state.data) return <p className="muted">Loading…</p>;
  if (state.error) return <p className="error">Could not load: {state.error.message}</p>;
  return null;
}
