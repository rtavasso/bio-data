"""Draft ledger claims from your own registered tables; you edit and confirm them. Nothing is published.

Example:
  ./bin/python .agents/skills/bio-research/scripts/claims_draft.py --question Q --out claims.draft.json
  # edit claims.draft.json: rewrite every "EDIT:" text, status and scope field, delete rows you do not claim
  ./bin/python .agents/skills/bio-research/scripts/claims_draft.py confirm claims.draft.json --out claims.json
  ./bin/bio community publish "Finding" --body finding.md --question Q --artifact ARTIFACT --claims claims.json

The draft proposes one entry per named row of each artifact you produced in the question (or each
`--artifact`): TSV/CSV outputs give one entry per data row, keyed by its first column, with one
`locator` pointer per numeric cell (`row=KEY;col=NAME`, the cell grammar the write-up checker resolves;
a repeated key is addressed as `row=#N`); JSON outputs give one entry per top-level key (or per record
of a top-level list) with `key=PATH` pointers to its numeric values. Each entry's text starts `EDIT:` and
lists the cells verbatim; its status and every scope field are `EDIT:` placeholders too. `confirm`
refuses an entry whose text, status or any scope field the author did not set (delete a scope field you
do not state), and strips the `draft` notes. The helper reads this workspace's catalog and blobs read-only, never the board, and never
decides what a row means: status, scope and wording are the author's.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

FORMAT = "daw.claims_draft/1"
MARKER = "EDIT:"
STATUSES = ("supported", "descriptive", "untestable", "withdrawn")
SCOPE_FIELDS = ("species", "context", "endpoint", "direction")  # daw.commons.claims.Scope
NEEDS_POINTER = ("supported", "descriptive")
TABLE_SUFFIXES = (".tsv", ".tab", ".csv", ".txt")  # what daw.commons.locators.read_table accepts
READ_LIMIT = 8 * 1024 * 1024
NUMBER = re.compile(r"^[-+−]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?%?$")
KEY_SEGMENT = re.compile(r"^[^.\[\]]+$")
INDEX_LIKE = re.compile(r"^#\d")


def encode(value):
    """Percent-encode a locator value (spaces, `;`, `,`, brackets and parentheses are not allowed raw)."""
    return quote(str(value), safe="_.-~+:/")


def numeric(text):
    if not isinstance(text, str):
        return False
    value = text.strip()
    if not NUMBER.match(value):
        return False
    try:
        return math.isfinite(float(value.rstrip("%").replace("−", "-")))
    except ValueError:
        return False


class Catalog:
    """This workspace's catalog, opened read-only (mode=ro), and its content-addressed blobs."""

    def __init__(self, workspace):
        self.root = Path(workspace).expanduser().resolve()
        path = self.root / "catalog.sqlite"
        if not path.is_file():
            raise SystemExit(f"no catalog at {path}; pass --workspace or set BIO_WORKSPACE")
        self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.db.row_factory = sqlite3.Row

    def rows(self, sql, values=()):
        return [dict(r) for r in self.db.execute(sql, values)]

    def blob(self, sha):
        """Bytes of a blob after checking its sha256, or (None, reason)."""
        path = self.root / "blobs/sha256" / sha[:2] / sha
        if not path.is_file() or path.is_symlink():
            return None, "the output bytes are absent from this workspace (present: false)"
        if path.stat().st_size > READ_LIMIT:
            return None, f"the output is larger than {READ_LIMIT // (1024 * 1024)} MB"
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            return None, "the output bytes do not match their sha256"
        return data, None


def selected(catalog, question=None, artifacts=()):
    if artifacts:
        found = catalog.rows(f"SELECT * FROM artifact WHERE id IN ({','.join('?' for _ in artifacts)})", list(artifacts))
        missing = sorted(set(artifacts) - {r["id"] for r in found})
        if missing:
            raise SystemExit(f"not registered in this workspace: {', '.join(missing)}")
        return sorted(found, key=lambda r: (r["created"], r["id"]))
    sql = ("SELECT DISTINCT a.* FROM artifact a JOIN question_artifact qa ON qa.artifact_id=a.id "
           "WHERE qa.relationship='produced'")
    params = []
    if question:
        sql += " AND qa.question_id=?"
        params.append(question)
    return catalog.rows(sql + " ORDER BY a.created,a.id", params)


def table(data, name):
    """(header, rows) exactly as the write-up checker reads a TSV/CSV output (locators.read_table)."""
    text = data.decode("utf-8-sig")
    suffix = Path(name).suffix.lower()
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("##")]
    if not lines:
        return [], []
    delimiter = "," if suffix == ".csv" or (suffix == ".txt" and "\t" not in lines[0]) else "\t"
    parsed = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))
    return parsed[0], parsed[1:]


def entry(aid, title, label, cells, where):
    shown = "; ".join(f"{name} = {value}" for name, _, value in cells)
    # Status and scope are the author's: placeholders that `confirm` refuses until set (a scope field may be deleted).
    return {"text": f"{MARKER} {title}: {label}: {shown}", "status": f"{MARKER} " + "|".join(STATUSES),
            "scope": {field: f"{MARKER} set or delete" for field in SCOPE_FIELDS},
            "pointers": [{"kind": "locator", "id": aid, "locator": locator} for _, locator, _ in cells],
            "draft": {"artifact": aid, "row": label, **where,
                      "cells": [{"name": name, "locator": locator, "value": value} for name, locator, value in cells],
                      "todo": "Rewrite the text as the finding this row supports, keeping its numbers as shown; set "
                              "status and scope; delete this entry if you do not claim it."}}


def table_entries(aid, title, data, name, columns, max_rows, max_columns):
    header, rows = table(data, name)
    if not header or not rows:
        return [], "the table has no data rows"
    keys = [row[0].strip() if row else "" for row in rows]
    counts = {k: keys.count(k) for k in keys}
    wanted = [c for c in range(1, len(header)) if not columns or header[c].strip() in columns]
    unique_columns = {header[c].strip() for c in wanted if [h.strip() for h in header].count(header[c].strip()) == 1}
    out = []
    for n, row in enumerate(rows, 1):
        key = keys[n - 1]
        if not key:
            continue
        if counts[key] == 1 and not INDEX_LIKE.match(key):
            selector = encode(key)
        else:
            selector = f"#{n}"  # a repeated or index-like key is addressed by its 1-based data row
        cells = []
        for c in wanted:
            column = header[c].strip()
            if c < len(row) and numeric(row[c]):
                col = encode(column) if column in unique_columns and column and not INDEX_LIKE.match(column) \
                    else f"#{c + 1}"
                cells.append((column or f"column {c + 1}", f"row={selector};col={col}", row[c].strip()))
        if cells:
            out.append(entry(aid, title, key, cells[:max_columns], {"row_index": n, "output": name}))
        if len(out) >= max_rows:
            break
    return out, None if out else "no row has a numeric cell"


def _leaves(prefix, value, max_columns):
    """Numeric values directly under a JSON object (one level), as (name, key path, text)."""
    cells = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and KEY_SEGMENT.match(key) and isinstance(item, (int, float)) \
                    and not isinstance(item, bool) and math.isfinite(item):
                cells.append((key, f"key={encode(prefix + '.' + key)}", json.dumps(item)))
    return cells[:max_columns]


def json_entries(aid, title, data, name, max_rows, max_columns):
    try:
        value = json.loads(data.decode("utf-8-sig"))
    except ValueError:
        return [], "the output is not valid JSON"
    out = []

    def records(prefix, items):
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            label = next((v for v in item.values() if isinstance(v, str) and v.strip()), f"{prefix}[{i}]")
            cells = _leaves(f"{prefix}[{i}]", item, max_columns)
            if cells:
                out.append(entry(aid, title, label, cells, {"key": f"{prefix}[{i}]", "output": name}))
            if len(out) >= max_rows:
                return

    if isinstance(value, list):
        records("", value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if len(out) >= max_rows:
                break
            if not (isinstance(key, str) and KEY_SEGMENT.match(key)):
                continue
            if isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item):
                out.append(entry(aid, title, key, [(key, f"key={encode(key)}", json.dumps(item))], {"key": key, "output": name}))
            elif isinstance(item, dict):
                cells = _leaves(key, item, max_columns)
                if cells:
                    out.append(entry(aid, title, key, cells, {"key": key, "output": name}))
                for sub, value in item.items():  # one more level of named groups ({"groups": {"A": {...}}})
                    if isinstance(sub, str) and KEY_SEGMENT.match(sub) and isinstance(value, dict) \
                            and len(out) < max_rows:
                        cells = _leaves(f"{key}.{sub}", value, max_columns)
                        if cells:
                            out.append(entry(aid, title, f"{key}.{sub}", cells, {"key": f"{key}.{sub}", "output": name}))
            elif isinstance(item, list):
                records(key, item)
    return out[:max_rows], None if out else "no numeric values under named keys"


def draft(workspace, question=None, artifacts=(), *, columns=(), max_rows=50, max_columns=6):
    """The draft document: proposed entries plus every artifact skipped and why."""
    catalog = Catalog(workspace)
    proposed, skipped = [], []
    for row in selected(catalog, question, artifacts):
        manifest_bytes, reason = catalog.blob(row["manifest_blob"])
        manifest = json.loads(manifest_bytes) if manifest_bytes else {}
        output = manifest.get("output") if isinstance(manifest.get("output"), dict) else {}
        name = str(output.get("name") or "")
        title = str(manifest.get("title") or name or row["output_role"])[:120]
        data, reason = catalog.blob(row["output_blob"])
        if data is None:
            skipped.append({"artifact": row["id"], "output": name or None, "reason": reason})
            continue
        suffix = Path(name).suffix.lower()
        try:
            if suffix in TABLE_SUFFIXES:
                found, reason = table_entries(row["id"], title, data, name, set(columns), max_rows, max_columns)
            elif suffix == ".json":
                found, reason = json_entries(row["id"], title, data, name, max_rows, max_columns)
            else:
                found, reason = [], (f"not a TSV/CSV/JSON output ({name})" if name else
                                     "the manifest names no output file, so the checker cannot read a cell")
        except UnicodeDecodeError:
            found, reason = [], "the output is not UTF-8 text"
        proposed += found
        if reason:
            skipped.append({"artifact": row["id"], "output": name or None, "reason": reason})
    return {"format": FORMAT, "workspace": str(catalog.root), "question": question,
            "note": "A draft from your own registered outputs. Rewrite every EDIT: text, set every EDIT: status and scope "
                    "field (delete scope fields you do not state), delete "
                    "entries you do not claim, then run `claims_draft.py confirm`. Artifact pointers must be in the "
                    "post's --artifact list or already published. Nothing here was published.",
            "claims": proposed, "skipped": skipped}


def confirm(document):
    """(claims, problems): the edited draft as a `--claims` list, or the entries that still need the author."""
    claims = document.get("claims") if isinstance(document, dict) else document
    if not isinstance(claims, list) or not claims:
        return None, ["the draft has no claims (keep at least one, or do not pass --claims)"]
    out, problems = [], []
    for n, item in enumerate(claims):
        if not isinstance(item, dict):
            problems.append(f"claim {n}: not an object")
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip() or MARKER in text:
            problems.append(f"claim {n}: rewrite the {MARKER} text as your finding (or delete the entry)")
        if item.get("status") not in STATUSES:
            problems.append(f"claim {n}: set status to one of {', '.join(STATUSES)}")
        scope = item.get("scope", {})
        unset = ([k for k, v in scope.items() if v is not None and (not isinstance(v, str) or MARKER in v or not v.strip())]
                 if isinstance(scope, dict) else ["(not an object)"])
        if unset:
            problems.append(f"claim {n}: set or delete scope {', '.join(unset)}")
        pointers = item.get("pointers") or []
        if item.get("status") in NEEDS_POINTER and not pointers:
            problems.append(f"claim {n}: a {item.get('status')} claim needs at least one pointer")
        out.append({k: v for k, v in item.items() if k in ("text", "status", "scope", "pointers")})
    return (None if problems else out), problems


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "confirm":
        parser = argparse.ArgumentParser(prog="claims_draft.py confirm", description="Check an edited draft and "
                                         "write the claims list for `community publish --claims`.")
        parser.add_argument("draft", type=Path)
        parser.add_argument("--out", type=Path, required=True)
        args = parser.parse_args(argv[1:])
        claims, problems = confirm(json.loads(args.draft.read_text()))
        if problems:
            print(json.dumps({"confirmed": False, "problems": problems}, indent=2))
            return 2
        args.out.write_text(json.dumps(claims, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        print(json.dumps({"confirmed": True, "claims": len(claims), "out": str(args.out)}))
        return 0
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workspace", type=Path, default=Path(os.environ.get("BIO_WORKSPACE", "workspace")))
    parser.add_argument("--question", help="artifacts produced in this question (default: every produced artifact)")
    parser.add_argument("--artifact", action="append", default=[], help="draft from these artifacts only (repeatable)")
    parser.add_argument("--column", action="append", default=[], help="only these table columns (repeatable)")
    parser.add_argument("--max-rows", type=int, default=50, help="entries per artifact")
    parser.add_argument("--max-columns", type=int, default=6, help="pointers per entry")
    parser.add_argument("--out", type=Path, help="write the draft here (default: stdout)")
    args = parser.parse_args(argv)
    document = draft(args.workspace, args.question, args.artifact, columns=args.column,
                     max_rows=max(1, args.max_rows), max_columns=max(1, args.max_columns))
    text = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.out:
        args.out.write_text(text)
        print(json.dumps({"draft": str(args.out), "claims": len(document["claims"]), "skipped": len(document["skipped"])}))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
