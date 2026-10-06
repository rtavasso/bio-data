import { Untrusted } from "../Untrusted";
import type { GapReport } from "../../types/observatory-map";

// Retrieval gaps with `daw.gaps` semantics: active gaps grouped by source and key; withdrawn and corrected
// reports are kept and shown separately, never ranked as observed failures.

const text = (value: unknown) => (typeof value === "string" ? value : value === undefined ? "" : JSON.stringify(value));

export default function Gaps({ report }: { report: GapReport }) {
  const empty = !report.groups.length && !report.withdrawn_events.length && !report.corrections_requiring_review.length
    && !report.unstructured_events.length;
  if (empty) return <p className="muted">No retrieval gaps are recorded for this question.</p>;
  return (
    <Untrusted>
      {report.groups.map((group) => (
        <div key={`${group.source_or_format}:${group.gap_key}`} className="q-gap">
          <strong>{group.gap_key}</strong> <span className="muted">{group.source_or_format} · {group.observations} report(s)</span>
          {group.examples.map((example) => (
            <dl key={example.event} className="q-summary">
              <div><dt>desired</dt><dd>{text(example.payload.desired_information)}</dd></div>
              <div><dt>why tools failed</dt><dd>{text(example.payload.why_current_tools_failed)}</dd></div>
              {example.payload.possible_indexing_solution !== undefined && (
                <div><dt>possible solution</dt><dd>{text(example.payload.possible_indexing_solution)}</dd></div>
              )}
              <div><dt>event</dt><dd className="mono">{example.event}</dd></div>
            </dl>
          ))}
        </div>
      ))}
      {report.withdrawn_events.map((gap) => (
        <div key={gap.event} className="q-gap withdrawn">
          <span className="obs-chip">withdrawn</span> <span className="mono">{gap.event}</span>
          {gap.withdrawals.map((w) => <p key={w.event} className="muted">Reason: {text(w.payload.reason)}</p>)}
        </div>
      ))}
      {report.corrections_requiring_review.map((gap) => (
        <div key={gap.event} className="q-gap">
          <span className="obs-chip warn">corrected; review</span> <span className="mono">{gap.event}</span>
        </div>
      ))}
      {report.unstructured_events.map((gap) => (
        <p key={gap.event} className="muted">Unstructured gap note <span className="mono">{gap.event}</span>: {gap.reason}</p>
      ))}
    </Untrusted>
  );
}
