import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { WatcherPanel } from "./WatcherPanel";
import type { WatcherList, WatcherRun } from "../../types/discovery";

const list: WatcherList = {
  providers: ["europepmc", "pride"], cadence: "weekly by default",
  items: [{
    id: "watcher_1", item: "frontier_1", author: "operator", provider: "europepmc", interval_seconds: 604800,
    query: { query: "demo marker knockdown", filters: { source: "MED" }, max_pages: 1, page_size: 25 },
    next_due: 0, next_due_utc: "2026-10-13T00:00:00Z", enabled: true, created: "2026-10-06", runs: 1,
    last_run: { id: "watcher_run_1", created: "2026-10-06T00:00:00", found: 1, post: "post_notice" },
  }],
};
const runs: { items: WatcherRun[] } = {
  items: [{
    id: "watcher_run_1", watcher: "watcher_1", item: "frontier_1", provider: "europepmc", query: list.items[0].query,
    receipt_blob: "a".repeat(64), post: "post_notice", created: "2026-10-06T00:00:00",
    found: [{ accession: "DEMO0001", provider: "europepmc", title: "Synthetic hit" }],
    receipt: { new: [{ accession: "DEMO0001", provider: "europepmc", title: "Synthetic hit" }], warnings: [], exhausted: true, pages: [] },
  }],
};

let posts: { url: string; body: unknown }[] = [];
beforeEach(() => {
  posts = [];
  globalThis.fetch = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    if (init?.method === "POST") {
      posts.push({ url: path, body: JSON.parse(String(init.body)) });
      return new Response(JSON.stringify(list.items[0]), { status: 200 });
    }
    return new Response(JSON.stringify(path.includes("/runs") ? runs : list), { status: 200 });
  }) as typeof fetch;
});

test("lists watchers with status and runs; provider hits are labelled untrusted", async () => {
  render(<MemoryRouter><WatcherPanel item="frontier_1" /></MemoryRouter>);
  await waitFor(() => expect(screen.getByText("demo marker knockdown")).toBeTruthy());
  expect(screen.getByText(/where source=MED/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "latest notice" }).getAttribute("href")).toBe("/post/post_notice");
  fireEvent.click(screen.getByRole("button", { name: "Runs" }));
  await waitFor(() => expect(screen.getByText("DEMO0001")).toBeTruthy());
  expect(screen.getByText("new")).toBeTruthy();
  expect(screen.getByText("DEMO0001").closest("[data-untrusted]")).toBeTruthy();
});

test("attaching a watcher posts the scoped query with literal filters", async () => {
  render(<MemoryRouter><WatcherPanel item="frontier_1" /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole("option", { name: "pride" })).toBeTruthy());
  fireEvent.change(screen.getByLabelText("Watcher query"), { target: { value: "Nae1 knockdown" } });
  fireEvent.change(screen.getByLabelText("Literal filters on returned hits"), { target: { value: "source=MED" } });
  fireEvent.click(screen.getByRole("button", { name: "Attach watcher" }));
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(posts[0]).toEqual({ url: "/api/watchers", body: {
    item: "frontier_1", provider: "europepmc", interval_seconds: 604800, query: { query: "Nae1 knockdown", filters: { source: "MED" } },
  } });
});
