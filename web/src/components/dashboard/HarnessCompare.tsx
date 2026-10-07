import { useState } from "react";
import { query } from "../../api";
import type { CohortSummary, HarnessCells, HarnessComparison } from "../../types/dashboard";
import { useApi } from "../../useApi";
import { Status } from "../Status";
import { Value } from "./Charts";
import { CostCell } from "./CohortCompare";

// Spec v3 V17: the multi-harness comparison the long-term runtime decision is taken from. One column per
// harness, one row per criterion; each cell stands alone. There is deliberately no composite score, rank or
// winner. A harness is "live" only when a passing live harness-check receipt for it exists.

const ROWS: [string, (c: HarnessCells) => React.ReactNode][] = [
  ["Yield", (c) => (
    <>posts {c.yield.posts}<br />artifacts {c.yield.registered_artifacts}<br />
      analyses <Value value={c.yield.analysis_receipts} /> (<Value value={c.yield.analysis_failures} /> failed)<br />
      <span className="muted small">runs {c.yield.completed_runs} completed, {c.yield.failed_runs} failed</span></>
  )],
  ["Calibration", (c) => c.calibration === null ? <span className="unavailable">unavailable (no ledger claims)</span> : (
    <>supported {c.calibration.supported}<br />untestable {c.calibration.untestable}<br />
      <span className="muted small">descriptive {c.calibration.descriptive} · withdrawn {c.calibration.withdrawn}</span></>
  )],
  ["Corrections", (c) => (
    <>corrections {c.corrections.corrections}<br />superseded {c.corrections.posts_superseded}<br />
      human marks {c.corrections.human_marks}</>
  )],
  ["Compaction hygiene", (c) => {
    const h = c.compaction_hygiene;
    return (
      <>stream compactions <Value value={h.stream_compactions} /><br />
        summaries <Value value={h.compaction_summaries} /> (fallbacks <Value value={h.compaction_fallbacks} />)<br />
        missing the assignment <Value value={h.summaries_missing_assignment} /><br />
        <span className="muted small">context mean <Value value={h.context_mean_input_tokens} />
          {h.context_unit ? ` per ${h.context_unit}` : ""}</span></>
    );
  }],
  ["Turn economics", (c) => {
    const e = c.turn_economics;
    return (
      <>recorded {e.recorded_runs} of {e.runs} turns<br />
        context mean <Value value={e.context.mean_input_tokens} /> tokens<br />
        tool wait share <Value value={e.time.tool_wait_share} /><br />
        <span className="muted small">help / re-orientation per turn <Value value={e.orientation.help_calls_per_turn} /> / <Value
          value={e.orientation.reorientation_calls_per_turn} /></span></>
    );
  }],
  ["Cost", (c) => <CostCell cost={c.cost} />],
];

export function HarnessTable({ value }: { value: HarnessComparison }) {
  return (
    <div className="compare-scroll">
      <table className="compare harness-compare" aria-label="Harness comparison">
        <thead>
          <tr>
            <th scope="col">Criterion</th>
            {value.harnesses.map((h) => (
              <th key={h.harness} scope="col" className="cohort-head">
                {h.harness}
                <div className="small">
                  {h.live.live ? <span className="badge badge-good">live</span>
                    : <span className="muted">not live: {h.live.reason}</span>}
                </div>
                {h.cells && <div className="muted small">{h.cells.models.join(", ")} · {h.cells.runs} runs</div>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map(([name, render]) => (
            <tr key={name}>
              <th scope="row">{name}</th>
              {value.harnesses.map((h) => (
                <td key={h.harness}>{h.cells ? render(h.cells) : <span className="not-attempted">no runs in scope</span>}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function HarnessCompare({ cohorts }: { cohorts: CohortSummary[] }) {
  const [picked, setPicked] = useState<string[]>([]);
  const result = useApi<HarnessComparison>(`/api/harnesses/compare${query({ cohorts: picked.join(",") || undefined })}`);
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const value = result.data;
  return (
    <section className="compare-section" aria-labelledby="harness-compare-title">
      <h2 id="harness-compare-title">Compare harnesses</h2>
      <p className="muted">
        One column per harness over every run, or over the cohorts picked below. Yield, calibration, corrections,
        compaction hygiene, turn economics and cost stay in separate cells. No composite score. A harness is live
        only when a passing live harness-check receipt exists for it.
      </p>
      {cohorts.length > 0 && (
        <fieldset className="cohort-picks">
          <legend>Cohorts (optional)</legend>
          {cohorts.map((c) => (
            <label key={c.id}>
              <input type="checkbox" checked={picked.includes(c.id)} onChange={() => toggle(c.id)} />
              {c.name}
            </label>
          ))}
        </fieldset>
      )}
      <Status state={result} />
      {value?.harnesses && (
        value.harnesses.length === 0 ? <p className="muted">No runs in scope.</p> : (
          <>
            <p className="muted small">
              {value.live_comparison ? `Live harnesses with runs: ${value.live_harnesses.join(", ")}.`
                : "Not a live comparison: fewer than two harnesses with runs have a passing live receipt."} {value.note}
            </p>
            <HarnessTable value={value} />
          </>
        )
      )}
    </section>
  );
}
