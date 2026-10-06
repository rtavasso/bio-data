import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import { Badge, MarkList, ReuseBadge } from "../components/board/Badges";
import { ParticipantLink } from "../components/board/People";
import { ProvenanceTree } from "../components/board/ProvenanceTree";
import { short, size, when } from "../components/board/format";
import { Markdown } from "../components/Markdown";
import { CommentBox, MarkForm } from "../components/participation/Actions";
import type { ArtifactView, DerivationInput } from "../types/board";
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

// Artifact page: manifest, derivation inputs/code/parameters, provenance, holders, naming posts, fetchers.
export default function Artifact() {
  const { id = "" } = useParams();
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
          {m.summary && <Untrusted><p>{m.summary}</p></Untrusted>}
          {m.limitations && m.limitations.length > 0 && (
            <section className="panel"><h2>Limitations</h2><ul>{m.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></section>
          )}
          <section className="panel">
            <h2>Output bytes</h2>
            <p>
              {a.bytes.name ?? "output"} · {size(a.bytes.size)} · <span className="mono" title={a.output_blob}>sha256 {a.output_blob.slice(0, 16)}…</span>
            </p>
            <p>
              <a href={a.bytes.url} target="_blank" rel="noopener noreferrer">Open as text</a> ·{" "}
              <a href={`${a.bytes.url}?download=true`} download>Download</a>{" "}
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
                {a.posts.map((p) => (
                  <li key={p.id}>
                    <Link to={`/post/${p.id}`}>{p.hidden ? "Hidden post" : p.title}</Link>{" "}
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
            {a.comments.length === 0 ? <p className="muted">No comments.</p> : a.comments.map((c) => (
              <div key={c.id} className="comment">
                <p className="meta"><ParticipantLink id={c.author.id} /> · <Link to={`/post/${c.id}`}>{when(c.created)}</Link></p>
                {c.hidden ? <p className="hidden-notice">Hidden by moderation: {c.hidden.reason}</p> : (
                  <Untrusted><Markdown source={c.snippet ?? ""} /></Untrusted>
                )}
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
