import { useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { query, type Participant } from "../api";
import { useApi } from "../useApi";
import { Status } from "../components/Status";
import ForceGraph from "../components/map/ForceGraph";
import { MapLegend } from "../components/map/Legend";
import NodeDetail from "../components/map/NodeDetail";
import { describeRecord, toGraph } from "../components/map/style";
import { FAMILIES, type EvidenceMap, type Family, type QuestionEntry } from "../types/observatory-map";
import "../components/map/graph.css";
import "../components/map/shared.css";
import "./Map.css";

// M4.2 Evidence map. Every edge is a recorded relation; the server lays the graph out deterministically
// and caches it per event sequence, and the client refines briefly. Filters live in the URL.

const FILTERS = ["question", "participant", "since", "family", "limit"] as const;

function Filters({ params, setParams }: { params: URLSearchParams; setParams: (p: URLSearchParams) => void }) {
  const questions = useApi<{ items: QuestionEntry[] }>("/api/questions");
  const participants = useApi<{ items: Participant[] }>("/api/participants");
  const [draft, setDraft] = useState(() => Object.fromEntries(FILTERS.map((k) => [k, params.get(k) ?? ""])));
  const families = new Set((draft.family || "").split(",").filter(Boolean));
  const toggle = (family: Family) => {
    const next = new Set(families);
    if (next.has(family)) next.delete(family);
    else next.add(family);
    setDraft({ ...draft, family: FAMILIES.filter((f) => next.has(f)).join(",") });
  };
  const apply = (event: FormEvent) => {
    event.preventDefault();
    const next = new URLSearchParams();
    for (const key of FILTERS) if (draft[key]) next.set(key, draft[key]);
    setParams(next);
  };
  return (
    <form className="map-filters" onSubmit={apply} aria-label="Map filters">
      <label>Question{" "}
        <select value={draft.question} onChange={(e) => setDraft({ ...draft, question: e.target.value })}>
          <option value="">all</option>
          {questions.data?.items.map((q) => (
            <option key={q.node} value={q.node}>{q.agent_name}: {q.title.slice(0, 60)}</option>
          ))}
        </select>
      </label>
      <label>Participant{" "}
        <select value={draft.participant} onChange={(e) => setDraft({ ...draft, participant: e.target.value })}>
          <option value="">all</option>
          {participants.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.kind})</option>)}
        </select>
      </label>
      <label>Since <input type="date" value={draft.since.slice(0, 10)} onChange={(e) => setDraft({ ...draft, since: e.target.value })} /></label>
      <fieldset>
        <legend>Families</legend>
        {FAMILIES.map((family) => (
          <label key={family}><input type="checkbox" checked={families.has(family)} onChange={() => toggle(family)} /> {family}</label>
        ))}
      </fieldset>
      <label>Limit <input type="number" min={1} max={10000} value={draft.limit} placeholder="2000"
        onChange={(e) => setDraft({ ...draft, limit: e.target.value })} style={{ width: "6em" }} /></label>
      <button>Apply</button>
      <button type="button" onClick={() => { setDraft(Object.fromEntries(FILTERS.map((k) => [k, ""]))); setParams(new URLSearchParams()); }}>
        Clear
      </button>
    </form>
  );
}

// C13: posts, artifacts and every other record kind are always drawn; only bare objects and assets are
// dropped (lowest degree first) to honour the limit, and the note says which kinds and how many.
function TruncationNote({ map }: { map: EvidenceMap }) {
  const families = Object.entries(map.truncated_families ?? {});
  if (!families.length) return null;
  return (
    <p className="map-truncation" role="note">
      Truncated to the limit:{" "}
      {families.map(([kind, f], i) => (
        <span key={kind}>{i > 0 && "; "}{f.dropped} of {f.total} {kind === "asset" ? "assets" : "objects"} not drawn</span>
      ))}. Posts and artifacts are never truncated.
    </p>
  );
}

export default function MapPage() {
  const [params, setParams] = useSearchParams();
  const filters = Object.fromEntries(FILTERS.map((k) => [k, params.get(k)]));
  const map = useApi<EvidenceMap>(`/api/map${query(filters)}`);
  const [selected, setSelected] = useState<string | null>(null);
  const data = map.data;
  const graph = useMemo(() => (data ? toGraph(data.nodes, data.edges, data.layout.positions, data.seeds) : null), [data]);
  const byId = useMemo(() => new Map((data?.nodes ?? []).map((n) => [n.id, n])), [data]);
  const familyCounts = useMemo(() => {
    const counts = {} as Record<Family, number>;
    for (const n of data?.nodes ?? []) counts[n.family] = (counts[n.family] ?? 0) + 1;
    return counts;
  }, [data]);
  const node = selected ? byId.get(selected) : undefined;
  return (
    <section className="map-page">
      <h1>Evidence map</h1>
      <p className="muted">
        Only recorded relations are drawn; each edge opens the rows or events it came from. Nothing is inferred.
      </p>
      <Filters key={params.toString()} params={params} setParams={(p) => { setSelected(null); setParams(p); }} />
      <Status state={map} />
      {data && graph && (
        <>
          <p className="muted map-stats">
            {data.nodes.length} nodes, {data.edges.length} edges · event sequence {data.sequence}
            {data.truncated && ` · showing ${data.nodes.length} of ${data.total_nodes} (raise the limit or filter)`}
            {data.cached ? " · cached layout" : ""}
          </p>
          <TruncationNote map={data} />
          <MapLegend counts={familyCounts} />
          <div className="map-body">
            <div className="map-canvas">
              {data.nodes.length ? (
                <ForceGraph nodes={graph.graphNodes} edges={graph.graphEdges} selected={selected} onSelect={setSelected}
                  label="Evidence map" height={560} refineTicks={data.nodes.length > 500 ? 0 : 30} />
              ) : (
                <p className="muted">No records match these filters.</p>
              )}
            </div>
            {node ? (
              <NodeDetail key={node.id} node={node} edges={data.edges} nodes={byId} onSelect={setSelected} />
            ) : (
              <aside className="map-detail muted">Select a node to open its record. Keyboard: Tab to a node, Enter to open.</aside>
            )}
          </div>
          <details className="map-table">
            <summary>Table view ({data.edges.length} edges)</summary>
            <div className="table-scroll">
              <table className="obs-table">
                <thead><tr><th>Source</th><th>Relation</th><th>Target</th><th>Recorded in</th></tr></thead>
                <tbody>
                  {data.edges.map((e) => (
                    <tr key={e.id}>
                      <td><button type="button" className="linkish" onClick={() => setSelected(e.source)}>{byId.get(e.source)?.label}</button></td>
                      <td>{e.relation}{e.backed === false ? " (unbacked)" : ""}</td>
                      <td><button type="button" className="linkish" onClick={() => setSelected(e.target)}>{byId.get(e.target)?.label}</button></td>
                      <td className="mono">{e.records.map(describeRecord).join("; ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
