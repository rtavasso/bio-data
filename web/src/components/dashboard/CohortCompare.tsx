import { useState } from "react";
import { query } from "../../api";
import type { CohortSummary, CompareCell, Comparison, Cost } from "../../types/dashboard";
import { useApi } from "../../useApi";
import { Status } from "../Status";
import { Untrusted } from "../Untrusted";
import { Value } from "./Charts";

// M9.3: the same assignment across cohorts, side by side. Criteria stay in separate columns;
// there is deliberately no composite score, rank or winner.

const CRITERIA = ["Yield", "Calibration", "Corrections", "Cost"] as const;

export function CostCell({ cost }: { cost: Cost }) {
  const t = cost.tokens;
  if (cost.runs === 0) return <div className="cost-cell muted">no runs in scope</div>;
  return (
    <div className="cost-cell">
      <div>tokens in <Value value={t.input_tokens} /> · cached <Value value={t.cached_input_tokens} /> · out <Value value={t.output_tokens} /></div>
      {t.input_tokens === null && t.input_tokens_partial !== null && (
        <div className="muted small">partial: {t.input_tokens_partial} in / {t.output_tokens_partial ?? "?"} out over {cost.token_reported_runs} of {cost.runs} runs</div>
      )}
      <div>compute <Value value={cost.compute_hours} digits={3} unit=" h" /></div>
      <div>
        cost {cost.amount === null ? <span className="unavailable">unavailable</span> : <span className="num">{cost.amount.toFixed(4)} {cost.currency}</span>}
        {cost.amount === null && cost.amount_partial !== null && (
          <span className="muted small"> (partial {cost.amount_partial.toFixed(4)} {cost.currency} over {cost.priced_runs} of {cost.runs} runs)</span>
        )}
      </div>
    </div>
  );
}

function Cells({ cell }: { cell: CompareCell | null | undefined }) {
  if (!cell) {
    return <td colSpan={CRITERIA.length} className="not-attempted">not attempted by this cohort</td>;
  }
  const c = cell.calibration;
  return (
    <>
      <td>
        posts {cell.yield.posts}<br />artifacts {cell.yield.registered_artifacts}<br />
        analyses <Value value={cell.yield.analysis_receipts} /> (<Value value={cell.yield.analysis_failures} /> failed)
      </td>
      <td>
        {c === null ? <span className="unavailable">unavailable (no ledger claims)</span> : (
          <>supported {c.supported}<br />untestable {c.untestable}<br />
            <span className="muted small">descriptive {c.descriptive} · withdrawn {c.withdrawn}</span></>
        )}
      </td>
      <td>
        corrections {cell.corrections.corrections}<br />superseded {cell.corrections.posts_superseded}<br />
        human marks {cell.corrections.human_marks}
      </td>
      <td><CostCell cost={cell.cost} /></td>
    </>
  );
}

export function ComparisonTable({ value }: { value: Comparison }) {
  return (
    <div className="compare-scroll">
      <table className="compare">
        <thead>
          <tr>
            <th rowSpan={2} scope="col">Assignment</th>
            {value.cohorts.map((c) => (
              <th key={c.id} colSpan={CRITERIA.length} scope="colgroup" className="cohort-head">
                {c.name}
                <div className="muted small">{c.harnesses.join(", ")} · {c.models.join(", ")} · {c.runs} runs</div>
              </th>
            ))}
          </tr>
          <tr>
            {value.cohorts.map((c) => CRITERIA.map((name) => <th key={c.id + name} scope="col">{name}</th>))}
          </tr>
        </thead>
        <tbody>
          {value.assignments.map((row) => (
            <tr key={row.key}>
              <th scope="row" className="assignment">
                <Untrusted><span className="excerpt">{row.excerpt}</span></Untrusted>
                <code className="small">{row.source === "explicit" ? row.key : row.key.slice(0, 12)}</code>
              </th>
              {value.cohorts.map((c) => <Cells key={c.id} cell={row.cells[c.id]} />)}
            </tr>
          ))}
          <tr className="totals">
            <th scope="row">All runs in cohort</th>
            {value.cohorts.map((c) => <Cells key={c.id} cell={value.totals[c.id]} />)}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export default function CohortCompare({ cohorts }: { cohorts: CohortSummary[] }) {
  const [picked, setPicked] = useState<string[]>([]);
  const path = picked.length >= 2 ? `/api/cohorts/compare${query({ ids: picked.join(",") })}` : null;
  const result = useApi<Comparison>(path);
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  return (
    <section className="compare-section" aria-labelledby="compare-title">
      <h2 id="compare-title">Compare cohorts</h2>
      <p className="muted">
        Pick two or more cohorts. Runs are grouped by assignment (an explicit key or the request body hash);
        yield, calibration, corrections and cost stay in separate columns. No composite score.
      </p>
      {cohorts.length < 2 && <p className="muted">At least two cohorts are needed: <code>bio commons cohort create</code>.</p>}
      <fieldset className="cohort-picks">
        <legend>Cohorts</legend>
        {cohorts.map((c) => (
          <label key={c.id}>
            <input type="checkbox" checked={picked.includes(c.id)} onChange={() => toggle(c.id)} />
            {c.name} <span className="muted small">({c.runs} runs, {c.assignments} assignments)</span>
          </label>
        ))}
      </fieldset>
      {path && <Status state={result} />}
      {path && result.data && (
        <>
          <p className="muted small">{result.data.shared_assignments} assignment(s) attempted by every selected cohort. {result.data.note}</p>
          <ComparisonTable value={result.data} />
        </>
      )}
    </section>
  );
}
