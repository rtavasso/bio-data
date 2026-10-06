import { Link } from "react-router-dom";
import { query } from "../../api";
import type { MarkRecord, Pointer } from "../../types/participation";
import { useApi } from "../../useApi";
import { routeFor } from "../Markdown";
import "./participation.css";

// Verification marks are attribution: who checked what, with pointers. They never change a status the
// platform computes, so they are shown beside the target, never merged into it.

function PointerLink({ pointer }: { pointer: Pointer }) {
  const route = routeFor(pointer.id);
  const label = `${pointer.kind} ${pointer.id}`;
  return (
    <li>
      {route ? <Link to={route}>{label}</Link> : <span className="mono">{label}</span>}
      {pointer.locator && <span className="muted"> · {pointer.locator}</span>}
    </li>
  );
}

export function MarkList({ marks, empty = "No verification marks yet." }: { marks: MarkRecord[]; empty?: string }) {
  return (
    <section className="pp-marks" aria-label="Verification marks">
      <p className="pp-marks-label">Verification marks · attribution, not status</p>
      {marks.length === 0 ? <p className="muted">{empty}</p> : (
        <ul>
          {marks.map((m) => (
            <li key={m.id} className="pp-mark">
              <span className="pp-mark-head">
                <span className={`pp-mark-kind ${m.kind}`}>{m.kind.replace("_", " ")}</span>
                <Link to={`/agent/${m.participant}`}>{m.participant_name ?? m.participant}</Link>
                {m.participant_kind && <span className="muted">({m.participant_kind})</span>}
                <time className="muted" dateTime={m.created}>{new Date(m.created).toLocaleString()}</time>
              </span>
              <span>{m.note}</span>
              {m.pointers.length > 0 && <ul className="pp-mark-pointers">{m.pointers.map((p, i) => <PointerLink key={i} pointer={p} />)}</ul>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// Marks on one target; pass `marks` when a view already returned them, or `refresh` to refetch after a write.
export function Marks({ targetKind, targetId, marks, refresh = 0 }: {
  targetKind: "post" | "claim" | "artifact"; targetId: string; marks?: MarkRecord[]; refresh?: number;
}) {
  const path = marks ? null : `/api/marks${query({ target_kind: targetKind, target_id: targetId, refresh: refresh || undefined })}`;
  const loaded = useApi<{ items: MarkRecord[] }>(path);
  if (marks) return <MarkList marks={marks} />;
  if (loaded.error) return <p className="error">Could not load marks: {loaded.error.message}</p>;
  if (!loaded.data) return <p className="muted">Loading marks…</p>;
  return <MarkList marks={loaded.data.items} />;
}

export default Marks;
