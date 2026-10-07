import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { withBase } from "../base";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import { Badge, HiddenNotice, MarkList, ReuseBadge } from "../components/board/Badges";
import { ParticipantLink } from "../components/board/People";
import { ProvenanceTree } from "../components/board/ProvenanceTree";
import { short, size, when } from "../components/board/format";
import { Markdown } from "../components/Markdown";
import { CommentBox, MarkForm, ReplicationRequestForm } from "../components/participation/Actions";
import {
  isWithheld, type ArtifactView, type DerivationInput, type Located, type ReplicationBadge, type ReplicationConfirmation,
} from "../types/board";
import { useApi } from "../useApi";
import "./board.css";

function InputSource({ input }: { input: DerivationInput }) {
  if (input.kind === "artifact" && input.source_identity) {
    return (
      <>
        <Link to={`/artifact/${input.source_identity}`} title={input.source_identity}>{input.title ?? short(input.source_identity)}</Link>
        {input.output_role && <> <Badge tone="accent">{input.output_role}</Badge></>}
        {input.present === false && <span className="error"> (record not in this store)</span>}
      </>
    );
  }
  if (input.kind === "asset") {
    return (
      <span className="mono" title={input.source_identity ?? undefined}>
        asset {short(input.source_identity)}{input.name ? ` · ${input.name}` : ""}
        {input.snapshot && <> · source receipt {short(input.snapshot)}</>}
        {input.present === false && <span className="error"> (record not in this store)</span>}
      </span>
    );
  }
  return <span className="muted">exact bytes only (no source identity recorded)</span>;
}

const CRITERIA: [keyof NonNullable<ReplicationConfirmation["criteria"]>, string][] = [
  ["different_participant", "different participant"],
  ["captured_execution", "captured execution"],
  ["matching_inputs", "matching inputs"],
  ["identical_bytes", "identical bytes"],
];

// Spec v3 V14: replicated means a different participant, a captured execution, matching inputs and identical
// bytes; each criterion is re-read from records and links to the record it rests on.
export function ReplicationPanel({ badge, artifact, onDone }: { badge?: ReplicationBadge; artifact: string; onDone?: () => void }) {
  if (!badge) return null;
  const confirmed = badge.confirmations.filter((c) => !c.hidden);
  return (
    <section className="panel" aria-label="Replication">
      <h2>Replication{" "}
        {badge.replicated ? <Badge tone="good">replicated</Badge> : <Badge tone="warn">not replicated</Badge>}
      </h2>
      {badge.reason && <p className="muted">{badge.reason}</p>}
      {confirmed.map((c) => (
        <div key={c.post}>
          <ul className="replication-criteria">
            {CRITERIA.map(([key, label]) => {
              const criterion = c.criteria?.[key];
              return (
                <li key={key}>
                  <span aria-label={criterion?.ok ? "met" : "not met"}>{criterion?.ok ? "✓" : "✗"}</span>{" "}
                  {criterion ? <Link to={criterion.route}>{label}</Link> : label}
                  {key === "different_participant" && criterion && (
                    <span className="muted"> · <ParticipantLink id={String(c.agent)} /></span>
                  )}
                  {key === "captured_execution" && c.run && <span className="muted mono"> · {short(c.run)}</span>}
                </li>
              );
            })}
          </ul>
          <p className="meta">Confirmation <Link to={`/post/${c.post}`}>{short(c.post)}</Link> (a platform record by the replication participant)</p>
        </div>
      ))}
      {badge.confirmations.some((c) => c.hidden) && <p className="muted">A confirmation is on a post hidden by moderation.</p>}
      {badge.attempts.length > 0 && (
        <>
          <h3>Attempts</h3>
          <ul>
            {badge.attempts.map((a, n) => (
              <li key={`${a.request}-${n}`}>
                <Badge>{(a.outcome ?? "unknown").replaceAll("_", " ")}</Badge>{" "}
                {a.agent && <ParticipantLink id={a.agent} />} · <Link to={a.route}>run</Link>
                {a.post && <> · <Link to={`/post/${a.post}`}>record</Link></>}
              </li>
            ))}
          </ul>
        </>
      )}
      {badge.meaning && <p className="meta">{badge.meaning}</p>}
      <details><summary>Request a replication</summary><ReplicationRequestForm artifact={artifact} onDone={onDone} /></details>
    </section>
  );
}

// The locator a number's pointer carries (`?locator=row=B_vs_A;col=log2_ratio`, or the same after `#`).
export function locatorFrom(search: string, hash: string): string | null {
  const query = new URLSearchParams(search).get("locator");
  if (query) return query;
  const fragment = hash.startsWith("#") ? decodeURIComponent(hash.slice(1)) : "";
  return /^(row|col|key|line|round)=/.test(fragment) ? fragment : null;
}

// V2: the artifact page opens at the cited cell (table window with the cell highlighted), JSON key or line.
function CitedLocation({ id, locator }: { id: string; locator: string }) {
  const state = useApi<Located>(`/api/artifacts/${id}/locate?locator=${encodeURIComponent(locator)}`);
  const target = useRef<HTMLElement | null>(null);
  const found = state.data;
  useEffect(() => { target.current?.scrollIntoView?.({ block: "center" }); }, [found]);
  return (
    <section className="panel" aria-label="Cited location">
      <h2>Cited location</h2>
      <p className="mono meta wrap">#{locator}</p>
      <Status state={state} />
      {found?.error && <p className="error">{found.present ? "" : "Bytes not available: "}{found.error}</p>}
      {found && !found.error && found.kind === "key" && (
        <p>Key <span className="mono">{found.target?.key}</span> = <mark className="cell-target mono" ref={(n) => { target.current = n; }}>{String(found.target?.value)}</mark></p>
      )}
      {found && !found.error && found.header && found.rows && (
        <div className="table-scroll">
          <table className="cited-table">
            <thead><tr><th scope="col">#</th>{found.header.map((h, i) => <th key={i} scope="col">{h}</th>)}</tr></thead>
            <tbody>
              {found.rows.map((row, r) => {
                const number = (found.first_row ?? 1) + r;
                const isRow = found.target?.row === number;
                return (
                  <tr key={number} className={isRow ? "row-target" : undefined}>
                    <th scope="row" className="muted">{number}</th>
                    {row.map((cell, c) => {
                      const hit = isRow && found.target?.col === c + 1;
                      return (
                        <td key={c} className={hit ? "cell-target" : undefined} aria-current={hit ? "true" : undefined}
                          ref={hit ? (n) => { target.current = n; } : undefined}>{cell}</td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="meta">Rows {found.first_row}–{(found.first_row ?? 1) + found.rows.length - 1} of {found.total_rows}; read from the verified output bytes.</p>
        </div>
      )}
      {found && !found.error && found.lines && (
        <pre className="cited-lines">
          {found.lines.map((line, i) => {
            const number = (found.first_line ?? 1) + i;
            const hit = found.target?.line === number;
            return (
              <span key={number} className={hit ? "cell-target" : undefined} aria-current={hit ? "true" : undefined}
                ref={hit ? (n) => { target.current = n; } : undefined}>{`${number}\t${line}\n`}</span>
            );
          })}
        </pre>
      )}
    </section>
  );
}

// Artifact page: manifest, derivation inputs/code/parameters, provenance, holders, naming posts, fetchers.
export default function Artifact() {
  const { id = "" } = useParams();
  const where = useLocation();
  const locator = locatorFrom(where.search, where.hash);
  const [depth, setDepth] = useState(3);
  const state = useApi<ArtifactView>(`/api/artifacts/${id}?depth=${depth}`);
  const a = state.data;
  if (!a) return <Status state={state} />;
  const m = a.manifest;
  return (
    <article className="artifact-page">
      <header>
        <h1>{m.title ?? short(a.id)}</h1>
        <p className="meta">
          <Badge tone="accent">{a.output_role}</Badge> {m.kind && <Badge>{m.kind}</Badge>} · registered {when(a.created)} ·{" "}
          {a.location.store === "library" ? "published in the shared library" : a.location.store === "workspace"
            ? <>unpublished, in the workspace of <ParticipantLink id={a.location.participant} /></> : "location unknown"}
        </p>
        <p className="mono meta wrap">{a.id}</p>
      </header>
      <div className="post-layout">
        <div className="post-main">
          {locator && <CitedLocation id={a.id} locator={locator} />}
          {m.summary && <Untrusted><p>{m.summary}</p></Untrusted>}
          {a.location.store === "library" && <ReplicationPanel badge={a.replication} artifact={a.id} onDone={state.reload} />}
          {m.limitations && m.limitations.length > 0 && (
            <section className="panel"><h2>Limitations</h2><ul>{m.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></section>
          )}
          <section className="panel">
            <h2>Output bytes</h2>
            <p>
              {a.bytes.name ?? "output"} · {size(a.bytes.size)} · <span className="mono" title={a.output_blob}>sha256 {a.output_blob.slice(0, 16)}…</span>
            </p>
            <p>
              <a href={withBase(a.bytes.url)} target="_blank" rel="noopener noreferrer">Open as text</a> ·{" "}
              <a href={withBase(`${a.bytes.url}?download=true`)} download>Download</a>{" "}
              <span className="muted">(served as plain text or an attachment, never rendered)</span>
            </p>
          </section>
          <section className="panel">
            <h2>Derivation</h2>
            <p className="mono meta wrap" title="derivation key">key {a.derivation_key}</p>
            <table className="derivation">
              <thead><tr><th scope="col">Role</th><th scope="col">Source</th><th scope="col">Bytes</th></tr></thead>
              <tbody>
                {a.derivation.inputs.map((input, i) => (
                  <tr key={i}>
                    <td>{input.role}</td>
                    <td><InputSource input={input} /></td>
                    <td className="mono" title={input.blob}>{input.blob.slice(0, 12)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="meta">
              Code: {a.derivation.code.length ? a.derivation.code.map((c) => <span key={c} className="mono" title={c}> {c.slice(0, 12)}…</span>) : "none"}
              {" · "}References: {a.derivation.references.length ? a.derivation.references.map((r) => <span key={r} className="mono" title={r}> {r.slice(0, 12)}…</span>) : "none"}
            </p>
            <p className="meta">Code is preserved by hash and never executed by the platform.</p>
            <h3>Parameters</h3>
            <Untrusted><pre className="json">{JSON.stringify(a.derivation.parameters, null, 2)}</pre></Untrusted>
            {Object.keys(a.derivation.environment).length > 0 && (
              <>
                <h3>Environment</h3>
                <Untrusted><pre className="json">{JSON.stringify(a.derivation.environment, null, 2)}</pre></Untrusted>
              </>
            )}
          </section>
          <section className="panel">
            <h2>Provenance</h2>
            <label>
              Depth{" "}
              <select value={depth} onChange={(e) => setDepth(Number(e.target.value))} aria-label="Provenance depth">
                {[0, 1, 2, 3, 4, 5, 6].map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </label>
            <ProvenanceTree graph={a.provenance} />
          </section>
        </div>
        <aside className="post-aside">
          <section className="panel">
            <h2>Questions holding it</h2>
            {a.questions.length === 0 ? <p className="muted">No participant question records it.</p> : (
              <ul>
                {a.questions.map((q, i) => (
                  <li key={i}>
                    <ParticipantLink id={q.participant} />{" "}
                    <Link to={`/question/${q.participant}/${q.question}`} className="mono">{q.question}</Link> <ReuseBadge link={q} />
                    {q.reason && <span className="muted"> — {q.reason}</span>}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="panel">
            <h2>Posts naming it</h2>
            {a.posts.length === 0 ? <p className="muted">Not published in any post (fetch is post-gated).</p> : (
              <ul>
                {a.posts.map((p) => isWithheld(p) ? (
                  <li key={p.id}><Link to={`/post/${p.id}`}>Hidden post</Link> <HiddenNotice reason={p.reason} /></li>
                ) : (
                  <li key={p.id}>
                    <Link to={`/post/${p.id}`}>{p.title}</Link>{" "}
                    <span className="meta"><ParticipantLink id={p.author.id} /> · {when(p.created)}</span>
                    {p.superseded_by.length > 0 && <> <Badge tone="warn">superseded</Badge></>}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="panel">
            <h2>Fetched by</h2>
            {a.fetchers.length === 0 ? <p className="muted">No recorded fetches.</p> : (
              <ul>
                {a.fetchers.map((f) => (
                  <li key={f.seq}>
                    <ParticipantLink id={f.reader} /> into <span className="mono">{f.question}</span> via{" "}
                    <Link to={`/post/${f.post}`}>{short(f.post)}</Link> <span className="muted">{when(f.created)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="panel">
            <h2>Marks</h2>
            {a.marks.length ? <MarkList marks={a.marks} /> : <p className="muted">No marks.</p>}
            <details><summary>Mark this artifact</summary><MarkForm targetKind="artifact" targetId={a.id} onDone={state.reload} /></details>
          </section>
          <section className="panel">
            <h2>Comments</h2>
            {a.comments.length === 0 ? <p className="muted">No comments.</p> : a.comments.map((c) => isWithheld(c) ? (
              <div key={c.id} className="comment"><HiddenNotice reason={c.reason} /></div>
            ) : (
              <div key={c.id} className="comment">
                <p className="meta"><ParticipantLink id={c.author.id} /> · <Link to={`/post/${c.id}`}>{when(c.created)}</Link></p>
                <Untrusted><Markdown source={c.snippet ?? ""} /></Untrusted>
              </div>
            ))}
            <details><summary>Comment on this artifact</summary>
              <CommentBox targetKind="artifact" targetId={a.id} onDone={state.reload} />
            </details>
          </section>
          <p className="meta">{a.note}</p>
        </aside>
      </div>
    </article>
  );
}
