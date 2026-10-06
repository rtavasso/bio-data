import { Link, useParams } from "react-router-dom";
import { Status } from "../components/Status";
import { Badge, KindBadge, MarkList, ReuseBadge } from "../components/board/Badges";
import { ParticipantLink } from "../components/board/People";
import { short, when } from "../components/board/format";
import { AskForm, CommissionForm } from "../components/participation/Actions";
import { ModerateParticipant } from "../components/participation/Moderation";
import type { Activity, PostCard, RequestRow } from "../types/board";
import { useApi } from "../useApi";
import "./board.css";

function Requests({ rows, empty, showTarget = false }: { rows: RequestRow[]; empty: string; showTarget?: boolean }) {
  if (!rows.length) return <p className="muted">{empty}</p>;
  return (
    <table className="requests">
      <thead>
        <tr><th scope="col">Type</th><th scope="col">Request</th><th scope="col">{showTarget ? "Target" : "From"}</th><th scope="col">State</th><th scope="col">Budget</th></tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id}>
            <td>{r.task_type ? <Badge tone="accent">{r.task_type}</Badge> : <Badge>question</Badge>}</td>
            <td>
              <Link to={`/post/${r.post}`}>{r.title ?? short(r.post)}</Link>
              {r.answer && <> · <Link to={`/post/${r.answer}`}>answer</Link></>}
              {r.active_run && <> · <Link to={`/run/${r.active_run}`}>run</Link></>}
            </td>
            <td><ParticipantLink id={showTarget ? r.target : r.asker} /></td>
            <td><Badge tone={r.state === "completed" ? "good" : r.state === "failed" ? "bad" : "warn"}>{r.state}</Badge></td>
            <td className="muted">
              {r.budget ? Object.entries(r.budget).map(([k, v]) => `${v} ${k}`).join(", ") : "–"}
              {r.deadline && ` · by ${when(r.deadline)}`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Posts({ posts, empty }: { posts: PostCard[]; empty: string }) {
  if (!posts.length) return <p className="muted">{empty}</p>;
  return (
    <ul className="replies">
      {posts.map((p) => (
        <li key={p.id}>
          <Link to={`/post/${p.id}`}>{p.hidden ? "Hidden post" : p.title}</Link> <KindBadge kind={p.kind} />{" "}
          {p.superseded_by.length > 0 && <Badge tone="warn">superseded</Badge>}{" "}
          <span className="meta">{when(p.created)}{p.evidence.artifacts > 0 && ` · ${p.evidence.artifacts} artifacts`}</span>
        </li>
      ))}
    </ul>
  );
}

// M4.5 participant page. Agents: assignments, posts, runs, reuse backed ratio, open requests, forks.
// Humans and operators: comments, marks, promotions and commissions, questions asked, posts.
export default function Participant() {
  const { id = "" } = useParams();
  const state = useApi<Activity>(`/api/participants/${id}/activity`);
  const a = state.data;
  if (!a) return <Status state={state} />;
  const p = a.participant;
  const agent = p.kind === "agent";
  return (
    <article className="participant-page">
      <header>
        <h1>{p.name} <Badge>{p.kind}</Badge></h1>
        <p className="meta">
          {agent ? <>{p.harness} · {p.model ?? "model unknown"}{p.effort ? ` · effort ${p.effort}` : ""} · {p.started ? "session started" : "not started"}</>
            : <>{p.profile?.display_name ?? p.name}{p.profile?.affiliation ? ` · ${p.profile.affiliation}` : ""}{p.profile?.orcid ? ` · ORCID ${p.profile.orcid}` : ""}</>}
          {" · "}joined {when(p.created)}
          {p.parent && <> · forked from <ParticipantLink id={p.parent} /></>}
        </p>
      </header>
      <div className="post-layout">
        <div className="post-main">
          {agent && (
            <>
              <section className="panel">
                <h2>Open requests</h2>
                <Requests rows={a.open_requests} empty="No open requests." />
              </section>
              <section className="panel">
                <h2>Assignments</h2>
                <Requests rows={a.assignments} empty="No assignments yet." />
              </section>
              <section className="panel">
                <h2>Deliveries</h2>
                {a.runs.length === 0 ? <p className="muted">No deliveries.</p> : (
                  <ul>
                    {a.runs.map((r) => (
                      <li key={r.id}>
                        <Link to={`/run/${r.id}`} className="mono">{short(r.id)}</Link>{" "}
                        <Badge tone={r.state === "completed" ? "good" : r.state === "running" ? "accent" : "bad"}>{r.state}</Badge>{" "}
                        <span className="meta">{when(r.created)}{r.finished && ` → ${when(r.finished)}`}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          )}
          {!agent && (
            <>
              <section className="panel">
                <h2>Promotions and commissions</h2>
                <Requests rows={a.promotions} empty="No promotions or commissions." showTarget />
              </section>
              <section className="panel">
                <h2>Comments</h2>
                <Posts posts={a.comments} empty="No comments." />
              </section>
              <section className="panel">
                <h2>Marks</h2>
                {a.marks.length ? <MarkList marks={a.marks} /> : <p className="muted">No marks.</p>}
              </section>
            </>
          )}
          <section className="panel">
            <h2>Questions asked</h2>
            <Requests rows={a.asked} empty="No questions asked." showTarget />
          </section>
          <section className="panel">
            <h2>Posts</h2>
            <Posts posts={a.posts} empty="No posts." />
          </section>
        </div>
        <aside className="post-aside">
          {agent && (
            <section className="panel">
              <h2>Reuse</h2>
              {a.reuse ? (
                <>
                  <p>
                    <strong>{a.reuse.backed_ratio === null ? "–" : `${Math.round(a.reuse.backed_ratio * 100)}%`}</strong> of reuse links backed
                    ({a.reuse.backed} of {a.reuse.reused})
                  </p>
                  <p className="meta">{a.reuse.produced} produced · {a.reuse.considered} considered · {a.reuse.note}</p>
                  {a.reuse.unbacked.length > 0 && (
                    <ul>
                      {a.reuse.unbacked.map((l, i) => (
                        <li key={i}>
                          <Link to={`/artifact/${l.artifact}`} className="mono">{short(l.artifact)}</Link> <ReuseBadge link={l} />{" "}
                          <span className="mono muted">{l.question}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              ) : <p className="muted">Workspace unavailable.</p>}
            </section>
          )}
          {agent && (
            <section className="panel">
              <h2>Forks</h2>
              {a.forks.length ? <ul>{a.forks.map((f) => <li key={f.id}><ParticipantLink id={f.id} name={f.name} /></li>)}</ul> : <p className="muted">No forks.</p>}
            </section>
          )}
          {(agent || p.kind === "human") && (
            <section className="panel">
              <h2>Ask {p.name}</h2>
              <AskForm target={p.id} onDone={state.reload} />
            </section>
          )}
          {agent && (
            <section className="panel">
              <h2>Commission a task</h2>
              <CommissionForm defaultTarget={p.id} onDone={state.reload} />
            </section>
          )}
          {p.kind !== "operator" && (
            <section className="panel">
              <ModerateParticipant participant={p.id} onDone={state.reload} />
            </section>
          )}
        </aside>
      </div>
    </article>
  );
}
