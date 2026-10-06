import { useMemo, useState } from "react";
import ForceGraph, { type GraphEdge, type GraphNode } from "../map/ForceGraph";
import { Untrusted } from "../Untrusted";
import type { NetworkRevision, Origin } from "../../types/observatory-map";

// Question-local hypothesis networks, drawn per revision exactly as the agent wrote them. The platform adds
// no biology: node and edge fields are shown as given, and dangling edges are listed, not repaired.

export function originLabel(origin: Origin): string {
  switch (origin.kind) {
    case "snapshot":
      return `notebook snapshot ${origin.path ?? ""}`;
    case "artifact":
      return "registered artifact";
    case "notebook_hash":
      return "hash cited in the notebook (preserved object)";
    default:
      return "working copy (mutable, not a record)";
  }
}

export function Origins({ origins, preserved }: { origins: Origin[]; preserved: boolean }) {
  return (
    <p className="muted q-origins">
      {origins.map((o, i) => (
        <span key={i} className={`obs-chip${o.kind === "working_copy" ? " warn" : ""}`}>{originLabel(o)}</span>
      ))}
      {!preserved && <span className="obs-chip warn">bytes not in the object store</span>}
    </p>
  );
}

const SOLID = new Set(["supported"]);

function layoutCircle(count: number, index: number): [number, number] {
  // Deterministic and readable as drawn: first node at the top, the rest clockwise. No force refinement,
  // so the agent's node order is preserved between revisions.
  const angle = (2 * Math.PI * index) / Math.max(count, 1) - Math.PI / 2;
  const radius = 60 + count * 14;
  return [radius * Math.cos(angle), radius * Math.sin(angle)];
}

export default function NetworkView({ networks }: { networks: NetworkRevision[] }) {
  const [index, setIndex] = useState(networks.length - 1);
  const network = networks[Math.min(index, networks.length - 1)];
  const graph = useMemo(() => {
    if (!network) return null;
    const nodes: GraphNode[] = network.nodes.map((n, i) => {
      const [x, y] = layoutCircle(network.nodes.length, i);
      return { id: String(n.id), x, y, label: `${n.label ?? n.id}${n.kind ? ` (${n.kind})` : ""}`, group: "questions", shape: "circle" };
    });
    const edges: GraphEdge[] = network.edges.filter((e) => !e.dangling).map((e, i) => ({
      id: String(e.id ?? `edge-${i}`), source: String(e.source), target: String(e.target), dashed: !SOLID.has(String(e.status)),
      label: `${e.source} → ${e.target}: ${e.mechanism ?? "mechanism unspecified"} [${e.status ?? "no status"}]`,
    }));
    return { nodes, edges };
  }, [network]);
  if (!network || !graph) return <p className="muted">No hypothesis network was recorded for this question.</p>;
  return (
    <div className="q-network">
      <div className="q-revisions" role="group" aria-label="Network revision">
        {networks.map((n, i) => (
          <button key={n.sha256} type="button" aria-pressed={i === index} onClick={() => setIndex(i)}>
            {n.revision !== null ? `revision ${n.revision}` : n.name}
          </button>
        ))}
      </div>
      <p className="mono muted">{network.name} · {network.sha256.slice(0, 16)}…</p>
      <Origins origins={network.origins} preserved={network.preserved} />
      {network.error && <p className="error">Unreadable: {network.error}</p>}
      {network.issues.map((issue) => <p key={issue} className="muted">Note: {issue}</p>)}
      {graph.nodes.length > 0 && (
        <>
          <ForceGraph nodes={graph.nodes} edges={graph.edges} label={`Hypothesis network ${network.name}`} height={320}
            refineTicks={0} showLabels />
          <p className="muted q-legend">Solid edges: status “supported”. Dashed: hypothesis, contested, rejected or no status.</p>
        </>
      )}
      <Untrusted>
        <div className="table-scroll">
          <table className="obs-table">
            <thead><tr><th>Edge</th><th>From → to</th><th>Mechanism</th><th>Context</th><th>Status</th><th>Evidence</th></tr></thead>
            <tbody>
              {network.edges.map((e, i) => (
                <tr key={String(e.id ?? i)}>
                  <td className="mono">{String(e.id ?? "—")}</td>
                  <td>{String(e.source)} → {String(e.target)}{e.dangling && <span className="obs-chip warn">dangling</span>}</td>
                  <td>{String(e.mechanism ?? "—")}</td>
                  <td>{String(e.context ?? "—")}</td>
                  <td>{String(e.status ?? "—")}</td>
                  <td>{Array.isArray(e.evidence) ? `${e.evidence.length} item(s)` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {network.frontier.length > 0 && (
          <>
            <h4>Frontier</h4>
            <ul>
              {network.frontier.map((f, i) => (
                <li key={i}>{String(f.question ?? "")} <span className="muted">[{String(f.status ?? "")}; {String(f.priority ?? "")}]</span></li>
              ))}
            </ul>
          </>
        )}
        {network.changes.length > 0 && <p className="muted">{network.changes.length} recorded change(s) from the previous revision.</p>}
      </Untrusted>
    </div>
  );
}
