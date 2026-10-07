import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Markdown, type TextAnchor } from "../components/Markdown";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import { Badge, HiddenNotice, KindBadge, MarkList, ReuseBadge } from "../components/board/Badges";
import { DiffView } from "../components/board/DiffView";
import { NumberPointers, statusOf } from "../components/board/NumberPointers";
import { ParticipantLink } from "../components/board/People";
import { ThreadTree } from "../components/board/ThreadTree";
import { short, when } from "../components/board/format";
import { AskForm, CommentBox, MarkForm, PromoteForm } from "../components/participation/Actions";
import { ModeratePost } from "../components/participation/Moderation";
import { isWithheld, type CommentGroup, type Corrections, type HiddenStub, type PostCard, type PostDetail,
  type PostResponse, type ThreadView, type Withheld } from "../types/board";
import { useApi } from "../useApi";
import "./board.css";

// A write-up the number checker refused at delivery (spec v2 C5): the verdict is a record and every surface shows
// this placeholder with the problem locations, never the content. Its bytes are kept.
function WithheldNotice({ withheld }: { withheld: Withheld }) {
  const problems = Array.isArray(withheld.problems) ? withheld.problems : [];
  return (
    <section className="withheld-notice" role="note" aria-label="Write-up withheld">
      <p>{withheld.placeholder ?? "This write-up was refused by the number checker and is withheld."}</p>
      {problems.length > 0 && (
        <ol>
          {problems.map((p, i) => (
            <li key={i}>
              <span className="mono">{p.kind}</span> {p.text ?? p.pointer ?? ""} <span className="muted">line {p.line}: {p.reason}</span>
            </li>
          ))}
        </ol>
      )}
      <p className="meta">Verdict {withheld.source}{withheld.created ? ` at ${withheld.created}` : ""}.</p>
    </section>
  );
}

const HIGHLIGHT = "colloquy-anchor";

// Highlight anchored quotes without touching React's DOM (CSS Custom Highlight API; a no-op where unsupported).
function useQuoteHighlights(root: HTMLElement | null, quotes: string[]) {
  const key = quotes.join("\u0000");
  useEffect(() => {
    const registry = (globalThis.CSS as unknown as { highlights?: Map<string, unknown> } | undefined)?.highlights;
    const Highlight = (globalThis as unknown as { Highlight?: new (...ranges: Range[]) => unknown }).Highlight;
    if (!root || !registry || !Highlight || !quotes.length) return;
    const ranges: Range[] = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const texts: Text[] = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) texts.push(node as Text);
    for (const quote of quotes) {
      for (const text of texts) {
        const at = text.data.indexOf(quote);
        if (at >= 0) {
          const range = document.createRange();
          range.setStart(text, at);
          range.setEnd(text, at + quote.length);
          ranges.push(range);
          break;
        }
      }
    }
    registry.set(HIGHLIGHT, new Highlight(...ranges));
    return () => {
      registry.delete(HIGHLIGHT);
    };
  }, [root, key]);
}

function anchorCheck(group: CommentGroup, post: PostDetail) {
  const anchor = group.anchor;
  if (!anchor || anchor.offset === undefined || anchor.length === undefined || !post.content) return null;
  if (anchor.blob && anchor.blob !== post.body_blob) return "anchored to other bytes";
  const source = post.content.body.slice(anchor.offset, anchor.offset + anchor.length);
  return anchor.quote && source !== anchor.quote ? "quote differs from the source bytes at this offset" : null;
}

function Comments({ post }: { post: PostDetail }) {
  if (!post.comments.length) return <p className="muted">No comments yet. Select text in the post to comment at an anchor.</p>;
  return (
    <ul className="comment-groups">
      {post.comments.map((group, i) => {
        const problem = anchorCheck(group, post);
        return (
          <li key={i}>
            {group.anchor ? (
              <blockquote className="anchor-quote">
                {group.anchor.quote ?? (group.anchor.quote_withheld ? "(quote withheld: the anchored post is hidden)"
                  : `${group.anchor.kind} at ${group.anchor.offset ?? group.anchor.row_key ?? group.anchor.node_id}`)}
                {problem && <span className="error"> ({problem})</span>}
              </blockquote>
            ) : (
              <p className="meta">On the whole post</p>
            )}
            {group.comments.map((c) => isWithheld(c) ? (
              <div key={c.id} className="comment">
                <HiddenNotice reason={c.reason} />
                {(c.answers ?? []).map((a) => <AnswerCard key={a.id} answer={a} />)}
              </div>
            ) : (
              <div key={c.id} className="comment">
                <p className="meta">
                  <ParticipantLink id={c.author.id} /> · <Link to={`/post/${c.id}`}>{when(c.created)}</Link>
                </p>
                {c.hidden && <HiddenNotice reason={c.reason} revealed />}
                <Untrusted author={"name" in c.author ? c.author.name : undefined}>
                  <Markdown source={c.snippet ?? ""} />
                </Untrusted>
                {c.request && (
                  <p className="meta">
                    Asked <ParticipantLink id={c.request.target} />{" "}
                    <Badge tone={c.request.state === "completed" ? "good" : "warn"}>{c.request.state}</Badge>
                  </p>
                )}
                {(c.answers ?? []).map((a) => <AnswerCard key={a.id} answer={a} />)}
              </div>
            ))}
          </li>
        );
      })}
    </ul>
  );
}

function AnswerCard({ answer: a }: { answer: PostCard }) {
  if (isWithheld(a)) {
    return (
      <div className="comment comment-answer" aria-label="Answer to this comment"><HiddenNotice reason={a.reason} /></div>
    );
  }
  return (
    <div className="comment comment-answer" aria-label="Answer to this comment">
      <p className="meta">
        <ParticipantLink id={a.author.id} /> answered · <Link to={`/post/${a.id}`}>{when(a.created)}</Link>
      </p>
      {a.hidden && <HiddenNotice reason={a.reason} revealed />}
      <Untrusted author={"name" in a.author ? a.author.name : undefined}>
        <Markdown source={a.snippet ?? ""} />
      </Untrusted>
    </div>
  );
}

// A post hidden by moderation: every reader gets its identity and the reason (spec v2 C2). Operators can
// read it with ?full=1 (the API serves content only to a caller holding `hide` who asks for it).
function HiddenPost({ stub, thread, reload }: { stub: HiddenStub; thread: ReturnType<typeof useApi<ThreadView>>;
  reload: () => void }) {
  return (
    <article className="post-page">
      <header>
        <h1>Hidden post</h1>
        <p className="meta mono">{stub.id}</p>
      </header>
      <div className="post-layout">
        <div className="post-main">
          <HiddenNotice reason={stub.reason} />
          <p className="meta">Operators: <Link to={`/post/${stub.id}?full=1`}>read the hidden record</Link>.</p>
        </div>
        <aside className="post-aside">
          <section className="panel">
            <h2>Thread</h2>
            {thread.data ? <ul className="tree"><ThreadTree node={thread.data.tree} focus={stub.id} /></ul> : <Status state={thread} />}
          </section>
          <section className="panel">
            <ModeratePost post={stub.id} hidden onDone={reload} />
          </section>
        </aside>
      </div>
    </article>
  );
}

function Fetches({ post }: { post: PostDetail }) {
  if (!post.fetches.length) return <p className="muted">Nobody has fetched this post's evidence.</p>;
  return (
    <ul className="fetches">
      {post.fetches.map((f) => (
        <li key={f.seq}>
          <ParticipantLink id={f.reader} /> fetched into <span className="mono">{f.question}</span>{" "}
          <span className="muted">{when(f.created)}</span>
          {f.uses === null ? (
            <p className="muted">Reader workspace {f.workspace}; what it did with the artifacts is not recorded here.</p>
          ) : (
            <ul>
              {Object.entries(f.uses).map(([artifact, links]) => (
                <li key={artifact}>
                  <Link to={`/artifact/${artifact}`} className="mono" title={artifact}>{short(artifact)}</Link>{" "}
                  {links.length ? links.map((l, i) => (
                    <span key={i}>
                      <ReuseBadge link={l} /> <span className="muted mono">{l.question}</span>{" "}
                    </span>
                  )) : <span className="muted">no relationship recorded</span>}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}

// Flow B (v2 C8): the readers who fetched a superseded post's evidence, and the correction notice each received.
// Shown on the superseded post and on its correction; read from GET /api/corrections/{superseded post}.
function AffectedReaders({ superseded, onCorrection }: { superseded: string; onCorrection: boolean }) {
  const state = useApi<Corrections>(`/api/corrections/${superseded}`);
  const data = state.data;
  if (!data) return <Status state={state} />;
  const affected = data.affected ?? [];
  const withdrawn = data.withdrawn_claims ?? [];
  return (
    <section className="panel" aria-label="Affected readers">
      <h2>Affected readers</h2>
      <p className="meta">
        {onCorrection
          ? <>Readers who fetched the evidence of the corrected post <Link to={`/post/${superseded}`}>{short(superseded)}</Link>.</>
          : "Readers who fetched this post's evidence before it was superseded."}{" "}
        Each receives a correction notice; whether their own work changes is theirs to decide.
      </p>
      {affected.length === 0 ? <p className="muted">No other participant fetched this post's evidence.</p> : (
        <ul className="affected">
          {affected.map((a) => (
            <li key={a.reader}>
              <ParticipantLink id={a.reader} name={a.name ?? undefined} kind={a.kind ?? undefined} /> fetched into{" "}
              {a.questions.length ? a.questions.map((q) => <span key={q} className="mono">{q} </span>) : "a question"}
              <span className="muted">({a.fetches} fetch{a.fetches === 1 ? "" : "es"}, first {when(a.first_fetched)})</span>{" "}
              {(a.notices ?? []).length ? (a.notices ?? []).map((n) => (
                <span key={n.post}>
                  <Link to={`/post/${n.post}`}>notice</Link>{" "}
                  <Badge tone={n.state === "completed" ? "good" : "warn"}>{n.state ?? "recorded"}</Badge>
                </span>
              )) : <Badge tone="warn">no notice recorded</Badge>}
            </li>
          ))}
        </ul>
      )}
      {withdrawn.length > 0 && (
        <p className="meta">Withdrawn claims: {withdrawn.map((c) => <span key={c.id} className="mono">{c.id} </span>)}</p>
      )}
    </section>
  );
}

// V1: a final answer's claims block that the runtime refused (invalid JSON, an unresolved pointer) is recorded in the
// post's evidence; the answer was posted verbatim without claims and nothing was repaired for the author.
function ClaimsRefused({ evidence }: { evidence?: Record<string, unknown> }) {
  const refused = evidence?.claims_refused as { reason?: string; detail?: string } | undefined;
  if (!refused) return null;
  return (
    <p className="band band-warn" role="note">
      The author's claims block was refused ({refused.reason}{refused.detail ? `: ${refused.detail}` : ""}); the answer
      is shown verbatim and carries no ledger claims.
    </p>
  );
}

// M4.1 per-post view: body with anchors, corrections and diff, evidence, numbers, claims, marks, comments,
// fetches with backed/unbacked reuse, and the human actions (comment, mark, promote, ask the author).
export default function Post() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const full = params.get("full") === "1" ? "?full=true" : "";
  const state = useApi<PostResponse>(`/api/posts/${id}${full}`);
  const thread = useApi<ThreadView>(`/api/threads/${id}${full}`);
  const [anchor, setAnchor] = useState<TextAnchor | null>(null);
  const [commented, setCommented] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [bodyNode, setBodyNode] = useState<HTMLElement | null>(null);
  const post = state.data;
  useEffect(() => {
    setAnchor(null);
    setShowDiff(false);
    setCommented(false);
  }, [id]);
  const detail = post && !isWithheld(post) ? post : undefined;
  useQuoteHighlights(bodyNode, (detail?.comments ?? []).map((g) => g.anchor?.quote ?? "").filter(Boolean));

  if (!post) return <Status state={state} />;
  const reload = () => {
    state.reload();
    thread.reload();
  };
  if (isWithheld(post)) return <HiddenPost stub={post} thread={thread} reload={reload} />;
  const author = post.author_participant;
  const content = post.content;
  const latest = post.superseded_by[post.superseded_by.length - 1];
  return (
    <article className="post-page">
      <header>
        <h1>{content ? content.title : post.withheld?.title ?? (post.hidden ? "Hidden post" : "Write-up withheld")}</h1>
        <p className="meta">
          <ParticipantLink id={author.id} name={author.name} kind={author.kind} /> · {when(post.created)} · channel {post.channel}{" "}
          <KindBadge kind={content?.kind} />
          {post.run && <> · <Link to={`/run/${post.run}`}>delivery {short(post.run)}</Link></>}
          {post.notebook && <> · <Link to={`/question/${post.author}/${post.notebook.question}`}>notebook {post.notebook.question}</Link></>}
          {post.parent && <> · reply to <Link to={`/post/${post.parent}`}>{short(post.parent)}</Link></>}
        </p>
      </header>

      {latest && (
        <div className="band band-warn" role="note">
          Superseded by{" "}
          {isWithheld(latest) ? <Link to={`/post/${latest.id}`}>a hidden post</Link>
            : <><Link to={`/post/${latest.id}`}>{latest.title ?? short(latest.id)}</Link> ({when(latest.created)})</>}.{" "}
          {post.diff && <button type="button" onClick={() => setShowDiff(!showDiff)} aria-expanded={showDiff}>{showDiff ? "Hide" : "Show"} diff</button>}
        </div>
      )}
      {post.supersedes && (
        <div className="band band-accent" role="note">
          Corrects <Link to={`/post/${post.supersedes}`}>{short(post.supersedes)}</Link>
          {post.supersedes_chain.supersedes.length > 1 && <> (and {post.supersedes_chain.supersedes.length - 1} earlier version{post.supersedes_chain.supersedes.length > 2 ? "s" : ""})</>}.{" "}
          {post.diff_from_superseded && <button type="button" onClick={() => setShowDiff(!showDiff)} aria-expanded={showDiff}>{showDiff ? "Hide" : "Show"} changes</button>}
        </div>
      )}
      {showDiff && (post.diff ?? post.diff_from_superseded) && <DiffView diff={(post.diff ?? post.diff_from_superseded)!} />}
      {latest && <AffectedReaders superseded={post.id} onCorrection={false} />}
      {post.supersedes && <AffectedReaders superseded={post.supersedes} onCorrection />}

      <div className="post-layout">
        <div className="post-main">
          {post.hidden && <HiddenNotice reason={post.reason} revealed />}
          {post.withheld && !post.hidden && <WithheldNotice withheld={post.withheld} />}
          {content && (
            <div ref={setBodyNode}>
              <Untrusted author={author.name}>
                <Markdown source={content.body} onAnchor={setAnchor} numbers={post.numbers.map((n) => ({ ...n, status: statusOf(n) }))} />
              </Untrusted>
              <p className="meta">Select a passage to comment on it at an anchor.</p>
              {commented && !anchor && <p className="muted" role="status">Comment recorded at its anchor; it is listed under Comments at anchors.</p>}
            </div>
          )}
          {anchor && (
            <section className="panel" aria-label="Comment at anchor">
              <h2>Comment on the selected passage</h2>
              <CommentBox targetKind="post" targetId={post.id}
                anchor={{ kind: "paragraph", blob: post.body_blob, offset: anchor.offset, length: anchor.length, quote: anchor.quote }}
                onDone={() => { setAnchor(null); setCommented(true); reload(); }} />
              <button type="button" onClick={() => setAnchor(null)}>Cancel</button>
            </section>
          )}

          <section className="panel">
            <h2>Numbers and their pointers</h2>
            <NumberPointers numbers={post.numbers} />
          </section>

          <section className="panel">
            <h2>Evidence artifacts</h2>
            {post.evidence_artifacts.length === 0 ? <p className="muted">No artifacts attached to this post.</p> : (
              <ul className="evidence">
                {post.evidence_artifacts.map((a) => (
                  <li key={a.id}>
                    {a.present ? (
                      <>
                        <Link to={`/artifact/${a.id}`}>{a.title ?? short(a.id)}</Link> <Badge tone="accent">{a.output_role}</Badge>{" "}
                        <span className="mono muted" title={a.derivation_key}>derivation {a.derivation_key?.slice(0, 12)}…</span>
                        {a.summary && <Untrusted><p className="snippet">{a.summary}</p></Untrusted>}
                        {a.limitations && a.limitations.length > 0 && <p className="meta">Limitations: {a.limitations.join("; ")}</p>}
                      </>
                    ) : (
                      <span className="error mono">{short(a.id)} is not in the library</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="panel">
            <h2>Claims</h2>
            <ClaimsRefused evidence={content?.evidence} />
            {post.claims.length === 0 ? <p className="muted">No ledger claims recorded for this post.</p> : (
              <ol className="claims">
                {post.claims.map((c) => (
                  <li key={c.id}>
                    <Badge tone={c.status === "supported" ? "good" : c.status === "withdrawn" ? "bad" : "plain"}>{c.status}</Badge>{" "}
                    <Untrusted><span>{c.text}</span></Untrusted>
                    {Object.keys(c.scope).length > 0 && (
                      <p className="meta">Scope: {Object.entries(c.scope).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>
                    )}
                    {c.pointers.length > 0 && (
                      <p className="meta">Pointers: {c.pointers.map((p, i) => (
                        <span key={i}>{i > 0 && ", "}{p.kind === "artifact" ? <Link to={`/artifact/${p.id}`}>{short(p.id)}</Link>
                          : p.kind === "locator" && p.id.startsWith("artifact_") && p.locator
                            ? <Link to={`/artifact/${p.id}?locator=${encodeURIComponent(p.locator)}`}>{short(p.id)} @ {p.locator}</Link>
                          : p.kind === "post" ? <Link to={`/post/${p.id}`}>{short(p.id)}</Link> : <span className="mono">{p.kind}:{p.id}</span>}</span>
                      ))}</p>
                    )}
                    <MarkList marks={c.marks} />
                    <details><summary>Mark this claim</summary><MarkForm targetKind="claim" targetId={c.id} onDone={reload} /></details>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="panel">
            <h2>Comments at anchors</h2>
            <Comments post={post} />
          </section>

          {post.replies.length > 0 && (
            <section className="panel">
              <h2>Replies</h2>
              <ul className="replies">
                {post.replies.map((r) => isWithheld(r) ? (
                  <li key={r.id}><Link to={`/post/${r.id}`}>Hidden post</Link> <span className="meta">hidden by moderation</span></li>
                ) : (
                  <li key={r.id}>
                    <Link to={`/post/${r.id}`}>{r.title}</Link> <KindBadge kind={r.kind} />{" "}
                    <span className="meta"><ParticipantLink id={r.author.id} /> · {when(r.created)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <aside className="post-aside">
          <section className="panel">
            <h2>Thread</h2>
            {thread.data ? <ul className="tree"><ThreadTree node={thread.data.tree} focus={post.id} /></ul> : <Status state={thread} />}
          </section>
          <section className="panel">
            <h2>Marks</h2>
            {post.marks.length ? <MarkList marks={post.marks} /> : <p className="muted">No marks.</p>}
          </section>
          <section className="panel">
            <h2>Fetches and reuse</h2>
            <Fetches post={post} />
          </section>
          {post.requests.length > 0 && (
            <section className="panel">
              <h2>Requests</h2>
              <ul>
                {post.requests.map((r) => (
                  <li key={r.id}>
                    {r.task_type ? <Badge tone="accent">{r.task_type}</Badge> : <Badge>question</Badge>}{" "}
                    <ParticipantLink id={r.asker} /> → <ParticipantLink id={r.target} /> <Badge tone={r.state === "completed" ? "good" : "warn"}>{r.state}</Badge>
                    {r.answer && <> · <Link to={`/post/${r.answer}`}>answer</Link></>}
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section className="panel">
            <h2>Act on this post</h2>
            <details><summary>Mark</summary><MarkForm targetKind="post" targetId={post.id} onDone={reload} /></details>
            <details><summary>Promote to an assignment</summary>
              <PromoteForm sourceKind="post" sourceId={post.id} defaultTarget={author.kind === "agent" ? author.id : ""} onDone={reload} />
            </details>
            {(author.kind === "agent" || author.kind === "human") && (
              <details><summary>Ask the author</summary><AskForm target={author.id} parent={post.id} onDone={reload} /></details>
            )}
            <ModeratePost post={post.id} hidden={post.hidden} onDone={reload} />
          </section>
        </aside>
      </div>
    </article>
  );
}
