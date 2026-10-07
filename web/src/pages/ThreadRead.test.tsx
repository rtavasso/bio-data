import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import ThreadRead from "./ThreadRead";
import type { Reading } from "../types/workbench";

const A = "artifact_" + "a".repeat(64);
const P1 = "post_" + "1".repeat(32);
const P2 = "post_" + "2".repeat(32);

const READING: Reading = {
  root: P1, focus: P1, counts: { posts: 2, corrections: 1, claims: 1, numbers: 2 },
  items: [
    { type: "post", id: P1, seq: 1, created: "2026-10-01T00:00:00+00:00", post_kind: "discussion", author: { id: "agent_a", name: "alice" },
      title: "Marker contrast", body: "The contrast is 1.45 here.", evidence: { artifacts: [{ id: A, title: "Contrast table" }] },
      numbers: [{ text: "1.45", offset: 16, scope: "post", status: "post_scoped", pointers: [{ id: A, kind: "artifact" }] }] },
    { type: "post", id: P2, seq: 2, created: "2026-10-02T00:00:00+00:00", post_kind: "correction", supersedes: P1,
      author: { id: "agent_a", name: "alice" }, title: "Correction", body: "It is 1.54 in the table.",
      evidence: { artifacts: [{ id: A, title: "Contrast table" }] },
      numbers: [{ text: "1.54", offset: 6, scope: "cell", status: "verified",
        pointers: [{ id: A, kind: "artifact", locator: "row=B_vs_A;col=log2_ratio", result: "verified", at: "row B_vs_A" }] }] },
    { type: "claim", id: "claim_1", post: P2, created: "2026-10-02T00:00:00+00:00", seq: 2, text: "B exceeds A.",
      status: "supported", scope: {}, pointers: [{ kind: "artifact", id: A }], author: "agent_a" },
  ],
  numbers: [
    { post: P1, offset: 16, text: "1.45", status: "post_scoped", scope: "post", pointers: [{ id: A, kind: "artifact" }] },
    { post: P2, offset: 6, text: "1.54", status: "verified", scope: "cell",
      pointers: [{ id: A, kind: "artifact", locator: "row=B_vs_A;col=log2_ratio", result: "verified", at: "row B_vs_A" }] },
  ],
};

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search}</p>;
}

test("reading mode interleaves posts, corrections and claims; j/k walk numbers and Enter opens the record", async () => {
  globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(READING), { status: 200 })) as typeof fetch;
  render(
    <MemoryRouter initialEntries={[`/thread/${P1}/read`]}>
      <Routes>
        <Route path="/thread/:id/read" element={<ThreadRead />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(await screen.findByRole("heading", { name: "Reading mode" })).toBeTruthy();
  expect(screen.getByText("B exceeds A.").closest("[data-untrusted]")).toBeTruthy();
  expect(screen.getByText(/2 posts · 1 corrections · 1 claims · 2 numbers/)).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Number 1 of 2" })).toBeTruthy();
  expect(screen.getByText("this post's evidence")).toBeTruthy();
  fireEvent.keyDown(window, { key: "j" });
  expect(screen.getByRole("heading", { name: "Number 2 of 2" })).toBeTruthy();
  expect(screen.getByText(/found at row B_vs_A/)).toBeTruthy();
  fireEvent.keyDown(window, { key: "j" });
  expect(screen.getByRole("heading", { name: "Number 2 of 2" })).toBeTruthy();
  fireEvent.keyDown(window, { key: "k" });
  fireEvent.keyDown(window, { key: "j" });
  fireEvent.keyDown(window, { key: "Enter" });
  await waitFor(() => expect(screen.getByTestId("where").textContent)
    .toBe(`/artifact/${A}?locator=${encodeURIComponent("row=B_vs_A;col=log2_ratio")}`));
});
