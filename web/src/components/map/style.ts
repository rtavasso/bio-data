import type { Family, MapEdge, MapNode } from "../../types/observatory-map";
import type { GraphEdge, GraphNode, Shape } from "./ForceGraph";

// Families take the first five categorical slots in fixed order; a graph is an all-pairs form, so every
// family also has its own shape and the legend names it: identity is never colour alone.
export const FAMILY_STYLE: Record<Family, { shape: Shape; label: string }> = {
  posts: { shape: "circle", label: "Posts and claims" },
  artifacts: { shape: "square", label: "Artifacts" },
  questions: { shape: "hexagon", label: "Questions and frontier items" },
  sources: { shape: "diamond", label: "Sources: assets, receipts, objects" },
  participants: { shape: "triangle", label: "Participants and marks" },
};

export function nodeRoute(node: Pick<MapNode, "id" | "kind" | "agent" | "qid">): string | null {
  switch (node.kind) {
    case "post":
      return `/post/${node.id}`;
    case "artifact":
      return `/artifact/${node.id}`;
    case "participant":
      return `/agent/${node.id}`;
    case "question": {
      const [, agent, qid] = node.id.split(":");
      return `/question/${node.agent ?? agent}/${node.qid ?? qid}`;
    }
    default:
      return null;
  }
}

export function toGraph(nodes: MapNode[], edges: MapEdge[], positions: Record<string, [number, number]>, seeds: string[] = []) {
  const seedSet = new Set(seeds);
  const graphNodes: GraphNode[] = nodes.map((n) => ({
    id: n.id,
    x: positions[n.id]?.[0] ?? 0,
    y: positions[n.id]?.[1] ?? 0,
    label: `${n.label}${n.present ? "" : " (missing: named by a record, absent from every store)"}`,
    group: n.family,
    shape: FAMILY_STYLE[n.family]?.shape ?? "circle",
    ring: seedSet.has(n.id),
    missing: !n.present,
  }));
  const labels = new Map(nodes.map((n) => [n.id, n.label]));
  const graphEdges: GraphEdge[] = edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    dashed: e.style === "dashed",
    label: `${labels.get(e.source) ?? e.source} — ${e.relation}${e.backed === false ? " (unbacked)" : e.backed ? " (backed)" : ""} → ${labels.get(e.target) ?? e.target}${e.into_superseded?.length ? `; corrected by ${e.into_superseded.join(", ")}` : ""}`,
  }));
  return { graphNodes, graphEdges };
}

export function describeRecord(record: Record<string, unknown>): string {
  const key = record.seq !== undefined ? `seq ${record.seq}` : String(record.id ?? record.event ?? record.artifact_id ?? "");
  const field = record.field ? `.${record.field}` : record.relationship ? ` (${record.relationship})` : "";
  return `${record.store} · ${record.table}${field} ${key}`.trim();
}
