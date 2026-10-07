// Claim ledger, contradiction queue, frontier and wishlist views (M1.6, M1.7, M5.1, M5.3, M5.4).
// Every string here is author-stated, untrusted content.
import type { IncomingCitation } from "./publishing";

export type ClaimStatus = "supported" | "descriptive" | "untestable" | "withdrawn";
export type PointerKind = "post" | "artifact" | "receipt" | "locator" | "accession";

export interface Pointer {
  kind: PointerKind;
  id: string;
  locator?: string;
  present?: boolean;
}

export interface Scope {
  species?: string;
  context?: string;
  endpoint?: string;
  direction?: string;
}

export interface MarkSummary {
  id: string;
  participant: string;
  kind: string;
  note: string;
  created: string;
}

export interface Claim {
  id: string;
  post: string;
  author: string;
  author_name?: string | null;
  ordinal: number;
  text: string;
  status: ClaimStatus;
  stated_status?: ClaimStatus | null;
  scope: Scope;
  pointers: Pointer[];
  claims_blob: string;
  created: string;
  withdrawn_by?: string | null;
  replacement?: string | null;
  post_title?: string | null;
  marks: MarkSummary[];
  /** Spec v3 V12: threads at anchors on the claim (a disputed mark opens one), shown next to it. */
  threads?: DialogueThread[];
  /** A claim of a post hidden by moderation is served as `{id, post, hidden: true, reason}` only (spec v2 C2). */
  hidden?: boolean;
  reason?: string | null;
  /** Only on GET /api/claims/{id} (spec v3 V16): posts of imported snapshots citing this claim. */
  cited_from?: IncomingCitation[];
}

export interface DialoguePost {
  post: string;
  seq: number;
  created?: string;
  participant?: string;
  participant_name?: string | null;
  participant_kind?: string | null;
  kind?: string | null;
  in_reply_to?: string | null;
  text?: string;
  claims?: { id: string; status: string; text: string; withdrawn_by?: string | null }[];
  artifacts?: string[];
  mark?: string | null;
  hidden?: boolean;
  reason?: string | null;
}

export interface DialogueThread {
  thread: string;
  target_kind: string;
  target_id: string;
  post?: string | null;
  created: string;
  hidden?: boolean;
  reason?: string | null;
  target_author?: string | null;
  target_author_name?: string | null;
  opened_by?: { participant?: string; participant_name?: string | null; participant_kind?: string | null } | null;
  mark?: string | null;
  opened_by_dispute?: boolean;
  posts?: DialoguePost[];
  replies?: number;
  author_replies?: number;
  awaiting_author?: boolean;
}

export interface ClaimList {
  items: Claim[];
  total: number;
  query: string;
}

export interface ReviewRequest {
  id: string;
  post: string;
  target: string;
  task_type: string;
  state: string;
  subjects: string[];
}

export interface Contradiction {
  id: string;
  claims: [Claim, Claim];
  shared: { kind: string; id: string }[];
  scope: Record<"species" | "context" | "endpoint", "same" | "different" | "unstated">;
  reviews: ReviewRequest[];
  basis: string;
}

export interface ContradictionQueue {
  items: Contradiction[];
  total: number;
  policy: string;
}

export type FrontierKind = "open_question" | "untestable" | "gap" | "proposed_experiment" | "next_step";
export type FrontierStatus = "open" | "candidate_evidence" | "promoted" | "closed" | "withdrawn";

export interface WatchStatus {
  watchers: { id: string; provider: string; query: string; interval_seconds: number; enabled: number }[];
  runs: number;
  found: number;
  last_run: { created: string; provider: string; found: unknown[]; post?: string | null } | null;
}

export interface FrontierItem {
  id: string;
  question: string;
  question_title?: string | null;
  author: string;
  author_name?: string | null;
  kind: FrontierKind;
  text: string;
  status: FrontierStatus;
  status_reason?: string | null;
  blocked_by?: string | null;
  watcher_query?: string | Record<string, unknown> | null;
  missing_measurement?: string | null;
  pointers: Pointer[];
  detail: Record<string, string>;
  created: string;
  updated: string;
  promoted_to?: string | null;
  watch: WatchStatus;
  // Who set candidate_evidence, from records: a watcher run's event, the author's status event, or both.
  candidate_evidence?: CandidateEvidence | null;
  // Whether the item's own post exists on this board (null when it names none).
  post_present?: boolean | null;
  // V5 scouting deliverables: datasets inspected for this item, eligible or rejected with the scout's reason.
  datasets?: InspectedDataset[];
  datasets_summary?: DatasetsSummary;
}

export interface InspectedDataset {
  accession?: string;
  eligible?: boolean;
  reason?: string;
  receipt?: Pointer;
  recorded_by?: string;
  source?: "work_event" | "answer_block";
  event?: string;
  post?: string;
  question?: string;
  created?: string;
  // A dataset listed in a scouting answer hidden by moderation (spec v2 C2): id and reason only.
  hidden?: boolean;
}

export interface DatasetsSummary {
  inspected: number;
  eligible: number;
  rejected: number;
  withheld: number;
}

export interface CandidateEvidence {
  set_by: string;
  records: { by: "watcher" | "author" | "scouting"; watcher?: string; run?: string; post?: string | null; event?: string | null; reason?: string | null }[];
}

// V5 planning board (GET /api/frontier/board).
export type BoardColumnKey = "open" | "blocked" | "candidate_evidence" | "promoted" | "closed";

export interface RequestInfo {
  id: string;
  post: string;
  target: string;
  target_name: string;
  state: string;
  task_type?: string | null;
  budget?: Record<string, number> | null;
  deadline?: string | null;
  answer?: string | null;
  created: string;
}

export interface BoardCard extends FrontierItem {
  column: BoardColumnKey;
  request?: RequestInfo | null;
}

export interface SharedExperiment {
  id: string;
  kind?: FrontierKind | null;
  text: string;
  status: "open" | "promoted";
  column: BoardColumnKey;
  items: { id: string; present: boolean; question?: string; question_title?: string | null; author?: string;
           author_name?: string | null; kind?: FrontierKind; text?: string; status?: FrontierStatus }[];
  questions: string[];
  confirmations: { seq: number; participant: string; note: string; created: string }[];
  shared_terms: string[];
  promoted_to?: string | null;
  request?: RequestInfo | null;
  created: string;
  updated: string;
  note: string;
}

export interface BoardColumn {
  key: BoardColumnKey;
  label: string;
  items: BoardCard[];
  experiments: SharedExperiment[];
  count: number;
  budget: Record<string, number>;
  requests: number;
  targets: { target: string; name: string; requests: number }[];
  withdrawn?: number;
}

export interface FrontierBoardView {
  columns: BoardColumn[];
  total: number;
  experiments: number;
  by_kind: Record<FrontierKind, number>;
  by_column: Record<BoardColumnKey, number>;
  allowance: { allowance: Record<string, number> | null; spent: Record<string, number>;
               remaining: Record<string, number> | null; unlimited: boolean; configured?: boolean } | null;
  policy: string;
}

export interface Confirmation {
  seq: number;
  created: string;
  items: string[];
  participant: string;
  note: string;
}

export interface Cluster {
  id: string;
  kind: FrontierKind;
  items: string[];
  questions: string[];
  shared_terms: string[];
  pairs: { items: [string, string]; jaccard: number; shared_terms: string[] }[];
  confirmations: Confirmation[];
  basis: string;
}

export interface FrontierView {
  items: FrontierItem[];
  total: number;
  by_kind: Record<FrontierKind, string[]>;
  by_blocker: { blocked_by: string | null; items: string[] }[];
  clusters: Cluster[];
  kinds: FrontierKind[];
  statuses: FrontierStatus[];
  policy: string;
}

export interface WishlistEntry {
  text: string;
  normalized: string;
  distinct_questions: number;
  questions: { question: string; author: string; author_name?: string | null; title?: string | null }[];
  sources: { kind: "frontier_item" | "gap" | "labbook"; question: string; author: string; item?: string; line?: number }[];
}

export interface Wishlist {
  items: WishlistEntry[];
  total: number;
  grouping: string;
}

export const KIND_LABELS: Record<FrontierKind, string> = {
  open_question: "Open questions",
  untestable: "Untestable branches",
  gap: "Gaps",
  proposed_experiment: "Proposed experiments",
  next_step: "Next computable steps",
};
