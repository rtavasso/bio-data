import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { setSavedView, useSavedView, viewFromSearch } from "../../savedView";
import type { SavedView } from "../../types/workbench";
import { useApi } from "../../useApi";
import "./workbench.css";

// Copies `?view=<hash>` from the location into the saved-view store (every screen's API reads then carry it).
export function ViewSync() {
  const { search } = useLocation();
  const view = viewFromSearch(search);
  useEffect(() => setSavedView(view), [view]);
  return null;
}

export function describeView(view: SavedView): string {
  const spec = view.spec;
  const parts: string[] = [];
  if (spec.questions.length) parts.push(`${spec.questions.length} question${spec.questions.length > 1 ? "s" : ""}`);
  if (spec.participants.length) {
    const names = spec.participants.map((p) => view.participant_names?.[p] ?? p);
    parts.push(`participants ${names.join(", ")}`);
  }
  if (spec.since || spec.until) parts.push(`from ${spec.since ?? "the start"} to ${spec.until ?? "now"}`);
  return parts.join(" · ");
}

// Shown on every screen while a view is active: what it selects, how to share it, how to leave it.
export function ViewBar() {
  const view = useSavedView();
  const { pathname } = useLocation();
  const loaded = useApi<SavedView>(view ? `/api/views/${view}` : null);
  if (!view) return null;
  return (
    <div className="banner wb-viewbar" role="note" aria-label="Saved view">
      <strong>Saved view</strong>{" "}
      {loaded.data ? describeView(loaded.data) : loaded.error ? <span className="error">unknown view</span> : "…"}{" "}
      <span className="mono muted" title={view}>{view.slice(0, 12)}…</span>{" "}
      <span className="muted">Lists, the map and the inbox show only records whose recorded author, question and time match.</span>{" "}
      <Link to={pathname}>Clear</Link>
    </div>
  );
}
