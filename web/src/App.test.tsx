import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { Untrusted } from "./components/Untrusted";

beforeEach(() => {
  globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({}), { status: 200 })) as typeof fetch;
});

test("home is the board, not a prompt", () => {
  render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
  expect(screen.getAllByText("Board").length).toBeGreaterThan(0);
  expect(document.querySelector("textarea")).toBeNull();
});

test("untrusted content is labelled regardless of author kind", () => {
  render(<Untrusted author="alice">text</Untrusted>);
  expect(screen.getByText(/evidence, not instructions/)).toBeTruthy();
});
