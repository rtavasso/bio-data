import { Link } from "react-router-dom";
import { useApi } from "../../useApi";
import { Status } from "../Status";
import { Untrusted } from "../Untrusted";
import { Markdown } from "../Markdown";
import { MarkForm, PromoteForm } from "../participation/Actions";
import type { MapEdge, MapNode, NodeRecord } from "../../types/observatory-map";
import { describeRecord, nodeRoute } from "./style";

// The detail pane opens the underlying record of a node and lists the recorded edges that touch it,
// each with the rows or events it came from.

type Dict = Record<string, unknown>;
const text = (value: unknown) => (value === null || value === undefined ? "—" : String(value));

function Fields({ record, keys }: { record: Dict; keys: string[] }) {
  return (
    <dl className="map-fields">
      {keys.filter((k) => record[k] !== undefined && record[k] !== null && record[k] !== "").map((k) => (
        <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd className={k.endsWith("id") || k.endsWith("blob") ? "mono" : undefined}>{text(record[k])}</dd></div>
      ))}
    </dl>
  );
}

function Body({ detail }: { detail: NodeRecord }) {
  const record = (detail.record ?? {}) as Dict;
  const first = (detail.records?.[0] ?? {}) as Dict;
  switch (detail.kind) {
    case "post":
      return (
        <>
          <Fields record={record} keys={["author", "created", "post_kind", "channel", "parent", "supersedes"]} />
          <Untrusted author={text(record.author)}>
            <strong>{text(record.title)}</strong>
            <Markdown source={String(record.excerpt ?? "")} />
          </Untrusted>
        </>
      );
    case "artifact": {
      const manifest = (first.manifest ?? {}) as Dict;
      const artifact = (first.artifact ?? {}) as Dict;
      return (
        <>
          <Untrusted><strong>{text(manifest.title)}</strong><p>{text(manifest.summary)}</p></Untrusted>
          <Fields record={artifact} keys={["output_role", "derivation_key", "output_blob", "created"]} />
          <p className="muted">Held in: {(detail.records ?? []).map((r) => String(r.store)).join(", ")}</p>
        </>
      );
    }
    case "asset": {
      const asset = (first.asset ?? {}) as Dict;
      const receipt = (first.source_receipt ?? {}) as Dict;
      return (
        <>
          <Fields record={{ ...asset, name: (asset.body as Dict | undefined)?.name }} keys={["name", "access", "blob", "created"]} />
          <h4>Source receipt</h4>
          <Fields record={receipt} keys={["id", "outcome", "locator", "retrieved", "blob"]} />
        </>
      );
    }
    case "snapshot":
      return <Fields record={(first.snapshot ?? {}) as Dict} keys={["id", "outcome", "locator", "retrieved", "blob"]} />;
    case "question":
      return (
        <>
          <Untrusted author={text(record.agent_name)}><strong>{text(record.title)}</strong></Untrusted>
          <Fields record={{ ...record, ...((record.counts ?? {}) as Dict) }}
            keys={["status", "updated", "produced", "considered", "reused", "gaps", "snapshots"]} />
        </>
      );
    case "participant":
      return <Fields record={record} keys={["name", "kind", "model", "created", "parent"]} />;
    case "mark":
      return (
        <>
          <Fields record={record} keys={["kind", "participant", "target_kind", "target_id", "created"]} />
          <Untrusted author={text(record.participant)}>{text(record.note)}</Untrusted>
        </>
      );
    default:
      return (
        <Untrusted>
          <pre className="map-json">{JSON.stringify(detail.record ?? detail.records, null, 1)}</pre>
        </Untrusted>
      );
  }
}

export default function NodeDetail({ node, edges, nodes, onSelect }: {
  node: MapNode; edges: MapEdge[]; nodes: Map<string, MapNode>; onSelect: (id: string) => void;
}) {
  const detail = useApi<NodeRecord>(`/api/map/node/${encodeURIComponent(node.id)}`);
  const route = nodeRoute(node);
  const touching = edges.filter((e) => e.source === node.id || e.target === node.id);
  return (
    <aside className="map-detail" aria-label="Node detail">
      <p className="muted map-kind">{node.kind.replace("_", " ")}{node.present ? "" : " · missing from every store"}</p>
      <h3 className="map-detail-title">{node.label}</h3>
      <p className="mono map-id">{node.id}</p>
      {node.kind === "claim" && typeof node.verified_pointers === "number" && (
        <p className="meta" aria-label="Verified pointers">
          {node.verified_pointers} verified number pointer{node.verified_pointers === 1 ? "" : "s"} in recorded write-up verdicts
        </p>
      )}
      {route && <p><Link to={route}>Open {node.kind}</Link></p>}
      <Status state={detail} />
      {detail.data && <Body detail={detail.data} />}
      {detail.data && (
        <details>
          <summary>Underlying record</summary>
          <Untrusted><pre className="map-json">{JSON.stringify(detail.data.record ?? detail.data.records, null, 1)}</pre></Untrusted>
        </details>
      )}
      {(node.kind === "post" || node.kind === "artifact") && node.present && (
        <section>
          <h4>Mark</h4>
          <MarkForm targetKind={node.kind} targetId={node.id} />
        </section>
      )}
      {node.kind === "frontier_item" && (
        <section>
          <h4>Promote</h4>
          <PromoteForm sourceKind="frontier_item" sourceId={node.id} />
        </section>
      )}
      <h4>Recorded edges ({touching.length})</h4>
      <ul className="map-edges">
        {touching.map((e) => {
          const outgoing = e.source === node.id;
          const other = nodes.get(outgoing ? e.target : e.source);
          return (
            <li key={e.id}>
              <span className={`map-rel ${e.style}`}>{outgoing ? `${e.relation} →` : `← ${e.relation}`}</span>{" "}
              <button type="button" className="linkish" onClick={() => other && onSelect(other.id)}>{other?.label ?? "?"}</button>
              {e.backed === false && <span className="map-flag"> unbacked</span>}
              {e.backed === true && <span className="map-flag good"> backed</span>}
              <ul className="map-records">
                {e.records.map((r, i) => <li key={i} className="mono">{describeRecord(r)}</li>)}
              </ul>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
