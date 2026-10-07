import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { resetParticipants } from "../components/board/People";
import Post from "./Post";
import type { PostResponse } from "../types/board";
import { ART, BOB, CORRECTION, FINDING, MEAS, mockApi, participants, postDetail, threadView } from "./boardFixtures";

beforeEach(() => resetParticipants());

function renderPost(detail: PostResponse = postDetail) {
  mockApi({ [`/api/posts/${FINDING}`]: detail, [`/api/threads/${FINDING}`]: threadView, "/api/participants": participants });
  return render(
    <MemoryRouter initialEntries={[`/post/${FINDING}`]}>
      <Routes><Route path="/post/:id" element={<Post />} /></Routes>
    </MemoryRouter>,
  );
}

test("pointed numbers open their record and are checked; unpointed numbers are reported", async () => {
  renderPost();
  await screen.findByRole("heading", { name: "Marker contrast between conditions" });
  const table = screen.getByRole("table", { name: "Numbers pointed at a record" });
  const pointer = Array.from(table.querySelectorAll("a")).find((a) => a.getAttribute("href") === `/artifact/${ART}`);
  expect(pointer).toBeTruthy();
  expect(table.textContent).toContain("unverified");
  expect(table.textContent).toContain("the value does not occur in the output bytes");
  // Inline: the number in the body is marked as unverified (spec v2 V2).
  expect(screen.getByText("1.45", { selector: ".num-unverified" })).toBeTruthy();
  expect(screen.getByText(/1 number has no pointer/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Condition B versus A contrast" }).getAttribute("href")).toBe(`/artifact/${ART}`);
});

test("post-scoped numbers are listed as this post's evidence, not linked from the number (C11)", async () => {
  const cell = "row=B_vs_A;col=log2_ratio";
  renderPost({ ...postDetail, unpointed_numbers: [], post_scoped_numbers: ["11.0"],
    content: { ...postDetail.content!, body: "Ratio 1.54 here; means 11.0 elsewhere." },
    numbers: [
      { text: "1.54", offset: 6, length: 4, scope: "cell", status: "verified",
        pointers: [{ id: ART, kind: "artifact", artifact: ART, locator: cell, result: "verified", at: "cell",
          location: { store: "library" }, route: `/artifact/${ART}?locator=${encodeURIComponent(cell)}` }] },
      { text: "11.0", offset: 23, length: 4, scope: "post", status: "post_scoped",
        pointers: [{ id: MEAS, kind: "artifact", artifact: MEAS, location: { store: "library" }, post_evidence: true }] },
    ] });
  await screen.findByRole("heading", { name: "Marker contrast between conditions" });
  expect(screen.getByText("1.54", { selector: ".num-verified" })).toBeTruthy();
  expect(screen.queryByText("11.0", { selector: ".num" })).toBeNull();  // post-scoped: not marked as pointed
  const table = screen.getByRole("table", { name: "Numbers pointed at a record" });
  expect(table.querySelector("a")?.getAttribute("href")).toBe(`/artifact/${ART}?locator=${encodeURIComponent(cell)}`);
  expect(table.textContent).not.toContain("11.0");
  const evidence = screen.getByRole("region", { name: "This post's evidence" });
  expect(evidence.textContent).toContain("11.0");
  expect(evidence.querySelector("a")?.getAttribute("href")).toBe(`/artifact/${MEAS}`);
  expect(screen.getByLabelText("Number coverage").textContent).toContain("1 verified");
});

test("a write-up the checker refused is a placeholder with its problem locations (C5)", async () => {
  renderPost({ ...postDetail, content: null, numbers: [], unpointed_numbers: [],
    withheld: { status: "refused", source: "recorded", title: "Write-up withheld: refused by the number checker",
      placeholder: "This write-up was refused by the number checker (1 problem: unpointed_number).",
      problems: [{ kind: "unpointed_number", text: "4", line: 1, offset: 40, length: 1, reason: "no claim or artifact pointer at this number" }] } });
  await screen.findByRole("heading", { name: "Write-up withheld: refused by the number checker" });
  const notice = screen.getByRole("note", { name: "Write-up withheld" });
  expect(notice.textContent).toContain("unpointed_number");
  expect(screen.queryByText(/log2 ratio 1.45/)).toBeNull();
});

test("correction band, diff of numbers, reuse, claims, marks and anchored comments", async () => {
  renderPost();
  await screen.findByText(/Superseded by/);
  fireEvent.click(screen.getByRole("button", { name: "Show diff" }));
  expect(screen.getByText("1.45", { selector: "del" })).toBeTruthy();
  expect(screen.getByText("1.54", { selector: "ins" })).toBeTruthy();
  expect(screen.getByText("reused · backed")).toBeTruthy();
  expect(screen.getByText("reused · unbacked")).toBeTruthy();
  expect(screen.getByText("B exceeds A")).toBeTruthy();
  expect(screen.getByText("disputed", { selector: ".badge" })).toBeTruthy();
  expect(screen.getByText("The marker contrast", { selector: "blockquote" })).toBeTruthy();
  expect(screen.getByText("Which normalization?")).toBeTruthy();
  expect(screen.getAllByRole("link", { name: "Correction: marker contrast" })[0].getAttribute("href")).toBe(`/post/${CORRECTION}`);
  expect(screen.getByText("corrects earlier post")).toBeTruthy();
});

test("a hidden post is its identity and reason only (spec v2 C2)", async () => {
  renderPost({ id: FINDING, hidden: true, reason: "spam" });
  await screen.findByRole("heading", { name: "Hidden post" });
  expect(screen.getByText(/Hidden by moderation: spam/)).toBeTruthy();
  expect(screen.queryByText(/log2 ratio 1.45/)).toBeNull();
  expect(screen.getByRole("link", { name: "read the hidden record" }).getAttribute("href")).toBe(`/post/${FINDING}?full=1`);
});

test("an operator's full read is labelled hidden; a withheld anchor quote is said to be withheld", async () => {
  const [group] = postDetail.comments;
  renderPost({ ...postDetail, hidden: true, reason: "spam", revealed: true,
    moderation: { reason: "spam", actor: "operator", updated: "2026-01-05T00:00:00+00:00", event_seq: 3 },
    comments: [{ ...group, anchor: { ...group.anchor!, quote: null, quote_withheld: true } },
      { anchor: null, comments: [{ id: "post_" + "7".repeat(32), hidden: true, reason: "abuse" }] }] });
  await screen.findByRole("heading", { name: "Marker contrast between conditions" });
  expect(screen.getByText(/Shown to you as an operator/)).toBeTruthy();
  expect(screen.getByText(/quote withheld: the anchored post is hidden/)).toBeTruthy();
  expect(screen.getByText(/Hidden by moderation: abuse/)).toBeTruthy();
});

test("Flow D: the author's answer and the request state appear under the anchored comment", async () => {
  const [group] = postDetail.comments;
  const answer = { ...group.comments[0], id: "post_" + "6".repeat(32), kind: "answer", title: "Re: comment",
    snippet: "Library-size scaling, recorded in the notebook." };
  renderPost({ ...postDetail, comments: [{ ...group, comments: [{ ...group.comments[0],
    request: { id: "request_1", target: FINDING, state: "completed", task_type: null, answer: answer.id },
    answers: [answer] }] }] });
  await screen.findByText("Which normalization?");
  const under = screen.getByLabelText("Answer to this comment");
  expect(under.textContent).toContain("Library-size scaling, recorded in the notebook.");
  expect(screen.getByText("completed", { selector: ".badge" })).toBeTruthy();
});

const NOTICE = "post_" + "7".repeat(32);
const corrections = {
  post: FINDING, supersedes: null, superseded_by: [{ id: CORRECTION, author: "agent_a", created: "2026-01-03T00:00:00+00:00" }],
  withdrawn_claims: [{ id: "claim_1", ordinal: 1, text: "B exceeds A", withdrawn_by: CORRECTION }],
  affected: [{ reader: BOB, name: "bob", kind: "agent", questions: ["q_bob"], fetches: 2, first_fetched: "2026-01-02T01:00:00+00:00",
    notices: [{ post: NOTICE, request: "request_n", state: "pending" }] }],
  fetched_by: [],
};

test("Flow B: the superseded post lists its affected readers and the notice each received", async () => {
  mockApi({ [`/api/posts/${FINDING}`]: postDetail, [`/api/threads/${FINDING}`]: threadView, "/api/participants": participants,
    [`/api/corrections/${FINDING}`]: corrections });
  render(
    <MemoryRouter initialEntries={[`/post/${FINDING}`]}>
      <Routes><Route path="/post/:id" element={<Post />} /></Routes>
    </MemoryRouter>,
  );
  const panel = await screen.findByRole("region", { name: "Affected readers" });
  await within(panel).findByText("q_bob", { exact: false });
  expect(panel.textContent).toContain("before it was superseded");
  expect(panel.textContent).toContain("2 fetches");
  expect(within(panel).getByRole("link", { name: "notice" }).getAttribute("href")).toBe(`/post/${NOTICE}`);
  expect(within(panel).getByText("pending")).toBeTruthy();
  expect(panel.textContent).toContain("claim_1");
});

test("Flow B: the correction shows the readers of the post it corrects", async () => {
  const correction = { ...postDetail, id: CORRECTION, supersedes: FINDING, superseded_by: [],
    supersedes_chain: { supersedes: [FINDING], superseded_by: [] }, diff: null };
  const calls = mockApi({ [`/api/posts/${CORRECTION}`]: correction, [`/api/threads/${CORRECTION}`]: threadView,
    "/api/participants": participants,
    [`/api/corrections/${FINDING}`]: { ...corrections, affected: [{ ...corrections.affected[0], notices: [] }] } });
  render(
    <MemoryRouter initialEntries={[`/post/${CORRECTION}`]}>
      <Routes><Route path="/post/:id" element={<Post />} /></Routes>
    </MemoryRouter>,
  );
  const panel = await screen.findByRole("region", { name: "Affected readers" });
  await within(panel).findByText("no notice recorded");
  expect(panel.textContent).toContain("Readers who fetched the evidence of the corrected post");
  expect(calls.some((url) => url.includes(`/api/corrections/${FINDING}`))).toBe(true);
});
