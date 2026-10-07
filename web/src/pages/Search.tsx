import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { query } from "../api";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import { useApi } from "../useApi";
import type { SearchItem, SearchResult } from "../types/discovery";
import "./Search.css";

// Search (M1.5 + M1.8 lexical vector index). Exact-term search is the default and primary; the lexical
// vector index embeds the query with the pinned local hashing model and ranks by cosine. Results come from
// the library and, optionally, every agent workspace (read-only), each labelled with its catalog. Article
// paragraphs are their own family. State lives in the URL so a search can be shared.

const FAMILIES: [string, string][] = [
  ["", "all families"],
  ["forum", "posts"],
  ["artifact", "artifacts"],
  ["work", "notebooks"],
  ["claim", "claims"],
  ["data", "data"],
  // Article paragraphs are their own search; data search shows each article once, as its jats document.
  ["paragraph", "article paragraphs"],
];
const PAGE = 20;

function target(item: SearchItem): string | null {
  const participant = item.source.participant;
  if (item.family === "forum") return `/post/${item.subject}`;
  if (item.family === "artifact") return `/artifact/${item.subject}`;
  if (item.family === "work" && participant) return `/question/${participant}/${item.subject}`;
  if (item.family === "claim") return `/claims${query({ q: item.subject })}`;
  return null;
}

function sourceLabel(item: SearchItem) {
  return item.source.scope === "library" ? "library" : `workspace · ${item.source.name ?? item.source.participant}`;
}

function Result({ item, vector }: { item: SearchItem; vector: boolean }) {
  const href = target(item);
  return (
    <li className="search-hit">
      <div className="search-hit-head">
        <span className="family">{item.family}</span>
        {href ? <Link to={href}>{item.title}</Link> : <span className="search-title">{item.title}</span>}
      </div>
      <div className="search-hit-meta muted">
        <span>{sourceLabel(item)}</span>
        {item.locator && <span className="mono" title="Paragraph locator">{item.locator}</span>}
        {!href && <span className="mono">{item.subject}</span>}
        {vector && <span title="Cosine similarity">cos {item.score.toFixed(3)}</span>}
      </div>
      {item.summary && (
        <Untrusted>
          <p className="search-snippet">{item.summary.slice(0, 400)}</p>
        </Untrusted>
      )}
    </li>
  );
}

export default function Search() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const vector = params.get("vector") === "true";
  const family = params.get("family") ?? "";
  const scope = params.get("scope") === "workspaces" ? "workspaces" : "library";
  const offset = Number(params.get("offset") ?? 0) || 0;
  const [draft, setDraft] = useState(q);
  useEffect(() => setDraft(q), [q]);
  const path = q.trim() ? `/api/search${query({ q, vector: vector || undefined, family, scope, offset: offset || undefined, limit: PAGE })}` : null;
  const result = useApi<SearchResult>(path);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    if (!("offset" in changes)) next.delete("offset");
    setParams(next);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    update({ q: draft.trim() });
  };
  const data = result.data;
  return (
    <section className="search-page">
      <h1>Search</h1>
      <form className="search-form" onSubmit={submit} role="search">
        <input type="search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Search posts, artifacts, notebooks, claims…"
          aria-label="Search text" />
        <button>Search</button>
        <fieldset className="search-mode">
          <legend className="visually-hidden">Mode</legend>
          <label><input type="radio" name="mode" checked={!vector} onChange={() => update({ vector: null })} /> Exact terms</label>
          <label><input type="radio" name="mode" checked={vector} onChange={() => update({ vector: "true" })} /> Lexical vector index (similar spelling)</label>
        </fieldset>
        <select value={family} onChange={(e) => update({ family: e.target.value })} aria-label="Family">
          {FAMILIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <select value={scope} onChange={(e) => update({ scope: e.target.value === "library" ? null : e.target.value })} aria-label="Scope">
          <option value="library">shared library</option>
          <option value="workspaces">library + agent workspaces</option>
        </select>
      </form>
      {vector && (
        <p className="muted small">
          The lexical vector index uses a pinned local hashing model (hashing-ngram-v1): it finds shared words and spellings
          (normalisation ≈ normalization), not synonyms or meaning. It is not a learned embedding; an optional learned model
          path exists but is untested. Exact-term search remains primary.
        </p>
      )}
      {!q.trim() && <p className="muted">Enter a query. A missing hit is not negative evidence.</p>}
      <Status state={result} />
      {data && (
        <>
          <p className="muted small" aria-live="polite">
            {data.total} result{data.total === 1 ? "" : "s"} · {data.method}
          </p>
          <ul className="search-sources muted small">
            {data.sources.map((s) => (
              <li key={s.participant ?? s.scope}>
                {s.scope === "library" ? "library" : s.name}: {s.error ? <span className="error">{s.error}</span> : `${s.total ?? 0}`}
                {s.coverage && s.coverage.without_current_vector > 0 && ` (${s.coverage.without_current_vector} documents not embedded)`}
              </li>
            ))}
          </ul>
          {data.items.length === 0 ? (
            <p className="muted">No hits. {vector ? "Try exact terms, or check the lexical vector index coverage." : "Try the lexical vector index for spelling variants."}</p>
          ) : (
            <ol className="search-results" start={offset + 1}>
              {data.items.map((item) => <Result key={`${item.source.participant ?? "library"}:${item.id}`} item={item} vector={data.vector} />)}
            </ol>
          )}
          <nav className="search-pages" aria-label="Result pages">
            {offset > 0 && <button type="button" onClick={() => update({ offset: String(Math.max(0, offset - PAGE)) })}>Previous</button>}
            {data.next_offset !== null && <button type="button" onClick={() => update({ offset: String(data.next_offset) })}>Next</button>}
          </nav>
          <details className="muted small">
            <summary>Limitations</summary>
            <ul>{data.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          </details>
        </>
      )}
    </section>
  );
}
