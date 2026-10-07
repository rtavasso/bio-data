"""Run one saved local analysis with producer-specific code/input/output evidence.

Declare each input file with --input (repeatable, in the order the code takes them): the receipt records
its sha256 before the run and whether it was unchanged after. A replication is confirmed only when these
equal the derivation's recorded inputs and the printed `analysis_executed` line is in the captured stream.

Prints one JSON line: the receipt path and hash, the exit code, the last --tail lines of stdout (default 20,
at most 3000 characters) and, on a non-zero exit, the stderr tail, so a failure is diagnosed from this result
instead of a second read of the .stderr file. Full stdout/stderr are spooled next to the receipt
(RECEIPT.stdout, RECEIPT.stderr); print a summary from your script and leave whole tables in output files.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
from datetime import datetime, UTC


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


TAIL_CHARS = 3000


def tail(path, lines):
    """The last `lines` lines of a spooled stream, bounded by TAIL_CHARS; never fails the receipt."""
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return ""
    chosen = "\n".join(text.splitlines()[-lines:]) if lines > 0 else ""
    return chosen[-TAIL_CHARS:]


def run(receipt, outputs, command, inputs=(), *, tail_lines=20):
    if command and command[0] == "--":
        command = command[1:]
    if len(command) < 2 or not re.fullmatch(r"python(?:[23](?:\.\d+)?)?|Rscript", Path(command[0]).name):
        raise ValueError("use an explicit Python/R interpreter and a saved script, without shell syntax")
    script = Path(command[1]).resolve()
    if "scripts" not in script.parts or not script.is_file():
        raise ValueError("producer must be a saved local analysis under scripts/")
    outputs = [p.resolve() for p in outputs]
    if not outputs or len(set(outputs)) != len(outputs) or script in outputs:
        raise ValueError("declare distinct output files, separate from the producer")
    receipt = receipt.resolve()
    if receipt in outputs:
        raise ValueError("receipt cannot be an analysis output")
    inputs = [p.resolve() for p in inputs]
    if any(not p.is_file() or p in outputs or p == receipt for p in inputs):
        raise ValueError("declare existing input files, separate from the outputs and the receipt")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive paths preserve failed invocations and prevent stale receipt reuse.
    with receipt.open("x") as saved:
        before = {str(p): (p.stat().st_ino, p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in outputs}
        code = sha(script)
        value = {"version": 1, "argv": command, "cwd": str(Path.cwd()),
                 "producer": str(script), "code_sha256": code, "started": datetime.now(UTC).isoformat(),
                 "inputs": [{"path": str(p), "sha256": sha(p)} for p in inputs], "exit_code": None, "outputs": []}
        try:
            with receipt.with_suffix(receipt.suffix + ".stdout").open("xb") as out, receipt.with_suffix(receipt.suffix + ".stderr").open("xb") as err:
                value["exit_code"] = subprocess.run(command, stdout=out, stderr=err, check=False).returncode
            value["code_unchanged"] = sha(script) == code
            value["inputs_unchanged"] = all(p.is_file() and sha(p) == i["sha256"] for p, i in zip(inputs, value["inputs"]))
            for path in outputs:
                exists = path.is_file()
                stat = path.stat() if exists else None
                value["outputs"].append({"path": str(path), "sha256": sha(path) if exists else None,
                    "written": bool(exists and before[str(path)] != (stat.st_ino, stat.st_mtime_ns, stat.st_size))})
        except OSError as error:
            value["error"] = str(error)
        value["finished"] = datetime.now(UTC).isoformat()
        value["complete"] = (value["exit_code"] == 0 and value.get("code_unchanged", False)
                             and value.get("inputs_unchanged", False)
                             and len(value["outputs"]) == len(outputs) and all(o["written"] for o in value["outputs"]))
        json.dump(value, saved, indent=2, allow_nan=False)
    event = {"event": "analysis_executed", "receipt": str(receipt), "sha256": sha(receipt),
             "exit_code": value["exit_code"], "complete": value["complete"],
             "outputs_written": sum(1 for o in value["outputs"] if o["written"]), "outputs_declared": len(outputs),
             "stdout_tail": tail(receipt.with_suffix(receipt.suffix + ".stdout"), tail_lines)}
    if value["exit_code"] != 0 or value.get("error"):
        event["stderr_tail"] = tail(receipt.with_suffix(receipt.suffix + ".stderr"), tail_lines)
        if value.get("error"):
            event["error"] = value["error"]
    elif not value["complete"]:
        event["incomplete_reason"] = ("producer changed during the run" if not value.get("code_unchanged")
                                      else "an input changed during the run" if not value.get("inputs_unchanged")
                                      else "a declared output was not written")
    print(json.dumps(event, allow_nan=False), flush=True)
    return 0 if value["complete"] else (value["exit_code"] or 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, action="append", required=True)
    parser.add_argument("--input", type=Path, action="append", default=[], help="input file the code reads (repeatable)")
    parser.add_argument("--tail", type=int, default=20, help="stdout lines to print (0 = none); stderr tail is printed on failure")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    raise SystemExit(run(args.receipt, args.output, args.command, args.input, tail_lines=args.tail))
