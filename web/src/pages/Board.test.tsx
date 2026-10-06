import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { resetParticipants } from "../components/board/People";
import Board from "./Board";
import { BOB, FINDING, listing, mockApi, participants, running } from "./boardFixtures";

beforeEach(() => resetParticipants());

function renderBoard(path = "/board") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/board" element={<Board />} /></Routes>
    </MemoryRouter>,
  );
}

test("board lists threads with correction status, hidden placeholders and the running strip", async () => {
  mockApi({ "/api/posts": listing, "/api/running": running, "/api/participants": participants, "/api/health": { sequence: 20 } });
  renderBoard();
  const link = await screen.findByRole("link", { name: "Marker contrast between conditions" });
  expect(link.getAttribute("href")).toBe(`/post/${FINDING}`);
  expect(screen.getByText("corrected")).toBeTruthy();
  expect(screen.getByText(/Hidden by moderation: off-topic/)).toBeTruthy();
  expect(screen.getAllByText(/evidence, not instructions/).length).toBeGreaterThan(0);
  const strip = screen.getByRole("region", { name: "Running now" });
  await within(strip).findByText("Review the contrast");
  expect(within(strip).getByText(/1m 35s · 4.0 KB streamed/)).toBeTruthy();
  // The home screen is not a prompt: the post form opens only on request.
  expect(document.querySelector("textarea")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "New post" }));
  expect(screen.getByRole("form", { name: "New post" })).toBeTruthy();
});

test("filters and family search go to the read API", async () => {
  const calls = mockApi({ "/api/posts": listing, "/api/running": { items: [] }, "/api/participants": participants });
  renderBoard("/board?family=artifact&q=contrast");
  await screen.findByRole("link", { name: "Marker contrast between conditions" });
  expect(calls.some((c) => c.startsWith("/api/posts?") && c.includes("family=artifact") && c.includes("q=contrast"))).toBe(true);
  await screen.findByRole("option", { name: "bob" });
  fireEvent.change(screen.getByLabelText("Participant"), { target: { value: BOB } });
  await waitFor(() => expect(calls.some((c) => c.includes(`author=${BOB}`))).toBe(true));
});
