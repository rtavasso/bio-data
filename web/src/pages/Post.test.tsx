import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { resetParticipants } from "../components/board/People";
import Post from "./Post";
import { ART, CORRECTION, FINDING, mockApi, participants, postDetail, threadView } from "./boardFixtures";

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
