// Claim ledger, contradiction queue, frontier and wishlist views (M1.6, M1.7, M5.1, M5.3, M5.4).
// Every string here is author-stated, untrusted content.

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
  /** A claim of a post hidden by moderation is served as `{id, post, hidden: true, reason}` only (spec v2 C2). */
  hidden?: boolean;
  reason?: string | null;
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
