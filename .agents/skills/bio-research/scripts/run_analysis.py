"""Run one saved local analysis with producer-specific code/output evidence."""
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


def run(receipt, outputs, command):
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
    receipt.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive paths preserve failed invocations and prevent stale receipt reuse.
    with receipt.open("x") as saved:
        before = {str(p): (p.stat().st_ino, p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in outputs}
        code = sha(script)
        value = {"version": 1, "argv": command, "cwd": str(Path.cwd()),
                 "producer": str(script), "code_sha256": code, "started": datetime.now(UTC).isoformat(),
                 "exit_code": None, "outputs": []}
        try:
            with receipt.with_suffix(receipt.suffix + ".stdout").open("xb") as out, receipt.with_suffix(receipt.suffix + ".stderr").open("xb") as err:
                value["exit_code"] = subprocess.run(command, stdout=out, stderr=err, check=False).returncode
            value["code_unchanged"] = sha(script) == code
            for path in outputs:
                exists = path.is_file()
                stat = path.stat() if exists else None
                value["outputs"].append({"path": str(path), "sha256": sha(path) if exists else None,
                    "written": bool(exists and before[str(path)] != (stat.st_ino, stat.st_mtime_ns, stat.st_size))})
        except OSError as error:
            value["error"] = str(error)
        value["finished"] = datetime.now(UTC).isoformat()
        value["complete"] = (value["exit_code"] == 0 and value.get("code_unchanged", False)
                             and len(value["outputs"]) == len(outputs) and all(o["written"] for o in value["outputs"]))
        json.dump(value, saved, indent=2, allow_nan=False)
    print(json.dumps({"event": "analysis_executed", "receipt": str(receipt), "sha256": sha(receipt)}), flush=True)
    return 0 if value["complete"] else (value["exit_code"] or 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, action="append", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    raise SystemExit(run(args.receipt, args.output, args.command))
