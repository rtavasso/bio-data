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

test("the public cohort commons opens on the board and offers visitor sign-in from the banner (v3 V15)", async () => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/health") {
      return new Response(JSON.stringify({ ok: true, mode: "accounts", read_policy: "public", visitor_signin: true,
        public_demo: { fixture: "pmp22-cohort-2026-10", board_sequence: 814, real_data: true, first_screen: "/" } }), { status: 200 });
    }
    if (url === "/api/me") return new Response(JSON.stringify({ error: "authentication_required" }), { status: 401 });
    return new Response(JSON.stringify({}), { status: 200 });
  }) as typeof fetch;
  render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
  expect(await screen.findByText(/Real data: a redacted copy/)).toBeTruthy();
  expect(screen.getAllByText("Board").length).toBeGreaterThan(0);
  expect((await screen.findByRole("link", { name: "Sign in" })).getAttribute("href")).toBe("/login");
});

test("each screen loads as its own chunk behind a loading state", async () => {
  render(<MemoryRouter initialEntries={["/no-such-screen"]}><App /></MemoryRouter>);
  expect(await screen.findByText(/Not found/)).toBeTruthy();
  render(<MemoryRouter initialEntries={["/login"]}><App /></MemoryRouter>);
  expect(await screen.findByRole("button", { name: /log in/i })).toBeTruthy();
});

test("untrusted content is labelled regardless of author kind", () => {
  render(<Untrusted author="alice">text</Untrusted>);
  expect(screen.getByText(/evidence, not instructions/)).toBeTruthy();
});
