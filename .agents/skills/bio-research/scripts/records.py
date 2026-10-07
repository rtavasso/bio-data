"""Eligibility and locus records: the two tables peers kept asking for, written once with required fields.

Of 30 peer questions in the PMP22 cohort, 9 asked which datasets or samples another agent had screened and
7 asked for source-verified coordinates with assembly, strand and base convention; 15 answers began "No" or
"None". A published record answers both without a wake-up turn. The cohort invented 23 eligibility tables
and 15 locator manifests with no shared shape; this helper gives them one.

  records.py eligibility --question Q --add dataset=GSE177037 sample=GSM5362321 verdict=eligible reason="..." [--add ...]
  records.py locus --question Q --add gene=PMP22 feature=P1_promoter assembly=GRCh38 chrom=chr17 start=15229777 end=15230777 \\
      strand=- base=1-based source="PMC6607759 Fig 1A; coordinates lifted by the authors" [--add ...]
  ... --register     # bio object add the rows file, then bio register the table with the matching output role

Rows accumulate in outputs/<kind>.rows.json (the registered input) and the table is rewritten as
outputs/<kind>.tsv every time; calls without --register only add rows. `--register` registers the current
table once: repeating it with unchanged rows registers nothing and returns the existing artifact, and after
rows change it registers a new version and reports the artifact it supersedes (outputs/<kind>.registered.json).
Add every row, then register once. Required fields are refused when missing or empty; nothing is inferred; an
unknown field is refused with the nearest valid one, and free text goes in note=.
Publish the table with your first finding (`community publish --artifact`), then answer eligibility or
coordinate questions by pointing at it.
"""
import argparse
import csv
import difflib
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

KINDS = {
    "eligibility": {"file": "eligibility", "role": "eligibility",
                    "required": ("dataset", "verdict", "reason"),
                    "optional": ("sample", "assay", "contrast", "unit", "n", "source", "note"),
                    "verdicts": ("eligible", "excluded", "unresolved"),
                    "title": "Dataset/sample eligibility for this question"},
    "locus": {"file": "locus-map", "role": "source-locator-locus",
              "required": ("gene", "feature", "assembly", "chrom", "start", "end", "strand", "base", "source"),
              "optional": ("species", "note"), "verdicts": None,
              "title": "Source-verified loci with assembly, strand and base convention"},
}
STRANDS = ("+", "-", ".")
BASES = ("0-based", "1-based")


def parse_row(kind, items):
    spec = KINDS[kind]
    row = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"field must be key=value, not {item!r}")
        key, value = item.split("=", 1)
        fields = spec["required"] + spec["optional"]
        if key not in fields:
            near = difflib.get_close_matches(key, fields, n=1, cutoff=0.5)
            raise ValueError(f"unknown field {key!r}" + (f"; did you mean {near[0]!r}?" if near else "")
                             + f" Fields: {', '.join(fields)}; put any other free text in note=\"...\"")
        row[key] = value.strip()
    missing = [k for k in spec["required"] if not row.get(k)]
    if missing:
        raise ValueError(f"{kind} record needs {', '.join(missing)}; a locus without assembly, strand, base or source is not citable")
    if spec["verdicts"] and row["verdict"] not in spec["verdicts"]:
        raise ValueError(f"verdict must be one of {', '.join(spec['verdicts'])}")
    if kind == "locus":
        if row["strand"] not in STRANDS:
            raise ValueError("strand must be +, - or .")
        if row["base"] not in BASES:
            raise ValueError("base must be 0-based or 1-based (the convention of the source, stated by it)")
        if not (row["start"].isdigit() and row["end"].isdigit()) or int(row["start"]) > int(row["end"]):
            raise ValueError("start and end must be integers with start <= end")
    return {k: row.get(k, "") for k in spec["required"] + spec["optional"]}


def write(kind, question_dir, rows):
    spec = KINDS[kind]
    outputs = Path(question_dir) / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    rows_file, table = outputs / f"{spec['file']}.rows.json", outputs / f"{spec['file']}.tsv"
    existing = json.loads(rows_file.read_text()) if rows_file.exists() else []
    seen = {json.dumps(r, sort_keys=True) for r in existing}
    added = [r for r in rows if json.dumps(r, sort_keys=True) not in seen]
    existing.extend(added)
    rows_file.write_text(json.dumps(existing, indent=2, allow_nan=False) + "\n")
    columns = spec["required"] + spec["optional"]
    with table.open("w", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        for row in existing:
            writer.writerow([row.get(c, "") for c in columns])
    return {"rows_file": str(rows_file), "table": str(table), "rows": len(existing), "added": len(added)}


def register(kind, question, written, bio, workspace=None):
    """Register the current table once per distinct content: unchanged rows return the artifact registered for
    them (no new version); changed rows register and name the artifact they supersede. State is kept in
    outputs/<kind>.registered.json beside the rows file."""
    state_file = Path(written["rows_file"]).with_name(f"{KINDS[kind]['file']}.registered.json")
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    rows_sha = hashlib.sha256(Path(written["rows_file"]).read_bytes()).hexdigest()
    if state.get("rows_sha256") == rows_sha and state.get("artifact") and state.get("question") == question:
        return {"step": "register", "exit_code": 0, "artifact": state["artifact"], "unchanged": True,
                "note": f"rows unchanged since {state['artifact']} was registered; nothing new registered"}
    result = _register(kind, question, written, bio, workspace)
    if result.get("exit_code") == 0 and result.get("artifact"):
        previous = state.get("artifact") if state.get("question") == question else None
        if previous and previous != result["artifact"]:
            result["supersedes"] = previous
            result["note"] = f"rows changed: {result['artifact']} supersedes {previous}; cite the new one"
        state_file.write_text(json.dumps({"question": question, "rows_sha256": rows_sha, "artifact": result["artifact"],
                                          "rows": written["rows"],
                                          "history": state.get("history", []) + ([previous] if previous else [])},
                                         indent=2) + "\n")
    return result


def _register(kind, question, written, bio, workspace=None):
    """bio object add the rows file (the input), then bio register the table with this script as the code."""
    base = shlex.split(bio) + (["-w", str(workspace)] if workspace else [])
    added = subprocess.run(base + ["object", "add", written["rows_file"], "--classification", "work"],
                           capture_output=True, text=True, check=False)
    if added.returncode != 0:
        return {"step": "object add", "exit_code": added.returncode, "stderr": added.stderr[-1500:], "stdout": added.stdout[-1500:]}
    blob = json.loads(added.stdout.strip().splitlines()[-1])
    blob = blob.get("blob") or blob.get("sha256")
    spec = KINDS[kind]
    argv = base + ["register", written["table"], "--question", question, "--title", spec["title"],
                   "--summary", f"{written['rows']} {kind} rows written with records.py; verdicts and sources are the author's",
                   "--output-role", spec["role"], "--input", blob, "--code", str(Path(__file__).resolve()),
                   "--parameters", json.dumps({"kind": kind, "records_py": "1"})]
    done = subprocess.run(argv, capture_output=True, text=True, check=False)
    try:
        value = json.loads(done.stdout.strip().splitlines()[-1]) if done.stdout.strip() else {}
    except ValueError:
        value = {}
    return {"step": "register", "exit_code": done.returncode, "input_blob": blob, **value,
            **({"stderr": done.stderr[-1500:]} if done.returncode else {})}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kind", choices=sorted(KINDS))
    parser.add_argument("--question", required=True, help="question id (its folder is resolved under the workspace)")
    parser.add_argument("--question-dir", type=Path, default=None, help="explicit question folder (default: $BIO_WORKSPACE/questions/Q)")
    parser.add_argument("--add", action="append", nargs="+", default=[], metavar="k=v", help="one record; repeat --add per row")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--bio", default=os.environ.get("BIO_CLI", "./bin/bio"))
    parser.add_argument("--workspace", default=None)
    args = parser.parse_args(argv)
    workspace = Path(args.workspace or os.environ.get("BIO_WORKSPACE") or "workspace")
    question_dir = args.question_dir or workspace / "questions" / args.question
    try:
        rows = [parse_row(args.kind, items) for items in args.add]
    except ValueError as error:
        print(json.dumps({"event": "record_refused", "reason": str(error)}))
        return 2
    written = write(args.kind, question_dir, rows)
    result = {"event": f"{args.kind}_record_written", **written}
    if args.register:
        result["registration"] = register(args.kind, args.question, written, args.bio, args.workspace)
    print(json.dumps(result, allow_nan=False))
    return 0 if not args.register or result["registration"].get("exit_code") == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
