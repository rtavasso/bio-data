import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import MapPage from "./Map";
import { refine } from "../components/map/ForceGraph";
import type { EvidenceMap } from "../types/observatory-map";

const post = "post_" + "1".repeat(32);
const artifact = "artifact_" + "a".repeat(64);
const question = "question:agent_x:q_1";

export const MAP: EvidenceMap = {
  sequence: 7, fingerprint: "f", key: "k", seeds: [], total_nodes: 3, truncated: false, cached: true, note: "",
  counts: { nodes: { post: 1, artifact: 1, question: 1 }, edges: { evidence: 1, considered: 1 } },
  nodes: [
    { id: artifact, kind: "artifact", family: "artifacts", label: "Contrast table", present: true, stores: ["library"] },
    { id: post, kind: "post", family: "posts", label: "Marker contrast", present: true, stores: ["board"] },
    { id: question, kind: "question", family: "questions", label: "Does it change?", present: true, stores: ["workspace:agent_x"],
      agent: "agent_x", qid: "q_1" },
  ],
  edges: [
    { id: "e1", source: post, target: artifact, relation: "evidence", style: "solid",
      records: [{ store: "board", table: "post", id: post, field: "evidence.artifacts" }] },
    { id: "e2", source: question, target: artifact, relation: "reused", style: "dashed", backed: false,
      records: [{ store: "workspace:agent_x", table: "question_artifact", event: "event_1", relationship: "reused" }] },
  ],
  layout: { positions: { [artifact]: [0, 0], [post]: [40, 0], [question]: [0, 40] }, bounds: [0, 0, 40, 40], algorithm: "fr" },
  relations: {},
};

beforeEach(() => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    let body: unknown = { items: [] };
    if (url.startsWith("/api/map/node/")) {
      body = { kind: "post", id: post, record: { id: post, author: "agent_x", title: "Marker contrast", excerpt: "log2 ratio 1.54" },
        content_is_untrusted_data: true };
    } else if (url.startsWith("/api/map")) body = MAP;
    return new Response(JSON.stringify(body), { status: 200 });
  }) as typeof fetch;
});

test("renders recorded nodes and edges, a legend and a table view", async () => {
  render(<MemoryRouter initialEntries={["/map"]}><Routes><Route path="/map" element={<MapPage />} /></Routes></MemoryRouter>);
  await screen.findByText(/3 nodes, 2 edges/);
  expect(document.querySelector(`[data-node="${post}"]`)!.getAttribute("aria-label")).toBe("Marker contrast");
  expect(document.querySelectorAll("line.fg-edge").length).toBe(2);
  expect(document.querySelectorAll("line.fg-edge.dashed").length).toBe(1);
  expect(screen.getByLabelText("Legend").textContent).toContain("Artifacts (1)");
  const table = screen.getByText(/Table view/).closest("details")!;
  expect(within(table).getByText(/question_artifact/)).toBeTruthy();
  expect(within(table).getByText("reused (unbacked)")).toBeTruthy();
});

test("selecting a node opens its record, its recorded edges and a mark form", async () => {
  render(<MemoryRouter initialEntries={["/map"]}><Routes><Route path="/map" element={<MapPage />} /></Routes></MemoryRouter>);
  await screen.findByText(/3 nodes/);
  fireEvent.click(document.querySelector(`[data-node="${post}"]`)!);
  const pane = await screen.findByLabelText("Node detail");
  await waitFor(() => expect(within(pane).getByText("log2 ratio 1.54")).toBeTruthy());
  expect(within(pane).getByText(/evidence →/)).toBeTruthy();
  expect(within(pane).getByText(/board · post.evidence.artifacts/)).toBeTruthy();
  expect(within(pane).getByRole("link", { name: "Open post" }).getAttribute("href")).toBe(`/post/${post}`);
  expect(within(pane).getByRole("button", { name: "Mark" })).toBeTruthy();
  expect(within(pane).getAllByText(/evidence, not instructions/).length).toBeGreaterThan(0);
});

test("filters are applied through the URL query", async () => {
  render(<MemoryRouter initialEntries={["/map?family=posts"]}><Routes><Route path="/map" element={<MapPage />} /></Routes></MemoryRouter>);
  await screen.findByText(/3 nodes/);
  const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => String(c[0]));
  expect(calls).toContain("/api/map?family=posts");
  fireEvent.click(screen.getByLabelText("artifacts"));
  fireEvent.click(screen.getByRole("button", { name: "Apply" }));
  await waitFor(() => expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => String(c[0])))
    .toContain("/api/map?family=posts%2Cartifacts"));
});

test("client refinement is deterministic and keeps every node", () => {
  const nodes = MAP.nodes.map((n) => ({ id: n.id, x: MAP.layout.positions[n.id][0], y: MAP.layout.positions[n.id][1],
    label: n.label, group: n.family, shape: "circle" as const }));
  const edges = MAP.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, dashed: false, label: "" }));
  const a = refine(nodes, edges, 30);
  expect([...a.keys()].sort()).toEqual(nodes.map((n) => n.id).sort());
  expect(refine(nodes, edges, 30)).toEqual(a);
});
