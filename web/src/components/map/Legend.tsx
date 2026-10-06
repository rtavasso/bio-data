import { FAMILIES, type Family } from "../../types/observatory-map";
import { shapePath } from "./ForceGraph";
import { FAMILY_STYLE } from "./style";

export function Glyph({ family }: { family: Family }) {
  return (
    <svg width="16" height="16" viewBox="-8 -8 16 16" aria-hidden="true">
      <path d={shapePath(FAMILY_STYLE[family].shape, 6)} style={{ fill: `var(--viz-${family})` }} />
    </svg>
  );
}

export function MapLegend({ counts }: { counts?: Record<Family, number> }) {
  return (
    <div className="viz viz-legend" aria-label="Legend">
      {FAMILIES.map((family) => (
        <span key={family}>
          <Glyph family={family} /> {FAMILY_STYLE[family].label}
          {counts ? ` (${counts[family] ?? 0})` : ""}
        </span>
      ))}
      <span><i className="swatch-line" /> recorded relation; backed reuse</span>
      <span><i className="swatch-line dashed" /> considered, fetched, fork, or unbacked reuse</span>
    </div>
  );
}
