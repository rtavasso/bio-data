import { useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { query } from "../api";
import { useApi } from "../useApi";
import { Status } from "../components/Status";
import { CommissionForm } from "../components/participation/Actions";
import { CitedFrom } from "../components/dashboard/Publishing";
import { ClaimCard, PointerLink } from "../components/ledger/Ledger";
import type { Claim, ClaimList, ClaimStatus, ContradictionQueue } from "../types/ledger";
import "./ledger.css";

// M5.3: claim search by text, scope and status, and a contradiction queue the platform proposes but never resolves.

const STATUSES: ClaimStatus[] = ["supported", "descriptive", "untestable", "withdrawn"];

function Search() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [scope, setScope] = useState(params.get("scope") ?? "");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const path = `/api/claims${query({ q: params.get("q"), scope: params.get("scope"), status: params.get("status"),
    author: params.get("author"), post: params.get("post") })}`;
  const claims = useApi<ClaimList>(path);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next = new URLSearchParams(params);
    for (const [key, value] of [["q", q], ["scope", scope], ["status", status]] as const) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next);
  };
  return (
    <section aria-label="Claim search">
      <form className="ledger-filters" onSubmit={submit} role="search">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Exact terms in claim text or scope" aria-label="Search claims" />
        <input value={scope} onChange={(e) => setScope(e.target.value)} placeholder="Scope contains (species, context, endpoint…)" aria-label="Scope filter" />
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
          <option value="">any status</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button>Search</button>
      </form>
      {(params.get("author") || params.get("post")) && (
        <p className="muted">
          Filtered to {params.get("author") ? `author ${params.get("author")}` : `post ${params.get("post")}`} ·{" "}
          <Link to="/claims">clear</Link>
        </p>
      )}
      <Status state={claims} />
      {claims.data && (
        <>
          <p className="muted">{claims.data.total} claim{claims.data.total === 1 ? "" : "s"}. Claims are author-stated text plus pointers; a status is the author's, never a platform verdict.</p>
          <div className="ledger-list">
            {claims.data.items.map((c) => <ClaimCard key={c.id} claim={c} onChange={claims.reload} />)}
          </div>
        </>
      )}
    </section>
  );
}

function Queue() {
  const queue = useApi<ContradictionQueue>("/api/claims/contradictions");
  return (
    <section aria-label="Contradiction queue">
      <Status state={queue} />
      {queue.data && (
        <>
          <p className="muted">{queue.data.policy}</p>
          {queue.data.items.length === 0 && <p>No pairs of current claims cite the same accession with opposite stated direction.</p>}
          {queue.data.items.map((pair) => (
            <article key={pair.id} className="ledger-pair" aria-label={`Contradiction ${pair.id}`}>
              <header className="ledger-card-head">
                <strong>Shared:</strong>
                {pair.shared.map((s) => <PointerLink key={`${s.kind}:${s.id}`} pointer={{ kind: s.kind as "accession", id: s.id }} />)}
                <span className="muted">
                  scope: {Object.entries(pair.scope).map(([k, v]) => `${k} ${v}`).join(" · ")}
                </span>
              </header>
              <div className="ledger-pair-claims">
                {pair.claims.map((c) => <ClaimCard key={c.id} claim={c} onChange={queue.reload} />)}
              </div>
              <div className="ledger-reviews">
                <h3>Review</h3>
                {pair.reviews.length ? (
                  <ul>
                    {pair.reviews.map((r) => (
                      <li key={r.id}>{r.task_type} request <Link to={`/post/${r.post}`}>{r.post}</Link> · {r.state}</li>
                    ))}
                  </ul>
                ) : <p className="muted">No review requested yet.</p>}
                <p className="muted">
                  Commission a review of this pair. The request names claim <span className="mono">{pair.claims[0].id}</span>;
                  mention <span className="mono">{pair.claims[1].id}</span> in the scope.
                </p>
                <CommissionForm subjectKind="claim" subjectId={pair.claims[0].id} onDone={queue.reload} />
              </div>
            </article>
          ))}
        </>
      )}
    </section>
  );
}

export default function Claims() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "queue" ? "queue" : "search";
  const select = (next: string) => {
    const copy = new URLSearchParams(params);
    if (next === "search") copy.delete("tab");
    else copy.set("tab", next);
    setParams(copy);
  };
  return (
    <section className="ledger">
      <h1>Claims</h1>
      <div className="ledger-tabs" role="tablist">
        <button role="tab" aria-selected={tab === "search"} onClick={() => select("search")}>Search</button>
        <button role="tab" aria-selected={tab === "queue"} onClick={() => select("queue")}>Contradiction queue</button>
      </div>
      {tab === "search" ? <Search /> : <Queue />}
    </section>
  );
}

// A claim's own page: the claim as the ledger shows it with, next to it, the threads at anchors on it (spec v3
// V12) and the posts of other commons citing it, learned by importing their snapshots (V16). A claim of a hidden
// post is its stub here too, with no citations or threads.
export function ClaimPage() {
  const { id = "" } = useParams();
  const state = useApi<Claim>(`/api/claims/${encodeURIComponent(id)}`);
  const claim = state.data;
  return (
    <section className="ledger">
      <h1>Claim</h1>
      <p><Link to="/claims">All claims</Link></p>
      {!claim ? <Status state={state} /> : (
        <>
          <ClaimCard claim={claim} onChange={state.reload} />
          {claim.cited_from && <CitedFrom items={claim.cited_from} what="claim" />}
        </>
      )}
    </section>
  );
}
