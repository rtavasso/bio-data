import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { resetParticipants } from "../components/board/People";
import Participant from "./Participant";
import { BOB, RHEA, RUN, agentActivity, humanActivity, mockApi, participants } from "./boardFixtures";

beforeEach(() => resetParticipants());

function renderPage(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/agent/${id}`]}>
      <Routes><Route path="/agent/:id" element={<Participant />} /></Routes>
    </MemoryRouter>,
  );
}

test("agent page shows deliveries and the reuse backed ratio", async () => {
  mockApi({ [`/api/participants/${BOB}/activity`]: agentActivity, "/api/participants": participants });
  renderPage(BOB);
  await screen.findByText("50%");
  expect(screen.getByText(/of reuse links backed/)).toBeTruthy();
  expect(screen.getByText("reused · unbacked")).toBeTruthy();
  expect(screen.getAllByRole("link").some((a) => a.getAttribute("href") === `/run/${RUN}`)).toBe(true);
  expect(screen.getByRole("heading", { name: "Commission a task" })).toBeTruthy();
});

test("human page shows promotions with task type and budget", async () => {
  mockApi({ [`/api/participants/${RHEA}/activity`]: humanActivity, "/api/participants": participants });
  renderPage(RHEA);
  await screen.findByText("replication");
  expect(screen.getByText("60 minutes")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Replicate the contrast" })).toBeTruthy();
  expect(screen.queryByText(/reuse links backed/)).toBeNull();
});
