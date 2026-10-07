import { Link, useParams } from "react-router-dom";
import { withBase } from "../base";
import { useApi } from "../useApi";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import { Markdown } from "../components/Markdown";
import { AskForm, CommissionForm } from "../components/participation/Actions";
import TimelineCanvas, { formatSeconds } from "../components/run/TimelineCanvas";
import Messages from "../components/run/Messages";
import type { RunTimeline } from "../types/observatory-map";
import "../components/map/graph.css";
import "../components/map/shared.css";
import "./Run.css";

// M4.4 Agent timeline for one delivery. Monotonic time is the axis; wall time includes host sleep, so a
// suspension is shown as a greyed break with its wall duration. Token counts never default to zero.

function Clock({ timeline }: { timeline: RunTimeline }) {
  const e = timeline.execution;
  const value = (v: number | null | undefined) => (typeof v === "number" ? formatSeconds(v) : "unavailable");
  return (
    <dl className="run-clock">
      <div><dt>monotonic</dt><dd>{value(e.monotonic_seconds)}</dd></div>
      <div><dt>wall</dt><dd>{value(e.wall_seconds)}</dd></div>
      <div className={e.suspended_seconds ? "suspended" : undefined}>
        <dt>suspended</dt>
        <dd>{e.suspended_seconds ? formatSeconds(e.suspended_seconds) : `none above the ${e.suspension_floor_seconds} s floor`}</dd>
      </div>
      <div><dt>state</dt><dd>{e.state ?? "unknown"}{e.returncode !== null && e.returncode !== undefined ? ` (exit ${e.returncode})` : ""}</dd></div>
      <div><dt>started</dt><dd>{e.started ?? "unrecorded"}</dd></div>
    </dl>
  );
}

function Verdict({ outcome }: { outcome: "pass" | "fail" | "unknown" }) {
  const label = { pass: "✓ pass", fail: "✗ fail", unknown: "? exit code unknown" }[outcome];
  return <span className={`obs-chip ${outcome === "pass" ? "good" : outcome === "fail" ? "bad" : ""}`}>{label}</span>;
}

const at = (t: number | null, unit: string) => (t === null ? "—" : unit === "seconds" ? formatSeconds(t) : `#${t}`);

export default function RunPage() {
  const { id = "" } = useParams();
  const state = useApi<RunTimeline>(`/api/runs/${encodeURIComponent(id)}`);
  const t = state.data;
  if (!t) return <section><h1>Run</h1><Status state={state} /></section>;
  const unit = t.axis.unit;
  const summaries = t.compaction_summaries;
  return (
    <section className="run-page">
      <h1>Delivery <span className="mono">{t.run.id}</span></h1>
      <p className="muted">
        <Link to={`/agent/${t.agent.id}`}>{t.agent.name}</Link>
        {t.agent.model ? ` · ${t.agent.model}` : ""} · request <span className="mono">{t.run.request}</span>
        {t.request.task_type ? ` · ${t.request.task_type}` : ""}{t.request.post && <> · <Link to={`/post/${t.request.post}`}>request post</Link></>}
        {" · "}<a href={withBase(t.links.raw)} target="_blank" rel="noopener noreferrer">raw stream</a>
      </p>
      {t.request.title && <Untrusted><strong>{t.request.title}</strong></Untrusted>}
      {t.request.hidden && !t.request.title && <p className="hidden-notice" role="note">The request post is hidden by moderation: {t.request.reason}.</p>}
      <Clock timeline={t} />

      <section className="obs-section">
        <h2>Timeline</h2>
        <p className="muted run-axis">Axis: {t.axis.clock}. {t.suspensions.map((s) => (
          `Suspension of ${formatSeconds(s.seconds)} placed at ${at(s.at, unit)} (largest gap between event timestamps` +
          `${s.unplaced_seconds ? `; ${formatSeconds(s.unplaced_seconds)} could not be placed` : ""}).`
        ))}</p>
        <TimelineCanvas timeline={t} />
        <div className="viz viz-legend run-legend">
          <span><i className="run-key bar" /> tool call (red outline: non-zero exit)</span>
          <span className="run-good">✓ receipt passed</span>
          <span className="run-bad">✗ receipt failed</span>
          <span>C compaction</span>
          <span>F compaction fallback</span>
          <span>★ headline result</span>
          <span><i className="run-key break" /> host suspension (not to scale)</span>
        </div>
        <details>
          <summary>Table view ({t.calls.length} tool calls)</summary>
          <div className="table-scroll">
            <table className="obs-table">
              <thead><tr><th>line</th><th>at</th><th>lane</th><th>call</th><th>exit</th></tr></thead>
              <tbody>
                {t.calls.map((c) => (
                  <tr key={c.line}>
                    <td>{c.line}</td><td>{at(c.t, unit)}</td><td>{c.lane}</td>
                    <td className="mono">{c.summary || c.name}</td><td>{c.exit_code ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>

      <section className="obs-section run-grid">
        <div>
          <h2>Analysis receipts</h2>
          {t.receipts.length ? (
            <ul className="run-list">
              {t.receipts.map((r) => (
                <li key={r.line}><Verdict outcome={r.outcome} /> <span className="mono">{r.script ?? r.summary}</span>{" "}
                  <span className="muted">{at(r.t, unit)} · line {r.line}</span></li>
              ))}
            </ul>
          ) : <p className="muted">No run_analysis.py receipts in this delivery.</p>}
          <h2>Headline result</h2>
          {t.headline ? (
            <p>★ {at(t.headline.t, unit)}: <span className="mono">{t.headline.summary}</span> <span className="muted">({t.headline.basis})</span></p>
          ) : <p className="muted">No successful registration, publication or analysis was recorded.</p>}
        </div>
        <div>
          <h2>Compactions</h2>
          <p>
            {t.compactions.length} in the stream;{" "}
            {summaries === null ? "no agent-state database to read summaries from" :
              `${summaries.length} summaries in this delivery, ${summaries.filter((s) => s.fallback).length} deterministic fallback(s)`}
          </p>
          {summaries?.filter((s) => s.fallback).map((_, i) => (
            <p key={i} className="run-fallback"><span className="obs-chip warn">fallback</span> the summarizer failed; a placeholder replaced the context.</p>
          ))}
          <h2>Inbox and peer answers</h2>
          <p>{t.inbox_reads.length} inbox read(s), {t.inbox_reads.filter((r) => r.sent).length} of sent questions.</p>
          {t.answers_consumed.length ? (
            <ul className="run-list">
              {t.answers_consumed.map((a) => (
                <li key={a.line}>{at(a.t, unit)}: read {a.posts.map((p) => <Link key={p} to={`/post/${p}`} className="mono">{p.slice(0, 13)}… </Link>)}</li>
              ))}
            </ul>
          ) : <p className="muted">No peer answers were read in this delivery.</p>}
        </div>
      </section>

      <section className="obs-section">
        <h2>Final answer</h2>
        {t.final.text ? (
          <>
            <p className="muted">From {t.final.source}.</p>
            <Untrusted author={t.agent.name}><Markdown source={t.final.text} /></Untrusted>
          </>
        ) : t.final.hidden ? (
          <p className="hidden-notice" role="note">The answer post is hidden by moderation: {t.final.reason}. Its text,
            the raw stream and the model-facing messages are withheld; operators can read them.</p>
        ) : <p className="muted">No final answer was produced.</p>}
      </section>

      <section className="obs-section run-grid">
        <div>
          <h2>Token usage</h2>
          <table className="obs-table">
            <tbody>
              {Object.entries(t.tokens).filter(([k]) => k !== "note").map(([k, v]) => (
                <tr key={k}><th>{k.replace(/_/g, " ")}</th><td className={v === "unavailable" ? "obs-missing" : undefined}>{String(v)}</td></tr>
              ))}
            </tbody>
          </table>
          {typeof t.tokens.note === "string" && <p className="muted">{t.tokens.note}</p>}
        </div>
        <div>
          <h2>Behaviour metrics</h2>
          <table className="obs-table">
            <tbody>
              {Object.entries(t.metrics).filter(([k]) => k !== "limitations").map(([k, v]) => (
                <tr key={k}><th>{k.replace(/_/g, " ")}</th><td>{v === null ? <span className="obs-missing">unavailable</span> : String(v)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="obs-section">
        <h2>Model-facing messages</h2>
        <Messages path={t.links.messages} agent={t.agent.name} />
      </section>

      <section className="obs-section">
        <h2>Act</h2>
        <h3>Ask {t.agent.name}</h3>
        <AskForm target={t.agent.id} />
        <h3>Commission a task</h3>
        <CommissionForm subjectKind="run" subjectId={t.run.id} />
      </section>

      <details className="obs-section">
        <summary>Limitations</summary>
        <ul>{t.limitations.map((l) => <li key={l} className="muted">{l}</li>)}</ul>
        {t.malformed_lines.length > 0 && <p className="muted">Malformed stream lines: {t.malformed_lines.join(", ")}</p>}
      </details>
    </section>
  );
}
