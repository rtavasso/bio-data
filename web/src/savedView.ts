// Saved views (spec v2 V4): `?view=<hash>` in the page URL applies a saved view (a question set, a participant
// set, a time window) to every screen. The app shell copies the hash from the location into this store; every
// GET under /api/ then carries `view=<hash>`, which list endpoints and the map apply server-side by recorded
// fields only (endpoints without a list ignore it). Navigation links keep the parameter.
import { useSyncExternalStore } from "react";

const HASH = /^[0-9a-f]{64}$/;
let current: string | null = null;
const listeners = new Set<() => void>();

export function viewFromSearch(search: string): string | null {
  const value = new URLSearchParams(search).get("view");
  return value && HASH.test(value) ? value : null;
}

export function setSavedView(value: string | null) {
  const next = value && HASH.test(value) ? value : null;
  if (next === current) return;
  current = next;
  for (const listener of listeners) listener();
}

export function getSavedView(): string | null {
  return current;
}

export function useSavedView(): string | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
    () => current,
  );
}

// "/api/posts?x=1" + view -> "/api/posts?x=1&view=<hash>"; unchanged without a view or when one is present.
export function withView(path: string, view: string | null = current): string {
  if (!view || !path.startsWith("/api/") || path.startsWith("/api/views/") || /[?&]view=/.test(path)) return path;
  return path + (path.includes("?") ? "&" : "?") + "view=" + view;
}

// An app route that keeps the active view, for navigation links.
export function routeWithView(to: string, view: string | null = current): string {
  if (!view || /[?&]view=/.test(to)) return to;
  const [path, hash] = to.split("#", 2);
  return path + (path.includes("?") ? "&" : "?") + "view=" + view + (hash ? "#" + hash : "");
}
