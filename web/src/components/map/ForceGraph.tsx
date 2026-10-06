import { useEffect, useId, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { forceLink, forceManyBody, forceSimulation, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";

// A small, dependency-light graph view. Positions come from the server's deterministic layout; d3-force
// only refines them for a bounded number of ticks, so the picture is stable between reloads. SVG below
// `canvasThreshold` nodes (keyboard-focusable nodes), canvas above it. Wheel zooms, drag pans.

export type Shape = "circle" | "square" | "diamond" | "triangle" | "hexagon";

export interface GraphNode {
  id: string;
  x: number;
  y: number;
  label: string;
  group: string; // colour token: --viz-<group>
  shape: Shape;
  ring?: boolean; // seed or emphasised node
  missing?: boolean; // named by a record but absent from every store
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  dashed: boolean;
  label: string;
}

interface Placed extends SimulationNodeDatum {
  id: string;
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  height?: number;
  refineTicks?: number;
  canvasThreshold?: number;
  label: string;
  showLabels?: boolean;
}

const RADIUS = 7;

export function shapePath(shape: Shape, r = RADIUS): string {
  switch (shape) {
    case "square":
      return `M${-r * 0.85},${-r * 0.85}h${r * 1.7}v${r * 1.7}h${-r * 1.7}Z`;
    case "diamond":
      return `M0,${-r * 1.15}L${r * 1.15},0L0,${r * 1.15}L${-r * 1.15},0Z`;
    case "triangle":
      return `M0,${-r * 1.1}L${r},${r * 0.8}L${-r},${r * 0.8}Z`;
    case "hexagon": {
      const points = Array.from({ length: 6 }, (_, i) => {
        const a = (Math.PI / 3) * i;
        return `${(r * Math.cos(a)).toFixed(2)},${(r * Math.sin(a)).toFixed(2)}`;
      });
      return `M${points.join("L")}Z`;
    }
    default:
      return `M${r},0A${r},${r} 0 1,1 ${-r},0A${r},${r} 0 1,1 ${r},0Z`;
  }
}

export function refine(nodes: GraphNode[], edges: GraphEdge[], ticks: number): Map<string, [number, number]> {
  const placed: Placed[] = nodes.map((n) => ({ id: n.id, x: n.x, y: n.y }));
  const ids = new Set(placed.map((n) => n.id));
  const links: SimulationLinkDatum<Placed>[] = edges
    .filter((e) => ids.has(e.source) && ids.has(e.target) && e.source !== e.target)
    .map((e) => ({ source: e.source, target: e.target }));
  if (ticks > 0 && placed.length > 1) {
    const simulation = forceSimulation(placed)
      .force("link", forceLink<Placed, SimulationLinkDatum<Placed>>(links).id((d) => d.id).distance(40).strength(0.2))
      .force("charge", forceManyBody().strength(-25).distanceMax(160))
      .alpha(0.25)
      .stop();
    simulation.tick(ticks);
  }
  return new Map(placed.map((n) => [n.id, [n.x ?? 0, n.y ?? 0]]));
}

function cssColor(element: Element | null, group: string): string {
  if (!element) return "#888";
  return getComputedStyle(element).getPropertyValue(`--viz-${group}`).trim() || "#888";
}

export default function ForceGraph({
  nodes, edges, selected = null, onSelect, height = 520, refineTicks = 40, canvasThreshold = 500, label, showLabels,
}: Props) {
  const arrow = `fg-arrow-${useId().replace(/[^A-Za-z0-9_-]/g, "")}`;
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(800);
  const [hover, setHover] = useState<string | null>(null);
  const positions = useMemo(() => refine(nodes, edges, refineTicks), [nodes, edges, refineTicks]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const neighbours = useMemo(() => {
    const out = new Map<string, Set<string>>();
    for (const e of edges) {
      if (!out.has(e.source)) out.set(e.source, new Set());
      if (!out.has(e.target)) out.set(e.target, new Set());
      out.get(e.source)!.add(e.target);
      out.get(e.target)!.add(e.source);
    }
    return out;
  }, [edges]);

  const fit = useMemo(() => {
    const values = [...positions.values()];
    if (!values.length) return { k: 1, x: width / 2, y: height / 2 };
    const xs = values.map((p) => p[0]);
    const ys = values.map((p) => p[1]);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const k = Math.max(0.05, Math.min(3, Math.min(width / (x1 - x0 + 80), height / (y1 - y0 + 80))));
    return { k, x: width / 2 - k * ((x0 + x1) / 2), y: height / 2 - k * ((y0 + y1) / 2) };
  }, [positions, width, height]);
  const [view, setView] = useState(fit);
  useEffect(() => setView(fit), [fit]);

  useEffect(() => {
    const element = box.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.round(entry.contentRect.width))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      const px = event.clientX - rect.left;
      const py = event.clientY - rect.top;
      setView((v) => {
        const k = Math.max(0.05, Math.min(8, v.k * (event.deltaY < 0 ? 1.15 : 1 / 1.15)));
        return { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k };
      });
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, []);

  const drag = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null);
  const down = (event: ReactPointerEvent) => {
    if ((event.target as Element).closest?.("[data-node]")) return;
    drag.current = { x: event.clientX, y: event.clientY, vx: view.x, vy: view.y, moved: false };
    (event.currentTarget as Element).setPointerCapture?.(event.pointerId);
  };
  const move = (event: ReactPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = event.clientX - d.x;
    const dy = event.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
    setView((v) => ({ ...v, x: d.vx + dx, y: d.vy + dy }));
  };
  const up = (event: ReactPointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (d && !d.moved && canvasMode) pick(event);
    else if (d && !d.moved && !canvasMode) onSelect?.(null);
  };

  const canvasMode = nodes.length > canvasThreshold;
  const focus = selected ?? hover;
  const related = focus ? neighbours.get(focus) ?? new Set<string>() : null;
  const dim = (id: string) => related !== null && id !== focus && !related.has(id);
  const labelled = (id: string) =>
    showLabels ?? (nodes.length <= 40 || view.k > 1.6 || id === focus || byId.get(id)?.ring || related?.has(id));

  function pick(event: ReactPointerEvent) {
    const rect = box.current!.getBoundingClientRect();
    const gx = (event.clientX - rect.left - view.x) / view.k;
    const gy = (event.clientY - rect.top - view.y) / view.k;
    let best: string | null = null;
    let distance = (RADIUS * 2) / view.k;
    for (const [id, [x, y]] of positions) {
      const d = Math.hypot(x - gx, y - gy);
      if (d < distance) [best, distance] = [id, d];
    }
    onSelect?.(best);
  }

  useEffect(() => {
    if (!canvasMode || !canvas.current) return;
    const element = canvas.current;
    const context = element.getContext?.("2d");
    if (!context) return;
    const ratio = window.devicePixelRatio || 1;
    element.width = width * ratio;
    element.height = height * ratio;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    context.translate(view.x, view.y);
    context.scale(view.k, view.k);
    const muted = cssColor(box.current, "edge");
    for (const e of edges) {
      const a = positions.get(e.source);
      const b = positions.get(e.target);
      if (!a || !b) continue;
      context.globalAlpha = dim(e.source) || dim(e.target) ? 0.15 : 0.8;
      context.strokeStyle = muted;
      context.lineWidth = 1 / view.k;
      context.setLineDash(e.dashed ? [4 / view.k, 3 / view.k] : []);
      context.beginPath();
      context.moveTo(a[0], a[1]);
      context.lineTo(b[0], b[1]);
      context.stroke();
    }
    context.setLineDash([]);
    for (const n of nodes) {
      const p = positions.get(n.id);
      if (!p) continue;
      context.globalAlpha = dim(n.id) ? 0.2 : 1;
      context.save();
      context.translate(p[0], p[1]);
      context.scale(1 / view.k, 1 / view.k);
      const path = new Path2D(shapePath(n.shape));
      context.fillStyle = n.missing ? cssColor(box.current, "surface") : cssColor(box.current, n.group);
      context.fill(path);
      context.strokeStyle = n.id === selected ? cssColor(box.current, "ink") : cssColor(box.current, "surface");
      context.lineWidth = n.id === selected ? 2.5 : 1.5;
      context.stroke(path);
      context.restore();
    }
    context.globalAlpha = 1;
  }, [canvasMode, nodes, edges, positions, view, width, height, selected, hover]);

  return (
    <div className="force-graph" ref={box} style={{ height }} onPointerDown={down} onPointerMove={move} onPointerUp={up}>
      <div className="force-graph-controls">
        <button type="button" aria-label="Zoom in" onClick={() => setView((v) => ({ ...v, k: Math.min(8, v.k * 1.3) }))}>+</button>
        <button type="button" aria-label="Zoom out" onClick={() => setView((v) => ({ ...v, k: Math.max(0.05, v.k / 1.3) }))}>−</button>
        <button type="button" onClick={() => setView(fit)}>Fit</button>
      </div>
      {canvasMode ? (
        <canvas ref={canvas} style={{ width, height }} aria-label={`${label} (${nodes.length} nodes; use the table view)`} role="img" />
      ) : (
        <svg width="100%" height={height} role="group" aria-label={label}>
          <defs>
            <marker id={arrow} viewBox="0 0 10 10" refX="17" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M0,0L10,5L0,10Z" className="fg-arrow" />
            </marker>
          </defs>
          <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {edges.map((e) => {
              const a = positions.get(e.source);
              const b = positions.get(e.target);
              if (!a || !b) return null;
              return (
                <line key={e.id} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} markerEnd={`url(#${arrow})`}
                  className={`fg-edge${e.dashed ? " dashed" : ""}${dim(e.source) || dim(e.target) ? " dim" : ""}`}
                  vectorEffect="non-scaling-stroke">
                  <title>{e.label}</title>
                </line>
              );
            })}
            {nodes.map((n) => {
              const p = positions.get(n.id);
              if (!p) return null;
              return (
                <g key={n.id} data-node={n.id} transform={`translate(${p[0]},${p[1]})`} tabIndex={0} role="button"
                  aria-label={n.label} aria-pressed={n.id === selected}
                  className={`fg-node${dim(n.id) ? " dim" : ""}${n.id === selected ? " selected" : ""}${n.missing ? " missing" : ""}`}
                  onClick={(event) => { event.stopPropagation(); onSelect?.(n.id); }}
                  onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect?.(n.id); } }}
                  onPointerEnter={() => setHover(n.id)} onPointerLeave={() => setHover(null)}
                  onFocus={() => setHover(n.id)} onBlur={() => setHover(null)}>
                  <title>{n.label}</title>
                  <g transform={`scale(${1 / view.k})`}>
                    {n.ring && <circle r={RADIUS + 4} className="fg-ring" />}
                    <path d={shapePath(n.shape)} style={{ fill: n.missing ? undefined : `var(--viz-${n.group})` }} />
                    {labelled(n.id) && (
                      <text x={RADIUS + 5} y={4} className="fg-label">
                        {n.label.length > 48 ? n.label.slice(0, 47) + "…" : n.label}
                      </text>
                    )}
                  </g>
                </g>
              );
            })}
          </g>
        </svg>
      )}
    </div>
  );
}
