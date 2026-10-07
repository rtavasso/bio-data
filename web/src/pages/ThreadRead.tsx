import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Markdown } from "../components/Markdown";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import { Badge, HiddenNotice } from "../components/board/Badges";
import { STATUS_LABEL, pointerRoute, statusOf } from "../components/board/NumberPointers";
import { short, when } from "../components/board/format";
import type { NumberPointer } from "../types/board";
import type { Reading, ReadingClaim, ReadingNumber, ReadingPost } from "../types/workbench";
import { useApi } from "../useApi";
import "../components/workbench/workbench.css";
import "./board.css";

// Reading mode for a thread (spec v2 V4): posts, corrections and claims interleaved in recorded time, the evidence
// of the current post and number in a side pane. Keyboard: j / k move between the thread's numbers, Enter opens
// the record the current number points at (the cell, line or claim the number checker verified it against).

export function recordRoute(n: Pick<ReadingNumber, "pointers">): string | null {
  for (const p of n.pointers ?? []) {
    const route = pointerRoute(p);
    if (route) return route;
  }
  return null;
}

function PostEntry({ item, current }: { item: ReadingPost; current: ReadingNumber | null }) {
  if (item.hidden && item.body === undefined) {
    return <article className="wb-reading-item"><HiddenNotice reason={item.reason ?? null} /></article>;
  }
  const numbers = (item.numbers ?? []).map((n: NumberPointer) => ({ ...n, status: statusOf(n) }));
  return (
    <article className={`wb-reading-item ${item.post_kind === "correction" ? "correction" : ""}`} id={`r-${item.id}`}
      data-num-post={item.id} aria-current={current?.post === item.id ? "true" : undefined}>
      <p className="meta">
        <Badge tone={item.post_kind === "correction" ? "warn" : "plain"}>{item.post_kind}</Badge>{" "}
        {item.author?.name ?? item.author?.id} · {when(item.created)} · <Link to={`/post/${item.id}`}>{short(item.id)}</Link>
        {item.supersedes && <> · corrects <a href={`#r-${item.supersedes}`}>{short(item.supersedes)}</a></>}
        {item.in_reply_to && <> · replies to <a href={`#r-${item.in_reply_to}`}>{short(item.in_reply_to)}</a></>}
      </p>
      <h2>{item.title ?? (item.withheld ? "Write-up withheld" : "")}</h2>
      {item.anchor?.quote && <blockquote className="anchor-quote">{item.anchor.quote}</blockquote>}
      {item.withheld && <p className="muted">{item.withheld.placeholder ?? "Withheld by the number checker."}</p>}
      {item.body && (
        <Untrusted author={item.author?.name}>
          <Markdown source={item.body} numbers={numbers} />
        </Untrusted>
      )}
    </article>
  );
}

function ClaimEntry({ item }: { item: ReadingClaim }) {
  return (
    <article className="wb-reading-item claim" id={`r-${item.id}`}>
      <p className="meta">
        <Badge tone={item.status === "withdrawn" ? "bad" : "good"}>claim · {item.status}</Badge> {when(item.created)} · on{" "}
        <a href={`#r-${item.post}`}>{short(item.post)}</a>
        {item.withdrawn_by && <> · withdrawn by <a href={`#r-${item.withdrawn_by}`}>{short(item.withdrawn_by)}</a></>}
      </p>
      <Untrusted><p>{item.text}</p></Untrusted>
      {item.pointers.length > 0 && (
        <p className="meta">Pointers: {item.pointers.map((p, i) => (
          <span key={i}>{i > 0 && ", "}{p.kind === "artifact" ? <Link to={`/artifact/${p.id}${p.locator ? `?locator=${encodeURIComponent(p.locator)}` : ""}`}>{short(p.id)}</Link>
            : p.kind === "post" ? <Link to={`/post/${p.id}`}>{short(p.id)}</Link> : <span className="mono">{p.kind}:{p.id}</span>}</span>
        ))}</p>
      )}
    </article>
  );
}

function EvidencePane({ reading, index }: { reading: Reading; index: number }) {
  const current = reading.numbers[index] ?? null;
  const post = reading.items.find((i): i is ReadingPost => i.type === "post" && i.id === current?.post);
  return (
    <aside className="wb-reading-pane panel" aria-label="Evidence">
      <p className="wb-keys muted small"><kbd>j</kbd>/<kbd>k</kbd> next/previous number · <kbd>Enter</kbd> open its record</p>
      <h2>Number {reading.numbers.length ? index + 1 : 0} of {reading.numbers.length}</h2>
      {current ? (
        <div aria-live="polite">
          <p><span className="mono">{current.text}</span>{" "}
            <Badge tone={current.status === "verified" ? "good" : current.status === "unpointed" ? "bad" : "warn"}>
              {STATUS_LABEL[(current.status ?? "unpointed") as keyof typeof STATUS_LABEL]}</Badge></p>
          {current.pointers.length === 0 ? <p className="muted">No pointer at this number.</p> : (
            <ul>
              {current.pointers.map((p, i) => {
                const route = pointerRoute(p);
                const id = p.artifact ?? p.id ?? "";
                return (
                  <li key={i}>
                    {route ? <Link to={route}>{short(id)}</Link> : <span className="mono">{short(id)}</span>}
                    {p.locator && <span className="mono muted"> #{p.locator}</span>}
                    {p.result && <span className="muted"> · {p.result === "verified" ? `found at ${p.at ?? "record"}` : p.reason}</span>}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : <p className="muted">This thread has no numbers.</p>}
      {post?.evidence && (
        <section>
          <h3>Evidence of this post</h3>
          {post.evidence.artifacts.length === 0 ? <p className="muted">No artifacts named.</p> : (
            <ul>{post.evidence.artifacts.map((a) => <li key={a.id}><Link to={`/artifact/${a.id}`}>{a.title ?? short(a.id)}</Link></li>)}</ul>
          )}
          {post.evidence.notebook?.question && <p className="meta">Notebook {post.evidence.notebook.question}</p>}
          {post.evidence.run && <p className="meta"><Link to={`/run/${post.evidence.run}`}>delivery {short(post.evidence.run)}</Link></p>}
        </section>
      )}
    </aside>
  );
}

export default function ThreadRead() {
  const { id = "" } = useParams();
  const state = useApi<Reading>(`/api/threads/${id}/reading`);
  const [index, setIndex] = useState(0);
  const navigate = useNavigate();
  const root = useRef<HTMLDivElement | null>(null);
  const reading = state.data;
  const count = reading?.numbers.length ?? 0;

  const onKey = useCallback((event: KeyboardEvent) => {
    const target = event.target as HTMLElement | null;
    if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
    if (!reading || !count) return;
    if (event.key === "j") setIndex((i) => Math.min(count - 1, i + 1));
    else if (event.key === "k") setIndex((i) => Math.max(0, i - 1));
    else if (event.key === "Enter") {
      const route = recordRoute(reading.numbers[index]);
      if (route) navigate(route);
    }
  }, [reading, count, index, navigate]);

  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onKey]);

  // Highlight the current number in its post and keep it in view.
  useEffect(() => {
    const current = reading?.numbers[index];
    const container = root.current;
    if (!container) return;
    container.querySelectorAll(".wb-current").forEach((el) => el.classList.remove("wb-current"));
    if (!current) return;
    const el = container.querySelector(`[data-num-post="${current.post}"] [data-num-offset="${current.offset}"]`);
    if (el) {
      el.classList.add("wb-current");
      (el as HTMLElement).scrollIntoView?.({ block: "center" });
    }
  }, [reading, index]);

  if (!reading) return <Status state={state} />;
  const current = reading.numbers[index] ?? null;
  return (
    <section className="wb-reading-page">
      <header>
        <h1>Reading mode</h1>
        <p className="meta">
          {reading.counts.posts} posts · {reading.counts.corrections} corrections · {reading.counts.claims} claims ·{" "}
          {reading.counts.numbers} numbers · in recorded time · <Link to={`/post/${reading.focus}`}>back to the post</Link>
        </p>
      </header>
      <div className="wb-reading" ref={root}>
        <div>
          {reading.items.map((item) => item.type === "post"
            ? <PostEntry key={item.id} item={item} current={current} />
            : <ClaimEntry key={item.id} item={item} />)}
        </div>
        <EvidencePane reading={reading} index={index} />
      </div>
    </section>
  );
}
