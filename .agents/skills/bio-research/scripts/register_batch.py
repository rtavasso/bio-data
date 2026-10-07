"""Register several outputs with `bio register`, persisting each receipt before the next.

From run receipts (preferred: no hand-written plan):
  ./bin/python .agents/skills/bio-research/scripts/register_batch.py \
      --from-receipt workspace/questions/Q/outputs/execution-r001.json \
      --from-receipt workspace/questions/Q/outputs/execution-r002.json \
      --role contrast.tsv=contrast-table --role summary.json=summary \
      [--title contrast.tsv="PMP22 contrast"] [--summary contrast.tsv="..."] \
      --question Q --receipts workspace/questions/Q/outputs/registrations.json

Each run_analysis.py receipt already records the producer path and code sha256, the inputs with their sha256
and the outputs with theirs. Every output named by --role (its basename, or its full path when basenames
collide) is registered with: inputs = the receipt's input files (an input that is the output of an artifact
registered earlier in this batch is cited by that artifact ID; any other input is `bio object add`ed when it
is not yet a stored blob, and its blob is used), code = the receipt's producer, parameters = {"script_args":
the script's arguments from the receipt argv}. A receipt is refused, before anything is registered, when the
run was incomplete (exit code not 0, producer or an input changed during the run, a declared output not
written), when the producer, an input or an output no longer has the bytes the receipt recorded (never edit
a script after registering what it produced: write a new version and rerun it through run_analysis.py), or
when a --role names no output of the given receipts.

From a plan (--plan PLAN.json): a JSON list of objects, one per output:
  {"path": "outputs/table.tsv",            # required: the file to register
   "title": "...", "summary": "...",       # optional (title defaults to the file name)
   "output_role": "contrast-table",        # optional, default "result"
   "inputs": ["asset_...", "artifact_...", "<stored blob sha256>"],   # required by bio register
   "code": ["scripts/analyze.py"],         # required: script paths
   "parameters": {...},                    # optional object
   "references": ["<stored blob sha256>"]} # optional
Entries already present in the receipts file (keyed by path) are skipped, so a failed batch resumes without
guessing response fields. Nothing here executes analysis code or validates science.
"""
import argparse
import hashlib
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


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _pairs(values, flag):
    out = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"{flag} takes OUTPUT=VALUE (output basename or path), not {value!r}")
        key, text = value.split("=", 1)
        if not key or not text:
            raise ValueError(f"{flag} {value!r}: both OUTPUT and VALUE are required")
        out[key] = text
    return out


def receipt_problems(receipt, path):
    """Why a run_analysis.py receipt cannot back a registration now (empty when it can)."""
    problems = []
    if receipt.get("exit_code") != 0:
        problems.append(f"the run exited {receipt.get('exit_code')}")
    if not receipt.get("code_unchanged", False):
        problems.append("the producer changed during the run")
    if not receipt.get("inputs_unchanged", False):
        problems.append("an input changed during the run")
    unwritten = [Path(o["path"]).name for o in receipt.get("outputs", []) if not o.get("written") or not o.get("sha256")]
    if unwritten or not receipt.get("outputs"):
        problems.append(f"declared output not written: {', '.join(unwritten) or '(none declared)'}")
    if problems:
        return [f"{path}: incomplete run ({'; '.join(problems)}); fix and rerun through run_analysis.py"]
    producer = Path(receipt.get("producer", ""))
    if not producer.is_file() or sha256(producer) != receipt.get("code_sha256"):
        problems.append(f"{path}: producer {producer} was edited or removed after the run; never edit a script after "
                        "it produced registered output: write a new version and rerun it through run_analysis.py")
    for item in receipt.get("inputs", []):
        if not Path(item["path"]).is_file() or sha256(item["path"]) != item["sha256"]:
            problems.append(f"{path}: input {item['path']} no longer has the bytes the run read; rerun")
    for item in receipt["outputs"]:
        if not Path(item["path"]).is_file() or sha256(item["path"]) != item["sha256"]:
            problems.append(f"{path}: output {item['path']} changed after the run; rerun instead of editing outputs")
    return problems


def _bio_json(base, args):
    done = subprocess.run(base + args, capture_output=True, text=True, check=False)
    try:
        value = json.loads(done.stdout.strip().splitlines()[-1]) if done.stdout.strip() else {}
    except ValueError:
        value = {}
    return done.returncode, value, (done.stderr or done.stdout)[-1500:]


def plan_from_receipts(receipt_paths, roles, titles=None, summaries=None, *, bio, workspace=None, registered=None):
    """(plan, problems): plan entries for every --role output of the receipts, built only when no receipt is refused.
    Inputs not yet stored are `bio object add`ed (classification work) after every receipt passes its checks.
    `registered` maps an output sha256 to an artifact ID already registered (from the receipts file)."""
    titles, summaries, registered = titles or {}, summaries or {}, dict(registered or {})
    receipts, problems = [], []
    for path in receipt_paths:
        try:
            value = json.loads(Path(path).read_text())
        except (OSError, ValueError) as error:
            problems.append(f"{path}: not a readable receipt ({error})")
            continue
        if not isinstance(value, dict) or "producer" not in value or "outputs" not in value:
            problems.append(f"{path}: not a run_analysis.py receipt (no producer/outputs)")
            continue
        problems += receipt_problems(value, path)
        receipts.append((Path(path), value))
    outputs = [(path, receipt, item) for path, receipt in receipts for item in receipt["outputs"]]
    names = {}
    for _, _, item in outputs:
        names.setdefault(Path(item["path"]).name, []).append(item["path"])
    chosen = []
    for key, role in roles.items():
        matches = [o for o in outputs if o[2]["path"] == str(Path(key).resolve()) or o[2]["path"] == key]
        if not matches and "/" not in key:
            matches = [o for o in outputs if Path(o[2]["path"]).name == key]
        if not matches:
            known = ", ".join(sorted(names)) or "none"
            problems.append(f"--role {key}={role}: no such output in the given receipts (outputs: {known})")
        elif len(matches) > 1:
            problems.append(f"--role {key}: {len(matches)} outputs share that name; use the full path "
                            f"({', '.join(o[2]['path'] for o in matches)})")
        else:
            chosen.append((key, role, *matches[0]))
    for flag, values in (("--title", titles), ("--summary", summaries)):
        for key in values:
            if key not in roles:
                problems.append(f"{flag} {key}: give the output a --role too")
    if problems:
        return None, problems
    # Register producers before consumers: an output of one entry read by another is cited by artifact ID.
    produced = {item["sha256"] for _, _, _, _, item in chosen}
    ordered, placed = [], set()
    while chosen:
        ready = [c for c in chosen if all(i["sha256"] in placed or i["sha256"] not in produced
                                          or i["sha256"] == c[4]["sha256"] for i in c[3].get("inputs", []))]
        if not ready:
            return None, ["the --role outputs depend on each other in a cycle; register them in separate calls"]
        for entry in ready:
            chosen.remove(entry)
            ordered.append(entry)
            placed.add(entry[4]["sha256"])
    base = shlex.split(bio) + (["-w", str(workspace)] if workspace else [])
    plan, stored = [], set()
    for key, role, receipt_path, receipt, item in ordered:
        inputs = []
        for source in receipt.get("inputs", []):
            sha = source["sha256"]
            if sha in registered:
                inputs.append(registered[sha])
                continue
            if sha not in produced and sha not in stored:
                code, _, _ = _bio_json(base, ["object", "show", sha])
                if code != 0:
                    code, value, err = _bio_json(base, ["object", "add", source["path"], "--classification", "work"])
                    if code != 0 or value.get("blob") != sha:
                        return None, [f"{receipt_path}: bio object add {source['path']} failed or stored other bytes: {err}"]
                stored.add(sha)
            inputs.append(sha)  # a batch output's sha is replaced by its artifact ID at registration
        argv = receipt.get("argv") or []
        plan.append({"path": item["path"], "title": titles.get(key) or Path(item["path"]).name,
                     "summary": summaries.get(key) or (f"Written by {Path(receipt['producer']).name} "
                                                      f"(run receipt {receipt_path.name}, sha256 {sha256(receipt_path)[:16]})."),
                     "output_role": role, "inputs": inputs, "code": [receipt["producer"]],
                     "parameters": {"script_args": argv[2:]}, "output_sha256": item["sha256"],
                     "run_receipt": str(receipt_path)})
    return plan, []


def register_from_receipts(receipt_paths, roles, question, receipts, bio, workspace=None, titles=None, summaries=None):
    """Validate every receipt, then register its --role outputs, producers first. Returns (results, problems).
    A path registered before with other bytes (a rerun) is registered again; the earlier record is kept under
    `superseded` in the receipts file."""
    receipts = Path(receipts)
    done = json.loads(receipts.read_text()) if receipts.exists() else {}
    registered = {r["output_sha256"]: r["artifact"] for r in done.values()
                  if isinstance(r, dict) and r.get("artifact") and r.get("output_sha256")}
    plan, problems = plan_from_receipts(receipt_paths, roles, titles, summaries, bio=bio, workspace=workspace,
                                        registered=registered)
    if problems:
        return [], problems
    results = []
    for entry in plan:
        done = json.loads(receipts.read_text()) if receipts.exists() else {}
        prior = done.get(entry["path"])
        if isinstance(prior, dict) and prior.get("output_sha256") != entry["output_sha256"]:
            done.setdefault("superseded", []).append({"path": entry["path"], **prior})
            del done[entry["path"]]
            receipts.write_text(json.dumps(done, indent=2, allow_nan=False))
        entry = {**entry, "inputs": [registered.get(i, i) for i in entry["inputs"]]}
        step = register_all([entry], question, receipts, bio, workspace)
        results += step
        record = step[-1]
        if record.get("artifact"):
            saved = json.loads(receipts.read_text())
            saved[entry["path"]].update(output_sha256=entry["output_sha256"], run_receipt=entry["run_receipt"])
            receipts.write_text(json.dumps(saved, indent=2, allow_nan=False))
            registered[entry["output_sha256"]] = record["artifact"]
        if record.get("exit_code") not in (0, None):
            break
    return results, []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--plan", type=Path, help="JSON plan (schema above)")
    source.add_argument("--from-receipt", type=Path, action="append", help="run_analysis.py receipt (repeatable)")
    parser.add_argument("--role", action="append", default=[], metavar="OUTPUT=ROLE",
                        help="with --from-receipt: register this output (basename or path) under this output role")
    parser.add_argument("--title", action="append", default=[], metavar="OUTPUT=TEXT")
    parser.add_argument("--summary", action="append", default=[], metavar="OUTPUT=TEXT")
    parser.add_argument("--question", required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--bio", default=os.environ.get("BIO_CLI", "./bin/bio"), help="bio command (shell words)")
    parser.add_argument("--workspace", default=None, help="explicit -w for bio; default honours BIO_WORKSPACE")
    args = parser.parse_args(argv)
    if args.plan:
        if args.role or args.title or args.summary:
            parser.error("--role, --title and --summary go with --from-receipt; a plan states them per entry")
        results = register_all(json.loads(args.plan.read_text()), args.question, args.receipts, args.bio, args.workspace)
    else:
        try:
            roles, titles, summaries = (_pairs(args.role, "--role"), _pairs(args.title, "--title"),
                                        _pairs(args.summary, "--summary"))
        except ValueError as error:
            print(json.dumps({"event": "registrations_refused", "problems": [str(error)]}))
            return 2
        if not roles:
            print(json.dumps({"event": "registrations_refused",
                              "problems": ["name each output to register with --role OUTPUT=ROLE"]}))
            return 2
        results, problems = register_from_receipts(args.from_receipt, roles, args.question, args.receipts, args.bio,
                                                   args.workspace, titles, summaries)
        if problems:
            print(json.dumps({"event": "registrations_refused", "registered": 0, "problems": problems}, allow_nan=False))
            return 2
    failed = [r for r in results if r.get("exit_code") not in (0, None)]
    print(json.dumps({"event": "registrations", "registered": sum(1 for r in results if r.get("artifact")),
                      "failed": len(failed), "receipts": str(args.receipts),
                      "artifacts": [r.get("artifact") for r in results if r.get("artifact")],
                      **({"errors": [{"path": r["path"], "stderr": r.get("stderr") or r.get("stdout")} for r in failed]}
                         if failed else {})}, allow_nan=False))
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
