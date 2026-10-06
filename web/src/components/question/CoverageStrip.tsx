import { useState } from "react";
import { Untrusted } from "../Untrusted";
import type { CoverageTable } from "../../types/observatory-map";
import { Origins } from "./NetworkView";

// Evidence coverage as a heat strip: one cell per row, an ordinal blue ramp for inspection progress.
// "unavailable" is a recorded outcome (hatched neutral); a blank cell and a missing cell are shown as
// different things, and every cell keeps its text.

export const ORDER = ["not_searched", "searched", "located", "inspected", "analyzed"];

function Cell({ value }: { value: string | null }) {
  if (value === null) return <span className="obs-missing">missing</span>;
  if (value === "") return <span className="obs-missing">blank</span>;
  return <>{value}</>;
}

export function statusClass(value: string | null): string {
  if (value === null) return "cov-missing";
  if (value === "") return "cov-blank";
  if (value === "unavailable") return "cov-unavailable";
  const step = ORDER.indexOf(value);
  return step >= 0 ? `cov-step-${step + 1}` : "cov-other";
}

export default function CoverageStrip({ tables }: { tables: CoverageTable[] }) {
  const [index, setIndex] = useState(tables.length - 1);
  const table = tables[Math.min(index, tables.length - 1)];
  if (!table) return <p className="muted">No evidence-coverage table was recorded for this question.</p>;
  const status = table.columns.indexOf("inspection_status");
  const edges = table.columns.indexOf("edge_ids");
  return (
    <div>
      {tables.length > 1 && (
        <div className="q-revisions" role="group" aria-label="Coverage table">
          {tables.map((t, i) => (
            <button key={t.sha256} type="button" aria-pressed={i === index} onClick={() => setIndex(i)}>{t.name}</button>
          ))}
        </div>
      )}
      <p className="mono muted">{table.name} · {table.sha256.slice(0, 16)}…</p>
      <Origins origins={table.origins} preserved={table.preserved} />
      {status < 0 && <p className="muted">No inspection_status column; the strip cannot be drawn. The table is shown as given.</p>}
      {status >= 0 && (
        <div className="viz">
          <ol className="cov-strip" aria-label="Inspection status per coverage row">
            {table.rows.map((row) => {
              const value = row.cells[status];
              return (
                <li key={row.line} className={statusClass(value)}
                  title={`line ${row.line}: ${edges >= 0 ? row.cells[edges] ?? "missing" : ""} · ${value === null ? "missing" : value || "blank"}`}>
                  <span>{value === null ? "missing" : value || "blank"}</span>
                </li>
              );
            })}
          </ol>
          <p className="muted cov-key">
            Ramp: {ORDER.join(" → ")}. Hatched: unavailable (recorded). Outlined: blank or missing cell. Status describes
            work on a file, not support for an edge.
          </p>
        </div>
      )}
      {table.issues.map((issue) => <p key={issue} className="muted">Note: {issue}</p>)}
      <Untrusted>
        <div className="table-scroll">
          <table className="obs-table">
            <thead><tr><th>line</th>{table.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>
              {table.rows.map((row) => (
                <tr key={row.line}>
                  <td className="muted">{row.line}</td>
                  {row.cells.map((cell, i) => <td key={i}><Cell value={cell} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Untrusted>
    </div>
  );
}
