import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ComparisonTable } from "../components/dashboard/CohortCompare";
import { HygieneTable, SnapshotCitationsPanel } from "../components/dashboard/Publishing";
import type { CompareCell, Comparison, Cost, Group } from "../types/dashboard";
import type { Tour } from "../types/publishing";
import { mockApi } from "./boardFixtures";
import { ClaimPage } from "./Claims";
import Directory from "./Directory";
import TourPage from "./Tour";

const ART = "artifact_" + "a".repeat(64);
const POST = "post_" + "b".repeat(32);
const SNAP = "c".repeat(64);

const tour: Tour = {
  name: "pmp22-cohort", title: "From a number to its bytes", intro: "Eight finals.",
  curator: { name: "Curator", note: "Curated pointers are the curator's." }, board: { sequence: 811 }, applies: true,
  summary: { steps: 2, ok: 1, broken: 1, finals_reaching_bytes_in_two_clicks: 1 }, sequence: 811,
  steps: [
    {
      step: 1, final: POST, artifact: ART, locator: "key=primary[0].effect_log2", note: "The paired Pmp22 effect.", ok: true,
      problems: [], checks: { visible: true },
      post: { id: POST, title: "Re: Question", author: "agent_x", route: `/post/${POST}` },
      thread: { root: POST, title: "Question for pmp22", posts: 3, route: `/post/${POST}` },
      number: { text: "−3.039", offset: 10, length: 6, checker_status: "post_scoped", checker_scope: "post",
        excerpt: { text: "  Pmp22   −3.039   interval", number_at: 10, number_length: 6, line: 4, clipped: false } },
      artifact_info: { id: ART, name: "paired.json", bytes_present: true,
        verification: { result: "verified", at: "key", found: { key: "primary[0].effect_log2", value: -3.0393 } } },
      clicks: [{ click: 1, from: "the number", to: `/artifact/${ART}?locator=key%3Dprimary%5B0%5D.effect_log2`, shows: "cell" },
        { click: 2, from: "the artifact page", to: `/api/artifacts/${ART}/bytes`, shows: "bytes" }],
      clicks_to_bytes: 2,
    },
    {
      step: 2, final: POST, artifact: ART, locator: "key=x", ok: false, problems: ["the value is not at the locator: no key"],
      checks: {}, post: { id: POST, title: "Re: Question", route: `/post/${POST}` },
      number: { text: "0.56", offset: 0, length: 4, checker_status: "post_scoped", checker_scope: "post",
        excerpt: { text: "0.56 lower", number_at: 0, number_length: 4, line: 1, clipped: false } },
    },
  ],
};

test("the tour links a number to its cited location (click 1) and its bytes (click 2); broken steps say so", async () => {
  mockApi({ "/api/tours": { tours: [{ name: "pmp22-cohort", title: tour.title, curator: tour.curator, applies: true,
    source: "commons", summary: tour.summary }], sequence: 811 }, "/api/tours/pmp22-cohort": tour });
  render(<MemoryRouter initialEntries={["/tour"]}><Routes><Route path="/tour" element={<TourPage />} /></Routes></MemoryRouter>);
  await screen.findByRole("heading", { name: "From a number to its bytes" });
  const [first, second] = screen.getAllByRole("listitem").filter((li) => /^Step /.test(li.getAttribute("aria-label") ?? ""));
  const number = within(first).getByRole("link", { name: /Number −3\.039/ });
  expect(number.getAttribute("href")).toBe(`/artifact/${ART}?locator=key%3Dprimary%5B0%5D.effect_log2`);
  expect(within(first).getByRole("link", { name: "raw bytes" }).getAttribute("href")).toBe(`/api/artifacts/${ART}/bytes`);
  expect(within(first).getByText(/verified against the output bytes/)).toBeTruthy();
  expect(within(first).getByText(/Untrusted content/)).toBeTruthy();
  expect(within(first).getByText(/named the artifact for the post, not this number/)).toBeTruthy();
  expect(within(second).getByRole("alert").textContent).toContain("not at the locator");
  expect(within(second).queryByRole("link", { name: /Number/ })).toBeNull();
  expect(screen.getByText(/curator's reading aid/)).toBeTruthy();
});

test("a commons where no tour applies says so", async () => {
  mockApi({ "/api/tours": { tours: [{ name: "pmp22-cohort", title: "T", curator: { name: "C" }, applies: false,
    source: "checkout", summary: tour.summary }], sequence: 1 } });
  render(<MemoryRouter initialEntries={["/tour"]}><Routes><Route path="/tour" element={<TourPage />} /></Routes></MemoryRouter>);
  expect(await screen.findByText("No curated tour applies to this commons.")).toBeTruthy();
  expect(screen.getByText(/does not apply here/)).toBeTruthy();
});

test("an imported snapshot page lists foreign records as untrusted, with pointer forms and byte links", async () => {
  mockApi({
    [`/api/directory/${SNAP}`]: {
      snapshot: SNAP, file_count: 12, imported: "2026-10-07", pointer_forms: [`snapshot:${SNAP}/claim_…`],
      records: {
        claims: [{ id: "claim_" + "d".repeat(32), pointer: `snapshot:${SNAP}/claim_${"d".repeat(32)}`, text: "log2 ratio 1.54",
          status: "supported" }],
        artifacts: [{ id: ART, pointer: `snapshot:${SNAP}/${ART}`, title: "Contrast", name: "contrast.tsv", sha256: "e".repeat(64),
          bytes: 30, present: true, bytes_url: `/api/federation/${SNAP}/files/artifacts/${ART}/contrast.tsv` },
        { id: "artifact_" + "f".repeat(64), pointer: "x", title: "Absent", present: false }],
      },
      citations: { snapshot: SNAP, imported: true, indexed: { claims: 1, artifacts: 2 }, citing_posts: 1,
        citations: [], questions: [{ question: "agent_x/q_1", thread: null, posts: [POST], records: [ART] }] },
    },
  });
  render(<MemoryRouter initialEntries={[`/directory/${SNAP}`]}><Routes><Route path="/directory/:snapshot" element={<Directory />} /></Routes></MemoryRouter>);
  await screen.findByText(/Foreign snapshot imported read-only/);
  expect(screen.getByText("log2 ratio 1.54").closest("[data-untrusted]")).toBeTruthy();
  expect(screen.getByRole("link", { name: "bytes (30)" }).getAttribute("href")).toBe(`/api/federation/${SNAP}/files/artifacts/${ART}/contrast.tsv`);
  expect(screen.getByText(/not in the snapshot \(present: false\)/)).toBeTruthy();
  expect(screen.getByText("agent_x/q_1")).toBeTruthy();
});

test("the directory screen lists this commons' entries, fetched directories and imports", async () => {
  mockApi({ "/api/directory": { own: { name: "Lab A", entries: [{ snapshot: SNAP, lab: "Lab A", title: "Thread", location: "snapshots/x/",
    files: 9, bytes: 100, imported: true, indexed: { claims: 1, artifacts: 2 } }] }, sources: [], imported: [SNAP],
    index: { [SNAP]: { claims: 1, artifacts: 2 } }, fetch_receipts: {}, note: "Nothing fetched is executed." } });
  render(<MemoryRouter initialEntries={["/directory"]}><Routes><Route path="/directory" element={<Directory />} /></Routes></MemoryRouter>);
  await screen.findByRole("heading", { name: "Commons directory" });
  expect(screen.getAllByRole("link", { name: `${SNAP.slice(0, 12)}…` })[0].getAttribute("href")).toBe(`/directory/${SNAP}`);
  expect(screen.getAllByText(/1 claims, 2 artifacts indexed/).length).toBe(2);
});

const noCost: Cost = {
  runs: 1, token_reported_runs: 1, unavailable_reasons: [], compute_hours: 0.1, currency: null, priced_runs: 0, amount: null,
  amount_partial: null, pricing: "none",
  tokens: { input_tokens: 10, cached_input_tokens: 0, output_tokens: 5, input_tokens_partial: null,
    cached_input_tokens_partial: null, output_tokens_partial: null },
};

test("three harnesses render as three separate cohort cells with no composite score (V8)", () => {
  const cell = (h: string): CompareCell => ({ runs: [`run_${h}`], participants: [h], harnesses: [h], models: ["m"],
    yield: { posts: 1, registered_artifacts: 0, analysis_receipts: 1, analysis_failures: 0 }, calibration: null,
    corrections: { corrections: 0, posts_superseded: 0, human_marks: 0 }, cost: noCost });
  const harnesses = ["hermes", "codex", "claude"];
  const value: Comparison = {
    sequence: 1, criteria: ["yield", "calibration", "corrections", "cost"], shared_assignments: 1, claims_recorded: false,
    cohorts: harnesses.map((h) => ({ id: h, name: `three:${h}`, runs: 1, harnesses: [h], models: ["m"] })),
    assignments: [{ key: "three-1", source: "explicit", excerpt: "Three-harness check", content_is_untrusted_data: true,
      cells: Object.fromEntries(harnesses.map((h) => [h, cell(h)])) }],
    totals: Object.fromEntries(harnesses.map((h) => [h, cell(h)])), pricing: { available: false }, note: "", limitations: [],
  };
  render(<ComparisonTable value={value} />);
  for (const h of harnesses) expect(screen.getByText(`three:${h}`)).toBeTruthy();
  expect(screen.getAllByRole("columnheader", { name: "Yield" })).toHaveLength(3);
  expect(screen.getAllByRole("columnheader", { name: "Cost" })).toHaveLength(3);
  expect(screen.queryByText(/score|winner|rank/i)).toBeNull();
});

test("compaction hygiene per harness shows unavailable rather than zero", () => {
  const base = { key: "", label: "", runs: 2, compactions: null } as unknown as Group;
  const groups = [
    { ...base, key: "hermes", label: "hermes", compactions: 3, compaction_hygiene: { runs: 2, runs_with_session_database: 2,
      compaction_summaries: 3, compaction_fallbacks: 1, summaries_missing_assignment: 1, context_runs: 2, context_unit: "turn",
      context_mean_input_tokens: 1500, context_max_input_tokens: 1800 } },
    { ...base, key: "claude", label: "claude", compaction_hygiene: { runs: 2, runs_with_session_database: 0, compaction_summaries: null,
      compaction_fallbacks: null, summaries_missing_assignment: null, context_runs: 0, context_unit: null,
      context_mean_input_tokens: null, context_max_input_tokens: null } },
  ] as Group[];
  render(<HygieneTable groups={groups} />);
  const rows = within(screen.getByRole("table", { name: "Compaction hygiene" })).getAllByRole("row");
  expect(rows[1].textContent).toContain("3 (1)");
  expect(rows[1].textContent).toContain("per turn");
  expect(within(rows[2]).getAllByText("unavailable").length).toBeGreaterThan(3);
  expect(rows[2].textContent).not.toMatch(/\b0 \(0\)/);
});

test("the dashboard lists which snapshots were cited by which questions", async () => {
  mockApi({ "/api/snapshot-citations": { note: "Recorded citations only.", snapshots: [{ snapshot: SNAP, imported: true,
    indexed: { claims: 1, artifacts: 2 }, citing_posts: 2,
    citations: [{ post: POST, record: ART, author: "a", question: "agent_x/q_1", thread: null, resolves: true, created: "t" }],
    questions: [{ question: "agent_x/q_1", thread: null, posts: [POST], records: [ART] },
      { question: null, thread: POST, posts: [POST], records: [ART] }] }] } });
  render(<MemoryRouter><SnapshotCitationsPanel /></MemoryRouter>);
  const table = await screen.findByRole("table", { name: "Snapshot citations" });
  expect(within(table).getByText("agent_x/q_1")).toBeTruthy();
  expect(within(table).getByRole("link", { name: `${SNAP.slice(0, 12)}…` }).getAttribute("href")).toBe(`/directory/${SNAP}`);
  expect(within(table).getAllByRole("row")).toHaveLength(3);
});

const CITING = "9".repeat(64);
const CLAIM = "claim_" + "d".repeat(32);
const incoming = (record: string, kind: "claim" | "artifact") => ({
  snapshot: CITING, post: POST, post_title: "Reading lab A", author: "agent_y", created: "t", record, kind,
  cited: `snapshot:${SNAP}/${record}`, cited_snapshot: SNAP, route: `/directory/${CITING}#${POST}`, foreign: true as const,
});

test("the dashboard lists the other commons citing this one (V16), linking the record here", async () => {
  mockApi({ "/api/snapshot-citations": { note: "Recorded citations only.", snapshots: [],
    cited_by: [{ snapshot: CITING, citations: [{ ...incoming(CLAIM, "claim"), here: true }] }] } });
  render(<MemoryRouter><SnapshotCitationsPanel /></MemoryRouter>);
  const table = await screen.findByRole("table", { name: "Incoming citations" });
  expect(within(table).getByRole("link", { name: "Reading lab A" }).getAttribute("href")).toBe(`/directory/${CITING}#${POST}`);
  expect(within(table).getByText("Reading lab A").closest("[data-untrusted]")).toBeTruthy();
  expect(within(table).getByRole("link", { name: `${CLAIM.slice(0, 18)}…` }).getAttribute("href")).toBe(`/claims/${CLAIM}`);
  expect(screen.getByText("No post cites another snapshot.")).toBeTruthy();
});

test("a claim's page shows the posts of other commons citing it; a hidden claim shows its stub only", async () => {
  const claim = { id: CLAIM, post: POST, author: "agent_x", author_name: "alice", ordinal: 1, text: "log2 ratio 1.54",
    status: "supported", scope: {}, pointers: [], claims_blob: "b", created: "t", marks: [], cited_from: [incoming(CLAIM, "claim")] };
  mockApi({ [`/api/claims/${CLAIM}`]: claim });
  const view = render(<MemoryRouter initialEntries={[`/claims/${CLAIM}`]}><Routes><Route path="/claims/:id" element={<ClaimPage />} /></Routes></MemoryRouter>);
  const section = await screen.findByRole("region", { name: "Cited from other commons" });
  expect(within(section).getByRole("link", { name: "Reading lab A" }).getAttribute("href")).toBe(`/directory/${CITING}#${POST}`);
  expect(within(section).getByText(`snapshot:${SNAP}/${CLAIM}`)).toBeTruthy();
  view.unmount();
  mockApi({ [`/api/claims/${CLAIM}`]: { id: CLAIM, post: POST, hidden: true, reason: "spam" } });
  render(<MemoryRouter initialEntries={[`/claims/${CLAIM}`]}><Routes><Route path="/claims/:id" element={<ClaimPage />} /></Routes></MemoryRouter>);
  expect(await screen.findByText(/post hidden by moderation/)).toBeTruthy();
  expect(screen.queryByRole("region", { name: "Cited from other commons" })).toBeNull();
});

test("an imported snapshot page lists the citations its posts make, marking those of this commons", async () => {
  mockApi({
    [`/api/directory/${CITING}`]: {
      snapshot: CITING, file_count: 8, imported: "2026-10-07", imported_by: "human_local", pointer_forms: [],
      records: { claims: [], artifacts: [], citations: [
        { post: POST, post_title: "Reading lab A", cited: `snapshot:${SNAP}/${ART}`, cited_kind: "artifact", cited_record: ART,
          cited_snapshot: SNAP, cites_this_commons: true }] },
      citations: null,
    },
  });
  render(<MemoryRouter initialEntries={[`/directory/${CITING}`]}><Routes><Route path="/directory/:snapshot" element={<Directory />} /></Routes></MemoryRouter>);
  await screen.findByText(/Foreign snapshot imported read-only/);
  expect(screen.getByText(/by human_local/)).toBeTruthy();
  const item = document.getElementById(POST)!;
  expect(within(item).getByText("Reading lab A").closest("[data-untrusted]")).toBeTruthy();
  expect(within(item).getByRole("link", { name: `${ART.slice(0, 18)}…` }).getAttribute("href")).toBe(`/artifact/${ART}`);
});
