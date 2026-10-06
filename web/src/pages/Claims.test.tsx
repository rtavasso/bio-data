import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Claims from "./Claims";
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
