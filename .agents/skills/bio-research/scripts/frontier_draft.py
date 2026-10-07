"""Draft frontier items from your own records; you edit and confirm them. Nothing is recorded or published.

Example:
  ./bin/python .agents/skills/bio-research/scripts/frontier_draft.py --question Q --out frontier.draft.json
  # edit frontier.draft.json: set each "kind", rewrite every "EDIT:" text, delete rows you do not keep
  ./bin/python .agents/skills/bio-research/scripts/frontier_draft.py confirm frontier.draft.json --out frontier.json
  ./bin/bio community publish "Finding" --body finding.md --question Q --frontier frontier.json

Rows come only from your own records in this workspace and question folder:
  - each open retrieval gap of the question (`bio work gap`, not withdrawn, closed or resolved): the item it
    blocks, with the gap's receipt as pointer;
  - each sealed prediction marked untestable: a candidate of `outputs/discoveries*.json` with a
    `prediction_lock` whose status, validation mode or result says untestable;
  - each proposal post: a `PROPOSAL*.md` body file in the question folder;
  - the LABBOOK sections whose heading names a discriminating test, a next step (or next experiment or
    investigation), a proposed experiment, an untestable branch or open questions, one row per paragraph or
    list item, and lines labelled `Next step:`, `Discriminating test:` or `Proposed experiment:` anywhere.
Every row's `kind` is `EDIT` (with the source's `suggested_kind` in its draft note) and its text starts `EDIT:`;
`confirm` refuses a row whose kind you did not set to open_question, untestable, proposed_experiment or
next_step (record gaps with `bio work gap`) or whose text you did not rewrite, and strips the draft notes. A
LABBOOK, proposal or prediction pointer is filled in only when those exact bytes are already in this
workspace (`bio work sync`). The helper reads the catalog read-only and never the board.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

FORMAT = "daw.frontier_draft/1"
MARKER = "EDIT:"
KINDS = ("open_question", "untestable", "proposed_experiment", "next_step")  # gaps are recorded with `bio work gap`
ITEM_FIELDS = ("kind", "text", "blocked_by", "watcher_query", "missing_measurement", "pointers", "key", "post")
TEXT_LIMIT = 4000  # daw.commons.frontier.validate_item
FIELD_LIMIT = 1000
READ_LIMIT = 4 * 1024 * 1024
HEADINGS = (  # (pattern on a LABBOOK heading, suggested kind); first match wins
    (re.compile(r"discriminat", re.IGNORECASE), "proposed_experiment"),
    (re.compile(r"next\s+(?:computable\s+)?(?:step|investigation|analysis)", re.IGNORECASE), "next_step"),
    (re.compile(r"next\s+(?:experiment|test|design)|proposed\s+experiment", re.IGNORECASE), "proposed_experiment"),
    (re.compile(r"untestable", re.IGNORECASE), "untestable"),
    (re.compile(r"open\s+questions?", re.IGNORECASE), "open_question"),
)
LABELLED = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:\*\*)?(next\s+(?:computable\s+)?step|discriminating\s+test|"
                      r"proposed\s+experiment)(?:\*\*)?\s*:\s*(.+?)\s*$", re.IGNORECASE)
LABEL_KINDS = {"next": "next_step", "discriminating": "proposed_experiment", "proposed": "proposed_experiment"}
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
ITEM_START = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
UNTESTABLE = re.compile(r"untestable", re.IGNORECASE)


class Catalog:
    """This workspace's catalog, opened read-only (mode=ro)."""

    def __init__(self, workspace):
        self.root = Path(workspace).expanduser().resolve()
        path = self.root / "catalog.sqlite"
        if not path.is_file():
            raise SystemExit(f"no catalog at {path}; pass --workspace or set BIO_WORKSPACE")
        self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.db.row_factory = sqlite3.Row

    def rows(self, sql, values=()):
        return [dict(r) for r in self.db.execute(sql, values)]

    def one(self, sql, values=()):
        found = self.rows(sql, values)
        return found[0] if found else None

    def json_blob(self, sha):
        path = self.root / "blobs/sha256" / sha[:2] / sha
        if not path.is_file() or path.is_symlink() or path.stat().st_size > READ_LIMIT:
            return None
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            return None
        try:
            return json.loads(data)
        except ValueError:
            return None

    def has_blob(self, sha):
        return bool(sha and self.one("SELECT sha256 FROM blob WHERE sha256=?", (sha,)))

    def question(self, qid):
        row = self.one("SELECT * FROM question WHERE id=?", (qid,))
        if not row:
            raise SystemExit(f"unknown question {qid}")
        folder = (self.root / row["path"]).resolve()
        if not folder.is_relative_to((self.root / "questions").resolve()):
            raise SystemExit(f"question folder escapes the workspace: {row['path']}")
        return row, folder


def _clip(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _key(*parts):
    return "draft-" + hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:16]


def row(source, suggested, text, *, where, blocked_by=None, missing=None, pointers=(), why=""):
    item = {"kind": "EDIT", "text": f"{MARKER} " + _clip(text, TEXT_LIMIT - len(MARKER) - 1),
            "pointers": list(pointers), "key": _key(source, where)}
    if blocked_by:
        item["blocked_by"] = _clip(blocked_by, FIELD_LIMIT)
    if missing:
        item["missing_measurement"] = _clip(missing, FIELD_LIMIT)
    item["draft"] = {"source": source, **where, "suggested_kind": suggested, "kinds": list(KINDS),
                     "todo": "Set kind; rewrite the text as the open item you stand behind (" + why + "); keep "
                             "pointers that exist; delete this row if it is not an open item of this question."}
    return item


def _events(catalog, qid):
    events = []
    for event in catalog.rows("SELECT * FROM work_event WHERE question_id=? ORDER BY created,id", (qid,)):
        events.append((event, catalog.json_blob(event["body_blob"])))
    return events


def gap_rows(catalog, qid):
    events = _events(catalog, qid)
    ended = set()
    for event, payload in events:
        if not isinstance(payload, dict):
            continue
        target = payload.get("event") or payload.get("item") or payload.get("gap")
        if event["kind"] in ("retrieval_gap_withdrawal", "retrieval_gap_resolution", "retrieval_resolution"):
            ended.add(target)
        elif event["kind"] == "frontier_item_status":
            if payload.get("status") in ("closed", "withdrawn"):
                ended.add(target)
            elif payload.get("status") == "open":
                ended.discard(target)
    out = []
    for event, gap in events:
        if event["kind"] != "retrieval_gap" or event["id"] in ended or not isinstance(gap, dict):
            continue
        need = gap.get("desired_information")
        if not isinstance(need, str) or not need.strip():
            continue  # a pre-v3 freeform event is a notebook entry, not a gap item
        failed = gap.get("why_current_tools_failed") or "retrieval failed"
        pointers = [{"kind": "receipt", "id": gap["evidence_blob"]}] if catalog.has_blob(gap.get("evidence_blob")) else []
        out.append(row("retrieval_gap", "next_step", f"What becomes computable once this is retrieved: {need}",
                       where={"event": event["id"]}, blocked_by=f"retrieval gap {event['id']}: {failed}",
                       missing=need, pointers=pointers,
                       why="the computation or measurement this data would enable, and what its outcome decides"))
    return out


def prediction_rows(catalog, folder):
    out = []
    ledgers = sorted(p for p in (folder / "outputs").rglob("discoveries*.json") if p.is_file() and not p.is_symlink()) \
        if (folder / "outputs").is_dir() else []
    for path in ledgers:
        if path.stat().st_size > READ_LIMIT:
            continue
        try:
            ledger = json.loads(path.read_text())
        except (ValueError, UnicodeDecodeError):
            continue
        for candidate in ledger.get("candidates") or [] if isinstance(ledger, dict) else []:
            if not isinstance(candidate, dict) or not candidate.get("prediction_lock"):
                continue  # only sealed predictions
            marks = " ".join(str(candidate.get(k) or "") for k in ("status", "validation_mode", "validation_result"))
            if not UNTESTABLE.search(marks):
                continue
            sha = candidate.get("prediction_sha256")
            pointers = [{"kind": "receipt", "id": sha}] if catalog.has_blob(sha) else []
            text = candidate.get("next_test") or candidate.get("claim") or candidate.get("id")
            out.append(row("sealed_prediction", "untestable", f"{candidate.get('id')}: {text}",
                           where={"file": str(path.relative_to(folder)), "candidate": candidate.get("id"),
                                  "prediction_lock": candidate.get("prediction_lock")},
                           blocked_by=candidate.get("validation_result"), pointers=pointers,
                           why="why the available data cannot test it and what measurement would"))
    return out


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proposal_rows(catalog, folder):
    out = []
    for path in sorted(folder.iterdir()):
        if not (path.is_file() and not path.is_symlink() and path.name.upper().startswith("PROPOSAL")
                and path.suffix.lower() == ".md") or path.stat().st_size > READ_LIMIT:
            continue
        text = path.read_text(errors="replace")
        lines = [line.strip() for line in text.splitlines()]
        title = next((HEADING.match(x).group(2) for x in lines if HEADING.match(x)), path.stem)
        body = next((x for x in lines if x and not HEADING.match(x)), "")
        sha = _sha(path)
        pointers = [{"kind": "locator", "id": sha, "locator": "line=1"}] if catalog.has_blob(sha) else []
        out.append(row("proposal_post", "proposed_experiment", f"{title}: {body}",
                       where={"file": path.name, "sha256": sha}, pointers=pointers,
                       why="the experiment the proposal states, its readout and what each outcome decides"))
    return out


def _blocks(lines, start, end):
    """Paragraphs and list items between two headings, as (first line number, text)."""
    blocks, current, first = [], [], None
    for number in range(start, end):
        line = lines[number]
        if not line.strip() or ITEM_START.match(line):
            if current:
                blocks.append((first, " ".join(current)))
            current, first = ([line.strip()], number + 1) if line.strip() else ([], None)
            continue
        if not current:
            first = number + 1
        current.append(line.strip())
    if current:
        blocks.append((first, " ".join(current)))
    return [(n, ITEM_START.sub("", text, count=1).strip()) for n, text in blocks if text.strip()]


def labbook_rows(catalog, folder, max_rows):
    path = folder / "LABBOOK.md"
    if not path.is_file() or path.is_symlink() or path.stat().st_size > READ_LIMIT:
        return [], "no LABBOOK.md in the question folder"
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    sha = _sha(path)
    synced = catalog.has_blob(sha)
    headings = [(n, HEADING.match(line)) for n, line in enumerate(lines) if HEADING.match(line)]
    out, taken = [], set()

    def pointer(line):
        return [{"kind": "locator", "id": sha, "locator": f"line={line}"}] if synced else []

    for index, (number, match) in enumerate(headings):
        title = match.group(2)
        suggested = next((kind for pattern, kind in HEADINGS if pattern.search(title)), None)
        if not suggested:
            continue
        level = len(match.group(1))
        end = next((n for n, m in headings[index + 1:] if len(m.group(1)) <= level), len(lines))
        for line, block in _blocks(lines, number + 1, end)[:max_rows]:
            taken.add(line)
            out.append(row("labbook_section", suggested, block, where={"file": "LABBOOK.md", "heading": title,
                                                                        "line": line, "sha256": sha},
                           pointers=pointer(line),
                           why="one computable step, experiment, branch or question, with what would settle it"))
    for number, line in enumerate(lines, 1):
        match = LABELLED.match(line)
        if match and number not in taken:
            suggested = LABEL_KINDS[match.group(1).split()[0].casefold()]
            out.append(row("labbook_line", suggested, match.group(2), where={"file": "LABBOOK.md", "line": number,
                                                                             "label": match.group(1), "sha256": sha},
                           pointers=pointer(number), why="the labelled step as an open item"))
    return out, None if synced else "LABBOOK.md differs from every synced snapshot: run `bio work sync` to point at it"


def recorded(catalog, qid):
    """Non-gap frontier items this question already records (newest status wins), for the author's reference."""
    items, statuses = {}, {}
    for event, payload in _events(catalog, qid):
        if event["kind"] == "frontier_item" and isinstance(payload, dict):
            items[event["id"]] = {"event": event["id"], "kind": payload.get("kind"), "text": payload.get("text")}
        elif event["kind"] == "frontier_item_status" and isinstance(payload, dict):
            statuses[payload.get("item")] = payload.get("status")
    return [{**item, "status": statuses.get(item["event"], "open")} for item in items.values()
            if item["kind"] != "gap"]


def draft(workspace, question, *, max_rows=20):
    """The draft document: proposed rows by source, rows already recorded, and notes on what was not read."""
    catalog = Catalog(workspace)
    record, folder = catalog.question(question)
    notes = []
    rows = gap_rows(catalog, question) + prediction_rows(catalog, folder) + proposal_rows(catalog, folder)
    labbook, note = labbook_rows(catalog, folder, max_rows)
    rows += labbook
    if note:
        notes.append(note)
    sources = {}
    for item in rows:
        sources[item["draft"]["source"]] = sources.get(item["draft"]["source"], 0) + 1
    return {"format": FORMAT, "workspace": str(catalog.root), "question": question, "title": record["title"],
            "status": record["status"],
            "note": "A draft from your own records. Set each kind, rewrite every EDIT: text, delete rows you do not "
                    "keep, then run `frontier_draft.py confirm`. Nothing here was recorded or published.",
            "items": rows, "sources": sources, "already_recorded": recorded(catalog, question), "notes": notes}


def confirm(document):
    """(items, problems): the edited draft as a `--frontier` list, or the rows that still need the author."""
    items = document.get("items") if isinstance(document, dict) else document
    if not isinstance(items, list) or not items:
        return None, ["the draft has no items (keep at least one, or do not pass --frontier)"]
    out, problems = [], []
    for n, item in enumerate(items):
        if not isinstance(item, dict):
            problems.append(f"item {n}: not an object")
            continue
        if item.get("kind") not in KINDS:
            problems.append(f"item {n}: set kind to one of {', '.join(KINDS)} (gaps are recorded with bio work gap)")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip() or MARKER in text:
            problems.append(f"item {n}: rewrite the {MARKER} text as the open item (or delete the row)")
        elif len(text) > TEXT_LIMIT:
            problems.append(f"item {n}: text longer than {TEXT_LIMIT} characters")
        for field in ("blocked_by", "missing_measurement"):
            if item.get(field) is not None and (not isinstance(item[field], str) or MARKER in item[field]):
                problems.append(f"item {n}: {field} must be your text")
        out.append({k: item[k] for k in ITEM_FIELDS if item.get(k) not in (None, [], "")})
    return (None if problems else out), problems


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "confirm":
        parser = argparse.ArgumentParser(prog="frontier_draft.py confirm", description="Check an edited draft and "
                                         "write the item list for `community publish --frontier`.")
        parser.add_argument("draft", type=Path)
        parser.add_argument("--out", type=Path, required=True)
        args = parser.parse_args(argv[1:])
        items, problems = confirm(json.loads(args.draft.read_text()))
        if problems:
            print(json.dumps({"confirmed": False, "problems": problems}, indent=2))
            return 2
        args.out.write_text(json.dumps(items, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        print(json.dumps({"confirmed": True, "items": len(items), "out": str(args.out)}))
        return 0
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workspace", type=Path, default=Path(os.environ.get("BIO_WORKSPACE", "workspace")))
    parser.add_argument("--question", required=True)
    parser.add_argument("--max-rows", type=int, default=20, help="rows per LABBOOK section")
    parser.add_argument("--out", type=Path, help="write the draft here (default: stdout)")
    args = parser.parse_args(argv)
    document = draft(args.workspace, args.question, max_rows=max(1, args.max_rows))
    text = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.out:
        args.out.write_text(text)
        print(json.dumps({"draft": str(args.out), "items": len(document["items"]), "sources": document["sources"]}))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
