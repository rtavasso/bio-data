import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { resetParticipants } from "../components/board/People";
import Artifact, { locatorFrom } from "./Artifact";
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

test("the artifact page opens at a number's locator and highlights the cited cell (V2)", async () => {
  const cell = "row=B_vs_A;col=log2_ratio";
  const calls = mockApi({
    [`/api/artifacts/${ART}/locate`]: {
      artifact: ART, locator: cell, parsed: { row: "B_vs_A", col: "log2_ratio" }, kind: "cell", name: "contrast.tsv", present: true,
      header: ["contrast", "log2_ratio"], rows: [["A_vs_A", "0"], ["B_vs_A", "1.54"]], first_row: 1, total_rows: 2,
      target: { row: 2, col: 2, row_key: "B_vs_A", column: "log2_ratio", value: "1.54" }, value: 1.54,
    },
    [`/api/artifacts/${ART}`]: artifactView, "/api/participants": participants,
  });
  render(
    <MemoryRouter initialEntries={[`/artifact/${ART}?locator=${encodeURIComponent(cell)}`]}>
      <Routes><Route path="/artifact/:id" element={<Artifact />} /></Routes>
    </MemoryRouter>,
  );
  const region = await screen.findByRole("region", { name: "Cited location" });
  const target = await within(region).findByText("1.54");
  expect(target.tagName).toBe("TD");
  expect(target.getAttribute("aria-current")).toBe("true");
  expect(target.className).toContain("cell-target");
  expect(within(region).getByText("0").getAttribute("aria-current")).toBeNull();
  expect(calls).toContain(`/api/artifacts/${ART}/locate?locator=${encodeURIComponent(cell)}`);
});

test("a locator in the hash also opens the page at the cited line", async () => {
  expect(locatorFrom("", "#line=3")).toBe("line=3");
  expect(locatorFrom("?locator=key%3Da.b", "")).toBe("key=a.b");
  expect(locatorFrom("", "#section")).toBeNull();
  mockApi({
    [`/api/artifacts/${ART}/locate`]: { artifact: ART, locator: "line=2", parsed: { line: "2" }, kind: "line", name: "log.txt",
      present: true, lines: ["first", "second 32.0"], first_line: 1, total_lines: 2, target: { line: 2 } },
    [`/api/artifacts/${ART}`]: artifactView, "/api/participants": participants,
  });
  render(
    <MemoryRouter initialEntries={[`/artifact/${ART}#line=2`]}>
      <Routes><Route path="/artifact/:id" element={<Artifact />} /></Routes>
    </MemoryRouter>,
  );
  const region = await screen.findByRole("region", { name: "Cited location" });
  const line = await within(region).findByText(/second 32\.0/);
  expect(line.getAttribute("aria-current")).toBe("true");
});
