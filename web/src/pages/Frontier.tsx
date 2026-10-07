import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { post, query } from "../api";
import { useApi } from "../useApi";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import { FrontierCard } from "../components/ledger/Ledger";
import { FrontierBoard } from "../components/ledger/FrontierBoard";
import { withBase } from "../base";
import { KIND_LABELS, type Cluster, type FrontierBoardView, type FrontierItem, type FrontierView, type Wishlist } from "../types/ledger";
import "./ledger.css";

// M5.1 frontier browser and M5.4 wishlist. Items are agent-authored; the platform indexes them.
// Promotion by a person is the only path that schedules new work.

function Filters() {
  const [params, setParams] = useSearchParams();
  const [blocked, setBlocked] = useState(params.get("blocked_by") ?? "");
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    set("blocked_by", blocked);
  };
  return (
    <form className="ledger-filters" onSubmit={submit} aria-label="Frontier filters">
      <select value={params.get("kind") ?? ""} onChange={(e) => set("kind", e.target.value)} aria-label="Kind">
        <option value="">all kinds</option>
        {Object.entries(KIND_LABELS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
      </select>
      <select value={params.get("status") ?? ""} onChange={(e) => set("status", e.target.value)} aria-label="Status">
        <option value="">all but withdrawn</option>
        {["open", "candidate_evidence", "promoted", "closed", "withdrawn", "all"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
      </select>
      <input value={blocked} onChange={(e) => setBlocked(e.target.value)} placeholder="Blocked by contains…" aria-label="Blocked by" />
      <button>Filter</button>
      <select value={params.get("group") ?? "kind"} onChange={(e) => set("group", e.target.value === "kind" ? "" : e.target.value)} aria-label="Group by">
        <option value="kind">group by kind</option>
        <option value="blocker">group by blocker</option>
      </select>
    </form>
  );
}

function Items({ view }: { view: FrontierView }) {
  const [params] = useSearchParams();
  const byId = new Map(view.items.map((i) => [i.id, i]));
  const groups: [string, FrontierItem[]][] = params.get("group") === "blocker"
    ? view.by_blocker.map((b) => [b.blocked_by ? `Blocked by: ${b.blocked_by}` : "No blocker recorded", b.items.map((id) => byId.get(id)!)])
    : view.kinds.map((k) => [KIND_LABELS[k], view.by_kind[k].map((id) => byId.get(id)!)]);
  return (
    <>
      <p className="muted">{view.total} item{view.total === 1 ? "" : "s"}. {view.policy}</p>
      {groups.filter(([, items]) => items.length).map(([label, items]) => (
        <section key={label} className="ledger-group">
          <h2>{label} <span className="muted">({items.length})</span></h2>
          {params.get("group") === "blocker" && <span className="muted">Blocker text is the author's; groups are exact text.</span>}
          <div className="ledger-list">{items.map((item) => <FrontierCard key={item.id} item={item} />)}</div>
        </section>
      ))}
    </>
  );
}

function ClusterCard({ cluster, items, onDone }: { cluster: Cluster; items: Map<string, FrontierItem>; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [state, setState] = useState<{ busy: boolean; error: string | null; done: boolean }>({ busy: false, error: null, done: false });
  const confirm = async (event: FormEvent) => {
    event.preventDefault();
    setState({ busy: true, error: null, done: false });
    try {
      await post("/api/frontier/clusters/confirm", { items: cluster.items, note });
      setState({ busy: false, error: null, done: true });
      onDone();
    } catch (reason) {
      setState({ busy: false, error: (reason as Error).message, done: false });
    }
  };
  return (
    <article className="ledger-pair" aria-label={`Cluster ${cluster.id}`}>
      <header className="ledger-card-head">
        <strong>Suggested: same {cluster.kind.replace("_", " ")} in {cluster.questions.length} questions</strong>
        <span className="muted">{cluster.basis}</span>
      </header>
      <p>Shared terms: {cluster.shared_terms.map((t) => <code key={t} className="ledger-term">{t}</code>)}</p>
      <ul className="ledger-cluster-items">
        {cluster.items.map((id) => {
          const item = items.get(id);
          return (
            <li key={id}>
              {item ? (
                <Untrusted author={item.author_name ?? item.author}>
                  {item.text}{" "}
                  <span className="muted">— <Link to={`/question/${item.author}/${item.question}`}>{item.question_title ?? item.question}</Link></span>
                </Untrusted>
              ) : <span className="mono">{id}</span>}
            </li>
          );
        })}
      </ul>
      <p className="muted">
        {cluster.pairs.map((p) => `Jaccard ${p.jaccard}`).join(" · ")}
      </p>
      {cluster.confirmations.length > 0 && (
        <ul aria-label="Confirmations">
          {cluster.confirmations.map((c) => (
            <li key={c.seq}>Confirmed by <Link to={`/agent/${c.participant}`}>{c.participant}</Link>{c.note && <>: <Untrusted>{c.note}</Untrusted></>}</li>
          ))}
        </ul>
      )}
      <form className="action-form" onSubmit={confirm}>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why these are the same experiment (optional)" aria-label="Confirmation note" />
        <button disabled={state.busy}>Confirm same experiment</button>
        {state.error && <span className="error" role="alert">{state.error}</span>}
        {state.done && <span className="muted" role="status">Confirmation recorded (attribution only; items are not merged). The shared experiment it creates is on the Board, promotable like an item.</span>}
      </form>
    </article>
  );
}

function Clusters({ view, reload }: { view: FrontierView; reload: () => void }) {
  const items = new Map(view.items.map((i) => [i.id, i]));
  if (!view.clusters.length) return <p>No items in different questions share enough exact terms to suggest a cluster.</p>;
  return (
    <>
      <p className="muted">Suggestions by exact-term overlap across questions. A person confirms; the platform never merges items.</p>
      {view.clusters.map((c) => <ClusterCard key={c.id} cluster={c} items={items} onDone={reload} />)}
    </>
  );
}

function WishlistTab() {
  const wishlist = useApi<Wishlist>("/api/wishlist");
  return (
    <section aria-label="Dataset wishlist">
      <Status state={wishlist} />
      {wishlist.data && (
        <>
          <p className="muted">Exact missing-measurement statements, grouped by {wishlist.data.grouping}.</p>
          <p className="ledger-export" aria-label="Export the wishlist">
            Export as a lab-ready proposal (every requirement with the questions that need it):{" "}
            <a href={withBase("/api/wishlist/export?format=md&download=true")}>Markdown</a>
            <a href={withBase("/api/wishlist/export?format=html")} target="_blank" rel="noreferrer">HTML</a>
          </p>
          {wishlist.data.items.length === 0 && <p>No missing measurements recorded.</p>}
          <ol className="ledger-wishlist">
            {wishlist.data.items.map((entry) => (
              <li key={entry.normalized}>
                <Untrusted>{entry.text}</Untrusted>
                <p>
                  <strong>{entry.distinct_questions}</strong> question{entry.distinct_questions === 1 ? "" : "s"}:{" "}
                  {entry.questions.map((q, n) => (
                    <span key={q.question}>
                      {n > 0 && ", "}
                      <Link to={`/question/${q.author}/${q.question}`}>{q.title ?? q.question}</Link>
                      <span className="muted"> ({q.author_name ?? q.author})</span>
                    </span>
                  ))}
                </p>
                <p className="muted">from {Array.from(new Set(entry.sources.map((s) => s.kind))).join(", ")}</p>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}

// V5 board mode: items and shared experiments by state, with the requests, budgets and targets of promotions.
function BoardTab() {
  const [params] = useSearchParams();
  const board = useApi<FrontierBoardView>(`/api/frontier/board${query({ kind: params.get("kind"),
    question: params.get("question"), author: params.get("author") })}`);
  return (
    <section aria-label="Frontier board">
      <Status state={board} />
      {board.data && <FrontierBoard view={board.data} onDone={board.reload} />}
    </section>
  );
}

export default function Frontier() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "items";
  const path = `/api/frontier${query({ kind: params.get("kind"), status: params.get("status"), blocked_by: params.get("blocked_by"),
    question: params.get("question"), author: params.get("author") })}`;
  const view = useApi<FrontierView>(tab === "wishlist" || tab === "board" ? null : path);
  const select = (next: string) => {
    const copy = new URLSearchParams(params);
    if (next === "items") copy.delete("tab");
    else copy.set("tab", next);
    setParams(copy);
  };
  return (
    <section className="ledger">
      <h1>Frontier</h1>
      <div className="ledger-tabs" role="tablist">
        {[["items", "Open items"], ["board", "Board"], ["clusters", "Clusters"], ["wishlist", "Wishlist"]].map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} onClick={() => select(key)}>
            {label}{key === "clusters" && view.data ? ` (${view.data.clusters.length})` : ""}
          </button>
        ))}
      </div>
      {tab === "wishlist" ? <WishlistTab /> : tab === "board" ? <BoardTab /> : (
        <>
          {tab === "items" && <Filters />}
          <Status state={view} />
          {view.data && (tab === "clusters" ? <Clusters view={view.data} reload={view.reload} /> : <Items view={view.data} />)}
        </>
      )}
    </section>
  );
}
