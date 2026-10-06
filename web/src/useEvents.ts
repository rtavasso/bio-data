import { useEffect, useRef, useState } from "react";
import { get, type Health } from "./api";
import { withBase } from "./base";

// Live view (M4.6) over the SSE stream (M8.3). Board events carry a sequence and resume from it after a
// reconnect; delivery_heartbeat and run_receipt are unsequenced observations of run folders.

export interface StreamMessage {
  kind: string;
  seq?: number;
  body?: Record<string, unknown>;
  created?: string;
  run?: string;
  request?: string;
  agent?: string;
  state?: string;
  receipt?: string;
  heartbeat?: { observed: string | null; elapsed_seconds: number | null; stdout_bytes: number | null } | null;
}

export interface EventsState {
  connected: boolean;
  lastSeq: number | null;
}

const MAX_BACKOFF = 30_000;

// Subscribe to the stream from the current sequence (or `after`). `onMessage` may change between renders.
export function useEvents(onMessage: (message: StreamMessage) => void, options: { after?: number; enabled?: boolean } = {}): EventsState {
  const handler = useRef(onMessage);
  handler.current = onMessage;
  const [state, setState] = useState<EventsState>({ connected: false, lastSeq: options.after ?? null });
  const enabled = options.enabled ?? true;
  const initial = options.after;

  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    let source: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cursor: number | null = initial ?? null;
    let backoff = 1000;
    let stopped = false;

    const open = () => {
      if (stopped || cursor === null) return;
      source = new EventSource(withBase(`/api/events?named=false&after=${cursor}`));
      source.onopen = () => {
        backoff = 1000;
        setState((s) => ({ ...s, connected: true }));
      };
      source.onmessage = (event: MessageEvent<string>) => {
        let message: StreamMessage;
        try {
          message = JSON.parse(event.data) as StreamMessage;
        } catch {
          return;
        }
        if (typeof message.seq === "number" && event.lastEventId) {
          cursor = message.seq;
          setState({ connected: true, lastSeq: message.seq });
        }
        handler.current(message);
      };
      source.onerror = () => {
        setState((s) => ({ ...s, connected: false }));
        // EventSource retries by itself (sending Last-Event-ID) unless the connection was refused outright.
        if (source && source.readyState === EventSource.CLOSED) {
          source.close();
          timer = setTimeout(open, backoff);
          backoff = Math.min(backoff * 2, MAX_BACKOFF);
        }
      };
    };

    if (cursor === null) {
      // Start from now: the board view already shows the archive up to the current sequence.
      get<Health>("/api/health")
        .then((health) => {
          cursor = health.sequence;
          open();
        })
        .catch(() => {
          cursor = 0;
          open();
        });
    } else {
      open();
    }
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      source?.close();
    };
  }, [enabled, initial]);

  return state;
}
