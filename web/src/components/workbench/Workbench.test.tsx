import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../../App";
import Audit from "../../pages/Audit";
import { setSavedView } from "../../savedView";
import type { Inbox, InboxItem } from "../../types/workbench";
import { ReplyBox, RequestReview } from "./AnchorActions";
import { InboxList, useInbox } from "./Inbox";

const HASH = "c".repeat(64);

function respond(routes: Record<string, [number, unknown]>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    const key = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => url.startsWith(k));
    const [status, body] = key ? routes[key] : [404, { error: "unknown_endpoint" }];
    return new Response(JSON.stringify(body), { status });
  }) as typeof fetch;
  return calls;
}

afterEach(() => setSavedView(null));

const ITEM: InboxItem = {
  id: "answer:request_1", kind: "answer", seq: 12, created: "2026-10-01T00:00:00+00:00", post: "post_" + "a".repeat(32),
  title: "Re: question", author: "agent_alice", hidden: false, reason: null, read: false, read_at: null,
  relation: { table: "request", id: "request_1", field: "answer" }, request: "request_1", task_type: "question",
  asked: "post_" + "b".repeat(32),
};
const INBOX: Inbox = { participant: "human_x", items: [ITEM], total: 1, unread: 1, latest: 12, sequence: 20 };

function InboxHarness() {
  const inbox = useInbox(true);
  return <InboxList inbox={inbox} />;
}

test("inbox lists recorded items and marks them read through the write path", async () => {
  const calls = respond({ "/api/me/inbox/read": [200, { participant: "human_x", marked: [ITEM.id], read_at: "t" }],
    "/api/me/inbox": [200, INBOX] });
  render(<MemoryRouter><InboxHarness /></MemoryRouter>);
  expect(await screen.findByText("Re: question")).toBeTruthy();
  expect(screen.getByText("Answer to your request")).toBeTruthy();
  expect(screen.getByText(/1 unread of 1/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Mark read" }));
  await waitFor(() => expect(screen.getByText(/0 unread of 1/)).toBeTruthy());
  const write = calls.find((c) => c.url === "/api/me/inbox/read")!;
  expect(write.init?.method).toBe("POST");
  expect((write.init?.headers as Record<string, string>)["X-Colloquy-Request"]).toBe("1");
  expect(JSON.parse(String(write.init?.body))).toEqual({ items: [ITEM.id] });
});

test("a hidden inbox item shows the moderation reason, not the title", async () => {
  respond({ "/api/me/inbox": [200, { ...INBOX, items: [{ ...ITEM, hidden: true, title: null, reason: "spam" }] }] });
  render(<MemoryRouter><InboxHarness /></MemoryRouter>);
  expect(await screen.findByText(/Hidden by moderation: spam/)).toBeTruthy();
});

test("every screen accepts ?view=: API reads carry it and the view bar names it", async () => {
  const calls = respond({
    [`/api/views/${HASH}`]: [200, { view: HASH, spec: { format: 1, questions: ["q_" + "1".repeat(16)], participants: ["agent_b"],
      since: null, until: null }, created_by: "human_x", created: "t", participant_names: { agent_b: "bob" } }],
    "/api/posts": [200, { items: [], total: 0 }],
    "/api/": [200, {}],
  });
  render(<MemoryRouter initialEntries={[`/board?view=${HASH}`]}><App /></MemoryRouter>);
  expect(await screen.findByText(/1 question · participants bob/)).toBeTruthy();
  await waitFor(() => expect(calls.some((c) => c.url.startsWith("/api/posts") && c.url.includes(`view=${HASH}`))).toBe(true));
  expect(calls.some((c) => c.url.startsWith(`/api/views/${HASH}?`))).toBe(false);
  const links = Array.from(document.querySelectorAll("nav a")).map((a) => a.getAttribute("href"));
  expect(links.every((href) => href?.includes(`view=${HASH}`))).toBe(true);
});

test("a members-only commons tells an anonymous reader to log in", async () => {
  respond({ "/api/access": [200, { mode: "accounts", read: "members", authenticated: false, participant: null, member: false,
    reason: "authentication_required", note: "" }], "/api/": [401, { error: "authentication_required" }] });
  render(<MemoryRouter initialEntries={["/board"]}><App /></MemoryRouter>);
  expect(await screen.findByText(/readable by its members only/)).toBeTruthy();
});

test("reply under an anchor and request review go through the write API", async () => {
  const calls = respond({ "/api/comments/": [200, { post: "post_r", parent: "post_c", in_reply_to: "post_c" }],
    "/api/reviews": [200, { id: "request_9", post: "post_x", target: "agent_b", state: "pending", task_type: "review",
      claim: "claim_1", anchor: {}, anchor_comment: "post_c" }],
    "/api/participants": [200, { items: [{ id: "agent_b", name: "bob", kind: "agent", created: "t" }] }] });
  const done = vi.fn();
  render(<MemoryRouter><ReplyBox comment="post_c" onDone={done} /><RequestReview claim="claim_1" comment="post_c" /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Reply"), { target: { value: "Same here." } });
  fireEvent.click(screen.getByRole("button", { name: "Reply" }));
  await waitFor(() => expect(done).toHaveBeenCalled());
  const reply = calls.find((c) => c.url === "/api/comments/post_c/replies")!;
  expect(JSON.parse(String(reply.init?.body))).toEqual({ body: "Same here." });
  await screen.findByRole("option", { name: "bob" });
  fireEvent.change(screen.getByLabelText("Reviewer"), { target: { value: "agent_b" } });
  fireEvent.click(screen.getByRole("button", { name: "Request review" }));
  expect(await screen.findByText(/Review commissioned \(request_9\)/)).toBeTruthy();
  const review = calls.find((c) => c.url === "/api/reviews")!;
  expect(JSON.parse(String(review.init?.body))).toEqual({ claim: "claim_1", target: "agent_b", budget: { minutes: 30 }, comment: "post_c" });
});

test("audit log: operators page events by kind; others are refused", async () => {
  const calls = respond({
    "/api/audit": [200, { items: [{ seq: 5, kind: "mark_recorded", created: "t", body: { participant: "human_x" } }], total: 1,
      facets: { mark_recorded: 1 }, kinds: ["mark_recorded", "published"], next_before: null, login_failures_recorded: 0 }],
    "/api/access": [200, { mode: "accounts", read: "private", authenticated: true, participant: "op", member: true, reason: null, note: "operators" }],
    "/api/members": [200, { read_policy: "private", items: [] }],
  });
  render(<MemoryRouter><Audit /></MemoryRouter>);
  expect(await screen.findByText("mark_recorded", { selector: "td" })).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Event kind"), { target: { value: "published" } });
  fireEvent.click(screen.getByRole("button", { name: "Filter" }));
  await waitFor(() => expect(calls.some((c) => c.url.startsWith("/api/audit") && c.url.includes("kind=published"))).toBe(true));
  respond({ "/api/audit": [403, { error: "permission_denied" }] });
  render(<MemoryRouter><Audit /></MemoryRouter>);
  expect(await screen.findByText("The audit log is for operators.")).toBeTruthy();
});
