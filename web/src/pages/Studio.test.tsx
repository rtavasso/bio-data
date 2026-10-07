import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Studio from "./Studio";
import type { StudioItem, StudioOverview } from "../types/studio";

const writeup = "post_" + "a".repeat(32);
const artifact = "artifact_" + "c".repeat(64);
const snapshot = "f".repeat(64);

function item(over: Partial<StudioItem>): StudioItem {
  return {
    request: "request_1", task_type: "writing", state: "completed", post: "post_req", origin: "commission",
    title: "Commission: writing for dana", created: "2026-10-01T00:00:00+00:00", updated: "2026-10-01T00:00:00+00:00",
    deadline: null, budget: { minutes: 30 }, target: { id: "agent_1", name: "dana" }, commissioner: { id: "human_1", name: "mira" },
    subject: { kind: "post", id: "post_" + "b".repeat(32) }, note: "Summarise.", answer: null, deliverables: [], ...over,
  };
}

const overview: StudioOverview = {
  groups: {
    writeups: [item({ outputs: [{ post: writeup, title: "Corrected contrast", status: "rendered", flagged: true, withdrawn_claims: ["claim_1"] }] }),
      item({ request: "request_2", state: "pending", outputs: [] })],
    reviews: [item({ request: "request_3", task_type: "review", review: { valid: true, criteria_missing: [], marks: [
      { mark: "mark_1", kind: "checked_source", criterion: "limitations_stated", verdict: "supported", target_kind: "post", target_id: writeup }] } })],
    replications: [item({ request: "request_4", task_type: "replication", replication: {
      results: [{ original: artifact, outcome: "byte_identical", receipts: { [artifact]: { receipt_blob: "e".repeat(64), code_sha256: "d".repeat(64), exit_code: 0 } } }],
      followup: [{ original: artifact, outcome: "byte_identical", mark: "mark_2", post: "post_conf", author: "system_1" }] } }),
      item({ request: "request_5", task_type: "replication", replication: {
        results: [{ original: artifact, outcome: "no_execution_receipt", unreceipted: [{ artifact, output_blob: "b".repeat(64) }] }],
        followup: [{ original: artifact, outcome: "no_execution_receipt" }] } })],
    digests: [],
  },
  states: {
    writeups: { pending: 1, running: 0, completed: 1, failed: 0 }, reviews: { pending: 0, running: 0, completed: 1, failed: 0 },
    replications: { pending: 0, running: 0, completed: 1, failed: 0 }, digests: { pending: 0, running: 0, completed: 0, failed: 0 },
  },
  regeneration_flags: [{ post: writeup, title: "Corrected contrast", status: "rendered", flagged: true, withdrawn_claims: ["claim_1"] }],
  digest_schedules: [{ id: "digest_1", person: "human_1", person_name: "mira", target: "agent_1", target_name: "dana", scope: {},
    interval_days: 7, budget: { minutes: 30 }, next_due: "2026-10-08T00:00:00+00:00", last_until: null, enabled: true, created: "2026-10-01T00:00:00+00:00" }],
  exports: [], federation: [{ snapshot, scope: { kind: "thread" }, counts: {}, imported: null, file_count: 9, foreign: true }],
  sequence: 10, note: "",
};

const calls: { url: string; init?: RequestInit }[] = [];

beforeEach(() => {
  calls.length = 0;
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url === "/api/studio") return new Response(JSON.stringify(overview), { status: 200 });
    if (url === "/api/exports") return new Response(JSON.stringify({ snapshot, scope: { kind: "board" }, files: 12, bytes: 100, counts: {}, location: `exports/${snapshot}` }), { status: 200 });
    return new Response(JSON.stringify({ items: [] }), { status: 200 });
  }) as typeof fetch;
});

test("outputs are grouped by type with state, flags and links to the rendered write-up", async () => {
  render(<MemoryRouter initialEntries={["/studio"]}><Studio /></MemoryRouter>);
  const flags = await screen.findByLabelText("Regeneration flags");
  expect(within(flags).getByRole("link", { name: "Corrected contrast" }).getAttribute("href")).toBe(`/studio/${writeup}`);
  expect(screen.getByRole("tab", { name: /Write-ups \(2\) · 1 open/ }).getAttribute("aria-selected")).toBe("true");
  expect(screen.getByText("regeneration required")).toBeTruthy();
  expect(screen.getByText("pending")).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: /Replications/ }));
  expect(screen.getByText("byte identical")).toBeTruthy();
  expect(screen.getByRole("link", { name: "confirmation" }).getAttribute("href")).toBe("/post/post_conf");
  // Spec v2 C6: confirmations are platform records under an execution receipt; copied bytes confirm nothing.
  expect(screen.getByText("(platform record by the replication participant)")).toBeTruthy();
  expect(screen.getByText("eeeeeeeeeeee")).toBeTruthy();
  expect(screen.getByText("no execution receipt").className).toContain("warn");
  fireEvent.click(screen.getByRole("tab", { name: /Reviews/ }));
  expect(screen.getByText("limitations_stated: checked source")).toBeTruthy();
  expect(screen.getByText("foreign")).toBeTruthy();
  expect(screen.getByLabelText("Commission type")).toBeTruthy();
});

test("export shows the resulting content-addressed snapshot ID", async () => {
  render(<MemoryRouter initialEntries={["/studio"]}><Studio /></MemoryRouter>);
  const form = await screen.findByRole("form", { name: "Export" });
  fireEvent.change(within(form).getByLabelText("Export scope"), { target: { value: "board" } });
  fireEvent.click(within(form).getByRole("button", { name: "Export static snapshot" }));
  await waitFor(() => expect(within(form).getByRole("status").textContent).toContain(snapshot));
  const sent = calls.find((c) => c.url === "/api/exports");
  expect(JSON.parse(String(sent?.init?.body))).toEqual({ scope: "board" });
  expect((sent?.init?.headers as Record<string, string>)["X-Colloquy-Request"]).toBe("1");
});
