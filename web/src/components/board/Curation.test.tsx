import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Login from "../../pages/Login";
import TourPage from "../../pages/Tour";
import type { NumberPointer } from "../../types/board";
import type { Tour } from "../../types/publishing";
import { CurationPanel } from "./Curation";
import { NumberPointers } from "./NumberPointers";

// Spec v3 B6 and G2 on the web: a text match and a person's curated pointer carry their own badges (never the
// author's "verified"), a curator records a pointer through POST /api/curation/pointers, the tour walks every
// number of its finals, and (V15) a public commons offers visitor sign-in on the login page.

type Call = { url: string; init?: RequestInit };
const ART = "artifact_" + "a".repeat(64);
const POST = "post_" + "b".repeat(32);

function capture(reply: (url: string, init?: RequestInit) => [number, unknown]) {
  const calls: Call[] = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    const [status, body] = reply(String(input), init);
    return new Response(JSON.stringify(body), { status });
  }) as typeof fetch;
  return calls;
}

const numbers: NumberPointer[] = [
  { text: "32.0", offset: 7, scope: "text", status: "verified",
    pointers: [{ id: ART, kind: "artifact", result: "verified", at: "text", artifact: ART, route: `/artifact/${ART}?locator=line%3D3` }] },
  { text: "1.54", offset: 20, scope: "cell", status: "verified",
    pointers: [{ id: ART, kind: "artifact", locator: "row=B;col=x", result: "verified", at: "cell", artifact: ART }] },
  { text: "−3.039", offset: 40, scope: "curated", status: "verified",
    pointers: [{ id: ART, kind: "artifact", locator: "key=primary[0].effect_log2", result: "verified", at: "key", artifact: ART,
      curated: true, curator: "human_r", curator_name: "rhea", note: "the paired effect" }] },
  { text: "0.56", offset: 60, scope: "post", status: "post_scoped", pointers: [{ id: ART, kind: "artifact", artifact: ART, post_evidence: true }] },
  { text: "12", offset: 80, scope: "post", status: "post_scoped", pointers: [],
    unlocatable: { mark: "mark_1", curator: "human_r", curator_name: "rhea", note: "computed in prose", created: "t" } },
];

test("a text match and a curated pointer have their own badges and never count as the author's verified", () => {
  render(<MemoryRouter><NumberPointers numbers={numbers} /></MemoryRouter>);
  const coverage = screen.getByLabelText("Number coverage").textContent ?? "";
  expect(coverage).toContain("1 verified");
  expect(coverage).toContain("1 text match");
  expect(coverage).toContain("1 curated by a person");
  expect(coverage).toContain("1 marked unlocatable");
  const table = screen.getByRole("table", { name: "Numbers pointed at a record" });
  const rows = within(table).getAllByRole("row").slice(1);
  expect(rows[0].textContent).toContain("text match");
  expect(rows[2].textContent).toContain("curated");
  expect(rows[2].textContent).toContain("curated by rhea: the paired effect");
  expect(screen.getByLabelText("Marked unlocatable").textContent).toContain("rhea: computed in prose");
});

test("a curator finds candidate locators and records a curated pointer or an unlocatable mark", async () => {
  const calls = capture((url) => url.startsWith("/api/curation/locate")
    ? [200, { post: POST, number: "0.56", offset: 60, note: "Candidates only.", candidates: [{ artifact: ART, name: "t.json", locators: ["key=results[0].x"] }] }]
    : [200, { mark: "mark_2", kind: "pointer_curated" }]);
  const done = vi.fn();
  render(<CurationPanel post={POST} numbers={numbers} onDone={done} />);
  // Only numbers nobody resolved: the post-scoped 0.56 (12 is marked unlocatable).
  expect(screen.getByText(/1 number without one/)).toBeTruthy();
  fireEvent.click(screen.getByText("0.56"));
  fireEvent.click(screen.getByRole("button", { name: "Find candidate locators" }));
  fireEvent.click(await screen.findByRole("radio"));
  fireEvent.change(screen.getByLabelText("Curation note"), { target: { value: "read the results table" } });
  fireEvent.click(screen.getByRole("button", { name: "Record curated pointer" }));
  await waitFor(() => expect(done).toHaveBeenCalled());
  const sent = calls.find((c) => c.url === "/api/curation/pointers")!;
  expect((sent.init?.headers as Record<string, string>)["X-Colloquy-Request"]).toBe("1");
  expect(JSON.parse(String(sent.init?.body))).toEqual({ post: POST, offset: 60, note: "read the results table", artifact: ART,
    locator: "key=results[0].x" });
  fireEvent.click(screen.getByRole("button", { name: "Mark unlocatable" }));
  await waitFor(() => expect(calls.filter((c) => c.url === "/api/curation/pointers")).toHaveLength(2));
  expect(JSON.parse(String(calls[calls.length - 1].init?.body))).toMatchObject({ offset: 60, unlocatable: true });
});

test("the tour walks every number of its finals: author, curated (with the curator), unlocatable, unresolved", async () => {
  const tour: Tour = {
    name: "pmp22-cohort", title: "From a number to its bytes", curator: { name: "Curator" }, applies: true, steps: [],
    summary: { steps: 0, ok: 0, broken: 0, finals_reaching_bytes_in_two_clicks: 0, finals_resolved: 0 }, sequence: 1,
    finals: [{ post: POST, available: true, title: "Final", route: `/post/${POST}`, author_verified: 0, curated: 1,
      unlocatable: 1, unresolved: 1, curators: ["rhea"], resolved: false, numbers: [
        { offset: 40, text: "−3.039", scope: "curated", status: "verified", resolution: "curated", route: `/artifact/${ART}?locator=k`,
          curated: { curator_name: "rhea", locator: "key=primary[0].effect_log2" } },
        { offset: 80, text: "12", scope: "post", status: "post_scoped", resolution: "unlocatable",
          unlocatable: { curator_name: "rhea", note: "computed in prose" } },
        { offset: 60, text: "0.56", scope: "post", status: "post_scoped", resolution: "unresolved" },
      ] }],
  };
  capture((url) => [200, url === "/api/tours/pmp22-cohort" ? tour : {}]);
  render(<MemoryRouter initialEntries={["/tour/pmp22-cohort"]}><Routes><Route path="/tour/:name" element={<TourPage />} /></Routes></MemoryRouter>);
  const final = await screen.findByLabelText("Final Final");
  expect(final.textContent).toContain("curated by rhea");
  expect(within(final).getByRole("link", { name: "−3.039" }).getAttribute("href")).toBe(`/artifact/${ART}?locator=k`);
  expect(final.textContent).toContain("unlocatable (rhea: computed in prose)");
  expect(final.textContent).toContain("no pointer yet");
});

test("a public commons offers visitor sign-in on the login page and shows the token once", async () => {
  const calls = capture((url) => url === "/api/health"
    ? [200, { ok: true, mode: "accounts", visitor_signin: true, board_version: 2, sequence: 1, demo: false, content_policy: "x" }]
    : [200, { id: "human_v", name: "visitor-1", kind: "human", visitor: true, token: "colloquy_secret", note: "keep it" }]);
  render(<MemoryRouter initialEntries={["/login"]}><Routes><Route path="/login" element={<Login onLogin={vi.fn()} />} /></Routes></MemoryRouter>);
  fireEvent.change(await screen.findByLabelText("Display name"), { target: { value: "A reviewer" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in as a visitor" }));
  expect(await screen.findByText("colloquy_secret")).toBeTruthy();
  const sent = calls.find((c) => c.url === "/api/visitors")!;
  expect(JSON.parse(String(sent.init?.body))).toEqual({ display_name: "A reviewer" });
});
