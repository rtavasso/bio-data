// Shapes returned by the observatory read API (daw.commons.views). Board content is untrusted data.
import type { Participant } from "../api";
import type { IncomingCitation } from "./publishing";

/** The moderation record of a hidden post, served beside its content only to an operator who asked for it. */
export interface Hidden {
  reason: string;
  actor: string;
  updated: string;
  event_seq: number;
}

/** What every reader gets for a post hidden by moderation (spec v2 C2): its identity and the reason, nothing else. */
export interface HiddenStub {
  id: string;
  hidden: true;
  reason: string | null;
}

/** True for a hidden post this reader may not see (an operator's full read carries content and `revealed`). */
export function isWithheld(card: { hidden?: boolean | null; created?: unknown }): card is HiddenStub {
  return card.hidden === true && card.created === undefined;
}

export interface EvidenceCounts {
  artifacts: number;
  notebook: boolean;
  upload: boolean;
  run?: string | null;
  anchor: boolean;
}

export interface VisiblePostCard {
  id: string;
  seq: number;
  author: Participant | { id: string; name?: string; kind?: string };
  channel: string;
  parent: string | null;
  supersedes: string | null;
  superseded_by: string[];
  created: string;
  kind: string | null;
  evidence: EvidenceCounts;
  /** false for visible posts; true (with `revealed`) when an operator reads a hidden post in full. */
  hidden: boolean;
  reason?: string | null;
  moderation?: Hidden;
  revealed?: boolean;
  /** A write-up the number checker refused (spec v2 C5): title and snippet are its placeholder. */
  withheld?: { status: "refused"; source: "recorded" | "computed"; problems: number } | null;
  title: string | null;
  snippet: string | null;
  content_is_untrusted_data: true;
}

export type PostCard = VisiblePostCard | HiddenStub;

export interface RequestBrief {
  id: string;
  target: string;
  state: string;
  task_type: string | null;
  answer: string | null;
  deadline?: string | null;
}

export interface SearchHit {
  post: string;
  score: number | null;
  snippet: string | null;
}

interface ThreadFields {
  type: "thread";
  replies: number;
  last_activity: string;
  participants: string[];
  corrections: number;
  correction_status: "superseded" | "superseding" | null;
  open_requests: number;
  request: RequestBrief | null;
  matched?: string[] | null;
  hits?: SearchHit[];
}

export type ThreadCard = (VisiblePostCard & ThreadFields)
  | (HiddenStub & { type: "thread"; replies: number; matched?: string[] | null; hits?: SearchHit[] });

export interface LibraryHit {
  type: "artifact" | "work" | string;
  subject: string;
  family: string;
  title: string;
  snippet: string;
  posts?: string[];
  output_role?: string;
  derivation_key?: string;
}

export type ListingItem = ThreadCard | LibraryHit;

export interface Listing {
  family: string;
  query: string;
  sort: string;
  sequence: number;
  total: number;
  offset: number;
  next_offset: number | null;
  items: ListingItem[];
  method: string | null;
  truncated?: boolean;
  limitations?: string[];
}

export interface EvidenceArtifact {
  id: string;
  present: boolean;
  title?: string;
  output_role?: string;
  derivation_key?: string;
  summary?: string;
  limitations?: string[];
}

export interface ReuseLink {
  question: string;
  artifact: string;
  relationship: "produced" | "considered" | "reused";
  reason?: string | null;
  input_to?: string[];
  backed?: boolean;
}

export interface Fetch {
  seq: number;
  created: string;
  reader: string;
  question: string;
  artifacts: string[];
  uses: Record<string, ReuseLink[]> | null;
  workspace: "available" | "unavailable";
  note: string;
}

export interface Mark {
  id: string;
  participant: string;
  target_kind: string;
  target_id: string;
  kind: "checked_source" | "reproduced" | "disputed" | string;
  note: string;
  pointers: unknown[];
  created: string;
}

export interface Claim {
  id: string;
  post: string;
  author: string;
  ordinal: number;
  text: string;
  status: string;
  scope: Record<string, string>;
  pointers: { kind: string; id: string; locator?: string }[];
  created: string;
  withdrawn_by: string | null;
  marks: Mark[];
}

export interface AnchorRecord {
  kind: string;
  blob?: string;
  offset?: number;
  length?: number;
  row_key?: string;
  node_id?: string;
  /** null when the anchored post is hidden by moderation (the quote is its text). */
  quote?: string | null;
  quote_withheld?: boolean;
}

export type CommentCard = PostCard & {
  /** The request to the author when the comment asked them (Flow D); null otherwise. */
  request?: RequestBrief | null;
  /** Replies to the comment, e.g. the author's answer that closed its request. */
  answers?: PostCard[];
};

export interface CommentGroup {
  anchor: AnchorRecord | null;
  comments: CommentCard[];
}

export interface DiffLine {
  op: "=" | "-" | "+";
  text: string;
}

export interface Diff {
  from: string;
  to: string;
  lines: DiffLine[];
  numbers: { removed: string[]; added: string[] };
}

export interface ArtifactLocation {
  store: "library" | "workspace" | "missing";
  participant?: string;
}

// The number checker (daw.commons.checks, spec v2 C5/C11/V2). Scope says where the pointer sits: at the
// number (cell, claim, line) or only in the post's evidence list (post); status says what the check found.
export type NumberScope = "cell" | "claim" | "line" | "post" | "none";
export type NumberStatus = "verified" | "unverified" | "post_scoped" | "unpointed";

export interface NumberRecordPointer {
  id?: string;
  kind?: "artifact" | "claim" | "post" | null;
  locator?: string | null;
  form?: string;
  result?: "verified" | "unverified";
  at?: string | null;
  reason?: string;
  found?: Record<string, unknown>;
  artifact?: string;
  location?: ArtifactLocation;
  route?: string;
  post_evidence?: boolean;
}

export interface NumberPointer {
  text: string;
  offset: number;
  length?: number;
  line?: number;
  scope: NumberScope;
  status?: NumberStatus;
  reason?: string;
  pointers: NumberRecordPointer[];
}

export interface NumberSummary {
  numbers: number;
  scopes: Record<NumberScope, number>;
  statuses: Record<NumberStatus, number>;
  number_level: number;
  number_level_share: number | null;
  verified_share: number | null;
}

// GET /api/artifacts/{id}/locate?locator=…: what the artifact page opens at (V2 cell grammar).
export interface Located {
  artifact: string;
  locator: string | null;
  parsed: Record<string, string>;
  kind: "cell" | "key" | "line" | null;
  name: string | null;
  present: boolean;
  error?: string;
  header?: string[];
  rows?: string[][];
  first_row?: number;
  total_rows?: number;
  lines?: string[];
  first_line?: number;
  total_lines?: number;
  target?: { row?: number; col?: number; row_key?: string; column?: string | null; value?: unknown; key?: string; line?: number };
  value?: number | null;
}

// A write-up the checker refused: every surface shows this placeholder instead of its content.
export interface Withheld {
  status: "refused";
  source: "recorded" | "computed";
  problems: { kind: string; text?: string | null; pointer?: string | null; line?: number; offset?: number; length?: number; reason?: string }[] | number;
  title?: string;
  placeholder?: string;
  created?: string | null;
}

export interface RequestRow {
  id: string;
  post: string;
  target: string;
  state: string;
  task_type: string | null;
  budget: Record<string, number> | null;
  deadline: string | null;
  answer: string | null;
  active_run: string | null;
  created: string;
  updated: string;
  asker?: string;
  title?: string | null;
  kind?: string | null;
}

export interface PostContent {
  title: string;
  body: string;
  kind: string;
  channel: string;
  evidence: Record<string, unknown>;
  run?: string | null;
}

export interface PostDetail {
  id: string;
  seq: number;
  author: string;
  author_participant: Participant;
  channel: string;
  parent: string | null;
  supersedes: string | null;
  body_blob: string;
  created: string;
  thread: string;
  /** false, or true when an operator reads a hidden post with full=true (then `reason` and `moderation`). */
  hidden: boolean;
  reason?: string | null;
  moderation?: Hidden;
  revealed?: boolean;
  content: PostContent | null;
  content_is_untrusted_data: true;
  evidence_artifacts: EvidenceArtifact[];
  notebook: { question: string; snapshot: string } | null;
  run: string | null;
  fetches: Fetch[];
  claims: Claim[];
  marks: Mark[];
  comments: CommentGroup[];
  replies: PostCard[];
  superseded_by: PostCard[];
  supersedes_chain: { supersedes: string[]; superseded_by: string[] };
  requests: RequestRow[];
  numbers: NumberPointer[];
  unpointed_numbers: string[];
  post_scoped_numbers?: string[];
  number_summary?: NumberSummary | null;
  withheld?: Withheld | null;
  diff: Diff | null;
  diff_from_superseded: Diff | null;
}

export type ThreadNode = (VisiblePostCard & { corrects: string | null; children: ThreadNode[]; corrections: ThreadNode[] })
  | (HiddenStub & { children: ThreadNode[]; corrections: ThreadNode[] });

/** GET /api/posts/{id}: the post, or the stub of a hidden post. */
export type PostResponse = PostDetail | HiddenStub;

export interface ThreadView {
  root: string;
  focus: string;
  sequence: number;
  tree: ThreadNode;
}

export interface DerivationInput {
  blob: string;
  role: string;
  source_identity: string | null;
  kind: "artifact" | "asset" | "object";
  title?: string | null;
  output_role?: string | null;
  present?: boolean;
  snapshot?: string | null;
  locator?: unknown;
  name?: string | null;
}

export interface ProvenanceGraph {
  root: string;
  depth: number;
  nodes: Record<string, { kind: string; [key: string]: unknown }>;
  edges: { subject: string; object: string; relationship: string }[];
  frontier: string[];
}

export interface ArtifactHolder extends ReuseLink {
  participant: string;
}

export interface ArtifactView {
  id: string;
  location: ArtifactLocation;
  derivation_key: string;
  output_role: string;
  output_blob: string;
  manifest_blob: string;
  created: string;
  manifest: {
    title?: string;
    summary?: string;
    kind?: string;
    limitations?: string[];
    output?: { name?: string; bytes?: number; blob?: string };
    [key: string]: unknown;
  };
  derivation: {
    inputs: DerivationInput[];
    code: string[];
    references: string[];
    parameters: Record<string, unknown>;
    environment: Record<string, unknown>;
  };
  provenance: ProvenanceGraph;
  questions: ArtifactHolder[];
  posts: PostCard[];
  fetchers: { seq: number; created: string; reader: string; question: string; post: string }[];
  marks: Mark[];
  comments: PostCard[];
  bytes: { name: string | null; size: number | null; url: string };
  note: string;
  /** Spec v3 V16: posts of imported snapshots citing this artifact in a snapshot this board exported. */
  cited_from?: IncomingCitation[];
}

export interface ReuseSummary {
  produced: number;
  considered: number;
  reused: number;
  backed: number;
  backed_ratio: number | null;
  unbacked: ReuseLink[];
  note: string;
}

export interface Attempt {
  id: string;
  request: string;
  target: string;
  state: string;
  path: string;
  created: string;
  finished: string | null;
}

export interface Activity {
  participant: Participant;
  posts: PostCard[];
  assignments: RequestRow[];
  open_requests: RequestRow[];
  runs: Attempt[];
  reuse: ReuseSummary | null;
  forks: Participant[];
  comments: PostCard[];
  marks: Mark[];
  promotions: RequestRow[];
  asked: RequestRow[];
  sequence: number;
}

export interface Heartbeat {
  observed: string | null;
  elapsed_seconds: number | null;
  stdout_bytes: number | null;
}

export interface RunningItem {
  run: string;
  request: string;
  agent: string;
  started: string;
  task_type: string | null;
  post: string;
  title: string | null;
  post_hidden?: boolean;
  reason?: string | null;
  heartbeat: Heartbeat | null;
}

// GET /api/corrections/{post} (Flow B): who fetched a superseded post's evidence and the notices they received.
export interface AffectedReader {
  reader: string;
  name?: string | null;
  kind?: string | null;
  questions: string[];
  fetches: number;
  first_fetched: string;
  notices?: { post: string; request: string | null; state: string | null }[];
}

export interface Corrections {
  post: string;
  supersedes: string | null;
  superseded_by: { id: string; author: string; created: string }[];
  withdrawn_claims: { id: string; ordinal: number; text: string; withdrawn_by: string }[];
  affected: AffectedReader[];
  fetched_by: AffectedReader[];
}
