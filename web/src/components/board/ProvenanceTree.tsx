import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { ProvenanceGraph } from "../../types/board";
import { short } from "./format";

function label(id: string, graph: ProvenanceGraph) {
  const node = graph.nodes[id];
  if (!node) return <span className="mono muted" title={`${id} (beyond depth)`}>{short(id, 16)}</span>;
  if (node.kind === "artifact") {
    const manifest = node.manifest as { title?: string } | undefined;
    return <Link to={`/artifact/${id}`} title={id}>{manifest?.title ?? short(id)}</Link>;
  }
  if (node.kind === "asset") return <span className="mono" title={id}>asset {short(id)}</span>;
  if (node.kind === "object") return <span className="mono" title={id}>bytes {id.slice(0, 12)}… ({String(node.bytes)} B)</span>;
  return <span className="mono" title={id}>{node.kind} {short(id)}</span>;
}

// Recorded derivation edges only (daw.artifacts.provenance); a node already shown is not expanded twice.
export function ProvenanceTree({ graph }: { graph: ProvenanceGraph }) {
  const out = new Map<string, { object: string; relationship: string }[]>();
  for (const edge of graph.edges) {
    if (!out.has(edge.subject)) out.set(edge.subject, []);
    out.get(edge.subject)!.push(edge);
  }
  const seen = new Set<string>();
  const render = (id: string, relationship: string | null, position = 0): ReactNode => {
    const repeat = seen.has(id);
    seen.add(id);
    const children = repeat ? [] : out.get(id) ?? [];
    return (
      <li key={`${position}:${relationship}:${id}`}>
        {relationship && <span className="relationship">{relationship}</span>} {label(id, graph)}
        {repeat && <span className="muted"> (shown above)</span>}
        {children.length > 0 && <ul>{children.map((edge, i) => render(edge.object, edge.relationship, i))}</ul>}
      </li>
    );
  };
  return (
    <div className="provenance">
      <ul className="tree">{render(graph.root, null)}</ul>
      {graph.frontier.length > 0 && (
        <p className="meta">{graph.frontier.length} record{graph.frontier.length > 1 ? "s" : ""} beyond depth {graph.depth}.</p>
      )}
    </div>
  );
}
