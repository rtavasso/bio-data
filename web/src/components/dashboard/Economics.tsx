import type { Economics, Group, Num, SkillRow, TurnEconomics } from "../../types/dashboard";
import { Value, ratioText } from "./Charts";

// Spec v3 V13: turn economics per harness and per skill version, the skills' text size against its budget with
// reads per turn, and tokens per useful datum. Every value is also text; null renders "unavailable", never zero.

const COMPONENTS: [keyof TurnEconomics["composition"]["bytes_measured"], string][] = [
  ["system_prompt", "system prompt"], ["delivery_prompt", "delivery prompt"], ["skills", "skills"],
  ["tool_outputs", "tool outputs"], ["summaries", "summaries"], ["conversation", "conversation"],
];

function kib(value: Num): string | null {
  return value === null ? null : `${(value / 1024).toFixed(value >= 10240 ? 0 : 1)} KiB`;
}

// Generation versus tool wait as two bars on one scale (minutes), labelled directly.
function TimeBars({ e, max }: { e: TurnEconomics; max: number }) {
  const { generation_minutes: generation, tool_wait_minutes: wait } = e.time;
  if (generation === null || wait === null) return <span className="unavailable">unavailable</span>;
  const top = Math.max(max, 1);
  const rows: [string, number, string][] = [["generation", generation, "viz-1"], ["tool wait", wait, "viz-2"]];
  return (
    <svg className="bars" viewBox="0 0 160 40" role="img"
      aria-label={`Generation ${generation} min, tool wait ${wait} min`}>
      {rows.map(([name, minutes, tone], i) => (
        <g key={name} transform={`translate(0 ${i * 20})`}>
          <text x={0} y={12} className="bar-label">{name}</text>
          <rect x={58} y={3} width={70} height={12} rx={2} className="track" />
          {minutes > 0 && <rect x={58} y={3} width={Math.max((minutes / top) * 70, 4)} height={12} rx={2} className={tone}>
            <title>{`${name}: ${minutes} min`}</title></rect>}
          <text x={160} y={12} className="bar-value" textAnchor="end">{Math.round(minutes)}</text>
        </g>
      ))}
    </svg>
  );
}

function Composition({ e }: { e: TurnEconomics }) {
  const c = e.composition;
  const parts = COMPONENTS.map(([key, label]) => {
    const share = c.shares ? c.shares[key] : null;
    const bytes = kib(c.bytes_measured[key]);
    return `${label} ${share !== null && share !== undefined ? ratioText(share) : bytes ?? "unmeasured"}`;
  });
  return <span className="small">{parts.join(" · ")}{c.shares ? "" : " (bytes; shares need every source measured)"}</span>;
}

function Row({ label, e, max }: { label: string; e: TurnEconomics | undefined; max: number }) {
  if (!e) return <tr><th scope="row">{label}</th><td colSpan={7}><span className="unavailable">unavailable</span></td></tr>;
  return (
    <tr>
      <th scope="row">{label}</th>
      <td>{e.recorded_runs} of {e.runs}{e.reindexed_runs ? <span className="muted small"> ({e.reindexed_runs} reindexed)</span> : null}</td>
      <td><Value value={e.context.mean_input_tokens} digits={0} />{e.context.unit && <span className="muted small"> per {e.context.unit}</span>}</td>
      <td><Composition e={e} /></td>
      <td><Value value={e.compactions.stream_markers} /> · <Value value={e.compactions.summaries} /> (<Value value={e.compactions.fallbacks} />)</td>
      <td><TimeBars e={e} max={max} /></td>
      <td><Value value={e.orientation.help_calls_per_turn} /> / <Value value={e.orientation.reorientation_calls_per_turn} /></td>
      <td><Value value={e.ceremony_tail_minutes.median} digits={1} /></td>
    </tr>
  );
}

export function EconomicsTable({ rows, label }: { rows: { key: string; label: string; e: TurnEconomics | undefined }[]; label: string }) {
  if (!rows.length) return <p className="muted">No runs in scope.</p>;
  const max = Math.max(1, ...rows.flatMap((r) => [r.e?.time.generation_minutes ?? 0, r.e?.time.tool_wait_minutes ?? 0]));
  return (
    <div className="compare-scroll">
      <table className="coverage-table" aria-label={label}>
        <thead>
          <tr>
            <th scope="col">{label}</th><th scope="col">Runs recorded</th><th scope="col">Context tokens</th>
            <th scope="col">Context sources</th>
            <th scope="col">Compactions · summaries (fallbacks, marker match)</th>
            <th scope="col">Generation vs tool wait, min</th><th scope="col">Help / re-orientation calls per turn</th>
            <th scope="col">Ceremony tail, median min</th>
          </tr>
        </thead>
        <tbody>{rows.map((r) => <Row key={r.key} label={r.label} e={r.e} max={max} />)}</tbody>
      </table>
    </div>
  );
}

export function UsefulDataTable({ rows }: { rows: { key: string; label: string; e: TurnEconomics | undefined }[] }) {
  return (
    <div className="compare-scroll">
      <table className="coverage-table" aria-label="Cost per useful datum">
        <thead>
          <tr>
            <th scope="col">Group</th><th scope="col">Tokens (runs reporting)</th>
            <th scope="col">Per registered artifact</th><th scope="col">Per claim with a verified pointer</th>
            <th scope="col">Per frontier item later promoted</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ key, label, e }) => (
            <tr key={key}>
              <th scope="row">{label}</th>
              {e ? (
                <>
                  <td><Value value={e.tokens} /> <span className="muted small">({e.tokens_reported_runs} of {e.runs})</span></td>
                  <td><Value value={e.tokens_per.registered_artifact} digits={0} /> <span className="muted small">({e.useful_data.registered_artifacts ?? "—"})</span></td>
                  <td><Value value={e.tokens_per.verified_claim} digits={0} /> <span className="muted small">({e.useful_data.verified_claims ?? "—"})</span></td>
                  <td><Value value={e.tokens_per.promoted_frontier_item} digits={0} /> <span className="muted small">({e.useful_data.promoted_frontier_items ?? "—"})</span></td>
                </>
              ) : <td colSpan={4}><span className="unavailable">unavailable</span></td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Skill text size against its budget (one bar: the track is the budget), and how often a turn reads it.
function SizeBar({ row }: { row: SkillRow }) {
  if (row.bytes === null) return <span className="unavailable">not in this checkout</span>;
  const budget = row.budget ?? row.bytes;
  const width = Math.min(1, row.bytes / Math.max(budget, 1)) * 100;
  return (
    <svg className="bars" viewBox="0 0 160 20" role="img" aria-label={`${row.bytes} of ${row.budget ?? "no"} budget bytes`}>
      <rect x={0} y={3} width={100} height={12} rx={2} className="track" />
      <rect x={0} y={3} width={Math.max(width, 2)} height={12} rx={2} className="viz-1">
        <title>{`${row.skill}: ${row.bytes} bytes of ${row.budget ?? "no"} budget`}</title></rect>
      <text x={160} y={12} className="bar-value" textAnchor="end">{kib(row.bytes)}</text>
    </svg>
  );
}

export function SkillsTable({ economics }: { economics: Economics }) {
  const { skills } = economics;
  return (
    <div className="compare-scroll">
      <table className="coverage-table" aria-label="Skill sizes and reads">
        <thead>
          <tr><th scope="col">Skill</th><th scope="col">Text size against budget</th><th scope="col">Bytes / budget</th>
            <th scope="col">Reads per turn <span className="muted small">({skills.runs} turns)</span></th></tr>
        </thead>
        <tbody>
          {skills.items.map((row) => (
            <tr key={row.skill}>
              <th scope="row">{row.skill}</th>
              <td><SizeBar row={row} /></td>
              <td><Value value={row.bytes} /> / <Value value={row.budget} /></td>
              <td><Value value={row.reads_per_turn} /> <span className="muted small">(<Value value={row.reads} />)</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function economicsRows(groups: Group[]) {
  return groups.map((g) => ({ key: g.key, label: g.label, e: g.turn_economics }));
}
