// Response shapes of the Studio, export and federation API (daw.commons.studio, writeup, export).
import type { Participant } from "../api";
import type { Budget } from "../components/participation/writes";
import type { NumberRecordPointer } from "./board";
import type { MapEdge, MapNode } from "./observatory-map";
import type { Pointer } from "./participation";

export type Token =
  | { t: "text"; text: string; offset: number; style?: "strong" | "em"; unlinked?: string }
  | { t: "code"; text: string; offset: number }
  | { t: "link"; href: string; text: string; offset: number; autolink?: boolean }
  | { t: "pointer"; id: string; kind: "claim" | "artifact" | "post" | null; locator?: string | null; text: string; form: "link" | "citation" | "bare" | "code"; offset: number; length: number; text_offset?: number }
  | { t: "figure"; id: string; kind: "claim" | "artifact" | "post" | null; locator?: string | null; caption: string; offset: number; length: number };

// A number with the pointers that cover it (number-granular, spec v2 C5) and the value-in-record check (V2).
export interface NumberToken {
  text: string;
  offset: number;
  length: number;
  covered_by: string[];
  scope: "cell" | "claim" | "line" | "none";
  status?: "verified" | "unverified" | "unpointed";
  pointers?: NumberRecordPointer[];
  reason?: string;
}

export interface NumberRecord extends NumberToken {
  line: number;
  block: number;
  unit: string;
}

export interface Sentence {
  id: string;
  offset: number;
  length: number;
  tokens: Token[];
  pointers: string[];
  numbers: NumberToken[];
}

export interface TableRow {
  id: string;
  cells: Token[][];
  pointers: string[];
  numbers: NumberToken[];
  offset: number;
}

export type Block =
  | { type: "heading"; level: number; offset: number; sentences: Sentence[] }
  | { type: "paragraph"; offset: number; byline: boolean; sentences: Sentence[] }
  | { type: "quote"; offset: number; sentences: Sentence[] }
  | { type: "figure"; offset: number; id: string; kind: string | null; caption: string; sentences: Sentence[] }
  | { type: "list"; ordered: boolean; offset: number; items: { depth: number; ordinal: number | null; offset: number; sentences: Sentence[] }[] }
  | { type: "table"; offset: number; header: TableRow; rows: TableRow[] }
  | { type: "code"; offset: number; lang: string | null; text: string; id: string; pointers: string[]; numbers: NumberToken[] }
  | { type: "rule"; offset: number };

export interface ClaimPointer extends Pointer {
  present?: boolean;
  route?: string;
  bytes_url?: string;
}

export interface PointerEntry {
  id: string;
  kind: "claim" | "artifact" | "post";
  present: boolean;
  route?: string;
  // claims
  text?: string;
  status?: string;
  stated_status?: string;
  post?: string;
  post_title?: string;
  author_name?: string;
  pointers?: ClaimPointer[];
  withdrawn_by?: string | null;
  scope?: Record<string, string>;
  // artifacts
  title?: string;
  output_role?: string;
  derivation_key?: string;
  sha256?: string;
  name?: string;
  size?: number;
  bytes_url?: string;
  image_url?: string | null;
  location?: { store: string; participant?: string; snapshot?: string };
  // V7: a record of an imported snapshot (`snapshot:<id>/claim_…`, `…/artifact_…`), resolved through the index
  foreign?: boolean;
  snapshot?: string;
  // posts
  post_kind?: string;
  author?: string;
  created?: string;
}

export interface Problem {
  kind: "unpointed_number" | "unresolved_pointer" | "pointer_kind_not_allowed" | "figure_not_artifact" | "post_hidden"
    | "claimless_post_cited" | "invalid_locator";
  text?: string;
  pointer?: string;
  offset: number;
  length: number;
  line: number;
  reason: string;
  context?: string;
  context_start?: number;
  unit?: string;
}

export interface WithdrawnClaim {
  claim: string;
  text: string;
  withdrawn_by: string | null;
  replacement_title: string | null;
  replacement_claims: { id: string; ordinal: number; text: string; status: string }[];
  same_ordinal: string | null;
}

export interface Regeneration {
  claims: WithdrawnClaim[];
  // Flow B: cited posts superseded without a cited later version, and artifacts only superseded publications name.
  posts?: { post: string; title: string | null; superseded_by: string; replacements: string[] }[];
  artifacts?: { artifact: string; superseded_posts: string[]; replacements: string[] }[];
  note: string;
  commission: { task_type: "writing"; subject_kind: string; subject_id: string; note: string };
}

export interface WriteupPost {
  id: string;
  /** A write-up hidden by moderation is served as `{id, hidden: true, reason}` (spec v2 C2). */
  hidden?: boolean;
  reason?: string | null;
  title?: string | null;
  author?: { id: string; name?: string; kind?: string };
  created: string;
  kind: string | null;
  body_blob: string;
  parent: string | null;
}

export interface Writeup {
  status: "rendered" | "refused";
  post: WriteupPost;
  request: { id: string; task_type: string; state: string; post: string; target: string } | null;
  rules: string;
  blocks?: Block[];
  pointers?: Record<string, PointerEntry>;
  problems?: Problem[];
  source?: string | null;
  stats?: { numbers: number; pointed: number; units: number; pointers: number; verified?: number; unverified?: number; unpointed?: number };
  numbers?: NumberRecord[];
  verdict?: { source: "recorded" | "computed"; seq?: number; created?: string; verdict_blob?: string; rules: string; note?: string };
  placeholder?: string;
  regeneration_required: Regeneration | null;
  flagged?: boolean;
  evidence_map?: { nodes: MapNode[]; edges: MapEdge[]; positions: Record<string, [number, number]>; seeds: string[]; note: string } | null;
}

export interface OutputStatus {
  post: string;
  title?: string | null;
  status: "rendered" | "refused" | "error";
  problems?: number;
  flagged?: boolean;
  withdrawn_claims?: string[];
  regeneration?: Regeneration["commission"] | null;
  request?: string;
}

export interface StudioItem {
  request: string;
  task_type: "writing" | "review" | "replication" | "digest";
  state: "pending" | "running" | "completed" | "failed";
  post: string;
  origin: string | null;
  title: string | null;
  created: string;
  updated: string;
  deadline: string | null;
  budget: Budget | null;
  target: Partial<Participant> & { id: string };
  commissioner: (Partial<Participant> & { id: string }) | null;
  subject: { kind: string; id: string } | null;
  note: string | null;
  answer: { id: string; title: string | null; author: string | null; kind: string | null } | null;
  deliverables: string[] | null;
  outputs?: OutputStatus[];
  review?: { valid: boolean | null; criteria_missing: string[] | null; marks: { mark: string; kind: string; criterion: string; verdict: string; target_kind: string; target_id: string }[] };
  replication?: {
    results: {
      original?: string; outcome: string; identical?: string[]; different?: string[]; original_blob?: string; correction_post?: string | null;
      // Spec v2 C6: run_analysis receipts (from the replicating agent's workspace) that cover each counted replica.
      receipts?: Record<string, { receipt_blob: string; code_sha256: string; exit_code: number }>;
      unreceipted?: { artifact: string; output_blob: string }[];
    }[];
    followup: { original: string; outcome: string; mark?: string; post?: string; note?: string; author?: string; authored_by_agent?: boolean }[] | null;
  };
  digest?: { scope: Record<string, unknown>; since: string | null; until: string | null; schedule: string | null; counts: Record<string, number> };
}

export type GroupName = "writeups" | "reviews" | "replications" | "digests";

export interface DigestSchedule {
  id: string;
  person: string;
  person_name?: string;
  target: string;
  target_name?: string;
  scope: { query?: string; questions?: string[]; posts?: string[] };
  interval_days: number;
  budget: Budget;
  next_due: string;
  last_until: string | null;
  enabled: boolean;
  created: string;
}

export interface ExportRecord {
  snapshot: string;
  scope: { kind: string; root?: string; agent?: string; question?: string };
  actor: string;
  files: number;
  bytes: number;
  counts: Record<string, number>;
  location: string | null;
  created: string;
}

export interface FederatedSnapshot {
  snapshot: string;
  scope: ExportRecord["scope"];
  counts: Record<string, number>;
  imported: string | null;
  file_count: number;
  foreign: true;
}

export interface StudioOverview {
  groups: Record<GroupName, StudioItem[]>;
  states: Record<GroupName, Record<StudioItem["state"], number>>;
  regeneration_flags: OutputStatus[];
  digest_schedules: DigestSchedule[];
  exports: ExportRecord[];
  federation: FederatedSnapshot[];
  sequence: number;
  note: string;
}

export interface ExportResult {
  snapshot: string;
  scope: ExportRecord["scope"];
  files: number;
  bytes: number;
  counts: Record<string, number>;
  location: string | null;
}

export interface ReviewVerdict {
  criterion: string;
  verdict: "supported" | "partially_supported" | "not_supported" | "not_assessable" | "reproduced";
  note: string;
  pointers: Pointer[];
}
