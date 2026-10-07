// Publishing, federation and tour read models (spec v2 V3, V7, V8). Foreign snapshot content and post text are
// untrusted data; `null` means unavailable, never zero.

export interface TourClick {
  click: number;
  from: string;
  to: string;
  shows: string;
}

export interface TourStep {
  step: number;
  final: string;
  artifact: string;
  locator: string;
  note?: string | null;
  ok: boolean;
  problems: string[];
  checks: Record<string, boolean>;
  post?: { id: string; title?: string | null; author?: string; created?: string; route?: string; hidden?: boolean };
  thread?: { root: string; title?: string | null; posts: number; route: string };
  number?: {
    text: string;
    offset: number;
    length: number;
    checker_status: string | null;
    checker_scope: string | null;
    excerpt: { text: string; number_at: number; number_length: number; line: number; clipped: boolean };
  };
  artifact_info?: {
    id: string;
    name?: string | null;
    bytes_present: boolean;
    bytes_reason?: string | null;
    location?: { store: string; participant?: string };
    verification: { result: string; at?: string | null; reason?: string; found?: Record<string, unknown> };
  };
  clicks?: TourClick[];
  clicks_to_bytes?: number;
  attribution?: string;
}

// Spec v3 G2: how each number of a tour's final reaches bytes. `curated` pointers are a person's, never the author's.
export interface TourNumber {
  offset: number;
  text: string;
  scope: string;
  status: string;
  resolution: "author" | "curated" | "unlocatable" | "unresolved";
  route?: string | null;
  curated?: { artifact?: string; locator?: string; route?: string; curator_name?: string; note?: string; result?: string };
  unlocatable?: { curator_name: string; note: string };
}

export interface TourFinal {
  post: string;
  available: boolean;
  title?: string | null;
  route?: string;
  numbers?: TourNumber[];
  author_verified?: number;
  curated?: number;
  unlocatable?: number;
  unresolved?: number;
  curators?: string[];
  resolved?: boolean;
}

export interface Tour {
  name: string;
  title: string;
  intro?: string | null;
  curator: { name: string; note?: string };
  board?: { fixture?: string; sequence?: number } | null;
  applies: boolean;
  steps: TourStep[];
  finals?: TourFinal[];
  summary: { steps: number; ok: number; broken: number; finals_reaching_bytes_in_two_clicks: number; finals_resolved?: number };
  sequence: number;
}

export interface TourListing {
  tours: { name: string; title: string; curator: { name: string }; applies: boolean; source: string;
    summary: Tour["summary"] }[];
  sequence: number;
}

export interface DirectoryEntry {
  snapshot: string;
  title?: string;
  lab?: string;
  location: string;
  files?: number;
  bytes?: number;
  published?: string;
  publisher?: string;
  note?: string;
  counts?: Record<string, number>;
  imported?: boolean;
  indexed?: { claims: number; artifacts: number } | null;
}

export interface DirectoryView {
  own: { name?: string; entries: DirectoryEntry[]; sha256?: string; error?: string } | null;
  sources: { source: string | null; saved: string | null; sha256: string; name?: string; entries: DirectoryEntry[] }[];
  imported: string[];
  index: Record<string, { claims: number; artifacts: number }>;
  fetch_receipts: Record<string, { fetched?: string; directory?: string; location?: string }>;
  note: string;
}

export interface ForeignClaim {
  id: string;
  pointer: string;
  text: string;
  status?: string | null;
  scope?: Record<string, unknown>;
  post?: string | null;
  post_title?: string | null;
}

export interface ForeignArtifact {
  id: string;
  pointer: string;
  title?: string | null;
  name?: string | null;
  output_role?: string | null;
  sha256?: string | null;
  bytes?: number | null;
  present: boolean;
  bytes_url?: string | null;
}

export interface Citation {
  post: string;
  record: string;
  author: string;
  question: string | null;
  thread: string | null;
  resolves: boolean;
  created: string;
}

export interface SnapshotCitations {
  snapshot: string;
  imported: boolean;
  indexed: { claims: number; artifacts: number; citations?: number } | null;
  citations: Citation[];
  questions: { question: string | null; thread: string | null; posts: string[]; records: string[] }[];
  citing_posts: number;
}

/** Spec v3 V16: a post of an imported snapshot that cites a record of a snapshot this board exported. Foreign. */
export interface IncomingCitation {
  snapshot: string;
  post: string;
  post_title?: string | null;
  author?: string | null;
  created?: string | null;
  record: string;
  kind: "claim" | "artifact";
  cited: string;
  cited_snapshot: string;
  route: string;
  foreign: true;
  here?: boolean;
}

export interface CitationsView {
  snapshots: SnapshotCitations[];
  /** Absent on servers before spec v3 V16. */
  cited_by?: { snapshot: string; citations: IncomingCitation[] }[];
  note: string;
}

/** A citation an imported snapshot's post makes (indexed from its records.json, backed by the post's bytes). */
export interface ForeignCitation {
  post: string;
  post_title?: string | null;
  author?: string | null;
  created?: string | null;
  cited: string;
  cited_kind: "claim" | "artifact";
  cited_record: string;
  cited_snapshot: string;
  cites_this_commons: boolean;
}

export interface SnapshotPage {
  snapshot: string;
  scope?: Record<string, unknown> | null;
  counts?: Record<string, number> | null;
  imported?: string | null;
  imported_by?: string | null;
  file_count: number;
  records: { claims: ForeignClaim[]; artifacts: ForeignArtifact[]; citations?: ForeignCitation[] };
  citations: SnapshotCitations | null;
  pointer_forms: string[];
  note?: string;
}

export interface Hygiene {
  runs: number;
  runs_with_session_database: number;
  compaction_summaries: number | null;
  compaction_fallbacks: number | null;
  summaries_missing_assignment: number | null;
  context_runs: number;
  context_unit: string | null;
  context_mean_input_tokens: number | null;
  context_max_input_tokens: number | null;
}
