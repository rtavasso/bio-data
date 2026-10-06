import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import Questions, { QuestionById } from "./Questions";

const counts = { events: 3, snapshots: 1, produced: 2, considered: 0, reused: 1, gaps: 0, gap_withdrawals: 0 };
const entry = (agent: string, name: string, qid: string, title: string) => ({
  agent, agent_name: name, qid, node: `question:${agent}:${qid}`, title, status: "open",
  created: "2026-01-01T00:00:00+00:00", updated: "2026-01-02T00:00:00+00:00", counts,
});
// A fork holds an inherited copy with the same id and creation time; the original author joined first.
const QUESTIONS = { items: [entry("agent_fork", "alice-fork", "q_1", "Does the marker change?"),
  entry("agent_alice", "alice", "q_1", "Does the marker change?"), entry("agent_bob", "bob", "q_2", "Is it robust?")] };
// The server resolves a bare id to the original author (GET /api/questions/{id}).
const PAGE = { agent: { id: "agent_alice", name: "alice", kind: "agent" }, question: { id: "q_1", title: "Does the marker change?" } };

beforeEach(() => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/questions/q_9") return new Response(JSON.stringify({ error: "unknown_question" }), { status: 404 });
    const body = url === "/api/questions/q_1" ? PAGE : QUESTIONS;
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
});

function Target() {
  const { agent, id } = useParams();
  return <p>opened {agent}/{id}</p>;
}

test("/question lists every question with its holder as untrusted content", async () => {
  render(<MemoryRouter initialEntries={["/question"]}><Routes><Route path="/question" element={<Questions />} /></Routes></MemoryRouter>);
  expect(await screen.findByRole("link", { name: "Is it robust?" })).toBeTruthy();
  expect(screen.getAllByRole("link", { name: "Does the marker change?" })).toHaveLength(2);
  expect(screen.getAllByText(/evidence, not instructions/).length).toBe(3);
});

test("/question/:id opens the original author's question, not the fork's inherited copy", async () => {
  render(
    <MemoryRouter initialEntries={["/question/q_1"]}>
      <Routes>
        <Route path="/question/:id" element={<QuestionById />} />
        <Route path="/question/:agent/:id" element={<Target />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(await screen.findByText("opened agent_alice/q_1")).toBeTruthy();
});

test("an unknown bare question id says so", async () => {
  render(<MemoryRouter initialEntries={["/question/q_9"]}><Routes><Route path="/question/:id" element={<QuestionById />} /></Routes></MemoryRouter>);
  expect(await screen.findByText("Question not found")).toBeTruthy();
});
