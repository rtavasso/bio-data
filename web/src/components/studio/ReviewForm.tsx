import { useState, type FormEvent } from "react";
import { explain } from "../participation/writes";
import { parsePointers } from "../participation/Actions";
import { submitReview } from "./studio";
import type { ReviewVerdict } from "../../types/studio";

// A person's review (M6.2): one row per criterion with a verdict, a note and pointers. It is posted as a reply
// and recorded as marks on the target (supported → checked source, reproduced → reproduced,
// partially/not supported → disputed; not assessable records no mark). Marks are attribution, never status.

const VERDICTS: ReviewVerdict["verdict"][] = ["supported", "partially_supported", "not_supported", "not_assessable", "reproduced"];
const DEFAULT_CRITERIA = ["claims_traceable_to_pointers", "methods_reproducible_from_receipts", "limitations_stated", "scope_matches_evidence"];

interface Row {
  criterion: string;
  verdict: ReviewVerdict["verdict"];
  note: string;
  pointers: string;
}

export function ReviewForm({ targetKind, targetId, onDone }: {
  targetKind: "post" | "claim" | "artifact"; targetId: string; onDone?: () => void;
}) {
  const [rows, setRows] = useState<Row[]>(DEFAULT_CRITERIA.map((criterion) => ({ criterion, verdict: "not_assessable", note: "", pointers: "" })));
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const update = (n: number, patch: Partial<Row>) => setRows(rows.map((row, i) => (i === n ? { ...row, ...patch } : row)));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const made = await submitReview({
        target_kind: targetKind, target_id: targetId, summary,
        verdicts: rows.filter((r) => r.criterion.trim()).map((r) => ({
          criterion: r.criterion.trim(), verdict: r.verdict, note: r.note, pointers: parsePointers(r.pointers),
        })),
      });
      setDone(`Review posted; ${made.marks.length} mark${made.marks.length === 1 ? "" : "s"} recorded.`);
      onDone?.();
    } catch (reason) {
      setError(explain(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="st-review" onSubmit={submit} aria-label="Review form">
      <table>
        <thead><tr><th>Criterion</th><th>Verdict</th><th>Note</th><th>Pointers (kind:id[:locator])</th><th /></tr></thead>
        <tbody>
          {rows.map((row, n) => (
            <tr key={n}>
              <td><input value={row.criterion} onChange={(e) => update(n, { criterion: e.target.value })} aria-label={`Criterion ${n + 1}`} /></td>
              <td>
                <select value={row.verdict} onChange={(e) => update(n, { verdict: e.target.value as Row["verdict"] })} aria-label={`Verdict ${n + 1}`}>
                  {VERDICTS.map((v) => <option key={v} value={v}>{v.replace(/_/g, " ")}</option>)}
                </select>
              </td>
              <td><input value={row.note} onChange={(e) => update(n, { note: e.target.value })} aria-label={`Note ${n + 1}`} /></td>
              <td>
                <input value={row.pointers} onChange={(e) => update(n, { pointers: e.target.value })} aria-label={`Pointers ${n + 1}`}
                  placeholder="artifact:artifact_…" required={row.verdict !== "not_assessable"} />
              </td>
              <td><button type="button" className="linkish" onClick={() => setRows(rows.filter((_, i) => i !== n))} aria-label={`Remove criterion ${n + 1}`}>remove</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="action-form">
        <button type="button" onClick={() => setRows([...rows, { criterion: "", verdict: "supported", note: "", pointers: "" }])}>Add criterion</button>
        <textarea value={summary} onChange={(e) => setSummary(e.target.value)} rows={2} aria-label="Review summary"
          placeholder="Summary (optional, attributed)" />
        <button disabled={busy || !rows.length}>{busy ? "Posting…" : "Post review"}</button>
        <span aria-live="polite">{error ? <span className="error" role="alert">{error}</span> : done ? <span className="muted" role="status">{done}</span> : null}</span>
      </div>
    </form>
  );
}
