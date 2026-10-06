import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import QuestionPageView from "./Question";
import { statusClass } from "../components/question/CoverageStrip";
import type { QuestionPage } from "../types/observatory-map";

const PAGE: QuestionPage = {
  agent: { id: "agent_d", name: "dana", kind: "agent" },
  question: { id: "q_1", title: "Is there a perturbation dataset?", status: "open", created: "t0", updated: "t2", current_work: "work_b" },
  node: "question:agent_d:q_1",
  counts: { events: 3, snapshots: 2, produced: 1, considered: 0, reused: 0, gaps: 1, gap_withdrawals: 0 },
  revisions: [{ id: "work_a", created: "t0", summary: "", files: 3 }, { id: "work_b", created: "t2", summary: "", files: 3 }],
  notebook: { snapshot: "work_b", labbook: "# Notebook\n\nNo eligible dataset found.\n", question: "# Q", truncated: false,
    blobs: { "LABBOOK.md": "c".repeat(64) } },
  scripts: [],
  outputs: [{ artifact: "artifact_" + "f".repeat(64), present: true, title: "Search hits", summary: "", output_role: "figure",
    output_name: "hits.png", output_blob: "b".repeat(64), bytes: 10, figure: true, blob_url: "/api/blobs/agent_d/bbb?name=hits.png",
    limitations: [], relationships: [{ relationship: "produced", event: "event_1", created: "t1" }] }],
  figures: [],
  events: [
    { id: "event_0", kind: "question_created", created: "t0", summary: { title: "x" },
      state: { snapshot: null, produced: 0, considered: 0, reused: 0, gaps_open: 0 } },
    { id: "event_1", kind: "work_snapshot", created: "t0", summary: { snapshot: "work_a" },
      state: { snapshot: "work_a", produced: 0, considered: 0, reused: 0, gaps_open: 0 } },
    { id: "event_2", kind: "retrieval_gap", created: "t1", summary: {}, state: { snapshot: "work_a", produced: 0, considered: 0, reused: 0, gaps_open: 1 } },
    { id: "event_3", kind: "work_snapshot", created: "t2", summary: { snapshot: "work_b" },
      state: { snapshot: "work_b", produced: 1, considered: 0, reused: 0, gaps_open: 1 } },
  ],
  networks: [
    { sha256: "1".repeat(64), name: "mechanisms.initial.json", origins: [{ kind: "notebook_hash" }], records: [], preserved: true,
      created: "t1", revision: 1, scope: null, nodes: [{ id: "m", label: "Marker" }], edges: [], frontier: [], changes: [], issues: [] },
    { sha256: "2".repeat(64), name: "mechanisms.json", origins: [{ kind: "working_copy" }], records: [], preserved: false,
      created: "t2", revision: 2, scope: null, nodes: [{ id: "m", label: "Marker" }, { id: "r", label: "Readout" }],
      edges: [{ id: "e1", source: "m", target: "r", status: "hypothesis", mechanism: "feedback", dangling: false },
        { id: "e9", source: "m", target: "ghost", dangling: true }], frontier: [], changes: [{}], issues: [] },
  ],
  coverage: [{ sha256: "3".repeat(64), name: "evidence-coverage.tsv", origins: [{ kind: "notebook_hash" }], records: [], preserved: true,
    created: "t2", columns: ["edge_ids", "file_or_accession", "inspection_status"],
    rows: [{ line: 2, cells: ["e1", "", "unavailable"] }, { line: 3, cells: ["e1", null, "searched"] }], issues: [] }],
  gaps: { groups: [{ source_or_format: "geo", gap_key: "knockdown-counts", observations: 1, distinct_questions: 1,
    examples: [{ event: "event_2", payload: { desired_information: "counts after knockdown", why_current_tools_failed: "no hits" } }] }],
    withdrawn_events: [], corrections_requiring_review: [], unstructured_events: [], matching_events: 1, withdrawn_count: 0, corrected_count: 0 },
  posts: [],
  subgraph: { nodes: [], edges: [], positions: {} },
  note: "",
};

beforeEach(() => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.startsWith("/api/questions/") ? PAGE : url.startsWith("/api/map") ? { nodes: [] } : { items: [] };
    return new Response(JSON.stringify(body), { status: 200 });
  }) as typeof fetch;
});

function show(path = "/question/agent_d/q_1") {
  render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/question/:agent/:id" element={<QuestionPageView />} /></Routes></MemoryRouter>);
}

test("renders the notebook, outputs, networks by revision, coverage and gaps", async () => {
  show();
  await screen.findByText("No eligible dataset found.");
  expect(screen.getByRole("heading", { name: "Is there a perturbation dataset?" })).toBeTruthy();
  expect(screen.getByRole("img", { name: "Search hits" }).getAttribute("src")).toContain("/api/blobs/agent_d/");
  // Latest network revision first; the working copy is labelled as not a record; dangling edges are listed.
  expect(screen.getByText("working copy (mutable, not a record)")).toBeTruthy();
  expect(screen.getByText("dangling")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "revision 1" }));
  expect(screen.getByText("hash cited in the notebook (preserved object)", { selector: ".q-network .obs-chip" })).toBeTruthy();
  // Blank and missing coverage cells stay distinct.
  const strip = screen.getByLabelText("Inspection status per coverage row");
  expect(within(strip).getByText("unavailable").closest("li")!.className).toBe("cov-unavailable");
  expect(screen.getByText("blank", { selector: "td .obs-missing" })).toBeTruthy();
  expect(screen.getByText("missing", { selector: "td .obs-missing" })).toBeTruthy();
  expect(screen.getByText("knockdown-counts")).toBeTruthy();
});

test("the scrubber replays events and can load the notebook at that point", async () => {
  show();
  const slider = await screen.findByRole("slider");
  fireEvent.change(slider, { target: { value: "2" } });
  expect(screen.getByText("retrieval gap")).toBeTruthy();
  expect(screen.getByText("open gaps 1")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /show this revision/ }));
  const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => String(c[0]));
  expect(calls).toContain("/api/questions/agent_d/q_1?snapshot=work_a");
});

test("heat strip classes follow the documented inspection order", () => {
  expect(statusClass("not_searched")).toBe("cov-step-1");
  expect(statusClass("analyzed")).toBe("cov-step-5");
  expect(statusClass("")).toBe("cov-blank");
  expect(statusClass(null)).toBe("cov-missing");
  expect(statusClass("blocked")).toBe("cov-other");
});
