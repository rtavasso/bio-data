"""Register several outputs with `bio register`, persisting each receipt before the next.

Example:
  ./bin/python .agents/skills/bio-research/scripts/register_batch.py \
      --plan workspace/questions/Q/outputs/registrations.plan.json \
      --question Q --receipts workspace/questions/Q/outputs/registrations.json

The plan is a JSON list of objects with: path, title, summary, output_role,
inputs (asset/artifact IDs or stored blob hashes), code (script paths),
parameters (object, optional). Entries already present in the receipts file
are skipped, so a failed batch resumes without guessing response fields.
Nothing here executes analysis code or validates science.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


def register_all(plan, question, receipts, bio, workspace=None):
    receipts = Path(receipts)
    done = json.loads(receipts.read_text()) if receipts.exists() else {}
    base = shlex.split(bio) + (["-w", str(workspace)] if workspace else [])
    results = []
    for entry in plan:
        key = entry["path"]
        if key in done and done[key].get("artifact"):
            results.append({"path": key, "skipped": True, **done[key]})
            continue
        argv = base + ["register", entry["path"], "--question", question, "--title", entry.get("title") or Path(key).name,
                       "--summary", entry.get("summary", ""), "--output-role", entry.get("output_role", "result"),
                       "--parameters", json.dumps(entry.get("parameters", {}), allow_nan=False)]
        for item in entry.get("inputs", []):
            argv += ["--input", item]
        for item in entry.get("code", []):
            argv += ["--code", item]
        for item in entry.get("references", []):
            argv += ["--reference", item]
        completed = subprocess.run(argv, capture_output=True, text=True, check=False)
        try:
            value = json.loads(completed.stdout.strip().splitlines()[-1]) if completed.stdout.strip() else {}
        except ValueError:
            value = {}
        record = {"argv": argv, "exit_code": completed.returncode, **value}
        if completed.returncode != 0:
            record["stderr"] = completed.stderr[-2000:]
            record["stdout"] = completed.stdout[-2000:]
        done[key] = record
        receipts.write_text(json.dumps(done, indent=2, allow_nan=False))
        results.append({"path": key, "skipped": False, **record})
        if completed.returncode != 0:
            break
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--bio", default=os.environ.get("BIO_CLI", "./bin/bio"), help="bio command (shell words)")
    parser.add_argument("--workspace", default=None, help="explicit -w for bio; default honours BIO_WORKSPACE")
    args = parser.parse_args(argv)
    results = register_all(json.loads(args.plan.read_text()), args.question, args.receipts, args.bio, args.workspace)
    failed = [r for r in results if r.get("exit_code") not in (0, None)]
    print(json.dumps({"event": "registrations", "registered": sum(1 for r in results if r.get("artifact")),
                      "failed": len(failed), "receipts": str(args.receipts),
                      "artifacts": [r.get("artifact") for r in results if r.get("artifact")]}, allow_nan=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
