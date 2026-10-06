import { useState } from "react";
import type { WorkEvent } from "../../types/observatory-map";

// Replays the question's recorded work events in order. The slider shows the state reached after event i
// (current notebook snapshot, artifact links so far, open gaps) and can load the notebook at that point.

export default function Scrubber({ events, shown, onSnapshot }: {
  events: WorkEvent[]; shown: string | null; onSnapshot: (snapshot: string) => void;
}) {
  const [index, setIndex] = useState(events.length - 1);
  if (!events.length) return <p className="muted">No work events are recorded.</p>;
  const event = events[Math.min(index, events.length - 1)];
  const { state } = event;
  return (
    <div className="q-scrubber">
      <label className="q-scrub-label">
        Event {index + 1} of {events.length}
        <input type="range" min={0} max={events.length - 1} value={index} onChange={(e) => setIndex(Number(e.target.value))}
          aria-valuetext={`${event.kind} at ${event.created}`} />
      </label>
      <div className="q-scrub-state">
        <div>
          <strong>{event.kind.replace(/_/g, " ")}</strong> <span className="muted">{event.created}</span>
          <dl className="q-summary">
            {Object.entries(event.summary).map(([key, value]) => (
              <div key={key}><dt>{key}</dt><dd className="mono">{typeof value === "string" ? value : JSON.stringify(value)}</dd></div>
            ))}
          </dl>
        </div>
        <ul className="q-state" aria-label="State after this event">
          <li>produced {state.produced}</li>
          <li>considered {state.considered}</li>
          <li>reused {state.reused}</li>
          <li>open gaps {state.gaps_open}</li>
          <li>
            notebook {state.snapshot ? <span className="mono">{state.snapshot.slice(0, 18)}…</span> : "none yet"}
            {state.snapshot && state.snapshot !== shown && (
              <button type="button" className="linkish" onClick={() => onSnapshot(state.snapshot!)}> show this revision</button>
            )}
            {state.snapshot && state.snapshot === shown && <span className="muted"> (shown)</span>}
          </li>
        </ul>
      </div>
      <ol className="q-ticks" aria-hidden="true">
        {events.map((e, i) => (
          <li key={e.id} className={`${i <= index ? "past" : ""} kind-${e.kind.split("_")[0]}`} title={`${e.kind} · ${e.created}`}
            onClick={() => setIndex(i)} />
        ))}
      </ol>
    </div>
  );
}
