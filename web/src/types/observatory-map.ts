// Response shapes of the observatory read API (M4.2–M4.4): /api/map, /api/questions, /api/runs.

export type Family = "posts" | "artifacts" | "sources" | "questions" | "participants";
export const FAMILIES: Family[] = ["posts", "artifacts", "sources", "questions", "participants"];

export interface EdgeRecord {
  store: string;
  table: string;
  [field: string]: unknown;
}

export interface MapNode {
  id: string;
  kind: "post" | "claim" | "artifact" | "asset" | "snapshot" | "object" | "question" | "frontier_item" | "participant" | "mark";
  family: Family;
  label: string;
  present: boolean;
  stores: string[];
  created?: string;
  title?: string;
  agent?: string;
  qid?: string;
  output_role?: string;
  post_kind?: string;
  hidden?: boolean;
  status?: string;
  superseded_by?: string[];
  [field: string]: unknown;
}

export interface MapEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  style: "solid" | "dashed";
  created?: string | null;
  records: EdgeRecord[];
  backed?: boolean | null;
  reason?: string | null;
  /** Flow B: the target post was superseded by these posts (from recorded `supersedes` edges). */
  into_superseded?: string[];
}

export interface EvidenceMap {
  sequence: number;
  fingerprint: string;
  key: string;
  seeds: string[];
  nodes: MapNode[];
  edges: MapEdge[];
  total_nodes: number;
  truncated: boolean;
  counts: { nodes: Record<string, number>; edges: Record<string, number> };
  layout: { positions: Record<string, [number, number]>; bounds: [number, number, number, number]; algorithm: string };
  relations: Record<string, { style: string; record: string }>;
  cached: boolean;
  note: string;
}

export interface NodeRecord {
  kind: string;
  id: string;
  record?: Record<string, unknown>;
  records?: Record<string, unknown>[];
  content_is_untrusted_data?: boolean;
}

export interface QuestionCounts {
  events: number;
  snapshots: number;
  produced: number;
  considered: number;
  reused: number;
  gaps: number;
  gap_withdrawals: number;
}

export interface QuestionEntry {
  agent: string;
  agent_name: string;
  qid: string;
  node: string;
  title: string;
  status: string;
  created: string;
  updated: string;
  counts: QuestionCounts;
}

export interface Revision {
  id: string;
  created: string;
  status?: string;
  summary: string;
  files: number;
}

export interface Relationship {
  relationship: "produced" | "considered" | "reused";
  event: string;
  created: string;
  backed?: boolean | null;
  reason?: string | null;
}

export interface Output {
  artifact: string;
  present: boolean;
  title?: string | null;
  summary: string;
  output_role: string;
  output_name: string;
  output_blob?: string | null;
  bytes?: number | null;
  figure: boolean;
  blob_url?: string | null;
  limitations: string[];
  relationships: Relationship[];
}

export interface WorkEvent {
  id: string;
  kind: string;
  created: string;
  summary: Record<string, unknown>;
  state: { snapshot: string | null; produced: number; considered: number; reused: number; gaps_open: number };
}

export interface Origin {
  kind: "snapshot" | "artifact" | "notebook_hash" | "working_copy";
  id?: string;
  path?: string;
  created?: string;
  modified?: string;
  note?: string;
}

export interface NetworkRevision {
  sha256: string;
  name: string;
  origins: Origin[];
  records: Origin[];
  preserved: boolean;
  created: string;
  revision: number | null;
  scope: Record<string, unknown> | null;
  nodes: { id: string | number; label?: string; kind?: string; [k: string]: unknown }[];
  edges: { id?: string; source: string | number; target: string | number; status?: string; mechanism?: string;
    dangling: boolean; [k: string]: unknown }[];
  frontier: Record<string, unknown>[];
  changes: unknown[];
  issues: string[];
  error?: string;
}

export interface CoverageTable {
  sha256: string;
  name: string;
  origins: Origin[];
  records: Origin[];
  preserved: boolean;
  created: string;
  columns: string[];
  rows: { line: number; cells: (string | null)[]; extra?: string[] }[];
  issues: string[];
}

export interface GapReport {
  groups: { source_or_format: string; gap_key: string; observations: number; distinct_questions: number;
    examples: { event: string; payload: Record<string, unknown> }[] }[];
  withdrawn_events: { event: string; withdrawals: { event: string; payload: Record<string, unknown> }[] }[];
  corrections_requiring_review: { event: string; corrections: { event: string; payload: Record<string, unknown> }[] }[];
  unstructured_events: { event: string; reason: string }[];
  matching_events: number;
  withdrawn_count: number;
  corrected_count: number;
}

export interface Subgraph {
  nodes: MapNode[];
  edges: MapEdge[];
  positions: Record<string, [number, number]>;
}

export interface QuestionPage {
  agent: { id: string; name: string; kind: string };
  question: { id: string; title: string; status: string; created: string; updated: string; current_work: string | null };
  node: string;
  counts: QuestionCounts | null;
  revisions: Revision[];
  notebook: { snapshot: string | null; labbook: string | null; question: string | null; truncated: boolean;
    blobs: Record<string, string> };
  scripts: { path: string; blob: string; bytes: number | null; url: string }[];
  outputs: Output[];
  figures: Output[];
  events: WorkEvent[];
  networks: NetworkRevision[];
  coverage: CoverageTable[];
  gaps: GapReport;
  posts: { post: string; snapshot: string; created: string }[];
  subgraph: Subgraph;
  note: string;
}

export interface Call {
  line: number;
  result_line?: number | null;
  lane: string;
  name: string;
  summary: string;
  exit_code: number | null;
  status: string;
  t: number | null;
  t_end: number | null;
}

export interface Receipt extends Call {
  script: string | null;
  outcome: "pass" | "fail" | "unknown";
}

export type TokenValue = number | "unavailable";

export interface RunTimeline {
  run: { id: string; request: string; target: string; state: string; created: string; finished: string | null };
  request: { id?: string; post?: string; state?: string; task_type?: string | null; title?: string | null; kind?: string | null };
  agent: { id: string; name: string; model?: string | null; effort?: string | null; harness?: string };
  execution: { state?: string; started?: string; finished?: string; returncode?: number | null; wall_seconds?: number | null;
    monotonic_seconds?: number | null; suspended_seconds: number; suspension_floor_seconds: number; bounded: boolean };
  axis: { unit: "seconds" | "events"; duration: number; clock: string };
  suspensions: { at: number; seconds: number; gap_seconds: number; placement: string; unplaced_seconds: number }[];
  lanes: { id: string; label: string; count: number }[];
  calls: Call[];
  receipts: Receipt[];
  compactions: { line: number; t: number | null; source: string; text: string }[];
  compaction_summaries: { timestamp: number | null; fallback: boolean; excerpt: string; t: number | null }[] | null;
  inbox_reads: (Call & { sent: boolean })[];
  answers_consumed: (Call & { posts: string[]; requests: string[] })[];
  headline: (Call & { basis: string }) | null;
  final: { text: string | null; source: string | null };
  tokens: Record<string, TokenValue | string>;
  metrics: Record<string, unknown>;
  malformed_lines: number[];
  errors: number;
  links: { raw: string; messages: string };
  limitations: string[];
}

export interface RunListItem {
  id: string;
  request: string;
  target: string;
  agent_name: string;
  state: string;
  created: string;
  finished: string | null;
  task_type: string | null;
  request_title: string | null;
  request_kind: string | null;
}

export interface Messages {
  items: { index: number; role?: string; session?: string; timestamp?: number; content: string }[];
  total: number;
  offset: number;
  limit: number;
}
