import { Fragment, useId, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { withBase } from "../../base";
import type { Block, PointerEntry, Sentence, Token } from "../../types/studio";

// Renders the server's HTML-safe write-up blocks without ever injecting HTML. Every pointer is a link to its
// record; hovering or focusing shows what it opens, and clicking pins the record in the detail pane, which
// links on to the artifact page and its verified bytes (sentence → pointer → artifact → bytes).

export function shortId(id: string): string {
  const [kind, rest = ""] = id.split(/_(.*)/s);
  return rest.length > 10 ? `${kind}_${rest.slice(0, 8)}…` : id;
}

export function routeOf(id: string, entry?: PointerEntry): string | null {
  if (entry?.route) return entry.route;
  if (/^post_[0-9a-f]{32}$/.test(id)) return `/post/${id}`;
  if (/^artifact_[0-9a-f]{64}$/.test(id)) return `/artifact/${id}`;
  return null;
}

function summary(id: string, entry?: PointerEntry): string {
  if (!entry || !entry.present) return `${id}: not found`;
  if (entry.kind === "claim") return `Claim (${entry.status}) by ${entry.author_name ?? entry.author}: ${entry.text}`;
  if (entry.kind === "artifact") return `Artifact ${entry.title ?? id} · ${entry.output_role} · sha256 ${entry.sha256?.slice(0, 12)}…`;
  return `Post: ${entry.title ?? id}`;
}

function Pointer({ token, entry, onOpen, active }: {
  token: Extract<Token, { t: "pointer" }>; entry?: PointerEntry; onOpen: (id: string) => void; active: boolean;
}) {
  const tip = useId();
  const label = token.form === "link" ? token.text : token.form === "citation" ? `[${shortId(token.id)}]` : shortId(token.id);
  const withdrawn = entry?.kind === "claim" && (entry.status === "withdrawn" || entry.withdrawn_by);
  const className = `st-pointer kind-${token.kind ?? "unknown"}${withdrawn ? " withdrawn" : ""}${active ? " active" : ""}`;
  return (
    <span className="st-pointer-wrap">
      <a href={withBase(routeOf(token.id, entry) ?? "#")} className={className} aria-describedby={tip} data-pointer={token.id}
        onClick={(event) => { event.preventDefault(); onOpen(token.id); }}>
        {label}
      </a>
      <span role="tooltip" id={tip} className="st-tip">{summary(token.id, entry)}</span>
    </span>
  );
}

function Tokens({ tokens, pointers, onOpen, active }: {
  tokens: Token[]; pointers: Record<string, PointerEntry>; onOpen: (id: string) => void; active: string | null;
}) {
  return (
    <>
      {tokens.map((token, n) => {
        switch (token.t) {
          case "text": {
            const text = token.text.split("\n").map((line, i) => <Fragment key={i}>{i ? <br /> : null}{line}</Fragment>);
            return token.style === "strong" ? <strong key={n}>{text}</strong> : token.style === "em" ? <em key={n}>{text}</em> : <Fragment key={n}>{text}</Fragment>;
          }
          case "code":
            return <code key={n}>{token.text}</code>;
          case "link":
            return <a key={n} href={token.href} rel="nofollow noopener noreferrer" target="_blank">{token.text}</a>;
          case "pointer":
            return <Pointer key={n} token={token} entry={pointers[token.id]} onOpen={onOpen} active={active === token.id} />;
          case "figure":
            return <Pointer key={n} token={{ ...token, t: "pointer", text: `figure: ${token.caption}`, form: "link" }}
              entry={pointers[token.id]} onOpen={onOpen} active={active === token.id} />;
          default:
            return null;
        }
      })}
    </>
  );
}

function Sentences({ sentences, ...rest }: { sentences: Sentence[]; pointers: Record<string, PointerEntry>; onOpen: (id: string) => void; active: string | null }) {
  return (
    <>
      {sentences.map((s, i) => (
        <Fragment key={s.id}>
          {i ? " " : null}
          <span className="st-sentence" id={`sentence-${s.id}`} data-offset={s.offset}>
            <Tokens tokens={s.tokens} {...rest} />
          </span>
        </Fragment>
      ))}
    </>
  );
}

function Figure({ id, caption, entry, onOpen }: { id: string; caption: string; entry?: PointerEntry; onOpen: (id: string) => void }) {
  return (
    <figure className="st-figure">
      {entry?.image_url ? <img src={withBase(entry.image_url)} alt={caption} /> : <div className="st-figure-missing">No image preview</div>}
      <figcaption>
        {caption} ·{" "}
        <button type="button" className="linkish" onClick={() => onOpen(id)}>source artifact</button>
        {entry?.bytes_url && <> · <a href={withBase(entry.bytes_url)}>bytes</a></>}
      </figcaption>
    </figure>
  );
}

export function WriteupBlocks({ blocks, pointers, onOpen, active }: {
  blocks: Block[]; pointers: Record<string, PointerEntry>; onOpen: (id: string) => void; active: string | null;
}) {
  const shared = { pointers, onOpen, active };
  const out: ReactNode[] = blocks.map((block, n) => {
    switch (block.type) {
      case "heading": {
        const Tag = `h${Math.min(6, block.level + 1)}` as "h2";
        return <Tag key={n}><Sentences sentences={block.sentences} {...shared} /></Tag>;
      }
      case "paragraph":
        return <p key={n} className={block.byline ? "st-byline" : undefined}><Sentences sentences={block.sentences} {...shared} /></p>;
      case "quote":
        return <blockquote key={n}><p><Sentences sentences={block.sentences} {...shared} /></p></blockquote>;
      case "figure":
        return <Figure key={n} id={block.id} caption={block.caption} entry={pointers[block.id]} onOpen={onOpen} />;
      case "list": {
        const items = block.items.map((item, i) => (
          <li key={i} value={item.ordinal ?? undefined} style={{ marginLeft: `${item.depth * 1.25}rem` }}>
            <Sentences sentences={item.sentences} {...shared} />
          </li>
        ));
        return block.ordered ? <ol key={n}>{items}</ol> : <ul key={n}>{items}</ul>;
      }
      case "table":
        return (
          <div key={n} className="table-scroll">
            <table>
              <thead><tr>{block.header.cells.map((cell, i) => <th key={i}><Tokens tokens={cell} {...shared} /></th>)}</tr></thead>
              <tbody>
                {block.rows.map((row) => (
                  <tr key={row.id}>{row.cells.map((cell, i) => <td key={i}><Tokens tokens={cell} {...shared} /></td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      case "code":
        return <pre key={n}><code>{block.text}</code></pre>;
      default:
        return <hr key={n} />;
    }
  });
  return <div className="markdown st-writeup">{out}</div>;
}

export function PointerDetail({ id, entry, onClose }: { id: string; entry?: PointerEntry; onClose: () => void }) {
  return (
    <aside className="st-detail" aria-label="Pointer detail">
      <div className="st-detail-head">
        <strong>{entry?.kind ?? "record"}</strong> <span className="mono">{id}</span>
        <button type="button" className="linkish" onClick={onClose} aria-label="Close detail">close</button>
      </div>
      {!entry?.present && <p className="error">This pointer does not resolve.</p>}
      {entry?.kind === "claim" && entry.present && (
        <>
          <p>{entry.text}</p>
          <p className="muted">
            {entry.status}{entry.stated_status && entry.stated_status !== entry.status ? ` (stated ${entry.stated_status})` : ""} · by {entry.author_name ?? entry.author} · in{" "}
            {entry.post && <Link to={`/post/${entry.post}`}>{entry.post_title ?? entry.post}</Link>}
          </p>
          {entry.withdrawn_by && <p className="st-flag-inline">Withdrawn by <Link to={`/post/${entry.withdrawn_by}`}>{entry.withdrawn_by}</Link></p>}
          <h4>Pointers</h4>
          <ul className="st-detail-pointers">
            {(entry.pointers ?? []).map((p, i) => (
              <li key={i}>
                <span className="muted">{p.kind}</span>{" "}
                {p.route ? <Link to={p.route}>{shortId(p.id)}</Link> : <span className="mono">{p.id}</span>}
                {p.locator ? ` (${p.locator})` : ""}
                {p.bytes_url && <> · <a href={withBase(p.bytes_url)}>bytes</a></>}
              </li>
            ))}
          </ul>
        </>
      )}
      {entry?.kind === "artifact" && entry.present && (
        <>
          <p>{entry.title}</p>
          <dl className="st-dl">
            <dt>Role</dt><dd>{entry.output_role}</dd>
            <dt>Output</dt><dd className="mono">{entry.name} · sha256 {entry.sha256}</dd>
            <dt>Held in</dt><dd>{entry.location?.store === "library" ? "shared library" : `workspace of ${entry.location?.participant}`}</dd>
          </dl>
          <p><Link to={`/artifact/${id}`}>Artifact page (derivation and provenance)</Link> · {entry.bytes_url && <a href={withBase(entry.bytes_url)}>Verified bytes</a>}</p>
        </>
      )}
      {entry?.kind === "post" && entry.present && (
        <p><Link to={`/post/${id}`}>{entry.title ?? id}</Link> <span className="muted">({entry.post_kind}; context, not evidence for a number)</span></p>
      )}
    </aside>
  );
}
