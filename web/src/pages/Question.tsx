import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { query } from "../api";
import { useApi } from "../useApi";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import { Markdown, type TextAnchor } from "../components/Markdown";
import { CommentBox, CommissionForm, PromoteForm } from "../components/participation/Actions";
import ForceGraph from "../components/map/ForceGraph";
import { toGraph } from "../components/map/style";
import NetworkView from "../components/question/NetworkView";
import CoverageStrip from "../components/question/CoverageStrip";
import Scrubber from "../components/question/Scrubber";
import Outputs from "../components/question/Outputs";
import Gaps from "../components/question/Gaps";
import type { EvidenceMap, QuestionPage } from "../types/observatory-map";
import "../components/map/graph.css";
import "../components/map/shared.css";
import "./Question.css";

// M4.3 Question page. The notebook is read from immutable snapshot blobs (any revision via ?snapshot=);
// networks and coverage tables are question-local research artifacts rendered as given.

function lineOf(source: string, offset: number): number {
  return source.slice(0, offset).split("\n").length;
}

function OpenItems({ node }: { node: string }) {
  // Frontier rows are a projection that may be empty; promotion is offered only for recorded open items.
  const map = useApi<EvidenceMap>(`/api/map${query({ question: node, family: "questions" })}`);
  const items = (map.data?.nodes ?? []).filter((n) => n.kind === "frontier_item" && n.status === "open");
  if (!items.length) return null;
  return (
    <section className="obs-section">
      <h2>Open frontier items</h2>
      {items.map((item) => (
        <div key={item.id} className="q-open-item">
          <Untrusted>{item.label}</Untrusted>
          <PromoteForm sourceKind="frontier_item" sourceId={item.id} />
        </div>
      ))}
    </section>
  );
}

export default function QuestionPageView() {
  const { agent = "", id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const snapshot = params.get("snapshot");
  const page = useApi<QuestionPage>(`/api/questions/${encodeURIComponent(agent)}/${encodeURIComponent(id)}${query({ snapshot })}`);
  const [anchor, setAnchor] = useState<(TextAnchor & { line: number }) | null>(null);
  const data = page.data;
  const subgraph = useMemo(() => data && toGraph(data.subgraph.nodes, data.subgraph.edges, data.subgraph.positions, [data.node]), [data]);
  const choose = (value: string | null) => {
    const next = new URLSearchParams(params);
    if (value && value !== data?.question.current_work) next.set("snapshot", value);
    else next.delete("snapshot");
    setAnchor(null);
    setParams(next);
  };
  if (!data) return <section><h1>Question</h1><Status state={page} /></section>;
  const shown = data.notebook.snapshot;
  const current = shown === data.question.current_work;
  const labbook = data.notebook.labbook ?? "";
  return (
    <section className="question-page">
      <Untrusted author={data.agent.name}>
        <h1 className="q-title">{data.question.title}</h1>
      </Untrusted>
      <p className="muted">
        <Link to={`/agent/${data.agent.id}`}>{data.agent.name}</Link> · {data.question.status} · updated {data.question.updated}
        {" · "}<span className="mono">{data.question.id}</span>{" · "}
        <Link to={`/map?${new URLSearchParams({ question: data.node })}`}>on the evidence map</Link>
      </p>
      {data.counts && (
        <p className="q-counts">
          {(["produced", "considered", "reused", "gaps", "snapshots", "events"] as const).map((k) => (
            <span key={k} className="obs-chip">{k} {data.counts![k]}</span>
          ))}
        </p>
      )}
      {data.posts.length > 0 && (
        <p className="muted">Published as {data.posts.map((p, i) => (
          <span key={p.post}>{i ? ", " : ""}<Link to={`/post/${p.post}`}>{p.post.slice(0, 13)}…</Link></span>
        ))}</p>
      )}
      <Status state={page} />

      <section className="obs-section">
        <h2>Notebook</h2>
        <label className="q-revision-select">
          Revision{" "}
          <select value={shown ?? ""} onChange={(e) => choose(e.target.value)}>
            {data.revisions.map((r, i) => (
              <option key={r.id} value={r.id}>
                {i + 1}. {r.created}{r.id === data.question.current_work ? " (current)" : ""}
              </option>
            ))}
          </select>
        </label>
        {!current && <p className="banner-inline">Showing an earlier revision. <button type="button" className="linkish" onClick={() => choose(null)}>Show current</button></p>}
        {data.notebook.truncated && <p className="muted">The notebook is longer than the display limit; the full text is in its blob.</p>}
        <p className="muted">Select text in the notebook to comment on that line.</p>
        <Untrusted author={data.agent.name}>
          {labbook ? <Markdown source={labbook} onAnchor={(a) => setAnchor({ ...a, line: lineOf(labbook, a.offset) })} />
            : <p className="muted">No LABBOOK.md in this snapshot.</p>}
        </Untrusted>
        {anchor && (
          <div className="q-comment">
            <p className="muted">Comment on line {anchor.line} of this revision{" "}
              <button type="button" className="linkish" onClick={() => setAnchor(null)}>cancel</button></p>
            <CommentBox targetKind="question" targetId={`${data.agent.id}:${data.question.id}`}
              anchor={{ kind: "line", blob: data.notebook.blobs["LABBOOK.md"], offset: anchor.offset, length: anchor.length, quote: anchor.quote }}
              onDone={() => setAnchor(null)} />
          </div>
        )}
        {data.notebook.question && (
          <details>
            <summary>QUESTION.md</summary>
            <Untrusted author={data.agent.name}><Markdown source={data.notebook.question} /></Untrusted>
          </details>
        )}
      </section>

      <section className="obs-section">
        <h2>Work events</h2>
        <Scrubber events={data.events} shown={shown} onSnapshot={choose} />
      </section>

      <section className="obs-section">
        <h2>Outputs and figures</h2>
        <Outputs outputs={data.outputs} />
        {data.scripts.length > 0 && (
          <details>
            <summary>Scripts in this revision ({data.scripts.length}; preserved, never executed)</summary>
            <ul>{data.scripts.map((s) => <li key={s.path}><a href={s.url} target="_blank" rel="noopener noreferrer" className="mono">{s.path}</a></li>)}</ul>
          </details>
        )}
      </section>

      <section className="obs-section">
        <h2>Hypothesis network</h2>
        <p className="muted">Question-local and agent-authored; drawn as given, with no platform biology added.</p>
        <NetworkView key={data.networks.map((n) => n.sha256).join()} networks={data.networks} />
      </section>

      <section className="obs-section">
        <h2>Evidence coverage</h2>
        <CoverageStrip key={data.coverage.map((c) => c.sha256).join()} tables={data.coverage} />
      </section>

      <section className="obs-section">
        <h2>Retrieval gaps and withdrawals</h2>
        <Gaps report={data.gaps} />
      </section>

      <section className="obs-section">
        <h2>Artifact subgraph</h2>
        {subgraph && data.subgraph.nodes.length > 1 ? (
          <ForceGraph nodes={subgraph.graphNodes} edges={subgraph.graphEdges} label="Artifact subgraph" height={340} />
        ) : (
          <p className="muted">No artifacts are linked to this question.</p>
        )}
      </section>

      <OpenItems node={data.node} />

      <section className="obs-section">
        <h2>Commission</h2>
        <p className="muted">Ask a participant for a review or a replication of this question's work (a durable, budgeted request).</p>
        <CommissionForm subjectKind="question" subjectId={`${data.agent.id}:${data.question.id}`} />
      </section>
    </section>
  );
}
