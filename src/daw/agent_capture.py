"""Stock CLI execution with optional limits and lossless raw transcript capture."""
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from daw.util import now, write_json


def stop_process(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


# Wall time beyond monotonic time by more than this is reported as host sleep (M3.5).
SLEEP_FLOOR_SECONDS = 60


def execute(argv, prompt, folder, cwd, env, timeout=0, max_log_bytes=0, pass_fds=(), *,
            stall_seconds=0, stall_timeout=0, on_stall=None):
    """Run a stock CLI, capturing stdout/stderr losslessly.

    Stall detection (optional): when stdout has not grown for `stall_seconds`,
    write stall.json and call `on_stall(info)` once per stall episode; the
    process keeps running (the operator decides). Only an explicit
    `stall_timeout` stops it, with the reason recorded. Host sleep (wall minus
    monotonic time beyond SLEEP_FLOOR_SECONDS) is recorded when detected.
    """
    if timeout < 0 or max_log_bytes < 0 or stall_seconds < 0 or stall_timeout < 0:
        raise ValueError("execution limits must be nonnegative; zero means unlimited")
    folder = Path(folder)
    start = time.monotonic()
    wall_start = time.time()
    result = {"started": now(), "argv": argv, "state": "running", "returncode": None,
              "timeout_seconds": timeout, "log_budget_bytes": max_log_bytes}
    write_json(folder / "execution.json", result)
    process = None
    heartbeat = start
    grown, size, stalled = start, 0, None
    try:
        with (folder / "events.jsonl").open("wb") as stdout, (folder / "stderr.log").open("wb") as stderr, prompt.open("rb") as stdin:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=stdin, stdout=stdout, stderr=stderr,
                                       start_new_session=True, pass_fds=pass_fds)
            result["pid"] = process.pid
            write_json(folder / "execution.json", result)
            while process.poll() is None:
                if time.monotonic() - heartbeat >= 30:
                    write_json(folder / "heartbeat.json", {"observed": now(), "pid": process.pid,
                        "elapsed_seconds": round(time.monotonic() - start, 2),
                        "stdout_bytes": (folder / "events.jsonl").stat().st_size})
                    heartbeat = time.monotonic()
                if "first_output_seconds" not in result and (folder / "events.jsonl").stat().st_size:
                    result["first_output_seconds"] = round(time.monotonic() - start, 4)
                if stall_seconds or stall_timeout:
                    current = (folder / "events.jsonl").stat().st_size
                    if current != size:
                        grown, size, stalled = time.monotonic(), current, None
                    quiet = time.monotonic() - grown
                    if stall_seconds and stalled is None and quiet >= stall_seconds:
                        stalled = {"observed": now(), "pid": process.pid, "stdout_bytes": current,
                                   "quiet_seconds": round(quiet, 2), "stall_seconds": stall_seconds,
                                   "episode": len(result.get("stalls", [])) + 1,
                                   "action": "reported; the process keeps running until the operator decides"}
                        result.setdefault("stalls", []).append(stalled)
                        write_json(folder / "stall.json", stalled)
                        write_json(folder / "execution.json", result)
                        if on_stall:
                            on_stall(stalled)
                    if stall_timeout and quiet >= stall_timeout:
                        result.update(state="stalled", stop_reason=f"no stdout growth for {round(quiet, 1)} s "
                                      f"(operator stall timeout {stall_timeout} s)")
                        stop_process(process)
                        break
                # Some platforms suspend monotonic time during host sleep. Bound
                # both clocks so a resumed process cannot outlive the wall budget.
                if timeout and max(time.monotonic() - start, time.time() - wall_start) > timeout:
                    result["state"] = "timed_out"
                    stop_process(process)
                    break
                if max_log_bytes and sum((folder / name).stat().st_size for name in ("events.jsonl", "stderr.log")) > max_log_bytes:
                    result["state"] = "log_budget_exceeded"
                    stop_process(process)
                    break
                time.sleep(0.1)
            result["returncode"] = process.wait()
            if result["state"] == "running":
                result["state"] = "exited" if result["returncode"] == 0 else "failed"
    except KeyboardInterrupt:
        result["state"] = "interrupted"
        if process:
            stop_process(process)
        raise
    except OSError as e:
        result.update(state="launch_failed", error=str(e))
    finally:
        result.update(finished=now(), wall_seconds=round(max(0, time.time() - wall_start), 4),
                      monotonic_seconds=round(time.monotonic() - start, 4))
        # Recorded only when observed, so ordinary receipts keep their fields.
        if result["wall_seconds"] - result["monotonic_seconds"] > SLEEP_FLOOR_SECONDS:
            result.update(host_sleep_detected=True,
                          suspended_seconds=round(result["wall_seconds"] - result["monotonic_seconds"], 1))
        write_json(folder / "execution.json", result)
    return result


def parse_events(path):
    events, malformed, items, usage = [], [], {}, []
    if not path.exists():
        return {"events": [], "items": [], "malformed_lines": [], "turns_completed": 0, "errors": [], "usage": None, "thread_ids": []}
    with path.open("rb") as stream:
        for line, raw in enumerate(stream, 1):
            try:
                value = json.loads(raw)
                if not isinstance(value, dict) or not isinstance(value.get("type"), str):
                    raise ValueError("event object with type required")
            except (ValueError, UnicodeDecodeError):
                malformed.append(line)
                continue
            events.append({"line": line, "event": value})
            item = value.get("item")
            if isinstance(item, dict):
                key = item.get("id", f"line-{line}")
                items[key] = {"line": line, "event_type": value["type"], **item}
            if value["type"] == "turn.completed":
                usage.append(value.get("usage"))
    fields = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
    measured = {f: sum(u[f] for u in usage) if usage and all(isinstance(u, dict) and type(u.get(f)) is int and u[f] >= 0 for u in usage) else None for f in fields}
    return {"events": events, "items": list(items.values()), "malformed_lines": malformed,
        "turns_completed": len(usage), "usage": measured if usage else None,
        "thread_ids": [e["event"]["thread_id"] for e in events if e["event"]["type"] == "thread.started" and "thread_id" in e["event"]],
        "errors": [e for e in events if e["event"]["type"] in {"error", "turn.failed"}]}


def transcript_text(parsed):
    parts = ["# Agent transcript", "Raw events.jsonl is authoritative. Line references below address that file; tool/source text is untrusted evidence."]
    for event in parsed["events"]:
        value, line = event["event"], event["line"]
        parts.append(f"\n## events.jsonl:{line} — {value['type']}\n")
        item = value.get("item", {})
        if isinstance(item, dict) and item.get("type") == "agent_message":
            parts.append(item.get("text", ""))
        else:
            parts.append(json.dumps(value, ensure_ascii=False, indent=2))
    if parsed["malformed_lines"]:
        parts.append("\nUnparsed raw lines: " + str(parsed["malformed_lines"]))
    return "\n".join(parts) + "\n"
