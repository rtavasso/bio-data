import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../../api";
import { withBase } from "../../base";
import { useSavedView } from "../../savedView";
import type { Inbox, InboxItem } from "../../types/workbench";
import { explain } from "../participation/writes";
import { markInboxRead } from "./workbench";
import "./workbench.css";

// The personal inbox (spec v2 V4): answers to the person's asks, replies to their comments, corrections to posts
// they marked, watcher hits on items they promoted. Every item names the recorded relation that put it there.
// Loaded from GET /api/me/inbox and kept live by the per-caller SSE stream /api/me/inbox/stream (resuming after
// the last board sequence seen). Read state is the person's own write (POST /api/me/inbox/read).

export const KIND_LABEL: Record<string, string> = {
  answer: "Answer to your request", reply: "Reply", correction: "Correction to a post you marked",
  watcher_hit: "Watcher hit on an item you promoted",
};

export interface InboxState {
  items: InboxItem[];
  unread: number;
  error: string | null;
  loaded: boolean;
  reload: () => void;
  markRead: (keys: string[] | "all") => Promise<void>;
}

function merge(current: InboxItem[], incoming: InboxItem[]): InboxItem[] {
  const byId = new Map(current.map((i) => [i.id, i]));
  for (const item of incoming) byId.set(item.id, { ...byId.get(item.id), ...item });
  return Array.from(byId.values()).sort((a, b) => (b.seq ?? 0) - (a.seq ?? 0) || a.id.localeCompare(b.id));
}

export function useInbox(enabled = true): InboxState {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [version, setVersion] = useState(0);
  const latest = useRef(0);
  const view = useSavedView();

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    get<Inbox>("/api/me/inbox")
      .then((value) => {
        if (cancelled) return;
        const list = Array.isArray(value?.items) ? value.items : [];
        setItems(list);
        latest.current = typeof value?.latest === "number" ? value.latest : 0;
        setError(null);
        setLoaded(true);
      })
      .catch((reason: Error) => !cancelled && (setError(reason.message), setLoaded(true)));
    return () => {
      cancelled = true;
    };
  }, [enabled, version, view]);

  useEffect(() => {
    if (!enabled || !loaded || typeof EventSource === "undefined") return;
    const source = new EventSource(withBase(`/api/me/inbox/stream?after=${latest.current}`));
    source.onmessage = (event: MessageEvent<string>) => {
      try {
        const item = JSON.parse(event.data) as InboxItem & { kind: string };
        latest.current = Math.max(latest.current, item.seq ?? 0);
        setItems((current) => merge(current, [{ ...item, read: false, read_at: null }]));
      } catch {
        /* a malformed frame is ignored */
      }
    };
    return () => source.close();
  }, [enabled, loaded]);

  const markRead = useCallback(async (keys: string[] | "all") => {
    const result = await markInboxRead(keys === "all" ? { all: true } : { items: keys });
    const marked = new Set(result.marked);
    setItems((current) => current.map((i) => (marked.has(i.id) ? { ...i, read: true, read_at: result.read_at } : i)));
  }, []);

  return { items, unread: items.filter((i) => !i.read).length, error, loaded,
    reload: () => setVersion((v) => v + 1), markRead };
}

function Item({ item, onRead }: { item: InboxItem; onRead: () => void }) {
  return (
    <li className={item.read ? "wb-inbox-item read" : "wb-inbox-item unread"}>
      <div className="meta">
        <span className="wb-kind">{KIND_LABEL[item.kind] ?? item.kind}</span>
        {item.created && <> · <time dateTime={item.created}>{new Date(item.created).toLocaleString()}</time></>}
        {item.author && <> · by <span className="mono">{item.author}</span></>}
        {!item.read && <span className="wb-unread"> · unread</span>}
      </div>
      {item.hidden ? (
        <p className="muted">Hidden by moderation{item.reason ? `: ${item.reason}` : ""}.</p>
      ) : item.post ? (
        <Link to={`/post/${item.post}`}>{item.title ?? item.post}</Link>
      ) : <span className="muted">{item.item}</span>}
      <p className="muted small">
        {item.kind === "answer" && <>Answers your {item.task_type ?? "question"} <Link to={`/post/${item.asked}`}>request</Link>.</>}
        {item.kind === "reply" && <>In reply to your {item.to_comment ? "comment" : "post"} <Link to={`/post/${item.in_reply_to}`}>{item.in_reply_to?.slice(0, 13)}…</Link>{item.anchored ? ", at its anchor" : ""}.</>}
        {item.kind === "correction" && <>Supersedes <Link to={`/post/${item.corrects}`}>a post</Link> you marked.</>}
        {item.kind === "watcher_hit" && <>{item.new} new hit{item.new === 1 ? "" : "s"} for frontier item <span className="mono">{item.item}</span> (retrieval only; titles are provider text).</>}
        {" "}Recorded relation: <span className="mono">{String(item.relation?.table ?? item.relation?.kind ?? "")}</span>.
      </p>
      {!item.read && <button type="button" onClick={onRead}>Mark read</button>}
    </li>
  );
}

export function InboxList({ inbox }: { inbox: InboxState }) {
  const [error, setError] = useState<string | null>(null);
  const run = (keys: string[] | "all") => inbox.markRead(keys).catch((reason) => setError(explain(reason)));
  if (!inbox.loaded) return <p className="muted">Loading…</p>;
  if (inbox.error) return <p className="error">Could not load the inbox: {inbox.error}</p>;
  if (!inbox.items.length) return <p className="muted">Nothing yet. Answers, replies, corrections and watcher hits arrive here.</p>;
  return (
    <div className="wb-inbox">
      <p className="meta">
        {inbox.unread} unread of {inbox.items.length}{" "}
        {inbox.unread > 0 && <button type="button" onClick={() => run("all")}>Mark all read</button>}
        {error && <span className="error" role="alert"> {error}</span>}
      </p>
      <ul className="wb-inbox-list">
        {inbox.items.map((item) => <Item key={item.id} item={item} onRead={() => run([item.id])} />)}
      </ul>
    </div>
  );
}
