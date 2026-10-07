import { Link, useParams } from "react-router-dom";
import { withBase } from "../base";
import { useApi } from "../useApi";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import { Markdown } from "../components/Markdown";
import { AskForm, CommissionForm } from "../components/participation/Actions";
import TimelineCanvas, { formatSeconds } from "../components/run/TimelineCanvas";
import Messages from "../components/run/Messages";
import type { RunTimeline, Suspension } from "../types/observatory-map";
import "../components/map/graph.css";
import "../components/map/shared.css";
import "./Run.css";

// M4.4 Agent timeline for one delivery. Monotonic time is the axis; wall time includes host sleep, so a
// suspension is shown as a greyed break with its wall duration. Token counts never default to zero.
// Spec v2 C10: what the stream records is drawn solid; what a heuristic places (the suspension's position,
// the headline, peer answers read) is labelled and drawn "attributed, not recorded". null is "unavailable".

function Attributed({ basis }: { basis?: string }) {
  return <span className="obs-chip run-attributed" title={basis}>attributed, not recorded</span>;
}

// Spec v2 V6: items placed by run records (clock.jsonl, receipts.json, compactions.jsonl) say so.
function Recorded({ basis }: { basis?: string }) {
  return <span className="obs-chip run-recorded" title={basis}>recorded</span>;
}

// v3 G3: placed between samples reindexed from execution.json, heartbeat.json and the stream's own timestamps.
function Reindexed({ basis }: { basis?: string }) {
  return <span className="obs-chip run-recorded" title={basis}>placed between reindexed samples</span>;
}

function placementText(s: Suspension): string {
  if (s.placement === "reindexed_samples") return `placed between reindexed samples (${s.window?.sources.join(" and ") ?? ""})`;
  if (s.placement === "clock_records") return `between clock records ${s.records?.join(" and ") ?? ""}`;
  if (s.placement === "largest_event_gap_within_clock_window")
    return `bounded by clock samples to ${formatSeconds(s.window?.monotonic_seconds ?? 0)}; at the largest event gap inside`;
  if (s.placement === "before_first_event") return "before the first event";
  if (s.placement === "after_last_event") return "after the last event";
  return "largest gap between event timestamps";
}

function RecordsLine({ timeline }: { timeline: RunTimeline }) {
  const r = timeline.records;
  if (!r) return null;
  const parts: string[] = [];
  parts.push(r.clock ? `${r.clock.records} clock records${r.clock.reindexed ? " (reindexed from execution.json, heartbeat.json and the stream's timestamps)" : ""}`
    : "no clock records");
  parts.push(r.receipts ? `${r.receipts.counts.receipts} indexed receipt(s)${r.receipts.reindexed ? " (reindexed)" : ""}`
    : "no receipt index (receipts from exit codes)");
  parts.push(r.compactions ? (r.compactions.available ? `${r.compactions.count ?? 0} recorded compaction summaries`
    : `compaction summaries unavailable: ${r.compactions.reason ?? "not exposed"}`) : "no compaction record");
  return <p className="muted run-records">Run records: {parts.join("; ")}.</p>;
}

function Clock({ timeline }: { timeline: RunTimeline }) {
  const e = timeline.execution;
  const value = (v: number | null | undefined) => (typeof v === "number" ? formatSeconds(v) : "unavailable");
  return (
    <dl className="run-clock">
      <div><dt>monotonic</dt><dd>{value(e.monotonic_seconds)}</dd></div>
      <div><dt>wall</dt><dd>{value(e.wall_seconds)}</dd></div>
      <div className={e.suspended_seconds ? "suspended" : undefined}>
        <dt>suspended</dt>
        <dd>{e.suspended_seconds === null || e.suspended_seconds === undefined ? <span className="obs-missing">unavailable</span>
          : e.suspended_seconds ? formatSeconds(e.suspended_seconds) : `none above the ${e.suspension_floor_seconds} s floor`}</dd>
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

// v3 V13: the delivery's turn economics record. null values are unavailable, never zero.
function TurnEconomicsSection({ timeline }: { timeline: RunTimeline }) {
  const e = timeline.turn_economics;
  const show = (v: number | null | undefined, suffix = "") =>
    v === null || v === undefined ? <span className="obs-missing">unavailable</span> : `${v}${suffix}`;
  const source = (k: string, v: number | null) => {
    if (v === null) return `${k.replace(/_/g, " ")} unmeasured`;
    const share = e?.composition.shares?.[k];
    return `${k.replace(/_/g, " ")} ${share !== undefined && share !== null ? `${Math.round(share * 100)}%` : `${v} B`}`;
  };
  return (
    <section className="obs-section">
      <h2>Turn economics</h2>
      {!e ? <p className="muted">No turn_economics record for this delivery.</p> : (
        <>
          {e.reindexed && <p className="muted">Reindexed: {e.reindexed.note}.</p>}
          <table className="obs-table">
            <tbody>
              <tr><th>context tokens{e.context ? ` per ${e.context.unit}` : ""}</th><td>{show(e.context?.mean_input_tokens)}
                {e.context ? ` (max ${e.context.max_input_tokens}, ${e.context.records} ${e.context.unit}s)` : ""}</td></tr>
              <tr><th>model calls</th><td>{show(e.model_calls)}</td></tr>
              <tr><th>context sources ({e.composition.basis})</th>
                <td>{Object.entries(e.composition.bytes).map(([k, v]) => source(k, v)).join(" · ")}</td></tr>
              <tr><th>compactions · summaries (fallbacks, marker match)</th>
                <td>{show(e.compactions.stream_markers)} · {show(e.compactions.summaries)} ({show(e.compactions.fallbacks)})</td></tr>
              <tr><th>generation / tool wait</th>
                <td>{show(e.time.generation_minutes, " min")} / {show(e.time.tool_wait_minutes, " min")} <span className="muted">({e.time.basis})</span></td></tr>
              <tr><th>help / re-orientation calls</th>
                <td>{e.orientation ? `${e.orientation.help_calls} / ${e.orientation.reorientation_calls}` : show(null)}</td></tr>
              <tr><th>ceremony tail</th><td>{show(e.ceremony_tail_minutes, " min")}</td></tr>
              <tr><th>skill reads</th>
                <td>{e.skills.reads === null ? show(null) : Object.entries(e.skills.reads).map(([k, v]) => `${k} ×${v}`).join(", ") || "none"}
                  {` · skill version ${e.skills.version ?? "unrecorded"}`}</td></tr>
            </tbody>
          </table>
        </>
      )}
    </section>
  );
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
          <span key={`${s.at}-${s.seconds}`}>
            {`Suspension of ${formatSeconds(s.seconds)} placed at ${at(s.at, unit)} (${placementText(s)}` +
              `${s.unplaced_seconds ? `; ${formatSeconds(s.unplaced_seconds)} could not be placed` : ""}). `}
            {s.attributed ? <Attributed basis={s.basis} /> : s.reindexed ? <Reindexed basis={s.basis} /> : <Recorded basis={s.basis} />}
          </span>
        ))}</p>
        <RecordsLine timeline={t} />
        <TimelineCanvas timeline={t} />
        <div className="viz viz-legend run-legend">
          <span><i className="run-key bar" /> tool call (red outline: non-zero exit)</span>
          <span className="run-good">✓ receipt passed</span>
          <span className="run-bad">✗ receipt failed</span>
          <span>C compaction</span>
          <span>F compaction fallback (marker match)</span>
          <span>★ headline result</span>
          <span>↩ peer answer read</span>
          <span><i className="run-key break" /> host suspension (not to scale)</span>
          <span><i className="run-key attributed" /> attributed, not recorded (dotted, hatched: placed by a heuristic)</span>
          <span><i className="run-key break" /> recorded suspension: solid (placed between clock records or reindexed samples)</span>
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
              {t.receipts.map((r, i) => (
                <li key={`${r.line ?? "r"}-${i}`}><Verdict outcome={r.outcome} /> <span className="mono">{r.script ?? r.summary}</span>{" "}
                  <span className="muted">{at(r.t, unit)}{r.line !== null ? ` · line ${r.line}` : ""}
                    {r.receipt ? ` · receipt ${r.receipt.path} (sha256 ${r.receipt.sha256.slice(0, 12)}…)` : ""}</span>{" "}
                  {r.attributed ? <Attributed basis={r.basis} /> : r.source === "receipt" ? <Recorded basis="run_analysis.py receipt file indexed for this delivery" /> : null}</li>
              ))}
            </ul>
          ) : <p className="muted">No run_analysis.py receipts in this delivery.</p>}
          {(t.unreceipted_analysis_calls?.length ?? 0) > 0 && (
            <p className="muted">{t.unreceipted_analysis_calls?.length} run_analysis.py call(s) without an indexed receipt file
              (lines {t.unreceipted_analysis_calls?.map((c) => c.line).join(", ")}).</p>
          )}
          <h2>Headline result</h2>
          {t.headline ? (
            <p>★ {at(t.headline.t, unit)}: <span className="mono">{t.headline.summary}</span> <span className="muted">({t.headline.basis})</span>
              {t.headline.attributed && <> <Attributed basis={`chosen as the ${t.headline.basis}`} /></>}</p>
          ) : <p className="muted">No successful registration, publication or analysis was recorded.</p>}
        </div>
        <div>
          <h2>Compactions</h2>
          <p>
            {t.compactions === null
              ? <><span className="obs-missing">unavailable</span> in the stream (this harness does not mark compactions);</>
              : `${t.compactions.length} in the stream;`}{" "}
            {summaries === null ? (t.records?.compactions && !t.records.compactions.available
              ? <>summaries <span className="obs-missing">unavailable</span> ({t.records.compactions.reason})</>
              : "no agent-state database to read summaries from") :
              `${summaries.length} summaries in this delivery, ` + (summaries.some((s) => s.fallback === null)
                ? "fallbacks unavailable (this harness writes no fallback marker)"
                : `${summaries.filter((s) => s.fallback).length} deterministic fallback(s) by marker match`)}
          </p>
          {summaries?.filter((s) => s.fallback).map((_, i) => (
            <p key={i} className="run-fallback"><span className="obs-chip warn">fallback (marker match)</span> the summary text
              contains the deterministic-fallback marker: the summarizer failed and a placeholder replaced the context.</p>
          ))}
          <h2>Inbox and peer answers</h2>
          <p>{t.inbox_reads.length} inbox read(s), {t.inbox_reads.filter((r) => r.sent).length} of sent questions.</p>
          {t.answers_consumed.length ? (
            <ul className="run-list">
              {t.answers_consumed.map((a) => (
                <li key={a.line}>{at(a.t, unit)}: read {a.posts.map((p) => <Link key={p} to={`/post/${p}`} className="mono">{p.slice(0, 13)}… </Link>)}
                  {a.attributed && <Attributed basis={a.basis} />}</li>
              ))}
            </ul>
          ) : <p className="muted">No peer answers were read in this delivery.</p>}
        </div>
      </section>

      <TurnEconomicsSection timeline={t} />

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
