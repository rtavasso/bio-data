import { act, renderHook, waitFor } from "@testing-library/react";
import { useEvents, type StreamMessage } from "./useEvents";

class FakeSource {
  static CLOSED = 2;
  static instances: FakeSource[] = [];
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeSource.instances.push(this);
  }
  close() {
    this.closed = true;
  }
  emit(data: object, lastEventId = "") {
    this.onmessage?.({ data: JSON.stringify(data), lastEventId } as MessageEvent<string>);
  }
}

beforeEach(() => {
  FakeSource.instances = [];
  vi.stubGlobal("EventSource", FakeSource);
  globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ sequence: 41 }), { status: 200 })) as typeof fetch;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test("subscribes from the current sequence and resumes from the last board event after a refused connection", async () => {
  const seen: StreamMessage[] = [];
  const { result, unmount } = renderHook(() => useEvents((m) => seen.push(m)));
  await waitFor(() => expect(FakeSource.instances.length).toBe(1));
  const first = FakeSource.instances[0];
  expect(first.url).toBe("/api/events?named=false&after=41");
  act(() => {
    first.onopen?.();
    first.emit({ seq: 42, kind: "published", body: { post: "post_x" } }, "42");
    first.emit({ kind: "delivery_heartbeat", run: "run_x", heartbeat: { elapsed_seconds: 30 } });
  });
  expect(seen.map((m) => m.kind)).toEqual(["published", "delivery_heartbeat"]);
  expect(result.current).toEqual({ connected: true, lastSeq: 42 });
  vi.useFakeTimers();
  act(() => {
    first.readyState = FakeSource.CLOSED;
    first.onerror?.();
  });
  expect(result.current.connected).toBe(false);
  act(() => {
    vi.advanceTimersByTime(1000);
  });
  expect(FakeSource.instances[1].url).toBe("/api/events?named=false&after=42");
  unmount();
  expect(FakeSource.instances[1].closed).toBe(true);
});
