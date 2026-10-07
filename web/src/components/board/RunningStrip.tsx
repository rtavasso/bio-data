import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import type { Heartbeat, RunningItem } from "../../types/board";
import { useApi } from "../../useApi";
import { useEvents, type StreamMessage } from "../../useEvents";
import { Badge } from "./Badges";
import { ParticipantLink } from "./People";
import { duration, size, short } from "./format";

const RELOAD_ON = new Set(["delivery_started", "delivery_completed", "delivery_failed", "delivery_recovered",
  "published_answer_recovered", "retry_requested"]);

// Active deliveries (attempts in state running) with their latest heartbeat, updated live from the stream.
export function RunningStrip({ onMessage }: { onMessage?: (message: StreamMessage) => void }) {
  const running = useApi<{ items: RunningItem[] }>("/api/running");
  const [beats, setBeats] = useState<Record<string, Heartbeat>>({});
  const [receipts, setReceipts] = useState<Record<string, string[]>>({});
  const { reload } = running;
  const handle = useCallback((message: StreamMessage) => {
    if (message.kind === "delivery_heartbeat" && message.run && message.heartbeat) {
      setBeats((b) => ({ ...b, [message.run!]: message.heartbeat! }));
    } else if (message.kind === "run_receipt" && message.run && message.receipt) {
      setReceipts((r) => ({ ...r, [message.run!]: [...(r[message.run!] ?? []), message.receipt!] }));
    } else if (RELOAD_ON.has(message.kind)) {
      reload();
    }
    onMessage?.(message);
  }, [reload, onMessage]);
  const live = useEvents(handle);
  const items = running.data?.items ?? [];
  return (
    <section className="running-strip" aria-label="Running now">
      <h2>
        Running now <span className={`live-dot${live.connected ? " on" : ""}`} title={live.connected ? "live" : "reconnecting"} />
      </h2>
      {items.length === 0 ? (
        <p className="muted">No deliveries running.</p>
      ) : (
        <ul>
          {items.map((item) => {
            const beat = beats[item.run] ?? item.heartbeat;
            return (
              <li key={item.run}>
                <ParticipantLink id={item.agent} />{" "}
                {item.task_type && <Badge tone="accent">{item.task_type}</Badge>}{" "}
                <Link to={`/post/${item.post}`}>{item.post_hidden && !item.title ? "Hidden post" : item.title ?? short(item.post)}</Link>{" "}
                <Link to={`/run/${item.run}`} className="mono">{short(item.run)}</Link>{" "}
                <span className="muted">
                  {beat ? `${duration(beat.elapsed_seconds)} · ${size(beat.stdout_bytes)} streamed` : "no heartbeat yet"}
                  {receipts[item.run]?.length ? ` · ${receipts[item.run].join(", ")}` : ""}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
