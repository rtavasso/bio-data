import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link } from "react-router-dom";

// Renders untrusted Markdown (posts, notebooks). Raw HTML is never rendered; only http(s), mailto and
// in-app links survive. Record identifiers become links, so a number's pointer is one click away.
// With `onAnchor`, selecting text reports a locator into the source bytes: offset and length in the
// Markdown source (the stored blob), plus the quote, so anchors survive re-rendering.

export interface TextAnchor {
  kind: "paragraph" | "line";
  offset: number;
  length: number;
  quote: string;
}

const ROUTES: [RegExp, (id: string) => string][] = [
  [/^post_[0-9a-f]{32}$/, (id) => `/post/${id}`],
  [/^artifact_[0-9a-f]{64}$/, (id) => `/artifact/${id}`],
  [/^run_[0-9a-f]{32}$/, (id) => `/run/${id}`],
  [/^(agent|human|system|operator)_[0-9a-f]{32}$/, (id) => `/agent/${id}`],
];
const IDENTIFIER = /\b((?:post|run|agent|human|system|operator)_[0-9a-f]{32}|artifact_[0-9a-f]{64})\b/g;

export function routeFor(identifier: string): string | null {
  for (const [pattern, route] of ROUTES) if (pattern.test(identifier)) return route(identifier);
  return null;
}

export function linkIdentifiers(source: string): string {
  // Leave fenced and inline code untouched; link bare identifiers elsewhere.
  return source
    .split(/(```[\s\S]*?```|`[^`\n]*`|\[[^\]]*\]\([^)]*\))/g)
    .map((part, index) => (index % 2 ? part : part.replace(IDENTIFIER, (id) => `[${id}](${routeFor(id)})`)))
    .join("");
}

function safeHref(href?: string): string | null {
  if (!href) return null;
  if (href.startsWith("/") && !href.startsWith("//")) return href;
  try {
    const url = new URL(href);
    return ["http:", "https:", "mailto:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function anchorFromSelection(root: HTMLElement, source: string): TextAnchor | null {
  const selection = window.getSelection();
  const quote = selection?.toString().trim();
  if (!selection || !quote || selection.rangeCount === 0) return null;
  let node: Node | null = selection.getRangeAt(0).startContainer;
  while (node && node !== root && !(node instanceof HTMLElement && node.dataset.offset)) node = node.parentNode;
  const base = node instanceof HTMLElement && node.dataset.offset ? Number(node.dataset.offset) : 0;
  const found = source.indexOf(quote, base);
  const offset = found >= 0 ? found : source.indexOf(quote);
  if (offset < 0) return null; // Selection spans rendered decoration that is not in the source.
  return { kind: "paragraph", offset, length: quote.length, quote };
}

export function Markdown({ source, onAnchor }: { source: string; onAnchor?: (anchor: TextAnchor) => void }) {
  // Identifier links are added for display only; offsets refer to the original source.
  const display = onAnchor ? source : linkIdentifiers(source);
  const block = (Tag: "p" | "li" | "td" | "h1" | "h2" | "h3" | "h4") =>
    function Block({ node, children }: { node?: { position?: { start: { offset?: number } } }; children?: ReactNode }) {
      return <Tag data-offset={node?.position?.start.offset ?? undefined}>{children}</Tag>;
    };
  return (
    <div
      className="markdown"
      onMouseUp={
        onAnchor
          ? (event) => {
              const anchor = anchorFromSelection(event.currentTarget, source);
              if (anchor) onAnchor(anchor);
            }
          : undefined
      }
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          p: block("p"), li: block("li"), td: block("td"), h1: block("h1"), h2: block("h2"), h3: block("h3"), h4: block("h4"),
          a({ href, children }) {
            const safe = safeHref(href);
            if (!safe) return <span>{children}</span>;
            if (safe.startsWith("/")) return <Link to={safe}>{children}</Link>;
            return <a href={safe} rel="noopener noreferrer nofollow" target="_blank">{children}</a>;
          },
          img({ alt }) {
            return <span className="muted">[image omitted: {alt}]</span>;
          },
        }}
      >
        {display}
      </ReactMarkdown>
    </div>
  );
}
