import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import RunPage from "./Run";
import { formatSeconds, scaleFor } from "../components/run/TimelineCanvas";
import type { RunTimeline } from "../types/observatory-map";

const call = (line: number, lane: string, t: number, exit: number | null, summary: string) =>
  ({ line, result_line: line + 1, lane, name: "terminal", summary, exit_code: exit, status: "completed", t, t_end: t + 2 });

const RUN: RunTimeline = {
  run: { id: "run_1", request: "request_1", target: "agent_a", state: "completed", created: "t", finished: "t" },
  request: { id: "request_1", post: "post_" + "1".repeat(32), task_type: null, title: "Question for alice", kind: "question" },
  agent: { id: "agent_a", name: "alice", model: "m" },
  execution: { state: "exited", returncode: 0, wall_seconds: 7300, monotonic_seconds: 100, suspended_seconds: 7200,
    suspension_floor_seconds: 60, bounded: true, started: "2026-01-01T00:00:00+00:00" },
  axis: { unit: "seconds", duration: 30, clock: "monotonic" },
  suspensions: [{ at: 10, seconds: 7200, gap_seconds: 7201, placement: "largest_event_gap", unplaced_seconds: 0,
    attributed: true, basis: "placed at the largest gap between event timestamps" }],
  lanes: [{ id: "terminal:analysis", label: "analysis", count: 2 }, { id: "terminal:register", label: "register", count: 1 }],
  calls: [call(3, "terminal:analysis", 2, 0, "run_analysis.py a.py"), call(5, "terminal:analysis", 12, 1, "run_analysis.py b.py"),
    call(7, "terminal:register", 20, 0, "bio register out.tsv")],
  receipts: [{ ...call(3, "terminal:analysis", 2, 0, ""), script: "a.py", outcome: "pass" },
    { ...call(5, "terminal:analysis", 12, 1, ""), script: "b.py", outcome: "fail" }],
  compactions: [{ line: 4, t: 5, source: "stream", text: "compacting" }],
  compaction_summaries: [{ timestamp: 1, fallback: true, excerpt: "[CONTEXT COMPACTION] deterministic fallback", t: null }],
  inbox_reads: [], answers_consumed: [],
  headline: { ...call(7, "terminal:register", 20, 0, "bio register out.tsv"), basis: "first successful register", attributed: true },
  attributed: ["suspension", "headline"],
  final: { text: "The finding is **synthetic**.", source: "final.md" },
  tokens: { input_tokens: 1200, cached_input_tokens: "unavailable", output_tokens: 450, reasoning_output_tokens: "unavailable" },
  metrics: { tool_calls: 3, minutes_after_last_successful_analysis: null },
  malformed_lines: [], errors: 0,
  links: { raw: "/api/runs/run_1/raw", messages: "/api/runs/run_1/messages" },
  limitations: ["Wall clock includes host sleep."],
};

beforeEach(() => {
  HTMLCanvasElement.prototype.getContext = (() => null) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.startsWith("/api/runs/run_1/messages")
      ? { items: [{ index: 0, role: "user", timestamp: 1, content: "<b>prompt</b>" }], total: 1, offset: 0, limit: 20 }
      : url.startsWith("/api/runs/") ? RUN : { items: [] };
    return new Response(JSON.stringify(body), { status: 200 });
  }) as typeof fetch;
});

function show() {
  render(<MemoryRouter initialEntries={["/run/run_1"]}><Routes><Route path="/run/:id" element={<RunPage />} /></Routes></MemoryRouter>);
}

test("shows clocks with the suspension, receipts, fallbacks, headline, final answer and unavailable tokens", async () => {
  show();
  await screen.findByText(/Suspension of 2 h placed at 10 s/);
  expect(screen.getByText("1.7 min")).toBeTruthy();
  expect(screen.getByText("✓ pass")).toBeTruthy();
  expect(screen.getByText("✗ fail")).toBeTruthy();
  expect(screen.getByText(/1 deterministic fallback/)).toBeTruthy();
  expect(screen.getByText("(first successful register)")).toBeTruthy();
  expect(screen.getByText("synthetic").tagName).toBe("STRONG");
  expect(screen.getAllByText("unavailable").length).toBeGreaterThanOrEqual(2);
  expect(screen.getByRole("link", { name: "raw stream" }).getAttribute("href")).toBe("/api/runs/run_1/raw");
  expect(screen.getByRole("img", { name: /3 tool calls in 2 lanes/ })).toBeTruthy();
});

test("heuristically placed items are labelled attributed, not recorded, with a legend entry (C10)", async () => {
  show();
  await screen.findByText(/Suspension of 2 h placed at 10 s/);
  expect(screen.getByText(/attributed, not recorded \(dotted, hatched/)).toBeTruthy();
  const chips = screen.getAllByText("attributed, not recorded");
  expect(chips.length).toBe(2); // the suspension's placement and the headline
  expect(chips.map((c) => c.getAttribute("title"))).toContain("placed at the largest gap between event timestamps");
  // Recorded items (receipts) carry no attribution label.
  expect(screen.getByText("✓ pass").parentElement?.textContent).not.toMatch(/attributed/);
});

test("unavailable clocks and compactions render as unavailable, never zero (C10)", async () => {
  const unavailable = { ...RUN, execution: { ...RUN.execution, wall_seconds: null, suspended_seconds: null },
    suspensions: [], compactions: null, headline: null, attributed: [] };
  // Only the run endpoint answers with the run; other views on the page (e.g. participant pickers) get lists.
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => new Response(
    JSON.stringify(String(input).startsWith("/api/runs/") ? unavailable : { items: [] }), { status: 200 })) as typeof fetch;
  show();
  await screen.findByText(/this harness does not mark compactions/);
  expect(screen.queryByText(/0 in the stream/)).toBeNull();
  expect(screen.getAllByText("unavailable").length).toBeGreaterThanOrEqual(4); // wall, suspended, compactions, tokens
  expect(screen.queryByText("attributed, not recorded")).toBeNull();
});

test("model-facing messages load on request and stay verbatim untrusted text", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Load model-facing messages" }));
  const body = await screen.findByText("<b>prompt</b>");
  expect(body.tagName).toBe("PRE");
  expect(document.querySelector(".run-messages b")).toBeNull();
});

test("the monotonic scale inserts a fixed break after the suspension", () => {
  const x = scaleFor(RUN, 1000);
  expect(x(10) - x(9)).toBeLessThan(x(11) - x(10) - 20);
  expect(formatSeconds(7200)).toBe("2 h");
  expect(formatSeconds(90)).toBe("1.5 min");
});
