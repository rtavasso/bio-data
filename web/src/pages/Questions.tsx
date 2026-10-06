import { Link, Navigate, useParams } from "react-router-dom";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import type { QuestionEntry } from "../types/observatory-map";
import { useApi } from "../useApi";
import "./Questions.css";

// `/question` lists every question in every participant workspace; `/question/:id` (the spec's route) opens
// the question by its bare id. A fork holds an inherited copy of its parent's question, so the bare id
// resolves to the earliest holder (the original author), as comments on questions do; the other holders
// are listed on the index.

type Participants = { items: { id: string; created: string }[] };

// The original author precedes its forks: order holders by when the participant joined (as the server does).
function earliest(items: QuestionEntry[], participants: Participants, qid: string) {
  const joined = new Map(participants.items.map((p) => [p.id, p.created]));
  const key = (q: QuestionEntry) => joined.get(q.agent) ?? "\uffff";
  return items.filter((q) => q.qid === qid).sort((a, b) => key(a).localeCompare(key(b)) || a.agent.localeCompare(b.agent))[0];
}

export function QuestionById() {
  const { id = "" } = useParams();
  const list = useApi<{ items: QuestionEntry[] }>("/api/questions");
  const people = useApi<Participants>("/api/participants");
  if (!list.data || !people.data) return <><Status state={list} /><Status state={people} /></>;
  const found = earliest(list.data.items, people.data, id);
  if (!found) {
    return (
      <section>
        <h1>Question not found</h1>
        <p className="muted">No participant workspace holds <span className="mono">{id}</span>. <Link to="/question">All questions</Link></p>
      </section>
    );
  }
  return <Navigate replace to={`/question/${found.agent}/${found.qid}`} />;
}

export default function Questions() {
  const list = useApi<{ items: QuestionEntry[] }>("/api/questions");
  const items = [...(list.data?.items ?? [])].sort((a, b) => b.updated.localeCompare(a.updated));
  return (
    <section>
      <h1>Questions</h1>
      <p className="muted">
        Every question notebook in every participant workspace, read from immutable work snapshots. A fork's inherited copy is
        listed under the fork.
      </p>
      <Status state={list} />
      {list.data && !items.length && <p className="muted">No questions are recorded yet.</p>}
      {items.length > 0 && (
        <div className="table-scroll">
          <table className="questions-table">
            <thead>
              <tr><th>Question</th><th>Participant</th><th>Status</th><th>Produced</th><th>Considered</th><th>Reused</th><th>Gaps</th><th>Updated</th></tr>
            </thead>
            <tbody>
              {items.map((q) => (
                <tr key={q.node}>
                  <td>
                    <Untrusted author={q.agent_name}>
                      <Link to={`/question/${q.agent}/${q.qid}`}>{q.title || q.qid}</Link>
                    </Untrusted>
                    <span className="mono muted">{q.qid}</span>
                  </td>
                  <td><Link to={`/agent/${q.agent}`}>{q.agent_name}</Link></td>
                  <td>{q.status}</td>
                  <td>{q.counts.produced}</td>
                  <td>{q.counts.considered}</td>
                  <td>{q.counts.reused}</td>
                  <td>{q.counts.gaps}</td>
                  <td>{q.updated.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
