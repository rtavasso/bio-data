import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { query } from "../api";
import { Status } from "../components/Status";
import CohortCompare, { CostCell } from "../components/dashboard/CohortCompare";
import { ReuseBars, Sparkline, Value, ratioText } from "../components/dashboard/Charts";
import type { CohortSummary, Dashboard as DashboardData, Dimension, Group, Num } from "../types/dashboard";
import { useApi } from "../useApi";
import "./Dashboard.css";

// M9.2 evaluation dashboard: the audit report as live panels per cohort, participant, harness and
// task type. Behaviour counts, not scientific value. Filters live in the URL so a view is reproducible.

const DIMENSIONS: [Dimension, string][] = [
  ["cohort", "Cohort"], ["participant", "Participant"], ["harness", "Harness"], ["task_type", "Task type"],
];
const FILTERS = ["cohort", "participant", "harness", "task_type", "bucket"] as const;

function maxOf(groups: Group[], pick: (g: Group) => (Num | undefined)[]): number {
  let top = 0;
  for (const g of groups) for (const v of pick(g)) if (typeof v === "number" && v > top) top = v;
  return top;
}

function Stat({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="stat" title={hint}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{children}</div>
    </div>
  );
}

function Summary({ g }: { g: Group }) {
  return (
    <div className="stats" aria-label="Summary">
      <Stat label="Runs">{g.runs} <span className="muted small">({g.completed} completed, {g.failed} failed)</span></Stat>
      <Stat label="Monotonic vs wall hours" hint="Wall time includes host sleep">
        <Value value={g.monotonic_hours} digits={3} /> / <Value value={g.wall_hours} digits={3} />
      </Stat>
      <Stat label="Suspensions">{g.suspensions} <span className="muted small">({g.suspended_hours.toFixed(2)} h)</span></Stat>
      <Stat label="Minutes per executed analysis"><Value value={g.minutes_per_executed_analysis} /></Stat>
      <Stat label="Analyses (failed)">{g.analysis_receipts} ({g.analysis_failures})</Stat>
      <Stat label="Tool / inbox calls">{g.tool_calls} / {g.inbox_calls}</Stat>
      <Stat label="Plumbing share">{ratioText(g.plumbing_share)}</Stat>
      <Stat label="Compactions (fallbacks)">{g.compactions} (<Value value={g.compaction_fallbacks} />)</Stat>
      <Stat label="Ceremony tail, median min" hint="Minutes after the last successful analysis">
        <Value value={g.ceremony_tail_minutes.median} digits={1} />
      </Stat>
      <Stat label="Reuse backed">{ratioText(g.board.reuse.backed_ratio)} <span className="muted small">({g.board.reuse.backed}/{g.board.reuse.backed + g.board.reuse.unbacked})</span></Stat>
      <Stat label="Human marks per post"><Value value={g.board.human_marks_per_post} /></Stat>
      <Stat label="Provider-citation hits">{g.provider_citation_finals} finals · {g.board.provider_citation_posts} posts</Stat>
    </div>
  );
}

function Panel({ g, scale }: { g: Group; scale: { tail: number; fallbacks: number; perAnalysis: number; reuse: number } }) {
  const reuse = g.board.reuse;
  return (
    <article className="panel" aria-label={g.label}>
      <header>
        <h3>{g.label}</h3>
        <span className="muted small">{g.runs} runs · posts by {g.posts_scope}</span>
      </header>
      {g.runs === 0 ? <p className="no-runs">No deliveries in scope; board activity only.</p> : (
        <>
          <Sparkline label="Ceremony tail (median min)" points={g.trend} value={(p) => p.ceremony_tail_median} max={scale.tail} />
          <Sparkline label="Compaction fallbacks" points={g.trend} value={(p) => p.compaction_fallbacks} max={scale.fallbacks} />
          <Sparkline label="Minutes per executed analysis" points={g.trend} value={(p) => p.minutes_per_executed_analysis} max={scale.perAnalysis} />
        </>
      )}
      <div className="panel-row">
        <span>Reuse links</span>
        <span className="muted small">backed {ratioText(reuse.backed_ratio)}</span>
      </div>
      <ReuseBars backed={reuse.backed} unbacked={reuse.unbacked} max={scale.reuse} />
      <dl className="panel-facts">
        <dt>Human marks per post</dt><dd><Value value={g.board.human_marks_per_post} /> <span className="muted small">({g.board.human_marks}/{g.board.posts})</span></dd>
        <dt>Corrections</dt><dd>{g.board.corrections}</dd>
        <dt>Analyses (failed)</dt><dd>{g.analysis_receipts} ({g.analysis_failures})</dd>
        <dt>Monotonic h</dt><dd><Value value={g.monotonic_hours} digits={3} /></dd>
      </dl>
      {g.runs > 0 && <details>
        <summary>Trend table</summary>
        <table className="mini">
          <thead><tr><th>Period</th><th>Runs</th><th>Tail</th><th>Fallbacks</th><th>Min/analysis</th></tr></thead>
          <tbody>
            {g.trend.map((p) => (
              <tr key={p.bucket}>
                <td>{p.bucket}</td><td>{p.runs}</td><td><Value value={p.ceremony_tail_median} digits={1} /></td>
                <td><Value value={p.compaction_fallbacks} /></td><td><Value value={p.minutes_per_executed_analysis} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>}
    </article>
  );
}

function Panels({ groups }: { groups: Group[] }) {
  if (groups.length === 0) return <p className="muted">No groups for these filters.</p>;
  const scale = {
    tail: maxOf(groups, (g) => g.trend.map((p) => p.ceremony_tail_median)),
    fallbacks: maxOf(groups, (g) => g.trend.map((p) => p.compaction_fallbacks)),
    perAnalysis: maxOf(groups, (g) => g.trend.map((p) => p.minutes_per_executed_analysis)),
    reuse: maxOf(groups, (g) => [g.board.reuse.backed, g.board.reuse.unbacked]),
  };
  return <div className="multiples">{groups.map((g) => <Panel key={g.key} g={g} scale={scale} />)}</div>;
}

function CostTable({ groups, currency }: { groups: Group[]; currency: string | null }) {
  return (
    <div className="compare-scroll">
      <table className="cost-table">
        <thead><tr><th scope="col">Group</th><th scope="col">Runs with telemetry</th><th scope="col">Tokens, compute and {currency ?? "currency"} cost</th><th scope="col">Why unavailable</th></tr></thead>
        <tbody>
          {groups.map((g) => (
            <tr key={g.key}>
              <th scope="row">{g.label}</th>
              <td>{g.cost.token_reported_runs} of {g.cost.runs}</td>
              <td><CostCell cost={g.cost} /></td>
              <td className="muted small">{g.cost.unavailable_reasons.join("; ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Dashboard() {
  const [params, setParams] = useSearchParams();
  const [dimension, setDimension] = useState<Dimension>("participant");
  const filters = Object.fromEntries(FILTERS.map((k) => [k, params.get(k) ?? undefined]));
  const state = useApi<DashboardData>(`/api/dashboard${query(filters)}`);
  const cohorts = useApi<{ items: CohortSummary[] }>("/api/cohorts");
  const data = state.data;
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
  };
  const select = (key: string, label: string, options: { value: string; label: string }[]) => (
    <label>
      {label}{" "}
      <select value={params.get(key) ?? ""} onChange={(e) => set(key, e.target.value)}>
        <option value="">all</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
  return (
    <section className="dashboard">
      <h1>Evaluation dashboard</h1>
      <p className="muted">
        Behaviour per cohort, participant, harness and task type, computed from run files and board records.
        Counts are behaviour, not scientific value. <span className="unavailable">unavailable</span> means not reported, never zero.
      </p>
      {data && (
        <div className="filters" role="group" aria-label="Filters">
          {select("cohort", "Cohort", data.options.cohorts.map((c) => ({ value: c.id, label: c.name })))}
          {select("participant", "Participant", data.options.participants.map((p) => ({ value: p.id, label: p.name })))}
          {select("harness", "Harness", data.options.harnesses.map((h) => ({ value: h, label: h })))}
          {select("task_type", "Task type", data.options.task_types.map((t) => ({ value: t, label: t })))}
          <label>
            Trend by{" "}
            <select value={params.get("bucket") ?? "week"} onChange={(e) => set("bucket", e.target.value === "week" ? "" : e.target.value)}>
              <option value="week">week</option>
              <option value="day">day</option>
            </select>
          </label>
        </div>
      )}
      <Status state={state} />
      {data && (
        <>
          {data.projection.stale + data.projection.missing > 0 && (
            <p className="muted small" role="note">
              {data.projection.stale + data.projection.missing} of {data.projection.runs} runs computed in memory. {data.projection.note}
            </p>
          )}
          <Summary g={data.summary} />
          <div className="tabs" role="tablist" aria-label="Group panels by">
            {DIMENSIONS.map(([key, label]) => (
              <button key={key} role="tab" aria-selected={dimension === key} className={dimension === key ? "active" : ""}
                onClick={() => setDimension(key)}>
                {label} <span className="muted small">{data.panels[key].length}</span>
              </button>
            ))}
          </div>
          <div role="tabpanel"><Panels groups={data.panels[dimension]} /></div>
          <h2>Cost</h2>
          <p className="muted small">
            Tokens from harness telemetry where reported; currency only from an operator price table.
            Pricing: {data.pricing.available ? data.pricing.currency : data.pricing.reason}.
          </p>
          <CostTable groups={[data.summary, ...data.panels[dimension]]} currency={data.pricing.currency ?? null} />
        </>
      )}
      <CohortCompare cohorts={cohorts.data?.items ?? []} />
      {data && (
        <details className="limits">
          <summary>Limitations</summary>
          <ul>{data.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </details>
      )}
    </section>
  );
}
