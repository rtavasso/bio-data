// The URL path this commons is served under: "/" for `bio commons serve`, "/c/<tenant>/" under
// `bio commons host`. The server announces it in <meta name="colloquy-base">; the router basename and
// every API URL derive from it, so the same build works at any prefix.

export function readBase(doc: Document | undefined = typeof document === "undefined" ? undefined : document): string {
  const content = doc?.querySelector('meta[name="colloquy-base"]')?.getAttribute("content") ?? "/";
  // Only a plain absolute path is accepted; anything else falls back to the root.
  return /^\/(?:[A-Za-z0-9._~-]+\/)*$/.test(content) && !/\/\.\.?\//.test(content) ? content : "/";
}

export const BASE = readBase();

// react-router basename: the base without its trailing slash ("/" stays "/").
export function basename(base: string = BASE): string {
  return base === "/" ? "/" : base.replace(/\/$/, "");
}

// Root-relative app or API paths ("/api/...", as the server also returns them in links) under the base.
// Absolute URLs and anything else are returned unchanged.
export function withBase(path: string, base: string = BASE): string {
  if (!path.startsWith("/") || path.startsWith("//")) return path;
  return base + path.slice(1);
}
