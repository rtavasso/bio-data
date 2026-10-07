import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Me from "./Me";
import Login from "./Login";
import type { MeSummary } from "../types/participation";

const SUMMARY: MeSummary = {
  id: "human_" + "a".repeat(32), name: "mira", kind: "human", created: "2026-10-01T00:00:00+00:00",
  profile: { display_name: "Mira", affiliation: "Synthetic Lab" }, mode: "local", auth: "local",
  permissions: ["comment", "commission", "mark", "post", "promote", "read", "token"], writes_over_http: true,
  suspended: false,
  budget: { allowance: { minutes: 120 }, spent: { minutes: 30, tokens: 0, download_bytes: 0 }, remaining: { minutes: 90 }, unlimited: false },
  posts: [],
  comments: [{
    id: "post_" + "c".repeat(32), created: "2026-10-01T00:00:00+00:00", parent: "post_" + "d".repeat(32),
    body: "Does this hold for human cells?", target: { kind: "post", id: "post_" + "d".repeat(32), author: "agent_x" },
    anchor: { target_kind: "post", target_id: "post_" + "d".repeat(32), kind: "paragraph", blob: "b".repeat(64), offset: 3, length: 15, quote: "log2 ratio 1.54" },
    request: { id: "request_1", state: "completed", target: "agent_x", answer: "post_" + "e".repeat(32) },
  }],
  promotions: [{
    id: "request_2", post: "post_" + "f".repeat(32), target: "agent_bob", state: "pending", task_type: "replication",
    budget: { minutes: 30 }, deadline: null, answer: null, created: "t", updated: "t", kind: "promotion",
  }],
  commissions: [],
  marks: [{
    id: "mark_1", participant: "human_x", participant_name: "mira", target_kind: "post", target_id: "post_x", kind: "checked_source",
    note: "Opened the table.", pointers: [{ kind: "artifact", id: "artifact_" + "0".repeat(64), locator: "row B_vs_A" }],
    body_blob: "x", created: "2026-10-01T00:00:00+00:00", attribution_not_status: true,
  }],
  uploads: [], inbox: [], tokens: [], csrf_header: "X-Colloquy-Request",
};

function respond(routes: Record<string, [number, unknown]>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    const key = Object.keys(routes).find((k) => url.startsWith(k));
    const [status, body] = key ? routes[key] : [404, { error: "unknown_endpoint" }];
    return new Response(JSON.stringify(body), { status });
  }) as typeof fetch;
  return calls;
}

test("me shows identity, budget, anchored comments, marks as attribution, and promotions", async () => {
  respond({ "/api/me": [200, SUMMARY] });
  render(<MemoryRouter><Me /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "Mira" })).toBeTruthy();
  expect(screen.getByText("90 minutes")).toBeTruthy();
  expect(screen.getByText("log2 ratio 1.54")).toBeTruthy();
  expect(screen.getByText("Does this hold for human cells?").closest("[data-untrusted]")).toBeTruthy();
  expect(screen.getByText(/attribution, not status/)).toBeTruthy();
  expect(screen.getByText("replication")).toBeTruthy();
  expect(screen.queryByText("Operator: accounts")).toBeNull();
});

test("me lists the snapshots this participant imported (v3 B9)", async () => {
  const snapshot = "c".repeat(64);
  respond({ "/api/me": [200, { ...SUMMARY, imports: [{ snapshot, already_imported: false, scope: { kind: "board" },
    counts: { posts: 3 }, index: { claims: 2, artifacts: 5, citations: 1, changed: true }, seq: 9, created: "2026-10-07" }] }] });
  render(<MemoryRouter><Me /></MemoryRouter>);
  const section = await screen.findByRole("region", { name: "Imported snapshots" });
  expect(section.querySelector(`a[href="/directory/${snapshot}"]`)).toBeTruthy();
  expect(section.textContent).toContain("2 claims, 5 artifacts, 1 citations indexed");
});

test("me redirects to login on 401 in accounts mode, and login sends the token with the write header", async () => {
  const calls = respond({
    "/api/me": [401, { error: "authentication_required", detail: "log in" }],
    "/api/health": [200, { ok: true, mode: "accounts" }],
    "/api/session": [200, { id: "human_x", name: "rhea", kind: "human" }],
  });
  const onLogin = vi.fn();
  render(
    <MemoryRouter initialEntries={["/me"]}>
      <Routes>
        <Route path="/me" element={<Me />} />
        <Route path="/login" element={<Login onLogin={onLogin} />} />
      </Routes>
    </MemoryRouter>,
  );
  const input = await screen.findByLabelText("Token");
  fireEvent.change(input, { target: { value: "colloquy_secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Log in" }));
  await waitFor(() => expect(onLogin).toHaveBeenCalled());
  const login = calls.find((c) => c.url === "/api/session")!;
  expect(login.init?.method).toBe("POST");
  expect((login.init?.headers as Record<string, string>)["X-Colloquy-Request"]).toBe("1");
  expect(JSON.parse(String(login.init?.body))).toEqual({ token: "colloquy_secret" });
});
