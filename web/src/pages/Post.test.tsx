import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { resetParticipants } from "../components/board/People";
import Post from "./Post";
import { ART, BOB, CORRECTION, FINDING, mockApi, participants, postDetail, threadView } from "./boardFixtures";

beforeEach(() => resetParticipants());

function renderPost(detail = postDetail) {
  mockApi({ [`/api/posts/${FINDING}`]: detail, [`/api/threads/${FINDING}`]: threadView, "/api/participants": participants });
  return render(
    <MemoryRouter initialEntries={[`/post/${FINDING}`]}>
      <Routes><Route path="/post/:id" element={<Post />} /></Routes>
    </MemoryRouter>,
  );
}

test("every number in a post opens its artifact; unpointed numbers are reported", async () => {
  renderPost();
  await screen.findByRole("heading", { name: "Marker contrast between conditions" });
  const table = screen.getByRole("table");
  const pointer = Array.from(table.querySelectorAll("a")).find((a) => a.getAttribute("href") === `/artifact/${ART}`);
  expect(pointer).toBeTruthy();
  expect(screen.getByText(/1 number has no artifact pointer/)).toBeTruthy();
  expect(screen.getByText("no pointer")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Condition B versus A contrast" }).getAttribute("href")).toBe(`/artifact/${ART}`);
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

test("a hidden post shows the reason, not the content", async () => {
  renderPost({ ...postDetail, content: null, numbers: [], unpointed_numbers: [],
    hidden: { reason: "spam", actor: "operator", updated: "2026-01-05T00:00:00+00:00", event_seq: 3 } });
  await screen.findByRole("heading", { name: "Hidden post" });
  expect(screen.getByText(/Hidden by moderation: spam/)).toBeTruthy();
  expect(screen.queryByText(/log2 ratio 1.45/)).toBeNull();
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
