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
