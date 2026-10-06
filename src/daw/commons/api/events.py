"""Event stream (M8.3): Server-Sent Events over the board event log plus delivery heartbeats and receipts.

Board events are replayed by sequence: `id:` is the event's `seq`, `event:` its kind and `data:` the
JSON row. Reconnects resume after `Last-Event-ID` (or `?after=`). Two synthetic message kinds are
observed from `runs/<run>/` and carry **no** `id:`, so they never move the reconnect cursor:

- `delivery_heartbeat` when a running attempt's heartbeat.json changes (elapsed seconds, stdout bytes);
- `run_receipt` when execution.json, state-receipt.json or final.md appears in a run folder.

Synthetic messages are observations, not records; a reconnect does not replay them. The database is
polled read-only about once a second and a keepalive comment is sent every 15 seconds. `?once=true`
returns the backlog (and current heartbeats) and closes; `GET /api/events/log` is the same backlog as
JSON. `?named=false` sends every message as the default `message` type with `kind` inside `data`, for
clients that cannot subscribe to dynamic event names.
"""
import asyncio
import json
import time
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from daw.commons import views
from daw.commons.api.deps import Config, View
from daw.commons.archive import Archive
from daw.util import DawError

router = APIRouter(prefix="/api", tags=["events"])

RECEIPTS = ("execution.json", "state-receipt.json", "final.md")
BATCH = 500
FINISHED = {"delivery_completed", "delivery_failed", "delivery_recovered", "published_answer_recovered"}


class RunWatch:
    """Observes run folders of running (and just-finished) attempts. Runs already present when the
    stream starts form a silent receipt baseline; runs discovered later report every receipt found."""

    def __init__(self):
        self.runs = {}
        self.primed = False

    def poll(self, view, finished=(), *, settle=True):
        """`settle=False` while replaying a long backlog keeps the receipt baseline open."""
        messages = []
        active = {row["id"] for row in view.rows("SELECT id FROM attempt WHERE state='running'")}
        for run in active | set(finished):
            if run not in self.runs:
                self.runs[run] = {"beat": None, "receipts": set(), "baseline": not self.primed, "idle": 0}
        for run, state in list(self.runs.items()):
            try:
                attempt, folder = view.run_folder(run)
            except DawError:
                del self.runs[run]
                continue
            base = {"run": run, "request": attempt["request"], "agent": attempt["target"], "state": attempt["state"]}
            beat_path = folder / "heartbeat.json"
            signature = None
            if beat_path.is_file():
                stat = beat_path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
            if signature and signature != state["beat"]:
                state["beat"] = signature
                messages.append(("delivery_heartbeat", {**base, "heartbeat": views.heartbeat(folder)}))
            for name in RECEIPTS:
                if name not in state["receipts"] and (folder / name).is_file():
                    state["receipts"].add(name)
                    if not state["baseline"]:
                        messages.append(("run_receipt", {**base, "receipt": name}))
            state["baseline"] = False
            if run not in active:
                state["idle"] += 1
                if state["idle"] > 1 or len(state["receipts"]) == len(RECEIPTS):
                    del self.runs[run]
        self.primed = self.primed or settle
        return messages


def frame(kind, data, *, seq=None, named=True):
    """One SSE message. Board events carry `id: seq`; synthetic observations carry no id."""
    payload = data if named else {**data, "kind": kind}
    lines = [f"id: {seq}"] if seq is not None else []
    if named:
        lines.append(f"event: {kind}")
    lines.append("data: " + json.dumps(payload, separators=(",", ":"), default=str))
    return "\n".join(lines) + "\n\n"


def cursor_from(after, last_event_id):
    """Last-Event-ID (sent by EventSource on reconnect) wins over the original `after`."""
    if last_event_id:
        try:
            value = int(last_event_id.strip())
        except ValueError as e:
            raise DawError("invalid_last_event_id") from e
        if value >= 0:
            return value
    return after


def tick(view, watch, cursor):
    events = views.event_log(view, after=cursor, limit=BATCH)["items"]
    finished = [e["body"].get("run") for e in events if e["kind"] in FINISHED and e["body"].get("run")]
    return events, watch.poll(view, finished, settle=len(events) < BATCH)


async def stream(root, after, *, once=False, named=True, request=None, poll=1.0, keepalive=15.0):
    view = Archive(root)
    watch = RunWatch()
    cursor = after
    try:
        yield "retry: 3000\n\n"
        last = time.monotonic()
        while True:
            events, synthetic = await asyncio.to_thread(tick, view, watch, cursor)
            for event in events:
                cursor = event["seq"]
                yield frame(event["kind"], event, seq=event["seq"], named=named)
            for kind, data in synthetic:
                yield frame(kind, data, named=named)
            if events or synthetic:
                last = time.monotonic()
            if len(events) == BATCH:
                continue  # drain the backlog before sleeping
            if once:
                return
            if request is not None and await request.is_disconnected():
                return
            if time.monotonic() - last >= keepalive:
                last = time.monotonic()
                yield ": keepalive\n\n"
            await asyncio.sleep(poll)
    finally:
        view.close()


@router.get("/events/log")
def log(view: View, after: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=1000)] = 200):
    return views.event_log(view, after=after, limit=limit)


@router.get("/events")
async def events(request: Request, config: Config, after: Annotated[int, Query(ge=0)] = 0, once: bool = False,
                 named: bool = True, last_event_id: Annotated[str | None, Header()] = None):
    cursor = cursor_from(after, last_event_id)
    # The stream owns its own read-only archive: request-scoped dependencies close before a long response ends.
    return StreamingResponse(stream(config.root, cursor, once=once, named=named, request=request),
                             media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
