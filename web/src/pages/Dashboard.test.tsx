import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { Comparison, CompareCell, Cost, Dashboard as DashboardData, Group } from "../types/dashboard";
import Dashboard from "./Dashboard";

const noCost: Cost = {
  runs: 2, token_reported_runs: 0, unavailable_reasons: ["harness did not report input and output tokens"],
  tokens: { input_tokens: null, cached_input_tokens: null, output_tokens: null,
    input_tokens_partial: null, cached_input_tokens_partial: null, output_tokens_partial: null },
  compute_hours: 0.01, currency: null, priced_runs: 0, amount: null, amount_partial: null, pricing: "no pricing.toml in this commons",
};
const priced: Cost = {
  ...noCost, token_reported_runs: 2, unavailable_reasons: [], currency: "USD", priced_runs: 2, amount: 0.0191, pricing: "available",
  tokens: { ...noCost.tokens, input_tokens: 2400, cached_input_tokens: 600, output_tokens: 900 },
};

function group(label: string, extra: Partial<Group> = {}): Group {
  return {
    key: label, label, runs: 2, completed: 2, failed: 0, wall_hours: 0.5, monotonic_hours: 0.4, suspensions: 1,
    suspended_hours: 0.1, tool_calls: 12, inbox_calls: 2, analysis_receipts: 4, analysis_failures: 2,
    minutes_per_executed_analysis: 6, scripts_written: 4, plumbing_scripts: 1, plumbing_share: 0.25, compactions: 2,
    compaction_summaries: 1, compaction_fallbacks: null, provider_citation_finals: 0,
    ceremony_tail_minutes: { runs: 2, median: 3.5, mean: 3.5, max: 4 },
    board: { posts: 4, corrections: 1, posts_superseded: 1, human_marks: 1, human_marks_per_post: 0.25,
      provider_citation_posts: 0, registered_artifacts: 2, reuse: { backed: 1, unbacked: 1, backed_ratio: 0.5 }, claims: null },
    cost: noCost, posts_scope: "author",
    trend: [{ bucket: "2026-W40", runs: 1, ceremony_tail_median: 3, compactions: 1, compaction_fallbacks: null,
      minutes_per_executed_analysis: 5, monotonic_hours: 0.2 },
    { bucket: "2026-W41", runs: 1, ceremony_tail_median: 4, compactions: 1, compaction_fallbacks: null,
      minutes_per_executed_analysis: 7, monotonic_hours: 0.2 }],
    ...extra,
  };
}

const dashboard: DashboardData = {
  sequence: 9, bucket: "week",
  filters: { cohort: null, participant: null, harness: null, task_type: null },
  options: { cohorts: [{ id: "cohort_a", name: "hermes-cohort" }], participants: [{ id: "agent_a", name: "alice" }],
    harnesses: ["claude", "hermes"], task_types: ["peer_question"] },
  summary: group("all runs"),
  panels: {
    cohort: [group("hermes-cohort", { posts_scope: "run" })],
    participant: [group("alice"), group("bob", { runs: 0 })],
    harness: [group("hermes"), group("claude", { cost: priced })],
    task_type: [group("peer_question", { posts_scope: "run" })],
  },
  projection: { runs: 2, stored: 1, stale: 1, missing: 0, note: "Stale or missing rows are computed in memory." },
  frontier: { completed_questions: 4, completed_with_non_gap_item: 1, completed_with_non_gap_share: 0.25,
    items_by_kind: { open_question: 0, untestable: 1, gap: 6, proposed_experiment: 0, next_step: 2 },
    items_per_completed_question: { open_question: 0, untestable: 0.25, gap: 1.5, proposed_experiment: 0, next_step: 0.5 },
    finals_stating_next_step: 3, finals_next_step_matched: 1, finals_next_step_matched_share: 0.3333 },
  pricing: { available: false, reason: "no pricing.toml in this commons" },
  limitations: ["Counts are behaviour, not scientific value."],
};

const cell = (extra: Partial<CompareCell> = {}): CompareCell => ({
  runs: ["run_1"], participants: ["alice"], harnesses: ["hermes"], models: ["gpt"],
  yield: { posts: 1, registered_artifacts: 0, analysis_receipts: 2, analysis_failures: 1 },
  calibration: null, corrections: { corrections: 0, posts_superseded: 0, human_marks: 0 }, cost: noCost, ...extra,
});

const comparison: Comparison = {
  sequence: 9,
  cohorts: [{ id: "cohort_a", name: "hermes-cohort", runs: 3, harnesses: ["hermes"], models: ["gpt"] },
    { id: "cohort_b", name: "claude-cohort", runs: 2, harnesses: ["claude"], models: ["claude-test"] }],
  criteria: ["yield", "calibration", "corrections", "cost"],
  assignments: [
    { key: "k1", source: "request_body_sha256", excerpt: "Investigate the demo marker.", content_is_untrusted_data: true,
      cells: { cohort_a: cell(), cohort_b: cell({ cost: priced, calibration: { supported: 2, untestable: 1, descriptive: 0, withdrawn: 0, total: 3 } }) } },
    { key: "k2", source: "request_body_sha256", excerpt: "Which samples share donors?", content_is_untrusted_data: true,
      cells: { cohort_a: cell(), cohort_b: null } },
  ],
  totals: { cohort_a: cell(), cohort_b: cell({ cost: priced }) },
  shared_assignments: 1, claims_recorded: true, pricing: { available: true, currency: "USD" },
  note: "No composite score: each criterion is reported separately.", limitations: [],
};

let calls: string[] = [];
beforeEach(() => {
  calls = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    const body = url.startsWith("/api/dashboard") ? dashboard
      : url.startsWith("/api/cohorts/compare") ? comparison
      : url.startsWith("/api/cohorts") ? { items: [
        { id: "cohort_a", name: "hermes-cohort", created: "t", runs: 3, assignments: 2, note: "" },
        { id: "cohort_b", name: "claude-cohort", created: "t", runs: 2, assignments: 2, note: "" }] }
      : {};
    return new Response(JSON.stringify(body), { status: 200 });
  }) as typeof fetch;
});

function show(path = "/dashboard") {
  return render(<MemoryRouter initialEntries={[path]}><Dashboard /></MemoryRouter>);
}

test("panels show behaviour per group and unavailable values are never zero", async () => {
  show();
  await screen.findByText("Evaluation dashboard");
  await screen.findByLabelText("Summary");
  expect(screen.getByText(/1 of 2 runs computed in memory/)).toBeTruthy();
  const panels = screen.getAllByRole("article");
  expect(panels.map((p) => p.getAttribute("aria-label"))).toEqual(["alice", "bob"]);
  const alice = within(panels[0]);
  expect(alice.getByText("Ceremony tail (median min)")).toBeTruthy();
  expect(alice.getByLabelText("Reuse links: 1 backed, 1 unbacked")).toBeTruthy();
  // Compaction fallbacks were never reported: shown as unavailable, not a zero line.
  expect(alice.getByText(/Compaction fallbacks/).textContent).toContain("unavailable");
  // No pricing table and no telemetry: the cost table says so explicitly.
  const cost = document.querySelector("table.cost-table") as HTMLTableElement;
  expect(within(cost).getAllByText("unavailable").length).toBeGreaterThan(3);
  expect(within(cost).getAllByText(/harness did not report/).length).toBeGreaterThan(0);
});

test("unrecorded clocks and compactions show as unavailable in the summary, never 0 (spec v2 C10)", async () => {
  const blind = group("all runs", { suspensions: null, suspended_hours: null, clock_unavailable_runs: 2, compactions: null,
    compaction_unavailable_runs: 2, tool_calls: null, analysis_receipts: null, analysis_failures: null });
  globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ ...dashboard, summary: blind }), { status: 200 })) as typeof fetch;
  show();
  const summary = await screen.findByLabelText("Summary");
  const stat = (label: string) => within(summary).getByText(label).parentElement as HTMLElement;
  expect(stat("Suspensions").textContent).toMatch(/^Suspensionsunavailable \(unavailable h\) · 2 without clocks$/);
  expect(stat("Compactions (fallbacks)").textContent).toContain("unavailable (unavailable) · 2 runs unavailable");
  expect(stat("Analyses (failed)").textContent).toBe("Analyses (failed)unavailable (unavailable)");
  expect(stat("Tool / inbox calls").textContent).toBe("Tool / inbox callsunavailable / 2");
});

test("tabs switch the small multiples and filters live in the request URL", async () => {
  show("/dashboard?harness=claude");
  await screen.findByLabelText("Summary");
  expect(calls.some((c) => c === "/api/dashboard?harness=claude")).toBe(true);
  fireEvent.click(screen.getByRole("tab", { name: /Harness/ }));
  const labels = screen.getAllByRole("article").map((p) => p.getAttribute("aria-label"));
  expect(labels).toEqual(["hermes", "claude"]);
  expect(screen.getAllByText(/0\.0191 USD/).length).toBeGreaterThan(0);
  fireEvent.change(screen.getByLabelText(/Task type/), { target: { value: "peer_question" } });
  await waitFor(() => expect(calls.some((c) => c.includes("task_type=peer_question"))).toBe(true));
});

test("cohort comparison keeps criteria in separate columns with no composite score", async () => {
  show();
  await screen.findByText("Compare cohorts");
  await screen.findByText("claude-cohort");
  fireEvent.click(screen.getByLabelText(/hermes-cohort/));
  expect(calls.some((c) => c.startsWith("/api/cohorts/compare"))).toBe(false);
  fireEvent.click(screen.getByLabelText(/claude-cohort/));
  await waitFor(() => expect(calls).toContain("/api/cohorts/compare?ids=cohort_a%2Ccohort_b"));
  await waitFor(() => expect(document.querySelector("table.compare")).not.toBeNull());
  const compare = document.querySelector("table.compare") as HTMLTableElement;
  const headers = Array.from(compare.querySelectorAll("thead th")).map((th) => th.textContent);
  expect(headers.filter((h) => h === "Yield")).toHaveLength(2);
  expect(headers.filter((h) => h === "Cost")).toHaveLength(2);
  expect(headers.join(" ")).not.toMatch(/score|rank|total score/i);
  expect(within(compare).getByText("not attempted by this cohort")).toBeTruthy();
  expect(within(compare).getAllByText(/unavailable \(no ledger claims\)/).length).toBeGreaterThan(0);
  expect(within(compare).getByText(/supported 2/)).toBeTruthy();
  expect(compare.querySelectorAll('[data-untrusted="true"]').length).toBe(2);
});

test("number coverage per cohort: share of numbers with a pointer at the number (C11)", async () => {
  const numbers = { finals: 54, numbers: 936, scopes: { cell: 0, claim: 0, line: 0, post: 914, none: 22 },
    statuses: { verified: 0, unverified: 0, post_scoped: 914, unpointed: 22 }, number_level: 0,
    number_level_share: 0, claim_share: 0, cell_share: 0, verified_share: 0 };
  const withNumbers = (g: Group, value: typeof numbers | null): Group => ({ ...g, board: { ...g.board, numbers: value } });
  Object.assign(dashboard, {
    summary: withNumbers(dashboard.summary, numbers),
    panels: { ...dashboard.panels, cohort: [withNumbers(dashboard.panels.cohort[0], null)] },
  });
  show();
  const table = await screen.findByRole("table", { name: "Number coverage" });
  const [summary, cohort] = within(table).getAllByRole("row").slice(1);
  expect(summary.textContent).toContain("936");
  expect(summary.textContent).toContain("0%");
  expect(summary.textContent).toContain("914");
  expect(cohort.textContent).toContain("hermes-cohort");
  expect(cohort.textContent).toContain("unavailable");  // no final in the group: unavailable, never zero
  expect(screen.getByText("Numbers pointed at the number").parentElement?.textContent).toContain("(0/936)");
});

test("number coverage keeps author pointers, curated pointers and unpointed numbers apart (v3 B6, G2)", async () => {
  const numbers = { finals: 5, numbers: 50, scopes: { cell: 4, claim: 0, line: 0, text: 3, curated: 20, post: 20, none: 3 },
    statuses: { verified: 27, unverified: 0, post_scoped: 20, unpointed: 3 }, number_level: 7, number_level_share: 0.14,
    claim_share: 0, cell_share: 0.08, verified_share: 0.08, author_verified: 4, text_verified: 3, curated_verified: 20,
    pointers: { author: 7, curated: 20, unpointed: 23, unlocatable: 6 } };
  Object.assign(dashboard, { summary: { ...dashboard.summary, board: { ...dashboard.summary.board, numbers } } });
  show();
  const table = await screen.findByRole("table", { name: "Number coverage" });
  const [summary] = within(table).getAllByRole("row").slice(1);
  expect(summary.textContent).toContain("4 / 0 / 0 / 3");
  expect(summary.textContent).toContain("8%");                     // verified_share: the author's cell/claim/line only
  expect(summary.textContent).toContain("3 text matches apart");
  expect(summary.textContent).toContain("20 verified; a person's, not the author's");
  expect(summary.textContent).toContain("6 marked unlocatable");
});

test("claims authoring per cohort: claims per post, evidence posts with claims and pointer scopes (V1)", async () => {
  const authoring = { posts: 10, posts_with_claims: 4, claims: 12, claims_per_post: 1.2, evidence_posts: 5,
    evidence_posts_with_claims: 4, evidence_posts_with_claims_share: 0.8, claims_refused: 1, pointers: 20,
    pointer_kinds: { artifact: 2, locator: 15, post: 1, receipt: 0, accession: 2 },
    pointer_scopes: { cell: 14, key: 1, line: 0, record: 5, invalid: 0 }, cell_pointer_share: 0.7 };
  const numbers = { finals: 3, numbers: 40, scopes: { cell: 10, claim: 12, line: 0, post: 10, none: 8 },
    statuses: { verified: 20, unverified: 2, post_scoped: 10, unpointed: 8 }, number_level: 22,
    number_level_share: 0.55, claim_share: 0.3, cell_share: 0.25, verified_share: 0.5 };
  Object.assign(dashboard, {
    summary: { ...dashboard.summary, board: { ...dashboard.summary.board, authoring, numbers } },
  });
  show();
  const table = await screen.findByRole("table", { name: "Claims authoring" });
  const [summary] = within(table).getAllByRole("row").slice(1);
  expect(summary.textContent).toContain("(12/10)");
  expect(summary.textContent).toContain("80%");
  expect(summary.textContent).toContain("(4/5)");
  expect(summary.textContent).toContain("14 / 1 / 0 / 5");
  expect(summary.textContent).toContain("30%");
  expect(summary.textContent).toContain("25%");
});

test("frontier closure: items per completed question by kind and finals whose next step has an item (v3 G1)", async () => {
  show();
  const table = await screen.findByRole("table", { name: "Frontier closure" });
  const rows = within(table).getAllByRole("row").slice(1).map((r) => r.textContent);
  expect(rows).toContain("next step20.50");
  expect(rows).toContain("gap61.50");
  expect(screen.getByText(/1 of 4 completed questions record an item beyond gaps/).textContent).toContain(
    "1 of 3 finals");
});

test("turn economics per harness and per skill version, skills against budget and cost per datum (V13)", async () => {
  const economics = {
    runs: 2, recorded_runs: 2, unrecorded_runs: 0, reindexed_runs: 1,
    context: { unit: "turn", records: 2, mean_input_tokens: 1500, max_input_tokens: 1800, model_calls: null },
    composition: { bytes_measured: { system_prompt: null, delivery_prompt: 7000, skills: 10240, tool_outputs: 51200,
      summaries: null, conversation: null }, complete_runs: 0, shares: null },
    compactions: { stream_markers: 2, summaries: null, fallbacks: null, fallback_detection: "marker_match" },
    time: { runs: 2, generation_minutes: 30, tool_wait_minutes: 10, tool_wait_share: 0.25 },
    orientation: { runs: 2, help_calls_per_turn: 1.5, reorientation_calls_per_turn: 7, by_kind: { inbox: 4 } },
    ceremony_tail_minutes: { runs: 2, median: 5.1 },
    skill_reads: { runs: 2, total: 3, per_turn: { "bio-research": 1 } },
    tokens: 4000, tokens_reported_runs: 2,
    useful_data: { registered_artifacts: 4, verified_claims: 0, promoted_frontier_items: 0 },
    tokens_per: { registered_artifact: 1000, verified_claim: null, promoted_frontier_item: null },
  };
  Object.assign(dashboard, {
    summary: { ...dashboard.summary, turn_economics: economics },
    panels: { ...dashboard.panels, harness: [{ ...dashboard.panels.harness[0], turn_economics: economics }, dashboard.panels.harness[1]] },
    economics: {
      skill_versions: [{ key: "e0f9879bfc1c", label: "e0f9879bfc1c", first: "t", harnesses: ["hermes"], turn_economics: economics }],
      skills: { runs: 2, items: [{ skill: "bio-research", bytes: 12185, budget: 14336, reads: 2, reads_per_turn: 1 }] },
      limitations: [],
    },
  });
  show();
  const byHarness = await screen.findByRole("table", { name: "Harness" });
  const [summary, hermes, claude] = within(byHarness).getAllByRole("row").slice(1);
  expect(summary.textContent).toContain("2 of 2");
  expect(hermes.textContent).toContain("per turn");
  expect(hermes.textContent).toContain("system prompt unmeasured");
  expect(within(hermes).getByRole("img", { name: "Generation 30 min, tool wait 10 min" })).toBeTruthy();
  expect(claude.textContent).toContain("unavailable");  // no record: unavailable, never zero
  const versions = screen.getByRole("table", { name: "Skill version" });
  expect(versions.textContent).toContain("e0f9879bfc1c (hermes)");
  const skills = screen.getByRole("table", { name: "Skill sizes and reads" });
  expect(skills.textContent).toContain("12185 / 14336");
  expect(within(skills).getByRole("img", { name: "12185 of 14336 budget bytes" })).toBeTruthy();
  const datum = screen.getByRole("table", { name: "Cost per useful datum" });
  const [, hermesDatum] = within(datum).getAllByRole("row").slice(1);
  expect(hermesDatum.textContent).toContain("1000");
  expect(within(hermesDatum).getAllByText("unavailable").length).toBe(2);
});
