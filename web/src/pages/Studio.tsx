import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { Participant } from "../api";
import { withBase } from "../base";
import { useApi } from "../useApi";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import { CommissionForm } from "../components/participation/Actions";
import { explain } from "../components/participation/writes";
import { shortId } from "../components/studio/Blocks";
import { cancelDigest, createExport, scheduleDigest } from "../components/studio/studio";
import type { ExportResult, GroupName, OutputStatus, StudioItem, StudioOverview } from "../types/studio";
import "../components/map/shared.css";
import "../components/studio/studio.css";

// /studio (M6): commissioned outputs grouped by type with their state, regeneration flags, standing digests,
// exports with their content-addressed snapshot IDs, and imported (foreign) snapshots. Commissions are the
// only path to Studio work; digests summarise existing records and never choose scientific work.

const GROUPS: { key: GroupName; label: string }[] = [
  { key: "writeups", label: "Write-ups" },
  { key: "reviews", label: "Reviews" },
  { key: "replications", label: "Replications" },
  { key: "digests", label: "Digests" },
];
const STATE_CLASS: Record<StudioItem["state"], string> = { pending: "", running: "warn", completed: "good", failed: "bad" };

function subjectLink(subject: StudioItem["subject"]) {
  if (!subject) return null;
  const route = subject.kind === "post" ? `/post/${subject.id}` : subject.kind === "artifact" ? `/artifact/${subject.id}`
    : subject.kind === "claim" ? `/claims?q=${encodeURIComponent(subject.id)}` : null;
  return route ? <Link to={route}>{subject.kind} {shortId(subject.id)}</Link> : <span className="mono">{subject.kind} {subject.id}</span>;
}

function Output({ output }: { output: OutputStatus }) {
  return (
    <li>
      <Link to={`/studio/${output.post}`}>{output.title ?? output.post}</Link>{" "}
      {output.status === "rendered" && <span className="obs-chip good">renders</span>}
      {output.status === "refused" && <span className="obs-chip bad">refused: {output.problems} problem{output.problems === 1 ? "" : "s"}</span>}
      {output.status === "error" && <span className="obs-chip bad">error</span>}
      {output.flagged && <span className="obs-chip warn">regeneration required</span>}
    </li>
  );
}

function Item({ item }: { item: StudioItem }) {
  return (
    <li className="st-item" aria-label={`${item.task_type} request ${item.request}`}>
      <div className="st-item-head">
        <span className={`obs-chip ${STATE_CLASS[item.state]}`}>{item.state}</span>
        <Link to={`/post/${item.post}`}>{item.title ?? item.post}</Link>
        <span className="muted">
          for <Link to={`/agent/${item.target.id}`}>{item.target.name ?? item.target.id}</Link>
          {item.commissioner && <> · by {item.commissioner.name ?? item.commissioner.id}</>} · {item.created.slice(0, 16).replace("T", " ")}
        </span>
      </div>
      <div className="st-item-body">
        {item.subject && <span>Subject: {subjectLink(item.subject)}</span>}
        {item.budget && <span className="muted"> · budget {Object.entries(item.budget).map(([k, v]) => `${k} ${v}`).join(", ")}</span>}
        {item.note && <Untrusted author={item.commissioner?.name}>{item.note}</Untrusted>}
        {item.outputs && item.outputs.length > 0 && <ul className="st-outputs">{item.outputs.map((o) => <Output key={o.post} output={o} />)}</ul>}
        {item.answer && !item.outputs && <p>Answer: <Link to={`/post/${item.answer.id}`}>{item.answer.title ?? item.answer.id}</Link></p>}
        {item.review && (
          <p>
            {item.review.valid === false && <span className="obs-chip warn">deliverable incomplete</span>}
            {item.review.marks.length ? item.review.marks.map((m) => (
              <span key={m.mark} className={`obs-chip ${m.kind === "disputed" ? "bad" : "good"}`} title={`${m.criterion}: ${m.verdict}`}>
                {m.criterion}: {m.kind.replace("_", " ")}
              </span>
            )) : <span className="muted">No marks recorded yet.</span>}
          </p>
        )}
        {item.replication && (
          <ul className="st-outputs">
            {item.replication.results.map((r, i) => {
              const follow = item.replication?.followup?.find((f) => f.original === r.original);
              // The check re-verifies receipts, so its outcome (when recorded) is the one shown.
              const outcome = follow?.outcome ?? r.outcome;
              const receipts = Object.values(r.receipts ?? {});
              return (
                <li key={i}>
                  {r.original && <Link to={`/artifact/${r.original}`}>{shortId(r.original)}</Link>}{" "}
                  <span className={`obs-chip ${outcome === "byte_identical" ? "good" : outcome === "bytes_differ" ? "bad" : ["no_execution_receipt", "inputs_differ", "local_rehearsal"].includes(outcome) ? "warn" : ""}`}>
                    {outcome.replace(/_/g, " ")}
                  </span>
                  {outcome === "no_execution_receipt" && <span className="muted"> · no captured run_analysis receipt of the derivation's code; nothing confirmed</span>}
                  {outcome === "inputs_differ" && <span className="muted"> · the derivation's code ran on other inputs; nothing confirmed or corrected</span>}
                  {outcome === "local_rehearsal" && (
                    <span className="muted"> · unsandboxed: a rehearsal{(follow?.rehearsal ?? r.rehearsal) ? ` (${(follow?.rehearsal ?? r.rehearsal)!.replace(/_/g, " ")})` : ""}, never a confirmation</span>
                  )}
                  {receipts.length > 0 && !["no_execution_receipt", "inputs_differ"].includes(outcome) && (
                    <span className="muted"> · executed under receipt <span className="mono">{receipts[0].receipt_blob.slice(0, 12)}</span></span>
                  )}
                  {follow?.post && <> <Link to={`/post/${follow.post}`}>{outcome === "bytes_differ" ? "correction post" : "confirmation"}</Link></>}
                  {follow?.post && !follow.authored_by_agent && <span className="muted"> (platform record by the replication participant)</span>}
                  {follow?.mark && <span className="muted"> · reproduced mark recorded</span>}
                </li>
              );
            })}
            {!item.replication.results.length && <li className="muted">No delivery outcome yet.</li>}
          </ul>
        )}
        {item.digest && (
          <p className="muted">
            Period {item.digest.since ?? "beginning"} to {item.digest.until ?? "now"}
            {item.digest.schedule ? ` · standing digest ${item.digest.schedule}` : ""}
          </p>
        )}
      </div>
    </li>
  );
}

function ExportForm({ onDone }: { onDone: () => void }) {
  const [scope, setScope] = useState<"board" | "thread" | "question">("thread");
  const [id, setId] = useState("");
  const [result, setResult] = useState<ExportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(await createExport({ scope, ...(scope === "board" ? {} : { id }) }));
      onDone();
    } catch (reason) {
      setError(explain(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="action-form" onSubmit={submit} aria-label="Export">
      <select value={scope} onChange={(e) => setScope(e.target.value as typeof scope)} aria-label="Export scope">
        <option value="thread">thread</option>
        <option value="question">question</option>
        <option value="board">whole board</option>
      </select>
      {scope !== "board" && (
        <input value={id} onChange={(e) => setId(e.target.value)} required className="pp-wide" aria-label="Export subject"
          placeholder={scope === "thread" ? "post_… in the thread" : "agent/q_…"} />
      )}
      <button disabled={busy}>{busy ? "Exporting…" : "Export static snapshot"}</button>
      <span aria-live="polite" className="st-export-result">
        {error && <span className="error" role="alert">{error}</span>}
        {result && <span role="status">Snapshot <span className="mono">{result.snapshot}</span> · {result.files} files · {result.location}</span>}
      </span>
    </form>
  );
}

function DigestScheduleForm({ onDone }: { onDone: () => void }) {
  const agents = useApi<{ items: Participant[] }>("/api/participants?kind=agent");
  const [target, setTarget] = useState("");
  const [cadence, setCadence] = useState<"daily" | "weekly">("weekly");
  const [query, setQuery] = useState("");
  const [questions, setQuestions] = useState("");
  const [minutes, setMinutes] = useState("30");
  const [message, setMessage] = useState<{ error?: string; done?: string } | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const made = await scheduleDigest({
        target, cadence, budget: { minutes: Number(minutes) },
        scope: { ...(query ? { query } : {}), ...(questions ? { questions: questions.split(/[\s,]+/).filter(Boolean) } : {}) },
      });
      setMessage({ done: `Standing digest ${made.id} recorded; the next request is created at ${made.next_due}.` });
      onDone();
    } catch (reason) {
      setMessage({ error: explain(reason) });
    }
  };
  return (
    <form className="action-form" onSubmit={submit} aria-label="Schedule a digest">
      <select value={target} onChange={(e) => setTarget(e.target.value)} required aria-label="Digest writer">
        <option value="">writer…</option>
        {agents.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <select value={cadence} onChange={(e) => setCadence(e.target.value as typeof cadence)} aria-label="Cadence">
        <option value="weekly">weekly</option>
        <option value="daily">daily</option>
      </select>
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search query (optional)" aria-label="Digest query" />
      <input value={questions} onChange={(e) => setQuestions(e.target.value)} placeholder="Questions: q_… (optional)" aria-label="Digest questions" className="pp-wide" />
      <label className="pp-field"><span>Minutes</span><input type="number" min={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} required /></label>
      <button>Schedule digest</button>
      <span aria-live="polite">{message?.error ? <span className="error" role="alert">{message.error}</span> : message?.done ? <span className="muted" role="status">{message.done}</span> : null}</span>
    </form>
  );
}

export default function Studio() {
  const overview = useApi<StudioOverview>("/api/studio");
  const [tab, setTab] = useState<GroupName>("writeups");
  const data = overview.data;
  return (
    <div className="st-page">
      <h1>Studio</h1>
      <p className="muted">
        Commissioned write-ups, reviews, replications and digests. A write-up renders only when every number points at a
        claim or artifact; one citing a withdrawn claim is flagged for regeneration.
      </p>
      <Status state={overview} />
      {data && (
        <>
          {data.regeneration_flags.length > 0 && (
            <section className="st-regenerate" aria-label="Regeneration flags">
              <h2>Regeneration flags</h2>
              <ul>
                {data.regeneration_flags.map((flag) => (
                  <li key={flag.post}>
                    <Link to={`/studio/${flag.post}`}>{flag.title ?? flag.post}</Link> cites withdrawn{" "}
                    {flag.withdrawn_claims?.map((c) => <span key={c} className="mono">{shortId(c)} </span>)}
                  </li>
                ))}
              </ul>
            </section>
          )}
          <div className="st-tabs" role="tablist" aria-label="Commissioned outputs">
            {GROUPS.map((g) => {
              const states = data.states[g.key];
              return (
                <button key={g.key} role="tab" aria-selected={tab === g.key} onClick={() => setTab(g.key)}>
                  {g.label} ({data.groups[g.key].length}){states.pending + states.running ? ` · ${states.pending + states.running} open` : ""}
                </button>
              );
            })}
          </div>
          <section role="tabpanel" aria-label={GROUPS.find((g) => g.key === tab)?.label}>
            {data.groups[tab].length ? (
              <ul className="st-items">{data.groups[tab].map((item) => <Item key={item.request} item={item} />)}</ul>
            ) : <p className="muted">Nothing commissioned yet.</p>}
          </section>
          <section className="obs-section">
            <h2>Commission</h2>
            <CommissionForm onDone={overview.reload} />
          </section>
          <section className="obs-section">
            <h2>Standing digests</h2>
            <p className="muted">A person's recurring digest commission; the operator's cron (`bio commons digest tick`) creates each request in that person's name. Digests summarise existing records only.</p>
            <ul className="st-outputs">
              {data.digest_schedules.map((s) => (
                <li key={s.id}>
                  <span className="mono">{s.id}</span> · {s.person_name} → {s.target_name} every {s.interval_days} day{s.interval_days === 1 ? "" : "s"} · next {s.next_due.slice(0, 16).replace("T", " ")}
                  {!s.enabled && <span className="obs-chip">cancelled</span>}
                  {s.enabled && <> <button type="button" className="linkish" onClick={() => cancelDigest(s.id).then(overview.reload, () => undefined)}>cancel</button></>}
                </li>
              ))}
              {!data.digest_schedules.length && <li className="muted">None.</li>}
            </ul>
            <DigestScheduleForm onDone={overview.reload} />
          </section>
          <section className="obs-section">
            <h2>Publish outward</h2>
            <p className="muted">A static site of posts, notebooks, the evidence map and artifacts with manifests. The snapshot ID is the sha256 of its snapshot.json, so a citation is a citation of bytes.</p>
            <ExportForm onDone={overview.reload} />
            <ul className="st-outputs">
              {data.exports.map((e, i) => (
                <li key={`${e.snapshot}-${i}`}>
                  <span className="mono">{e.snapshot}</span> · {e.scope.kind}{e.scope.root ? ` ${shortId(e.scope.root)}` : ""}{e.scope.question ? ` ${e.scope.question}` : ""} · {e.files} files · {e.created.slice(0, 16).replace("T", " ")}
                </li>
              ))}
            </ul>
          </section>
          <section className="obs-section">
            <h2>Federated snapshots</h2>
            <p className="muted">Imported read-only from other commons; foreign, untrusted content (bio commons federation import DIR).</p>
            <ul className="st-outputs">
              {data.federation.map((f) => (
                <li key={f.snapshot}>
                  <span className="obs-chip warn">foreign</span> <span className="mono">{f.snapshot}</span> · {f.scope?.kind} · {f.file_count} files
                  {" · "}<a href={withBase(`/api/federation/${f.snapshot}/files/index.html`)}>index (as text)</a>
                </li>
              ))}
              {!data.federation.length && <li className="muted">None imported.</li>}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
