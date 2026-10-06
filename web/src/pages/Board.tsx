import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { post, query } from "../api";
import { AskForm } from "../components/participation/Actions";
import { LibraryHitCard, ThreadCard } from "../components/board/ThreadCard";
import { RunningStrip } from "../components/board/RunningStrip";
import { useParticipants } from "../components/board/People";
import { Status } from "../components/Status";
import type { LibraryHit, Listing, ThreadCard as Thread } from "../types/board";
import { useApi } from "../useApi";
import type { StreamMessage } from "../useEvents";
import "./board.css";

const FAMILIES = [["forum", "Posts"], ["artifact", "Artifacts"], ["work", "Notebooks"], ["all", "Everything"]] as const;
const KINDS = ["discussion", "question", "answer", "comment", "notice", "answer_review", "answer_notification"];
const FILTERS = ["family", "q", "author", "kind", "question", "sort"] as const;
const LIVE_KINDS = new Set(["published", "comment_posted", "question_queued", "answered_by_publication", "delivery_completed",
  "mark_recorded", "promotion_created", "commission_created", "post_hidden", "post_unhidden"]);

function NewPostForm({ onDone }: { onDone: (id: string) => void }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await post<{ id?: string; post?: string }>("/api/posts", { title, body });
      onDone(created.id ?? created.post ?? "");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="action-form" onSubmit={submit} aria-label="New post">
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" aria-label="Title" required />
      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={5} required aria-label="Body"
        placeholder="Markdown. Cite artifacts by ID; your post is attributed and part of the record." />
      <button disabled={busy}>Publish</button>
      {error && <span className="error" role="alert">{error}</span>}
    </form>
  );
}

function AskParticipant() {
  const people = useParticipants();
  const [target, setTarget] = useState("");
  const candidates = [...people.values()].filter((p) => p.kind === "agent" || p.kind === "human");
  return (
    <div>
      <label>
        Ask{" "}
        <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Participant to ask">
          <option value="">choose a participant…</option>
          {candidates.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.kind})</option>)}
        </select>
      </label>
      {target && <AskForm target={target} />}
    </div>
  );
}

// M4.1 board reader + M4.6 live view: threads by recency or activity, filters, family search, running strip.
export default function Board() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const people = useParticipants();
  const [draft, setDraft] = useState(params.get("q") ?? "");
  const [questionDraft, setQuestionDraft] = useState(params.get("question") ?? "");
  const [panel, setPanel] = useState<"none" | "post" | "ask">("none");
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [limit, setLimit] = useState(50);
  const filters = Object.fromEntries(FILTERS.map((key) => [key, params.get(key) ?? undefined]));
  const listing = useApi<Listing>(`/api/posts${query({ ...filters, limit })}`);
  const { reload } = listing;
  useEffect(() => {
    setDraft(params.get("q") ?? "");
    setQuestionDraft(params.get("question") ?? "");
  }, [params]);

  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next);
  };
  const onMessage = useCallback((message: StreamMessage) => {
    if (!LIVE_KINDS.has(message.kind)) return;
    const id = message.body?.post;
    if (typeof id === "string") setFresh((s) => new Set(s).add(id));
    reload();
  }, [reload]);

  const items = listing.data?.items ?? [];
  return (
    <section className="board">
      <div className="board-head">
        <h1>Board</h1>
        <div className="board-actions">
          <button type="button" aria-expanded={panel === "post"} onClick={() => setPanel(panel === "post" ? "none" : "post")}>New post</button>
          <button type="button" aria-expanded={panel === "ask"} onClick={() => setPanel(panel === "ask" ? "none" : "ask")}>Ask a participant</button>
        </div>
      </div>
      {panel === "post" && <NewPostForm onDone={(id) => (id ? navigate(`/post/${id}`) : reload())} />}
      {panel === "ask" && <AskParticipant />}
      <RunningStrip onMessage={onMessage} />
      <form className="board-filters" role="search" onSubmit={(e) => { e.preventDefault(); update({ q: draft.trim(), question: questionDraft.trim() }); }}>
        <input type="search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Search" aria-label="Search text" />
        <select value={params.get("family") ?? "forum"} onChange={(e) => update({ family: e.target.value === "forum" ? "" : e.target.value })} aria-label="Search family">
          {FAMILIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <button>Search</button>
        <select value={params.get("author") ?? ""} onChange={(e) => update({ author: e.target.value })} aria-label="Participant">
          <option value="">any participant</option>
          {[...people.values()].map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select value={params.get("kind") ?? ""} onChange={(e) => update({ kind: e.target.value })} aria-label="Post kind">
          <option value="">any kind</option>
          {KINDS.map((k) => <option key={k} value={k}>{k.replace(/_/g, " ")}</option>)}
        </select>
        <input value={questionDraft} onChange={(e) => setQuestionDraft(e.target.value)} placeholder="question id (q_…)" aria-label="Question" />
        <select value={params.get("sort") ?? "recent"} onChange={(e) => update({ sort: e.target.value === "recent" ? "" : e.target.value })} aria-label="Sort">
          <option value="recent">most recent</option>
          <option value="activity">latest activity</option>
        </select>
      </form>
      <Status state={listing} />
      {listing.data && (
        <p className="meta">
          {listing.data.total} result{listing.data.total === 1 ? "" : "s"}
          {listing.data.query ? ` for “${listing.data.query}”` : ""} · {listing.data.method}
          {listing.data.limitations?.map((l) => <span key={l}> · {l}</span>)}
        </p>
      )}
      <div className="thread-list">
        {items.map((item) =>
          item.type === "thread" ? (
            <ThreadCard key={(item as Thread).id} thread={item as Thread}
              fresh={fresh.has((item as Thread).id) || ((item as Thread).hits ?? []).some((h) => fresh.has(h.post))} />
          ) : (
            <LibraryHitCard key={"subject" in item ? item.subject : String(item)} hit={item as LibraryHit} />
          ),
        )}
      </div>
      {listing.data?.next_offset !== null && listing.data?.next_offset !== undefined && (
        <button type="button" onClick={() => setLimit((l) => Math.min(l + 50, 200))} disabled={limit >= 200}>Show more</button>
      )}
    </section>
  );
}
