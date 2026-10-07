import { Link } from "react-router-dom";
import { isWithheld, type LibraryHit, type ThreadCard as Thread, type VisiblePostCard } from "../../types/board";
import { Untrusted } from "../Untrusted";
import { Badge, HiddenNotice, KindBadge } from "./Badges";
import { ParticipantLink } from "./People";
import { short, when } from "./format";

function authorName(card: VisiblePostCard) {
  return "name" in card.author ? card.author.name : undefined;
}

function Hits({ thread }: { thread: Thread }) {
  if (!thread.hits || thread.hits.length === 0) return null;
  return (
    <ul className="hits" aria-label="Matching posts">
      {thread.hits.map((hit) => (
        <li key={hit.post}>
          <Link to={`/post/${hit.post}`}>{short(hit.post)}</Link>
          {hit.snippet && <span className="muted"> — {hit.snippet.slice(0, 160)}</span>}
        </li>
      ))}
    </ul>
  );
}

// One board thread: root post, correction status, activity and evidence counts. Snippets are untrusted.
// A thread whose root is hidden shows only the placeholder, the reason and the reply count.
export function ThreadCard({ thread, fresh = false }: { thread: Thread; fresh?: boolean }) {
  if (isWithheld(thread)) {
    return (
      <article className={`thread-card hidden-card${fresh ? " fresh" : ""}`} aria-label="hidden post">
        <header>
          <Link to={`/post/${thread.id}`} className="thread-title"><em>Hidden post</em></Link>
        </header>
        <p className="meta">{thread.replies} repl{thread.replies === 1 ? "y" : "ies"}</p>
        <HiddenNotice reason={thread.reason} />
        <Hits thread={thread} />
      </article>
    );
  }
  return (
    <article className={`thread-card${fresh ? " fresh" : ""}`} aria-label={thread.title ?? "post"}>
      <header>
        <Link to={`/post/${thread.id}`} className="thread-title">{thread.title}</Link>
        {thread.hidden && <Badge tone="bad">hidden</Badge>}
        <KindBadge kind={thread.kind} />
        {thread.correction_status === "superseded" && <Badge tone="warn">corrected</Badge>}
        {thread.correction_status === "superseding" && <Badge tone="accent">correction</Badge>}
        {thread.open_requests > 0 && <Badge tone="warn">{thread.open_requests} open request{thread.open_requests > 1 ? "s" : ""}</Badge>}
        {fresh && <Badge tone="accent">new</Badge>}
      </header>
      <p className="meta">
        <ParticipantLink id={thread.author.id} name={authorName(thread)} /> · {when(thread.created)} ·{" "}
        {thread.replies} repl{thread.replies === 1 ? "y" : "ies"} · last activity {when(thread.last_activity)}
        {thread.evidence.artifacts > 0 && <> · {thread.evidence.artifacts} artifact{thread.evidence.artifacts > 1 ? "s" : ""}</>}
        {thread.evidence.notebook && <> · notebook</>}
        {thread.corrections > 0 && <> · {thread.corrections} correction{thread.corrections > 1 ? "s" : ""}</>}
      </p>
      {thread.hidden && <HiddenNotice reason={thread.reason} revealed />}
      {thread.withheld ? (
        <p className="withheld-notice" role="note">{thread.snippet}</p>
      ) : thread.snippet && (
        <Untrusted author={authorName(thread)}>
          <p className="snippet">{thread.snippet}</p>
        </Untrusted>
      )}
      <Hits thread={thread} />
    </article>
  );
}

// Library search hits (artifact or notebook families) link to the posts that published them.
export function LibraryHitCard({ hit }: { hit: LibraryHit }) {
  const isArtifact = hit.type === "artifact";
  return (
    <article className="thread-card">
      <header>
        {isArtifact ? <Link to={`/artifact/${hit.subject}`} className="thread-title">{hit.title}</Link> : <span className="thread-title">{hit.title}</span>}
        <Badge>{hit.type}</Badge>
        {hit.output_role && <Badge tone="accent">{hit.output_role}</Badge>}
      </header>
      <p className="meta mono" title={hit.subject}>{short(hit.subject, 16)}</p>
      {hit.snippet && (
        <Untrusted>
          <p className="snippet">{hit.snippet}</p>
        </Untrusted>
      )}
      {hit.posts && hit.posts.length > 0 ? (
        <p className="meta">
          Published in {hit.posts.map((p, i) => <span key={p}>{i > 0 && ", "}<Link to={`/post/${p}`}>{short(p)}</Link></span>)}
        </p>
      ) : (
        isArtifact && <p className="meta muted">Not named by any post (read-only; fetch is post-gated).</p>
      )}
    </article>
  );
}
