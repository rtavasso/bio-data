import type { Hygiene } from "./publishing";

// Evaluation dashboard read model (GET /api/dashboard, /api/cohorts, /api/cohorts/compare).
// `null` always means unavailable (not reported or not recorded); it is never a zero.

export type Num = number | null;

export interface TrendPoint {
  bucket: string;
  runs: number;
  ceremony_tail_median: Num;
  compactions: Num;
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
  authoring?: ClaimsAuthoring;
}

// Spec v2 V1: claims per post, evidence-carrying posts with claims, refused final-answer claims blocks, and the kind
// and scope split of the claims' pointers (cell, key, line from the locator grammar; record: no locator).
export interface ClaimsAuthoring {
  posts: number;
  posts_with_claims: number;
  claims: number;
  claims_per_post: Num;
  evidence_posts: number;
  evidence_posts_with_claims: number;
  evidence_posts_with_claims_share: Num;
  claims_refused: number;
  pointers: number;
  pointer_kinds: Record<"artifact" | "locator" | "post" | "receipt" | "accession", number>;
  pointer_scopes: Record<"cell" | "key" | "line" | "record" | "invalid", number>;
  cell_pointer_share: Num;
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
  // Spec v2 C10: totals are null when no run in the group recorded the value (clock, stream or harness
  // capability unavailable); the *_unavailable_runs counts say how many runs were left out of a sum.
  suspensions: Num;
  suspended_hours: Num;
  clock_unavailable_runs?: number;
  tool_calls: Num;
  inbox_calls: Num;
  analysis_receipts: Num;
  analysis_failures: Num;
  minutes_per_executed_analysis: Num;
  scripts_written: Num;
  plumbing_scripts: Num;
  plumbing_share: Num;
  compactions: Num;
  compaction_unavailable_runs?: number;
  compaction_summaries: Num;
  compaction_fallbacks: Num;
  ceremony_tail_minutes: { runs: number; median: Num; mean: Num; max: Num };
  provider_citation_finals: Num;
  // Spec v2 V8: compaction hygiene per group (daw.commons.hygiene); null fields are unavailable.
  compaction_hygiene?: Hygiene;
  turn_economics?: TurnEconomics;
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
  economics?: Economics;
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
  yield: { posts: number; registered_artifacts: number; analysis_receipts: Num; analysis_failures: Num };
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

// Spec v3 V13: turn economics per group (daw.commons.economics.criteria), from each run's turn_economics.json.
// Composition is bytes of model-facing content by source; shares only where every source was measured.
export type Component = "system_prompt" | "delivery_prompt" | "skills" | "tool_outputs" | "summaries" | "conversation";

export interface TurnEconomics {
  runs: number;
  recorded_runs: number;
  unrecorded_runs: number;
  reindexed_runs: number;
  context: { unit: string | null; records: number; mean_input_tokens: Num; max_input_tokens: Num; model_calls: Num };
  composition: { bytes_measured: Record<Component, Num>; complete_runs: number; shares: Record<Component, number> | null };
  compactions: { stream_markers: Num; summaries: Num; fallbacks: Num; fallback_detection: string };
  time: { runs: number; generation_minutes: Num; tool_wait_minutes: Num; tool_wait_share: Num };
  orientation: { runs: number; help_calls_per_turn: Num; reorientation_calls_per_turn: Num; by_kind: Record<string, number> };
  ceremony_tail_minutes: { runs: number; median: Num };
  skill_reads: { runs: number; total: Num; per_turn: Record<string, Num> };
  tokens: Num;
  tokens_reported_runs: number;
  useful_data: { registered_artifacts: Num; verified_claims: Num; promoted_frontier_items: Num };
  tokens_per: { registered_artifact: Num; verified_claim: Num; promoted_frontier_item: Num };
}

export interface SkillVersionPanel {
  key: string;
  label: string;
  first: string;
  harnesses: string[];
  turn_economics: TurnEconomics;
}

export interface SkillRow {
  skill: string;
  bytes: Num;
  budget: Num;
  reads: Num;
  reads_per_turn: Num;
}

export interface Economics {
  skill_versions: SkillVersionPanel[];
  skills: { runs: number; items: SkillRow[] };
  limitations: string[];
}
