"""Bounded stock CLI execution and lossless raw transcript capture."""
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


def execute(argv, prompt, folder, cwd, env, timeout, max_log_bytes=32 * 2**20):
    folder = Path(folder)
    start = time.monotonic()
    wall_start = time.time()
    result = {"started": now(), "argv": argv, "state": "running", "returncode": None,
              "timeout_seconds": timeout, "log_budget_bytes": max_log_bytes}
    write_json(folder / "execution.json", result)
    process = None
    try:
        with (folder / "events.jsonl").open("wb") as stdout, (folder / "stderr.log").open("wb") as stderr, prompt.open("rb") as stdin:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=stdin, stdout=stdout, stderr=stderr, start_new_session=True)
            while process.poll() is None:
                if "first_output_seconds" not in result and (folder / "events.jsonl").stat().st_size:
                    result["first_output_seconds"] = round(time.monotonic() - start, 4)
                # Some platforms suspend monotonic time during host sleep. Bound
                # both clocks so a resumed process cannot outlive the wall budget.
                if max(time.monotonic() - start, time.time() - wall_start) > timeout:
                    result["state"] = "timed_out"
                    stop_process(process)
                    break
                if sum((folder / name).stat().st_size for name in ("events.jsonl", "stderr.log")) > max_log_bytes:
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
