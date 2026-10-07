import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Frontier from "./Frontier";
import type { FrontierItem } from "../types/ledger";

const watch = { watchers: [], runs: 0, found: 0, last_run: null };

function item(over: Partial<FrontierItem>): FrontierItem {
  return {
    id: "frontier_a", question: "q_a", question_title: "Marker question", author: "agent_a", author_name: "alice",
    kind: "proposed_experiment", text: "Measure the marker by qPCR with donor-matched samples.", status: "open",
    blocked_by: null, watcher_query: null, missing_measurement: "Donor identity per sample", pointers: [], detail: {},
    created: "2026-10-01T00:00:00+00:00", updated: "2026-10-01T00:00:00+00:00", promoted_to: null, watch, ...over,
  };
}

const items = [
  item({}),
  item({ id: "frontier_b", question: "q_b", question_title: "Normalization", author: "agent_b", author_name: "bob",
         text: "Measure the marker by qPCR using donor-matched samples and a spike-in.", watcher_query: { text: "spike-in" } }),
  item({ id: "frontier_c", kind: "untestable", text: "Knockdown effect cannot be tested.", blocked_by: "knockdown counts",
         status: "candidate_evidence", candidate_evidence: { set_by: "watcher", records: [{ by: "watcher", run: "watcher_run_1", post: "post_notice" }] },
         pointers: [{ kind: "post", id: "post_gone", present: false }, { kind: "post", id: "post_here", present: true }],
         post_present: false }),
];

const routes: Record<string, unknown> = {
  "/api/frontier": {
    items, total: 3, policy: "Items are agent-authored.",
    kinds: ["open_question", "untestable", "gap", "proposed_experiment", "next_step"],
    statuses: ["open", "candidate_evidence", "promoted", "closed", "withdrawn"],
    by_kind: { open_question: [], untestable: ["frontier_c"], gap: [], proposed_experiment: ["frontier_a", "frontier_b"], next_step: [] },
    by_blocker: [{ blocked_by: "knockdown counts", items: ["frontier_c"] }, { blocked_by: null, items: ["frontier_a", "frontier_b"] }],
    clusters: [{
      id: "cluster_1", kind: "proposed_experiment", items: ["frontier_a", "frontier_b"], questions: ["q_a", "q_b"],
      shared_terms: ["donor", "qpcr"], pairs: [{ items: ["frontier_a", "frontier_b"], jaccard: 0.875, shared_terms: ["donor", "qpcr"] }],
      confirmations: [], basis: "normalized token sets",
    }],
  },
  "/api/wishlist": {
    total: 1, grouping: "normalized exact text; no synonym merging",
    items: [{ text: "Donor identity per sample", normalized: "donor identity per sample", distinct_questions: 2,
              questions: [{ question: "q_a", author: "agent_a", title: "Marker question" }, { question: "q_b", author: "agent_b", title: "Normalization" }],
              sources: [{ kind: "frontier_item", question: "q_a", author: "agent_a" }] }],
  },
  "/api/participants": { items: [] },
};

let calls: { url: string; method: string; body?: string }[] = [];

beforeEach(() => {
  calls = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", body: init?.body as string | undefined });
    if (url === "/api/watchers" && init?.method === "POST") return new Response(JSON.stringify({ id: "watcher_1" }), { status: 200 });
    if (url.startsWith("/api/watchers?")) {
      return new Response(JSON.stringify({ items: [], providers: ["europepmc", "pride"], cadence: "operator cron" }), { status: 200 });
    }
    if (url === "/api/frontier/clusters/confirm") return new Response(JSON.stringify({ seq: 9 }), { status: 200 });
    return new Response(JSON.stringify(routes[url.split("?")[0]] ?? {}), { status: 200 });
  }) as typeof fetch;
});

test("items are grouped by kind with promotion and watcher actions", async () => {
  render(<MemoryRouter initialEntries={["/frontier"]}><Frontier /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: /Proposed experiments/ })).toBeTruthy();
  expect(screen.getByRole("heading", { name: /Untestable branches/ })).toBeTruthy();
  expect(screen.getAllByRole("button", { name: "Promote" }).length).toBe(3);
  fireEvent.click(within(screen.getByLabelText("Frontier item frontier_b")).getByRole("button", { name: "Watchers" }));
  // The discovery area's panel: a provider from the server's list, a cadence, and the agent-recorded query prefilled.
  await screen.findByRole("option", { name: "pride" });
  expect((screen.getByLabelText("Watcher query") as HTMLInputElement).value).toBe("spike-in");
  fireEvent.click(screen.getByRole("button", { name: "Attach watcher" }));
  expect(await screen.findByText(/Watcher attached/)).toBeTruthy();
  const sent = JSON.parse(calls.find((c) => c.url === "/api/watchers" && c.method === "POST")!.body!);
  expect(sent).toMatchObject({ item: "frontier_b", provider: "europepmc", query: { query: "spike-in", filters: {} } });
});

test("grouping by blocker uses the recorded blocker text", async () => {
  render(<MemoryRouter initialEntries={["/frontier?group=blocker"]}><Frontier /></MemoryRouter>);
  expect(await screen.findByText("Blocked by: knockdown counts")).toBeTruthy();
  expect(screen.getByText("No blocker recorded")).toBeTruthy();
});

test("cluster suggestions show shared terms and record a person's confirmation", async () => {
  render(<MemoryRouter initialEntries={["/frontier?tab=clusters"]}><Frontier /></MemoryRouter>);
  expect(await screen.findByText("qpcr")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Confirm same experiment" }));
  await waitFor(() => expect(calls.some((c) => c.url === "/api/frontier/clusters/confirm" && c.method === "POST")).toBe(true));
  const sent = JSON.parse(calls.find((c) => c.url === "/api/frontier/clusters/confirm")!.body!);
  expect(sent.items).toEqual(["frontier_a", "frontier_b"]);
  expect(await screen.findByText(/items are not merged/)).toBeTruthy();
});

test("candidate evidence says who set it and post pointers say whether the post is on the board", async () => {
  render(<MemoryRouter initialEntries={["/frontier"]}><Frontier /></MemoryRouter>);
  const card = within(await screen.findByLabelText("Frontier item frontier_c"));
  const badge = card.getByText("set by watcher");
  expect(badge.closest("a")?.getAttribute("href")).toBe("/post/post_notice");
  expect(card.getByText("not on this board", { exact: false, selector: ".ledger-badge" })).toBeTruthy();
  expect(card.queryByRole("link", { name: "post_gone" })).toBeNull();
  expect(card.getByRole("link", { name: "post_here" }).getAttribute("href")).toBe("/post/post_here");
  expect(card.getByText("The post this item names is not on this board.")).toBeTruthy();
  // Items in other states carry no setter badge.
  expect(within(screen.getByLabelText("Frontier item frontier_a")).queryByText(/^set by/)).toBeNull();
});

test("wishlist links each measurement to the questions that need it", async () => {
  render(<MemoryRouter initialEntries={["/frontier?tab=wishlist"]}><Frontier /></MemoryRouter>);
  expect(await screen.findByText("Donor identity per sample")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Normalization" }).getAttribute("href")).toBe("/question/agent_b/q_b");
  // V5: the proposal export, Markdown and static HTML.
  expect(screen.getByRole("link", { name: "Markdown" }).getAttribute("href")).toBe("/api/wishlist/export?format=md&download=true");
  expect(screen.getByRole("link", { name: "HTML" }).getAttribute("href")).toBe("/api/wishlist/export?format=html");
});

const request = { id: "request_1", post: "post_req", target: "agent_b", target_name: "bob", state: "pending",
  task_type: "scouting", budget: { minutes: 20 }, deadline: null, answer: null, created: "2026-10-02T00:00:00+00:00" };
const scouted = item({ id: "frontier_s", kind: "gap", text: "Per-donor counts.", status: "candidate_evidence",
  candidate_evidence: { set_by: "scouting", records: [{ by: "scouting" }] },
  datasets: [
    { accession: "GSE2", eligible: false, reason: "No donor identity.", receipt: { kind: "receipt", id: "a".repeat(64) },
      recorded_by: "agent_b", source: "work_event", event: "event_1" },
    { accession: "GSE4", eligible: true, reason: "Donor-matched.", source: "answer_block", post: "post_answer" },
  ],
  datasets_summary: { inspected: 2, eligible: 1, rejected: 1, withheld: 0 } });
const column = (key: string, label: string, extra: object = {}) => ({
  key, label, items: [], experiments: [], count: 0, budget: {}, requests: 0, targets: [], ...extra });
routes["/api/frontier/board"] = {
  total: 4, experiments: 1, policy: "Columns follow recorded states.",
  by_kind: {}, by_column: {}, allowance: { allowance: { minutes: 120 }, spent: { minutes: 20 }, remaining: { minutes: 100 }, unlimited: false },
  columns: [
    column("open", "Open", { items: [{ ...item({}), column: "open" }], count: 1 }),
    column("blocked", "Blocked", { items: [{ ...items[2], status: "open", candidate_evidence: null, column: "blocked" }], count: 1 }),
    column("candidate_evidence", "Candidate evidence", { items: [{ ...scouted, column: "candidate_evidence" }], count: 1 }),
    column("promoted", "Promoted", {
      items: [{ ...item({ id: "frontier_p", status: "promoted", promoted_to: "request_1" }), column: "promoted", request }],
      experiments: [{ id: "experiment_1", kind: "proposed_experiment", text: "Shared proposed experiment confirmed across 2 questions",
        status: "promoted", column: "promoted", questions: ["q_a", "q_b"], confirmations: [], shared_terms: ["qpcr"],
        items: [{ id: "frontier_a", present: true, question: "q_a", question_title: "Marker question", author: "agent_a", status: "open" },
                { id: "frontier_b", present: true, question: "q_b", question_title: "Normalization", author: "agent_b", status: "open" }],
        promoted_to: "request_2", request: { ...request, id: "request_2", task_type: "research", state: "running" },
        created: "2026-10-02T00:00:00+00:00", updated: "2026-10-02T00:00:00+00:00", note: "nothing was merged" }],
      count: 2, budget: { minutes: 40 }, requests: 2, targets: [{ target: "agent_b", name: "bob", requests: 2 }] }),
    column("closed", "Closed", { withdrawn: 0 }),
  ],
};

test("board mode shows columns by state with requests, budgets, targets and promotion from a card", async () => {
  render(<MemoryRouter initialEntries={["/frontier?tab=board"]}><Frontier /></MemoryRouter>);
  const promoted = within(await screen.findByLabelText("Promoted column"));
  expect(promoted.getByText(/2 requests · budget 40 minutes · targets bob \(2\)/)).toBeTruthy();
  const card = within(promoted.getByLabelText("Card frontier_p"));
  expect(card.getByLabelText("Promotion request").textContent).toMatch(/scouting.*bob.*20 minutes.*pending/);
  expect(card.queryByRole("button", { name: "Promote" })).toBeNull(); // promoted cards are not promoted twice
  // A shared experiment lists its member questions; its running request blocks a second promotion.
  const experiment = within(promoted.getByLabelText("Shared experiment experiment_1"));
  expect(experiment.getByRole("link", { name: "Normalization" }).getAttribute("href")).toBe("/question/agent_b/q_b");
  expect(experiment.queryByRole("button", { name: "Promote" })).toBeNull();
  expect(screen.getByLabelText("Your allowance").textContent).toContain("100 minutes remaining of 120 minutes");
  // The blocked column holds open items with a recorded blocker; promotion from its card defaults to scouting.
  const blocked = within(screen.getByLabelText("Blocked column"));
  fireEvent.click(within(blocked.getByLabelText("Card frontier_c")).getByRole("button", { name: "Promote" }));
  expect((blocked.getByLabelText("Task type") as HTMLSelectElement).value).toBe("scouting");
  // Candidate evidence from scouting: inspected datasets, eligible and rejected with reasons; analysis promotes as research.
  const candidate = within(screen.getByLabelText("Candidate evidence column"));
  const scout = within(candidate.getByLabelText("Card frontier_s"));
  expect(scout.getByText("Datasets inspected: 2 (1 eligible, 1 rejected)")).toBeTruthy();
  expect(scout.getByText("No donor identity.")).toBeTruthy();
  expect(scout.getByText("rejected")).toBeTruthy();
  fireEvent.click(scout.getByRole("button", { name: "Promote" }));
  expect((candidate.getByLabelText("Task type") as HTMLSelectElement).value).toBe("research");
});
