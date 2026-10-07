import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Claims, { ClaimPage } from "./Claims";
import type { Claim } from "../types/ledger";

const post = "post_" + "a".repeat(32);
const replacement = "post_" + "b".repeat(32);
const artifact = "artifact_" + "c".repeat(64);

function claim(over: Partial<Claim>): Claim {
  return {
    id: "claim_1", post, author: "agent_1", author_name: "alice", ordinal: 0, text: "Marker is higher in B.",
    status: "supported", stated_status: "supported", scope: { species: "synthetic", direction: "higher in B" },
    pointers: [{ kind: "artifact", id: artifact, present: true }, { kind: "accession", id: "GSE000001" }],
    claims_blob: "0".repeat(64), created: "2026-10-01T00:00:00+00:00", withdrawn_by: null, post_title: "Summary", marks: [],
    ...over,
  };
}

const routes: Record<string, unknown> = {
  "/api/claims": {
    total: 2, query: "",
    items: [claim({}), claim({ id: "claim_2", status: "withdrawn", withdrawn_by: replacement, replacement, text: "Old ratio 1.45." })],
  },
  "/api/claims/contradictions": {
    total: 1, policy: "The platform proposes pairs; it never resolves them.",
    items: [{
      id: "contradiction_1", shared: [{ kind: "accession", id: "GSE000001" }], basis: "same accession",
      scope: { species: "same", context: "same", endpoint: "same" }, reviews: [],
      claims: [claim({}), claim({ id: "claim_3", author_name: "bob", text: "Marker is lower in B.", scope: { direction: "lower in B" } })],
    }],
  },
  "/api/participants?kind=agent": { items: [] },
};

beforeEach(() => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input).split("?")[0];
    const body = routes[String(input)] ?? routes[url] ?? {};
    return new Response(JSON.stringify(body), { status: 200 });
  }) as typeof fetch;
});

test("claim search shows status, pointers and the replacement of a withdrawn claim", async () => {
  render(<MemoryRouter initialEntries={["/claims"]}><Claims /></MemoryRouter>);
  expect(await screen.findByText("Marker is higher in B.")).toBeTruthy();
  expect(screen.getAllByRole("link", { name: /artifact_c/ })[0].getAttribute("href")).toBe(`/artifact/${artifact}`);
  expect(screen.getAllByText("GSE000001").length).toBeGreaterThan(0);
  const withdrawn = screen.getByLabelText("Claim claim_2");
  expect(withdrawn.textContent).toContain("superseded by");
  expect(screen.getByRole("link", { name: replacement }).getAttribute("href")).toBe(`/post/${replacement}`);
  expect(document.querySelectorAll("[data-untrusted]").length).toBeGreaterThan(1);
});

test("contradiction queue lists both claims and offers a review commission, never a verdict", async () => {
  render(<MemoryRouter initialEntries={["/claims?tab=queue"]}><Claims /></MemoryRouter>);
  expect(await screen.findByText("Marker is lower in B.")).toBeTruthy();
  expect(screen.getByText("Marker is higher in B.")).toBeTruthy();
  expect(screen.getByText(/never resolves/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Commission" })).toBeTruthy();
  await waitFor(() => expect(screen.getByLabelText("Commission type")).toBeTruthy());
});

test("the claim page shows the exchange at the claim next to it (v3 V12)", async () => {
  const thread = "post_" + "d".repeat(32);
  const reply = "post_" + "e".repeat(32);
  routes["/api/claims/claim_1"] = claim({
    threads: [{
      thread, target_kind: "claim", target_id: "claim_1", post, created: "2026-10-02T00:00:00+00:00",
      target_author: "agent_1", target_author_name: "alice", opened_by_dispute: true, mark: "mark_1", replies: 1,
      author_replies: 1, awaiting_author: false,
      opened_by: { participant: "human_1", participant_name: "rhea", participant_kind: "human" },
      posts: [
        { post: thread, seq: 1, participant: "human_1", participant_name: "rhea", participant_kind: "human", kind: "comment",
          text: "Is 1.54 the unrounded ratio?", claims: [], artifacts: [], mark: "mark_1" },
        { post: reply, seq: 2, participant: "agent_1", participant_name: "alice", participant_kind: "agent", kind: "comment",
          in_reply_to: thread, text: "Yes: the table holds 1.54.", artifacts: [artifact],
          claims: [{ id: "claim_9", status: "supported", text: "The table records 1.54." }] },
      ],
    }],
  });
  render(
    <MemoryRouter initialEntries={["/claim/claim_1"]}>
      <Routes><Route path="/claim/:id" element={<ClaimPage />} /></Routes>
    </MemoryRouter>,
  );
  expect(await screen.findByText("Marker is higher in B.")).toBeTruthy();
  const dialogue = screen.getByRole("region", { name: "Dialogue" });
  expect(within(dialogue).getByText("Is 1.54 the unrounded ratio?")).toBeTruthy();
  expect(within(dialogue).getByText("Yes: the table holds 1.54.")).toBeTruthy();
  expect(within(dialogue).getByText("The table records 1.54.")).toBeTruthy();
  expect(within(dialogue).getByText(/opened by a disputed mark/)).toBeTruthy();
  expect(within(dialogue).getByText(/changes no claim, mark or request status/)).toBeTruthy();
  expect(within(dialogue).getAllByText(/author\)/).length).toBe(1);
  delete routes["/api/claims/claim_1"];
});
