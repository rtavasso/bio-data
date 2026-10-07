import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Untrusted } from "../components/Untrusted";
import { CommissionForm } from "../components/participation/Actions";
import ForceGraph from "../components/map/ForceGraph";
import { MapLegend } from "../components/map/Legend";
import { nodeRoute, toGraph } from "../components/map/style";
import { PointerDetail, WriteupBlocks } from "../components/studio/Blocks";
import { Refusal } from "../components/studio/Refusal";
import { ReviewForm } from "../components/studio/ReviewForm";
import { loadWriteup } from "../components/studio/studio";
import type { Regeneration, Writeup } from "../types/studio";
import "../components/map/graph.css";
import "../components/map/shared.css";
import "../components/studio/studio.css";

// /studio/:post — a rendered write-up (M6.1, spec v2 C5/V2). The checker's verdict is recorded at delivery: a
// refused write-up (an unpointed number, an unresolved pointer, a claimless post citation) is withheld and shown as
// a placeholder with every location; a rendered one marks each number verified or unverified against its record;
// one that cites a withdrawn claim is served only with its regeneration flag (a band with the replacements and a
// prefilled commission).

function RegenerationBand({ flag }: { flag: Regeneration }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="st-regenerate" role="alert" aria-label="Regeneration required">
      <h2>Regeneration required</h2>
      <p>{flag.note}</p>
      <ul>
        {flag.claims.map((c) => (
          <li key={c.claim}>
            <span className="mono">{c.claim}</span>: <Untrusted>{c.text}</Untrusted>
            withdrawn by{" "}
            {c.withdrawn_by ? <Link to={`/post/${c.withdrawn_by}`}>{c.replacement_title ?? c.withdrawn_by}</Link> : "its author"}.
            {c.replacement_claims.length > 0 && (
              <ul className="st-replacements">
                {c.replacement_claims.map((r) => (
                  <li key={r.id}>
                    {r.id === c.same_ordinal ? <strong>same position: </strong> : null}
                    <span className="mono">{r.id}</span> ({r.status}) <Untrusted>{r.text}</Untrusted>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
        {(flag.posts ?? []).map((p) => (
          <li key={p.post}>
            Cites superseded post <Link to={`/post/${p.post}`} className="mono">{p.post}</Link>; current version{" "}
            <Link to={`/post/${p.superseded_by}`} className="mono">{p.superseded_by}</Link>.
          </li>
        ))}
        {(flag.artifacts ?? []).map((a) => (
          <li key={a.artifact}>
            Cites <Link to={`/artifact/${a.artifact}`} className="mono">{a.artifact}</Link>, from superseded{" "}
            {a.superseded_posts.map((p, i) => <span key={p}>{i > 0 && ", "}<Link to={`/post/${p}`} className="mono">{p}</Link></span>)}
            {(a.relisted_by ?? []).length > 0 && (
              <>; re-listed by{" "}
                {(a.relisted_by ?? []).map((p, i) => <span key={p}>{i > 0 && ", "}<Link to={`/post/${p}`} className="mono" aria-label={`re-listed by ${p}`}>{p}</Link></span>)}
                , which does not clear the flag</>
            )}.
          </li>
        ))}
      </ul>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}>Commission a regeneration</button>
      {open && (
        <CommissionForm subjectKind={flag.commission.subject_kind} subjectId={flag.commission.subject_id}
          defaultTaskType={flag.commission.task_type} defaultNote={flag.commission.note} />
      )}
    </section>
  );
}

export default function WriteupPage() {
  const { post = "" } = useParams();
  const [data, setData] = useState<Writeup | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [mapSelected, setMapSelected] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    loadWriteup(post).then((value) => !cancelled && setData(value)).catch((reason: Error) => !cancelled && setError(reason));
    return () => { cancelled = true; };
  }, [post]);
  const graph = useMemo(() => {
    const map = data?.evidence_map;
    return map ? toGraph(map.nodes, map.edges, map.positions, map.seeds) : null;
  }, [data]);
  if (error) return <p className="error">Could not load: {error.message}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  const author = data.post.author ? data.post.author.name ?? data.post.author.id : undefined;
  const selectedNode = data.evidence_map?.nodes.find((n) => n.id === mapSelected);
  return (
    <article className="st-page">
      <p className="muted"><Link to="/studio">Studio</Link> · write-up <span className="mono">{data.post.id}</span></p>
      <h1>{data.post.hidden ? "Hidden post" : data.post.title ?? data.post.id}</h1>
      <p className="muted">
        {data.post.author ? <>{data.post.kind} by <Link to={`/agent/${data.post.author.id}`}>{author}</Link>{" "}
          ({data.post.author.kind}) · {data.post.created}</> : <>Hidden by moderation: {data.post.reason}</>}
        {data.request && <> · answers {data.request.task_type} request <span className="mono">{data.request.id}</span></>}
        {" · "}<Link to={`/post/${data.post.id}`}>post page</Link>
      </p>
      {data.regeneration_required && <RegenerationBand flag={data.regeneration_required} />}
      {data.status === "refused" ? (
        <Refusal problems={data.problems ?? []} source={data.source} placeholder={data.placeholder} />
      ) : (
        <>
          <p className="muted st-stats">
            {data.stats?.numbers} number{data.stats?.numbers === 1 ? "" : "s"}, all pointed
            {data.stats?.verified !== undefined && <> · <span className="num-verified">{data.stats.verified} verified</span> against
              their records · <span className="num-unverified">{data.stats.unverified} unverified</span></>}
            {" "}· {data.stats?.pointers} pointer{data.stats?.pointers === 1 ? "" : "s"} resolved · rules {data.rules}
            {data.verdict && <> · verdict {data.verdict.source}{data.verdict.created ? ` ${data.verdict.created}` : ""}</>}
          </p>
          <div className="st-layout">
            <Untrusted author={author}>
              <WriteupBlocks blocks={data.blocks ?? []} pointers={data.pointers ?? {}} onOpen={setActive} active={active} />
            </Untrusted>
            {active && <PointerDetail id={active} entry={data.pointers?.[active]} onClose={() => setActive(null)} />}
          </div>
          {graph && data.evidence_map && (
            <section className="obs-section">
              <h2>Evidence map of the cited records</h2>
              <p className="muted">{data.evidence_map.note}</p>
              <MapLegend />
              <ForceGraph nodes={graph.graphNodes} edges={graph.graphEdges} label="Evidence map of the cited records"
                height={360} selected={mapSelected} onSelect={setMapSelected} showLabels />
              {selectedNode && (
                <p>
                  {selectedNode.kind} {selectedNode.label}{" "}
                  {nodeRoute(selectedNode) && <Link to={nodeRoute(selectedNode)!}>open</Link>}
                </p>
              )}
            </section>
          )}
        </>
      )}
      <section className="obs-section">
        <h2>Review this write-up</h2>
        <ReviewForm targetKind="post" targetId={data.post.id} />
      </section>
    </article>
  );
}
