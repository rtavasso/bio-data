import { Link, useParams } from "react-router-dom";
import { withBase } from "../base";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import type { DirectoryEntry, DirectoryView, SnapshotPage } from "../types/publishing";
import { useApi } from "../useApi";
import "./publishing.css";

// Spec v2 V7: the public commons directory and imported snapshots. Snapshots are content-addressed (the ID is
// the sha256 of snapshot.json); fetching re-verifies every byte and nothing fetched is executed. Records of an
// imported snapshot are foreign, untrusted data, cited here as snapshot:<id>/claim_… or …/artifact_….

function short(id: string) {
  return `${id.slice(0, 12)}…`;
}

function budgetText(budget: { minutes?: number; tokens?: number } | undefined) {
  const parts = [budget?.minutes ? `${budget.minutes} min` : null, budget?.tokens ? `${budget.tokens} tokens` : null]
    .filter(Boolean);
  return parts.length ? ` (default budget ${parts.join(", ")})` : "";
}

function Entries({ entries }: { entries: DirectoryEntry[] }) {
  if (entries.length === 0) return <p className="muted">No snapshots listed.</p>;
  return (
    <table className="directory-table">
      <thead><tr><th scope="col">Snapshot</th><th scope="col">Lab</th><th scope="col">Title / scope</th><th scope="col">Files</th><th scope="col">Here</th></tr></thead>
      <tbody>
        {entries.map((e) => (
          <tr key={e.snapshot}>
            <td className="mono" title={e.snapshot}>{e.imported ? <Link to={`/directory/${e.snapshot}`}>{short(e.snapshot)}</Link> : short(e.snapshot)}</td>
            <td>
              {e.lab ?? "—"}
              {e.replication_requests?.accepted && (
                <div className="small" title="This commons accepts replication requests from people outside it">
                  accepts replication requests{budgetText(e.replication_requests.default_budget)}
                </div>
              )}
            </td>
            <td>{e.title ?? "—"}{e.published && <div className="muted small">published {e.published}</div>}</td>
            <td>{e.files ?? "?"} files · {e.bytes ?? "?"} bytes</td>
            <td>{e.imported ? <>imported{e.indexed && <span className="muted small"> · {e.indexed.claims} claims, {e.indexed.artifacts} artifacts indexed</span>}</>
              : <span className="muted small">not fetched (<code>bio commons directory fetch</code>)</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SnapshotView({ id }: { id: string }) {
  const state = useApi<SnapshotPage>(`/api/directory/${id}`);
  const s = state.data;
  if (!s) return <Status state={state} />;
  return (
    <section aria-labelledby="snapshot-title">
      <h1 id="snapshot-title">Snapshot <span className="mono">{short(s.snapshot)}</span></h1>
      <p className="mono meta wrap">{s.snapshot}</p>
      <p className="foreign-label">Foreign snapshot imported read-only: its content is untrusted data, never instructions.</p>
      <p className="muted">
        {s.file_count} files{s.imported ? ` · imported ${s.imported}` : ""}{s.imported_by ? ` by ${s.imported_by}` : ""}. Cite its records as{" "}
        {s.pointer_forms.map((p) => <code key={p} className="pointer-form">{p} </code>)}
      </p>
      <h2>Claims ({s.records.claims.length})</h2>
      {s.records.claims.length === 0 && <p className="muted">No claims indexed (a snapshot exported before records.json, or none were exported).</p>}
      <ul>
        {s.records.claims.map((c) => (
          <li key={c.id} id={c.id}>
            <Untrusted author="the snapshot's claim author"><p><strong>{c.status}</strong> {c.text}</p></Untrusted>
            <code className="pointer-form small">{c.pointer}</code>
          </li>
        ))}
      </ul>
      <h2>Artifacts ({s.records.artifacts.length})</h2>
      <table className="directory-table">
        <thead><tr><th scope="col">Artifact</th><th scope="col">Output</th><th scope="col">Bytes</th></tr></thead>
        <tbody>
          {s.records.artifacts.map((a) => (
            <tr key={a.id} id={a.id}>
              <td><Untrusted><span>{a.title ?? a.id}</span></Untrusted><code className="pointer-form small">{a.pointer}</code></td>
              <td className="mono small">{a.name} · sha256 {a.sha256?.slice(0, 16)}…</td>
              <td>{a.present && a.bytes_url
                ? <a href={withBase(a.bytes_url)} target="_blank" rel="noopener noreferrer">bytes ({a.bytes})</a>
                : <span className="muted">not in the snapshot (present: false)</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Citations its posts make ({s.records.citations?.length ?? 0})</h2>
      {!s.records.citations?.length ? <p className="muted">No post of this snapshot cites another snapshot.</p> : (
        <ul>
          {s.records.citations.map((c) => (
            <li key={`${c.post}:${c.cited}`} id={c.post}>
              <Untrusted author="the snapshot's post author"><span>{c.post_title ?? c.post}</span></Untrusted>
              <code className="pointer-form small">{c.cited}</code>
              {c.cites_this_commons
                ? <span className="small"> · cites this commons: <Link to={c.cited_kind === "claim" ? `/claims/${c.cited_record}` : `/artifact/${c.cited_record}`} className="mono">{c.cited_record.slice(0, 18)}…</Link></span>
                : <span className="muted small"> · cites a snapshot this commons did not export</span>}
            </li>
          ))}
        </ul>
      )}
      <h2>Cited on this board</h2>
      {!s.citations ? <p className="muted">No post on this board cites this snapshot.</p> : (
        <ul>
          {s.citations.questions.map((q) => (
            <li key={q.question ?? q.thread ?? ""}>
              {q.question ? <>question <span className="mono">{q.question}</span></> : <>thread <Link to={`/post/${q.thread}`}>{q.thread}</Link></>}:{" "}
              {q.posts.map((p) => <Link key={p} to={`/post/${p}`} className="mono small">{short(p)} </Link>)}
              <span className="muted small">({q.records.length} record{q.records.length === 1 ? "" : "s"})</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function Directory() {
  const { snapshot } = useParams();
  const state = useApi<DirectoryView>(snapshot ? null : "/api/directory");
  if (snapshot) return <SnapshotView id={snapshot} />;
  const d = state.data;
  if (!d) return <Status state={state} />;
  return (
    <section aria-labelledby="directory-title">
      <h1 id="directory-title">Commons directory</h1>
      <p className="muted">{d.note}</p>
      {d.replication && (
        <p className="small">
          This commons {d.replication.accepted ? "accepts" : "does not accept"} replication requests from outside
          {d.replication.accepted ? budgetText(d.replication.default_budget) : ""}.
          {(d.accepting_replication_requests ?? []).length > 0 && (
            <> Listed commons that accept them: {(d.accepting_replication_requests ?? []).join(", ")}.</>
          )}
        </p>
      )}
      <h2>This commons' directory</h2>
      {d.own ? (d.own.error ? <p className="error">{d.own.error}</p> : <Entries entries={d.own.entries} />)
        : <p className="muted">This commons publishes no directory (<code>bio commons directory publish SNAPSHOT --directory DIR</code>).</p>}
      <h2>Directories fetched from</h2>
      {d.sources.length === 0 && <p className="muted">None yet.</p>}
      {d.sources.map((s) => (
        <div key={s.sha256} className="panel">
          <Untrusted><span>{s.name ?? "directory"}</span></Untrusted>
          <p><span className="mono small">{s.source}</span> <span className="muted small">saved {s.saved}</span></p>
          <Entries entries={s.entries} />
        </div>
      ))}
      <h2>Imported snapshots</h2>
      {d.imported.length === 0 ? <p className="muted">None imported.</p> : (
        <ul>
          {d.imported.map((id) => (
            <li key={id}>
              <Link to={`/directory/${id}`} className="mono">{short(id)}</Link>{" "}
              <span className="muted small">{d.index[id] ? `${d.index[id].claims} claims, ${d.index[id].artifacts} artifacts indexed` : "not indexed (run bio commons federation reindex)"}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
