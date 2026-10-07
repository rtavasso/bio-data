import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { query } from "../api";
import { Status } from "../components/Status";
import CohortCompare, { CostCell } from "../components/dashboard/CohortCompare";
import { ReuseBars, Sparkline, Value, ratioText } from "../components/dashboard/Charts";
import type { DialogueStats, FrontierClosure, CohortSummary, Dashboard as DashboardData, Dimension, Group, Num } from "../types/dashboard";
import { HygieneTable, SnapshotCitationsPanel } from "../components/dashboard/Publishing";
import { EconomicsTable, SkillsTable, UsefulDataTable, economicsRows } from "../components/dashboard/Economics";
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
      <Stat label="Suspensions" hint="Runs whose wall or monotonic clock was not recorded are left out (unavailable, not zero)">
        <Value value={g.suspensions} /> <span className="muted small">(<Value value={g.suspended_hours} digits={2} /> h)</span>
        {g.clock_unavailable_runs ? <span className="muted small"> · {g.clock_unavailable_runs} without clocks</span> : null}
      </Stat>
      <Stat label="Minutes per executed analysis"><Value value={g.minutes_per_executed_analysis} /></Stat>
      <Stat label="Analyses (failed)"><Value value={g.analysis_receipts} /> (<Value value={g.analysis_failures} />)</Stat>
      <Stat label="Tool / inbox calls"><Value value={g.tool_calls} /> / <Value value={g.inbox_calls} /></Stat>
      {g.agent_reads && (
        <Stat label="Inbox / search / overview per turn" hint="Community reads per delivery, from captured commands (V11)">
          <Value value={g.agent_reads.inbox_calls_per_turn} /> / <Value value={g.agent_reads.forum_searches_per_turn} /> / <Value value={g.agent_reads.overview_calls_per_turn} />
        </Stat>
      )}
      <Stat label="Plumbing share">{ratioText(g.plumbing_share)}</Stat>
      <Stat label="Compactions (fallbacks)" hint="Harnesses whose stream does not mark compactions are unavailable, not zero">
        <Value value={g.compactions} /> (<Value value={g.compaction_fallbacks} />)
        {g.compaction_unavailable_runs ? <span className="muted small"> · {g.compaction_unavailable_runs} runs unavailable</span> : null}
      </Stat>
      <Stat label="Ceremony tail, median min" hint="Minutes after the last successful analysis">
        <Value value={g.ceremony_tail_minutes.median} digits={1} />
      </Stat>
      <Stat label="Reuse backed">{ratioText(g.board.reuse.backed_ratio)} <span className="muted small">({g.board.reuse.backed}/{g.board.reuse.backed + g.board.reuse.unbacked})</span></Stat>
      <Stat label="Human marks per post"><Value value={g.board.human_marks_per_post} /></Stat>
      <Stat label="Provider-citation hits"><Value value={g.provider_citation_finals} /> finals · {g.board.provider_citation_posts} posts</Stat>
      <Stat label="Numbers pointed at the number" hint="Share of numbers in finals with a line, claim or cell pointer (C11)">
        {ratioText(g.board.numbers?.number_level_share ?? null)}
        {g.board.numbers && <span className="muted small"> ({g.board.numbers.number_level}/{g.board.numbers.numbers})</span>}
      </Stat>
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
        <dt>Analyses (failed)</dt><dd><Value value={g.analysis_receipts} /> (<Value value={g.analysis_failures} />)</dd>
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

// C11/V1: per cohort, the share of numbers in finals with the author's pointer at the number (cell, claim, line or
// text scope), beside people's curated pointers (G2, never the author's) and the unpointed numbers (covered only by
// the post's evidence list, or by nothing). Author-verified counts cell, claim and line pointers; a text match (B6)
// and curated pointers are shown apart.
function NumberCoverageTable({ groups }: { groups: Group[] }) {
  const rows = groups.filter((g) => g.board.numbers !== undefined);
  return (
    <div className="compare-scroll">
      <table className="coverage-table" aria-label="Number coverage">
        <thead>
          <tr>
            <th scope="col">Group</th><th scope="col">Finals</th><th scope="col">Numbers</th>
            <th scope="col">Author pointer at the number</th><th scope="col">cell / claim / line / text</th>
            <th scope="col">Author-verified</th><th scope="col">Curated pointers</th>
            <th scope="col">Post's evidence only</th><th scope="col">Unpointed</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((g) => {
            const n = g.board.numbers;
            return (
              <tr key={g.key}>
                <th scope="row">{g.label}</th>
                {n ? (
                  <>
                    <td>{n.finals}</td><td>{n.numbers}</td>
                    <td>{ratioText(n.number_level_share)} <span className="muted small">({n.number_level})</span></td>
                    <td>{n.scopes.cell} / {n.scopes.claim} / {n.scopes.line} / {n.scopes.text ?? 0}</td>
                    <td>{ratioText(n.verified_share)} <span className="muted small">({n.author_verified ?? n.statuses.verified}; {n.statuses.unverified} unverified{n.text_verified ? `; ${n.text_verified} text matches apart` : ""})</span></td>
                    <td>{n.pointers?.curated ?? 0} <span className="muted small">({n.curated_verified ?? 0} verified; a person's, not the author's)</span></td>
                    <td>{n.statuses.post_scoped}</td>
                    <td>{n.statuses.unpointed}{n.pointers?.unlocatable ? <span className="muted small"> ({n.pointers.unlocatable} marked unlocatable)</span> : null}</td>
                  </>
                ) : <td colSpan={8}><span className="unavailable">unavailable</span> <span className="muted small">no final in this group</span></td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// V1: claims-first authoring per cohort. Claims per post, the share of evidence-carrying posts that state claims,
// refused final-answer claims blocks, the scope split of claim pointers, and the share of numbers in finals pointed
// at a claim or a cell (from the number coverage above).
function ClaimsAuthoringTable({ groups }: { groups: Group[] }) {
  const rows = groups.filter((g) => g.board.authoring);
  if (!rows.length) return null;
  return (
    <div className="compare-scroll">
      <table className="coverage-table" aria-label="Claims authoring">
        <thead>
          <tr>
            <th scope="col">Group</th><th scope="col">Claims per post</th><th scope="col">Posts with evidence and claims</th>
            <th scope="col">Refused claims blocks</th><th scope="col">Pointer scopes cell / key / line / record</th>
            <th scope="col">Numbers at a claim</th><th scope="col">Numbers at a cell</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((g) => {
            const a = g.board.authoring!;
            const s = a.pointer_scopes;
            return (
              <tr key={g.key}>
                <th scope="row">{g.label}</th>
                <td><Value value={a.claims_per_post} /> <span className="muted small">({a.claims}/{a.posts})</span></td>
                <td>{ratioText(a.evidence_posts_with_claims_share)} <span className="muted small">({a.evidence_posts_with_claims}/{a.evidence_posts})</span></td>
                <td>{a.claims_refused}</td>
                <td>{s.cell} / {s.key} / {s.line} / {s.record}{s.invalid ? <span className="muted small"> ({s.invalid} free-text)</span> : null}</td>
                <td>{ratioText(g.board.numbers?.claim_share ?? null)}</td>
                <td>{ratioText(g.board.numbers?.cell_share ?? null)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// V3 G1: frontier-first closure. Non-withdrawn items per completed question by kind, and finals that state a next
// step whose author recorded a matching (non-gap) item.
function FrontierClosurePanel({ f }: { f: FrontierClosure }) {
  return (
    <div className="compare-scroll">
      <table className="coverage-table" aria-label="Frontier closure">
        <thead>
          <tr><th scope="col">Kind</th><th scope="col">Items</th><th scope="col">Per completed question</th></tr>
        </thead>
        <tbody>
          {Object.entries(f.items_by_kind).map(([kind, n]) => (
            <tr key={kind}>
              <th scope="row">{kind.replace(/_/g, " ")}</th><td>{n}</td>
              <td><Value value={f.items_per_completed_question[kind] ?? null} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        {f.completed_with_non_gap_item} of {f.completed_questions} completed questions record an item beyond gaps
        ({ratioText(f.completed_with_non_gap_share)}); {f.finals_next_step_matched} of {f.finals_stating_next_step} finals
        stating a next step have a matching item ({ratioText(f.finals_next_step_matched_share)}).
      </p>
    </div>
  );
}

// V3 V12: dialogue at anchors. Threads per post, replies per thread, the author's replies, and ledger claims on a
// thread that a later post withdrew.
function DialoguePanel({ d }: { d: DialogueStats }) {
  return (
    <div className="compare-scroll">
      <table className="coverage-table" aria-label="Dialogue">
        <tbody>
          <tr><th scope="row">Threads</th><td>{d.threads}</td></tr>
          <tr><th scope="row">Threads per post (posts with a thread)</th><td><Value value={d.threads_per_post} /></td></tr>
          <tr><th scope="row">Replies per thread</th><td><Value value={d.replies_per_thread} /></td></tr>
          <tr><th scope="row">Threads the author replied in</th><td>{d.threads_with_author_reply} ({d.author_replies} replies)</td></tr>
          <tr><th scope="row">Opened by a disputed mark</th><td>{d.opened_by_dispute}</td></tr>
          <tr>
            <th scope="row">Claims changed after a thread</th>
            <td>{d.claims_changed_after_thread} of {d.claims_on_threads} ({ratioText(d.claims_changed_share)})</td>
          </tr>
        </tbody>
      </table>
      <p className="muted small">{d.note}</p>
    </div>
  );
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
          <h2>Number coverage</h2>
          <p className="muted small">
            Numbers in finals (answers of research deliveries), checked by the write-up checker: a pointer at the number
            (cell, claim or line scope) can be verified against its record; the post's evidence list alone cannot.
          </p>
          <NumberCoverageTable groups={[data.summary, ...data.panels.cohort]} />
          <h2>Compaction hygiene by harness</h2>
          <p className="muted small">
            Per harness: compaction summaries and fallbacks from session databases, summaries that name neither the
            request post nor the assignment key, and the input context the stream reports per call (or per turn).
          </p>
          <HygieneTable groups={[data.summary, ...data.panels.harness]} />
          <h2>Turn economics</h2>
          <p className="muted small">
            Per delivery (turn_economics records): context tokens per call or per turn, where the context came from
            (bytes by source), compactions and fallbacks (a marker match), minutes of model generation against tool
            wait, help and re-orientation calls, and the ceremony tail after the last successful analysis.
          </p>
          <h3>By harness</h3>
          <EconomicsTable label="Harness" rows={economicsRows([data.summary, ...data.panels.harness])} />
          {data.economics && (
            <>
              <h3>By skill version</h3>
              <p className="muted small">A skill version is the digest of the skill text staged for the turn; turns captured
                before it was recorded are "unrecorded".</p>
              <EconomicsTable label="Skill version" rows={data.economics.skill_versions.map((p) => ({
                key: p.key, label: `${p.label}${p.harnesses.length ? ` (${p.harnesses.join(", ")})` : ""}`, e: p.turn_economics }))} />
              <h3>Skills</h3>
              <p className="muted small">Skill text (SKILL.md and references) against its byte budget; a skill that grows must
                show a metric it moves.</p>
              <SkillsTable economics={data.economics} />
            </>
          )}
          <h3>Cost per useful datum</h3>
          <UsefulDataTable rows={economicsRows([data.summary, ...data.panels.harness])} />
          <h2>Claims authoring</h2>
          <p className="muted small">
            Ledger claims written by authors (the platform never writes one): per post, on posts that publish evidence,
            and where their pointers point. Target for the next cohort: every published analysis carries claims, and more
            than half of numbers in finals point at a claim, cell or line.
          </p>
          <ClaimsAuthoringTable groups={[data.summary, ...data.panels.cohort]} />
          {data.frontier && (
            <>
              <h2>Frontier closure</h2>
              <p className="muted small">
                Open items authors recorded (the platform never writes one), per completed question. Target for the
                next cohort: at least one item beyond retrieval gaps per completed question.
              </p>
              <FrontierClosurePanel f={data.frontier} />
            </>
          )}
          {data.dialogue && (
            <>
              <h2>Dialogue at anchors</h2>
              <p className="muted small">
                A person's comment at an anchor and the author's replies form a thread; a disputed mark on a claim opens
                one. A reply resolves nothing by itself.
              </p>
              <DialoguePanel d={data.dialogue} />
            </>
          )}
          <h2>Cost</h2>
          <p className="muted small">
            Tokens from harness telemetry where reported; currency only from an operator price table.
            Pricing: {data.pricing.available ? data.pricing.currency : data.pricing.reason}.
          </p>
          <CostTable groups={[data.summary, ...data.panels[dimension]]} currency={data.pricing.currency ?? null} />
        </>
      )}
      <CohortCompare cohorts={cohorts.data?.items ?? []} />
      <SnapshotCitationsPanel />
      {data && (
        <details className="limits">
          <summary>Limitations</summary>
          <ul>{data.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </details>
      )}
    </section>
  );
}
