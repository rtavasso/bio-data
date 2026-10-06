import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import type { Call, RunTimeline } from "../../types/observatory-map";

// A lightweight canvas timeline for one delivery: a monotonic axis, one lane per tool kind, the host
// suspension drawn as a fixed-width grey break (its wall duration is labelled, not drawn to scale),
// receipt pass/fail glyphs, compactions (C), compaction fallbacks (F) and the headline moment.

const GUTTER = 128;
const TOP = 34;
const LANE = 22;
const BREAK = 46;

export function formatSeconds(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds * 10) / 10} s`;
  if (seconds < 3600) return `${Math.round((seconds / 60) * 10) / 10} min`;
  return `${Math.round((seconds / 3600) * 10) / 10} h`;
}

function ticks(duration: number, count: number): number[] {
  if (duration <= 0) return [0];
  const raw = duration / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let t = 0; t <= duration + 1e-9; t += step) out.push(t);
  return out;
}

export function scaleFor(timeline: RunTimeline, width: number) {
  const suspension = timeline.suspensions[0];
  const plot = Math.max(80, width - GUTTER - 16 - (suspension ? BREAK : 0));
  const duration = Math.max(timeline.axis.duration, 1e-6);
  const k = plot / duration;
  return (t: number) => GUTTER + t * k + (suspension && t > suspension.at ? BREAK : 0);
}

export default function TimelineCanvas({ timeline }: { timeline: RunTimeline }) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(900);
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const lanes = useMemo(() => timeline.lanes.filter((l) => l.count > 0), [timeline]);
  const height = TOP + lanes.length * LANE + 12;
  const x = useMemo(() => scaleFor(timeline, width), [timeline, width]);
  const outcome = useMemo(() => new Map(timeline.receipts.map((r) => [r.line, r.outcome])), [timeline]);

  useEffect(() => {
    const element = box.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(360, Math.round(entry.contentRect.width))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext?.("2d");
    if (!element || !context || !box.current) return;
    const css = getComputedStyle(box.current);
    const token = (name: string) => css.getPropertyValue(`--viz-${name}`).trim() || "#888";
    const ratio = window.devicePixelRatio || 1;
    element.width = width * ratio;
    element.height = height * ratio;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    context.font = "11px system-ui, sans-serif";
    context.textBaseline = "middle";
    const bottom = TOP + lanes.length * LANE;
    // Axis and lane grid.
    context.fillStyle = token("muted");
    context.strokeStyle = token("grid");
    context.lineWidth = 1;
    for (const t of ticks(timeline.axis.duration, Math.max(2, Math.floor((width - GUTTER) / 110)))) {
      const px = Math.round(x(t)) + 0.5;
      context.beginPath();
      context.moveTo(px, TOP - 4);
      context.lineTo(px, bottom);
      context.stroke();
      context.fillText(timeline.axis.unit === "seconds" ? formatSeconds(t) : `#${Math.round(t)}`, px + 2, TOP - 10);
    }
    lanes.forEach((lane, i) => {
      const y = TOP + i * LANE;
      context.fillStyle = token("ink-2");
      context.fillText(`${lane.label} (${lane.count})`, 4, y + LANE / 2);
      context.strokeStyle = token("grid");
      context.beginPath();
      context.moveTo(GUTTER, y + LANE + 0.5);
      context.lineTo(width, y + LANE + 0.5);
      context.stroke();
    });
    // Suspension break: greyed, labelled with its wall duration.
    for (const s of timeline.suspensions) {
      const left = x(s.at) + 2;
      context.fillStyle = token("suspended");
      context.fillRect(left, TOP - 4, BREAK - 4, bottom - TOP + 4);
      context.fillStyle = token("ink-2");
      context.fillText(`suspended ${formatSeconds(s.seconds)}`, left - 20, TOP - 24);
    }
    // Calls as thin bars; failed exit codes outlined in the critical colour.
    const laneIndex = new Map(lanes.map((l, i) => [l.id, i]));
    for (const call of timeline.calls) {
      const row = laneIndex.get(call.lane);
      if (row === undefined || call.t === null) continue;
      const left = x(call.t);
      const right = call.t_end !== null ? x(call.t_end) : left + 3;
      const y = TOP + row * LANE + 6;
      context.fillStyle = token("posts");
      context.fillRect(left, y, Math.max(3, right - left), LANE - 12);
      if (call.exit_code !== null && call.exit_code !== 0) {
        context.strokeStyle = token("critical");
        context.lineWidth = 1.5;
        context.strokeRect(left - 1, y - 1, Math.max(3, right - left) + 2, LANE - 10);
      }
      const verdict = outcome.get(call.line);
      if (verdict && verdict !== "unknown") {
        context.fillStyle = token(verdict === "pass" ? "good" : "critical");
        context.fillText(verdict === "pass" ? "✓" : "✗", Math.max(3, right - left) + left + 3, y + (LANE - 12) / 2);
      }
    }
    // Markers across all lanes: compactions (C), fallback summaries (F), headline (★).
    const marker = (t: number, label: string, color: string, dashed: boolean) => {
      const px = Math.round(x(t)) + 0.5;
      context.strokeStyle = color;
      context.setLineDash(dashed ? [3, 3] : []);
      context.lineWidth = 1.5;
      context.beginPath();
      context.moveTo(px, TOP - 2);
      context.lineTo(px, bottom);
      context.stroke();
      context.setLineDash([]);
      context.fillStyle = color;
      context.fillText(label, px + 3, TOP + 4);
    };
    for (const c of timeline.compactions) if (c.t !== null) marker(c.t, "C", token("ink-2"), true);
    for (const s of timeline.compaction_summaries ?? []) if (s.t !== null && s.fallback) marker(s.t, "F", token("serious"), true);
    if (timeline.headline?.t !== null && timeline.headline?.t !== undefined) marker(timeline.headline.t, "★", token("ink"), false);
  }, [timeline, width, height, lanes, x, outcome]);

  const hover = (event: MouseEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const row = Math.floor((py - TOP) / LANE);
    const lane = lanes[row];
    if (!lane) return setTip(null);
    let best: Call | null = null;
    let distance = 8;
    for (const call of timeline.calls) {
      if (call.lane !== lane.id || call.t === null) continue;
      const left = x(call.t);
      const right = Math.max(left + 3, call.t_end !== null ? x(call.t_end) : left);
      const d = px < left ? left - px : px > right ? px - right : 0;
      if (d < distance) [best, distance] = [call, d];
    }
    setTip(best ? { x: px, y: py, text: `${best.summary || best.name} · line ${best.line}` +
      (best.exit_code !== null ? ` · exit ${best.exit_code}` : "") } : null);
  };

  return (
    <div className="viz run-timeline" ref={box}>
      <canvas ref={canvas} style={{ width, height }} onMouseMove={hover} onMouseLeave={() => setTip(null)} role="img"
        aria-label={`Timeline: ${timeline.calls.length} tool calls in ${lanes.length} lanes; the table view lists them`} />
      {tip && <div className="run-tip" style={{ left: Math.min(tip.x + 12, width - 260), top: tip.y + 12 }}>{tip.text}</div>}
    </div>
  );
}
