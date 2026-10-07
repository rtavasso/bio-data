import { Link } from "react-router-dom";
import type { Group } from "../../types/dashboard";
import type { SnapshotCitations } from "../../types/publishing";
import { useApi } from "../../useApi";
import { Status } from "../Status";
import { Value } from "./Charts";

// Spec v2 V8: compaction hygiene as a tracked metric per harness. null is unavailable (the harness keeps no
// session database, or the stream reports no per-call context), never zero.
export function HygieneTable({ groups }: { groups: Group[] }) {
  return (
    <div className="compare-scroll">
      <table className="coverage-table" aria-label="Compaction hygiene">
        <thead>
          <tr>
            <th scope="col">Group</th><th scope="col">Runs (with session database)</th><th scope="col">Compactions</th>
            <th scope="col">Summaries (fallbacks)</th><th scope="col">Summaries missing the assignment</th>
            <th scope="col">Context per call, mean / max tokens</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => {
            const h = g.compaction_hygiene;
            return (
              <tr key={g.key}>
                <th scope="row">{g.label}</th>
                <td>{g.runs} ({h ? h.runs_with_session_database : 0})</td>
                <td><Value value={g.compactions} /></td>
                <td><Value value={h?.compaction_summaries ?? null} /> (<Value value={h?.compaction_fallbacks ?? null} />)</td>
                <td><Value value={h?.summaries_missing_assignment ?? null} /></td>
                <td>
                  <Value value={h?.context_mean_input_tokens ?? null} /> / <Value value={h?.context_max_input_tokens ?? null} />
                  {h?.context_unit && <span className="muted small"> per {h.context_unit} · {h.context_runs} runs</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// Spec v2 V7: which imported snapshots this board's questions cite (recorded citations: post text naming
// snapshot:<id>/<record>), never inferred.
export function SnapshotCitationsPanel() {
  const state = useApi<{ snapshots: SnapshotCitations[]; note: string }>("/api/snapshot-citations");
  const data = state.data;
  const snapshots = data?.snapshots ?? [];
  return (
    <section aria-labelledby="citations-title">
      <h2 id="citations-title">Snapshots cited by questions</h2>
      <Status state={state} />
      {data && (
        <>
          <p className="muted small">{data.note}</p>
          {snapshots.length === 0 ? <p className="muted">No post cites another snapshot.</p> : (
            <div className="compare-scroll">
              <table className="coverage-table" aria-label="Snapshot citations">
                <thead><tr><th scope="col">Snapshot</th><th scope="col">Here</th><th scope="col">Cited by</th><th scope="col">Records</th></tr></thead>
                <tbody>
                  {snapshots.map((s) => s.questions.map((q, i) => (
                    <tr key={s.snapshot + (q.question ?? q.thread)}>
                      {i === 0 && (
                        <th scope="row" rowSpan={s.questions.length}>
                          <Link to={`/directory/${s.snapshot}`} className="mono">{s.snapshot.slice(0, 12)}…</Link>
                        </th>
                      )}
                      {i === 0 && (
                        <td rowSpan={s.questions.length}>
                          {s.imported ? "imported" : <span className="error">not imported</span>}
                          {s.indexed && <span className="muted small"> · {s.indexed.claims} claims, {s.indexed.artifacts} artifacts</span>}
                        </td>
                      )}
                      <td>
                        {q.question ? <>question <span className="mono">{q.question}</span></> : <>thread <Link to={`/post/${q.thread}`} className="mono">{q.thread?.slice(0, 14)}…</Link></>}
                        <div className="muted small">{q.posts.length} post{q.posts.length === 1 ? "" : "s"}</div>
                      </td>
                      <td>
                        {q.records.length}
                        {s.citations.some((c) => q.posts.includes(c.post) && !c.resolves) && <span className="error small"> (some do not resolve here)</span>}
                      </td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
