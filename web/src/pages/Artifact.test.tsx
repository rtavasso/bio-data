import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { resetParticipants } from "../components/board/People";
import Artifact from "./Artifact";
import { ART, FINDING, MEAS, artifactView, mockApi, participants } from "./boardFixtures";

beforeEach(() => resetParticipants());

test("artifact page shows derivation inputs, provenance, holders, posts and safe byte links", async () => {
  mockApi({ [`/api/artifacts/${ART}`]: artifactView, "/api/participants": participants });
  render(
    <MemoryRouter initialEntries={[`/artifact/${ART}`]}>
      <Routes><Route path="/artifact/:id" element={<Artifact />} /></Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: "Condition B versus A contrast" });
  const inputs = screen.getAllByRole("link", { name: "Per-condition marker means" });
  expect(inputs.every((a) => a.getAttribute("href") === `/artifact/${MEAS}`)).toBe(true);
  expect(screen.getByText("reused · backed")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Marker contrast between conditions" }).getAttribute("href")).toBe(`/post/${FINDING}`);
  expect(screen.getByRole("link", { name: "Download" }).getAttribute("href")).toBe(`/api/artifacts/${ART}/bytes?download=true`);
  expect(screen.getByText(/1 record beyond depth 1/)).toBeTruthy();
  expect(screen.getByText(/never executed/)).toBeTruthy();
  expect(screen.getByText("Is B_vs_A the right direction?")).toBeTruthy();
});
