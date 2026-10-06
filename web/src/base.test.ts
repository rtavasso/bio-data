import { basename, readBase, withBase } from "./base";
import { get } from "./api";

function docWith(content: string | null): Document {
  const doc = document.implementation.createHTMLDocument("t");
  if (content !== null) {
    const meta = doc.createElement("meta");
    meta.name = "colloquy-base";
    meta.content = content;
    doc.head.appendChild(meta);
  }
  return doc;
}

test("the base comes from the server's meta tag and falls back to the root", () => {
  expect(readBase(docWith("/c/lab-a/"))).toBe("/c/lab-a/");
  expect(readBase(docWith(null))).toBe("/");
  for (const bad of ["https://evil.example/", "c/lab", "/c/../x/", "//evil/", "/c/lab"]) {
    expect(readBase(docWith(bad))).toBe("/");
  }
});

test("router basename and API paths follow the base", () => {
  expect(basename("/")).toBe("/");
  expect(basename("/c/lab-a/")).toBe("/c/lab-a");
  expect(withBase("/api/posts?q=1", "/c/lab-a/")).toBe("/c/lab-a/api/posts?q=1");
  expect(withBase("/api/runs/r/raw", "/")).toBe("/api/runs/r/raw");
  expect(withBase("https://orcid.org/x", "/c/lab-a/")).toBe("https://orcid.org/x");
  expect(withBase("//evil.example/x", "/c/lab-a/")).toBe("//evil.example/x");
});

test("API calls use the base announced by the page", async () => {
  const calls: string[] = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return new Response("{}", { status: 200 });
  }) as typeof fetch;
  await get("/api/health");
  expect(calls).toEqual(["/api/health"]); // jsdom test page has no meta: the root
  vi.resetModules();
  const meta = document.createElement("meta");
  meta.name = "colloquy-base";
  meta.content = "/c/lab-b/";
  document.head.appendChild(meta);
  try {
    const prefixed = await import("./api");
    await prefixed.get("/api/health");
    expect(calls[1]).toBe("/c/lab-b/api/health");
  } finally {
    meta.remove();
  }
});
