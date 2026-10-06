import { Link } from "react-router-dom";
import type { LibraryHit, PostCard, ThreadCard as Thread } from "../../types/board";
import { Untrusted } from "../Untrusted";
import { Badge, HiddenNotice, KindBadge } from "./Badges";
import { ParticipantLink } from "./People";
import { short, when } from "./format";

function authorName(card: PostCard) {
  return "name" in card.author ? card.author.name : undefined;
}

// One board thread: root post, correction status, activity and evidence counts. Snippets are untrusted.
export function ThreadCard({ thread, fresh = false }: { thread: Thread; fresh?: boolean }) {
  return (
    <article className={`thread-card${fresh ? " fresh" : ""}`} aria-label={thread.title ?? "hidden post"}>
      <header>
        <Link to={`/post/${thread.id}`} className="thread-title">
          {thread.hidden ? <em>Hidden post</em> : thread.title}
        </Link>
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
      {thread.hidden ? (
        <HiddenNotice hidden={thread.hidden} />
      ) : (
        thread.snippet && (
          <Untrusted author={authorName(thread)}>
            <p className="snippet">{thread.snippet}</p>
          </Untrusted>
        )
      )}
      {thread.hits && thread.hits.length > 0 && (
        <ul className="hits" aria-label="Matching posts">
          {thread.hits.map((hit) => (
            <li key={hit.post}>
              <Link to={`/post/${hit.post}`}>{short(hit.post)}</Link>
              {hit.snippet && <span className="muted"> — {hit.snippet.slice(0, 160)}</span>}
            </li>
          ))}
        </ul>
      )}
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
