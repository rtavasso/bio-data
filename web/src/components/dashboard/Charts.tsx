import type { Num } from "../../types/dashboard";

// Handwritten SVG marks for the dashboard. Every chart has a text equivalent nearby (a value or
// a table), so identity and magnitude never depend on colour alone. `null` renders as
// "unavailable", never as zero.

export function Value({ value, digits = 2, unit = "" }: { value: Num | undefined; digits?: number; unit?: string }) {
  if (value === null || value === undefined) return <span className="unavailable">unavailable</span>;
  const text = Number.isInteger(value) ? String(value) : value.toFixed(digits);
  return <span className="num">{text}{unit}</span>;
}

export function ratioText(value: Num): string {
  return value === null ? "unavailable" : `${Math.round(value * 100)}%`;
}

const W = 160;
const H = 48;
const PAD = 6;

// One series per facet; the facet title names it, so no legend. Shared `max` keeps small multiples comparable.
export function Sparkline<T extends { bucket: string }>({ points, value, max, label, unit = "" }: {
  points: T[]; value: (point: T) => Num; max: number; label: string; unit?: string;
}) {
  const known = points.filter((p) => value(p) !== null);
  if (known.length === 0) {
    return <p className="spark-empty">{label}: <span className="unavailable">unavailable</span></p>;
  }
  const top = max > 0 ? max : 1;
  const step = points.length > 1 ? (W - 2 * PAD) / (points.length - 1) : 0;
  const x = (i: number) => (points.length > 1 ? PAD + i * step : W / 2);
  const y = (v: number) => H - PAD - (v / top) * (H - 2 * PAD);
  // Break the line at unavailable buckets rather than drawing through them.
  const segments: string[] = [];
  let current = "";
  points.forEach((p, i) => {
    const v = value(p);
    if (v === null) {
      if (current) segments.push(current);
      current = "";
      return;
    }
    current += `${current ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  });
  if (current) segments.push(current);
  const last = known[known.length - 1];
  return (
    <figure className="spark">
      <figcaption>
        {label} <span className="spark-last">latest <Value value={value(last)} unit={unit} /></span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label} by ${points.length > 1 ? "period" : "single period"}`}>
        <line className="axis" x1={PAD} x2={W - PAD} y1={H - PAD} y2={H - PAD} />
        {segments.map((d) => <path key={d} className="series" d={d} />)}
        {points.map((p, i) => {
          const v = value(p);
          if (v === null) return null;
          return (
            <g key={p.bucket} className="mark">
              <circle cx={x(i)} cy={y(v)} r={8} className="hit" />
              <circle cx={x(i)} cy={y(v)} r={3.5} className="dot" />
              <title>{`${p.bucket}: ${Number.isInteger(v) ? v : v.toFixed(2)}${unit}`}</title>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

// Backed versus unbacked reuse links as two bars on one scale, labelled directly.
export function ReuseBars({ backed, unbacked, max }: { backed: number; unbacked: number; max: number }) {
  const top = Math.max(max, 1);
  const rows: [string, number, string][] = [["backed", backed, "viz-1"], ["unbacked", unbacked, "viz-2"]];
  return (
    <svg className="bars" viewBox="0 0 160 40" role="img" aria-label={`Reuse links: ${backed} backed, ${unbacked} unbacked`}>
      {rows.map(([name, count, tone], i) => {
        const width = (count / top) * 80;
        return (
          <g key={name} transform={`translate(0 ${i * 20})`}>
            <text x={0} y={12} className="bar-label">{name}</text>
            <rect x={58} y={3} width={80} height={12} rx={2} className="track" />
            {count > 0 && <rect x={58} y={3} width={Math.max(width, 4)} height={12} rx={2} className={tone}><title>{`${name}: ${count}`}</title></rect>}
            <text x={160} y={12} className="bar-value" textAnchor="end">{count}</text>
          </g>
        );
      })}
    </svg>
  );
}
