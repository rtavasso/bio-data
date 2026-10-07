import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { MapNode } from "../../types/observatory-map";
import NodeDetail from "./NodeDetail";

const claim = "claim_" + "c".repeat(32);

beforeEach(() => {
  globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ kind: "claim", id: claim, record: { id: claim } }),
    { status: 200 })) as typeof fetch;
});

test("a claim node shows how many numbers in recorded write-ups were verified against it (V2)", async () => {
  const node: MapNode = { id: claim, kind: "claim", family: "posts", label: "claim 0 · supported · 2 verified", present: true,
    stores: ["board"], status: "supported", verified_pointers: 2 };
  render(<MemoryRouter><NodeDetail node={node} edges={[]} nodes={new Map([[claim, node]])} onSelect={() => undefined} /></MemoryRouter>);
  expect((await screen.findByLabelText("Verified pointers")).textContent).toContain("2 verified number pointers");
});
