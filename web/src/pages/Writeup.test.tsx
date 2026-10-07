import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import WriteupPage from "./Writeup";
import type { Writeup } from "../types/studio";

const post = "post_" + "a".repeat(32);
const claim = "claim_" + "b".repeat(32);
const artifact = "artifact_" + "c".repeat(64);
const replacement = "post_" + "d".repeat(32);

const rendered: Writeup = {
  status: "rendered", rules: "writeup-pointers/1", flagged: true,
  post: { id: post, title: "Corrected contrast", author: { id: "agent_1", name: "dana", kind: "agent" }, created: "2026-10-01T00:00:00+00:00", kind: "answer", body_blob: "0".repeat(64), parent: null },
  request: { id: "request_1", task_type: "writing", state: "completed", post: "post_x", target: "agent_1" },
  stats: { numbers: 1, pointed: 1, units: 1, pointers: 1 },
  blocks: [{
    type: "paragraph", offset: 0, byline: false,
    sentences: [{
      id: "s1", offset: 0, length: 40, pointers: [claim],
      numbers: [{ text: "1.45", offset: 14, length: 4, covered_by: [claim], scope: "claim", status: "verified",
        pointers: [{ id: claim, kind: "claim", result: "verified", at: "claim_text" }] }],
      tokens: [
        { t: "text", text: "The ratio is ", offset: 0 },
        { t: "pointer", id: claim, kind: "claim", text: "1.45", form: "link", offset: 13, length: 50, text_offset: 14 },
        { t: "text", text: ".", offset: 63 },
      ],
    }],
  }],
  pointers: {
    [claim]: {
      id: claim, kind: "claim", present: true, text: "log2(B/A) = 1.45.", status: "withdrawn", author_name: "alice",
      post: "post_old", post_title: "Summary", withdrawn_by: replacement,
      pointers: [{ kind: "artifact", id: artifact, route: `/artifact/${artifact}`, bytes_url: `/api/artifacts/${artifact}/bytes` }],
    },
  },
  regeneration_required: {
    note: "This write-up cites withdrawn claims.",
    claims: [{ claim, text: "log2(B/A) = 1.45.", withdrawn_by: replacement, replacement_title: "Correction", same_ordinal: "claim_new",
      replacement_claims: [{ id: "claim_new", ordinal: 0, text: "log2(B/A) = 1.54.", status: "supported" }] }],
    commission: { task_type: "writing", subject_kind: "post", subject_id: post, note: `Regenerate write-up ${post} from the current ledger.` },
  },
  evidence_map: { nodes: [], edges: [], positions: {}, seeds: [post], note: "Recorded relations only." },
};

const refused: Writeup = {
  status: "refused", rules: "writeup-pointers/1", post: rendered.post, request: null, regeneration_required: null,
  source: "Context first.\nThe marker rose 3-fold.",
  problems: [{ kind: "unpointed_number", text: "3", offset: 31, length: 1, line: 2, reason: "no claim or artifact pointer in this sentence", context: "The marker rose 3-fold." }],
};

function mount(body: Writeup, status = 200) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith("/api/studio/writeups/")) return new Response(JSON.stringify(body), { status });
    return new Response(JSON.stringify({ items: [] }), { status: 200 });
  }) as typeof fetch;
  render(
    <MemoryRouter initialEntries={[`/studio/${post}`]}>
      <Routes><Route path="/studio/:post" element={<WriteupPage />} /></Routes>
    </MemoryRouter>,
  );
}

test("a flagged write-up shows the regeneration band, replacements and a prefilled commission", async () => {
  mount(rendered);
  const band = await screen.findByRole("alert", { name: "Regeneration required" });
  expect(within(band).getByText("log2(B/A) = 1.54.")).toBeTruthy();
  expect(within(band).getByRole("link", { name: "Correction" }).getAttribute("href")).toBe(`/post/${replacement}`);
  fireEvent.click(within(band).getByRole("button", { name: "Commission a regeneration" }));
  expect((within(band).getByLabelText("Commission type") as HTMLSelectElement).value).toBe("writing");
  expect((within(band).getByLabelText("Scope") as HTMLInputElement).value).toContain(`Regenerate write-up ${post}`);
});

test("pointers show what they open and pin the record with links to the artifact and its bytes", async () => {
  mount(rendered);
  const pointer = await screen.findByRole("link", { name: "1.45" });
  expect(screen.getByRole("tooltip").textContent).toContain("Claim (withdrawn) by alice");
  expect(document.querySelectorAll("[data-untrusted]").length).toBeGreaterThan(0);
  fireEvent.click(pointer);
  const detail = screen.getByLabelText("Pointer detail");
  expect(within(detail).getByRole("link", { name: /artifact_c/ }).getAttribute("href")).toBe(`/artifact/${artifact}`);
  expect(within(detail).getByRole("link", { name: "bytes" }).getAttribute("href")).toBe(`/api/artifacts/${artifact}/bytes`);
  expect(screen.getByLabelText("Review form")).toBeTruthy();
});

test("a refused write-up lists every unpointed number with its location and is not rendered", async () => {
  mount(refused, 422);
  const refusal = await screen.findByRole("alert", { name: "Renderer refusal" });
  expect(within(refusal).getByText(/Not served: 1 problem/)).toBeTruthy();
  expect(within(refusal).getByText(/line 2, offset 31/)).toBeTruthy();
  expect(refusal.querySelector("mark")?.textContent).toBe("3");
  expect(screen.queryByLabelText("Pointer detail")).toBeNull();
});

test("numbers are marked in place: verified underlined, unverified marked with the reason", async () => {
  const cell = `${artifact}#row=B_vs_A;col=log2_ratio`;
  mount({
    ...rendered, flagged: false, regeneration_required: null,
    stats: { numbers: 2, pointed: 2, units: 1, pointers: 2, verified: 1, unverified: 1, unpointed: 0 },
    verdict: { source: "recorded", rules: "writeup-pointers/2", created: "2026-10-06T00:00:00+00:00" },
    blocks: [{
      type: "paragraph", offset: 0, byline: false,
      sentences: [{
        id: "s1", offset: 0, length: 60, pointers: [artifact],
        numbers: [
          { text: "1.54", offset: 9, length: 4, covered_by: [artifact], scope: "cell", status: "verified",
            pointers: [{ id: artifact, kind: "artifact", locator: "row=B_vs_A;col=log2_ratio", result: "verified", at: "cell" }] },
          { text: "1.45", offset: 30, length: 4, covered_by: [artifact], scope: "line", status: "unverified",
            pointers: [{ id: artifact, kind: "artifact", result: "unverified", reason: "the value does not occur in the output bytes" }] },
        ],
        tokens: [
          { t: "text", text: "Measured ", offset: 0 },
          { t: "pointer", id: artifact, kind: "artifact", locator: "row=B_vs_A;col=log2_ratio", text: "1.54", form: "link", offset: 8, length: 80, text_offset: 9 },
          { t: "text", text: "; reported ", offset: 19 },
          { t: "text", text: "1.45 ", offset: 30 },
          { t: "pointer", id: artifact, kind: "artifact", text: cell, form: "citation", offset: 35, length: 70 },
        ],
      }],
    }],
    pointers: { [artifact]: { id: artifact, kind: "artifact", present: true, title: "Contrast", output_role: "contrast-table" } },
  });
  const verified = await screen.findByText("1.54", { selector: ".num-verified" });
  expect(verified.closest("a")).toBeTruthy();
  const unverified = screen.getByText("1.45", { selector: ".num-unverified" });
  expect(unverified.getAttribute("title")).toContain("the value does not occur in the output bytes");
  expect(screen.getByText(/1 verified/)).toBeTruthy();
  expect(screen.getByText(/verdict recorded/)).toBeTruthy();
});

test("a withheld write-up shows the recorded verdict's locations without its source", async () => {
  mount({
    status: "refused", rules: "writeup-pointers/2", post: { ...rendered.post, title: "Write-up withheld: refused by the number checker" },
    request: null, regeneration_required: null, placeholder: "This write-up was refused by the number checker (1 problem).",
    verdict: { source: "recorded", rules: "writeup-pointers/2" },
    problems: [{ kind: "unpointed_number", text: "4", offset: 48, length: 1, line: 1, reason: "no claim or artifact pointer at this number",
      context: "The ratio is 1.54 [claim] across 4 samples.", context_start: 15 }],
  }, 422);
  const refusal = await screen.findByRole("alert", { name: "Renderer refusal" });
  expect(within(refusal).getByText(/refused by the number checker/)).toBeTruthy();
  expect(refusal.querySelector("mark")?.textContent).toBe("4");
  expect(screen.getByRole("heading", { name: "Write-up withheld: refused by the number checker" })).toBeTruthy();
});
