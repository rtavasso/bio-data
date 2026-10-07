// Evaluation dashboard read model (GET /api/dashboard, /api/cohorts, /api/cohorts/compare).
// `null` always means unavailable (not reported or not recorded); it is never a zero.

export type Num = number | null;

export interface TrendPoint {
  bucket: string;
  runs: number;
  ceremony_tail_median: Num;
  compactions: number;
  compaction_fallbacks: Num;
  minutes_per_executed_analysis: Num;
  monotonic_hours: Num;
}

export interface Tokens {
  input_tokens: Num;
  cached_input_tokens: Num;
  output_tokens: Num;
  input_tokens_partial: Num;
  cached_input_tokens_partial: Num;
  output_tokens_partial: Num;
}

export interface Cost {
  runs: number;
  token_reported_runs: number;
  tokens: Tokens;
  unavailable_reasons: string[];
  compute_hours: Num;
  currency: string | null;
  priced_runs: number;
  amount: Num;
  amount_partial: Num;
  pricing: string;
}

export interface ClaimCounts {
  supported: number;
  descriptive: number;
  untestable: number;
  withdrawn: number;
  total: number;
}

export interface BoardCriteria {
  posts: number;
  corrections: number;
  posts_superseded: number;
  human_marks: number;
  human_marks_per_post: Num;
  provider_citation_posts: number;
  registered_artifacts: number;
  reuse: { backed: number; unbacked: number; backed_ratio: Num };
  claims: ClaimCounts | null;
  numbers?: NumberCoverage | null;
}

// Number coverage of a group's finals (spec v2 C11, V1): pointers at the number (cell, claim, line) versus only the
// post's evidence list (post) or none; statuses from the value-in-record check. null: no final in the group.
export interface NumberCoverage {
  finals: number;
  numbers: number;
  scopes: { cell: number; claim: number; line: number; post: number; none: number };
  statuses: { verified: number; unverified: number; post_scoped: number; unpointed: number };
  number_level: number;
  number_level_share: Num;
  claim_share: Num;
  cell_share: Num;
  verified_share: Num;
}

export interface Group {
  key: string;
  label: string;
  runs: number;
  completed: number;
  failed: number;
  wall_hours: Num;
  monotonic_hours: Num;
  suspensions: number;
  suspended_hours: number;
  tool_calls: number;
  inbox_calls: number;
  analysis_receipts: number;
  analysis_failures: number;
  minutes_per_executed_analysis: Num;
  scripts_written: number;
  plumbing_scripts: number;
  plumbing_share: Num;
  compactions: number;
  compaction_summaries: Num;
  compaction_fallbacks: Num;
  ceremony_tail_minutes: { runs: number; median: Num; mean: Num; max: Num };
  provider_citation_finals: number;
  board: BoardCriteria;
  cost: Cost;
  trend: TrendPoint[];
  posts_scope: "author" | "run";
}

export type Dimension = "cohort" | "participant" | "harness" | "task_type";

export interface Pricing {
  available: boolean;
  currency?: string;
  reason?: string;
}

export interface Dashboard {
  sequence: number;
  bucket: "day" | "week";
  filters: Record<Dimension, string | null>;
  options: {
    cohorts: { id: string; name: string }[];
    participants: { id: string; name: string }[];
    harnesses: string[];
    task_types: string[];
  };
  summary: Group;
  panels: Record<Dimension, Group[]>;
  projection: { runs: number; stored: number; stale: number; missing: number; note: string };
  pricing: Pricing;
  limitations: string[];
}

export interface CohortSummary {
  id: string;
  name: string;
  created: string;
  runs: number;
  assignments: number;
  note: string;
}

export interface CompareCell {
  runs: string[];
  participants: string[];
  harnesses: string[];
  models: string[];
  yield: { posts: number; registered_artifacts: number; analysis_receipts: number; analysis_failures: number };
  calibration: ClaimCounts | null;
  corrections: { corrections: number; posts_superseded: number; human_marks: number };
  cost: Cost;
}

export interface Comparison {
  sequence: number;
  cohorts: { id: string; name: string; runs: number; harnesses: string[]; models: string[] }[];
  criteria: string[];
  assignments: {
    key: string;
    source: string;
    excerpt: string;
    content_is_untrusted_data: boolean;
    cells: Record<string, CompareCell | null>;
  }[];
  totals: Record<string, CompareCell | null>;
  shared_assignments: number;
  claims_recorded: boolean;
  pricing: Pricing;
  note: string;
  limitations: string[];
}
