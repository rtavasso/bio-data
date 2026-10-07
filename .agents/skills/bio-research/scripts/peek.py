"""Inspect a local file read-only with bounded output; never executes, renders or imports anything from it.

Examples:
  ./bin/python .agents/skills/bio-research/scripts/peek.py inputs/PMC123.xml            # JATS/XML: title, abstract head, section headings, table/figure captions
  ./bin/python .agents/skills/bio-research/scripts/peek.py outputs/table.tsv --rows 5    # header, dtypes guess, first rows, row count
  ./bin/python .agents/skills/bio-research/scripts/peek.py supp.zip                      # members with sizes; --member NAME peeks one
  ./bin/python .agents/skills/bio-research/scripts/peek.py supp.xlsx                     # sheets, dimensions, first rows of each
  ./bin/python .agents/skills/bio-research/scripts/peek.py record.json                   # key tree with types and list lengths
  ./bin/python .agents/skills/bio-research/scripts/peek.py paper.txt --grep "PMP22|Schwann"   # matching lines with numbers

The whole result is capped (--max-chars, default 6000, at most 12000) so one call fits a tool result; it replaces the
one-off inspect_*.py scripts and whole-file reads that dominated the cohort's context. A saved HTML
challenge page, a JSON error body or a "No result can be found" stub is reported as such, not as a
source. Formulas, macros and serialised objects are never evaluated: xlsx cells are read as values only.
"""
import argparse
import csv
import gzip
import io
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path

MAX_CHARS = 6000
HARD_CAP = 12000  # 95/246 cohort uses raised --max-chars, up to 34,000: narrow instead
TEXT_SUFFIXES = {".txt", ".md", ".tsv", ".tab", ".csv", ".json", ".xml", ".nxml", ".html", ".htm", ".gtf", ".gff", ".bed",
                 ".soft", ".fa", ".fasta", ".log", ".yaml", ".yml", ".toml"}
NOT_A_SOURCE = (("recaptcha", "a reCAPTCHA challenge page"), ("preparing to download", "a PMC 'Preparing to download' interstitial"),
                ("no result can be found", "a BioC 'No result can be found' stub"), ("client challenge", "a publisher bot challenge"),
                ("access denied", "an access-denied page"), ("not open access", "an EPMC 'not open access' notice"))
NUMBER = re.compile(r"[-+−]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _open(path):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rb"), path.with_suffix("")
    return path.open("rb"), path


def classify_text(head):
    low = head.lower()
    if "<html" in low or "<!doctype html" in low:
        for needle, label in NOT_A_SOURCE:
            if needle in low:
                return "not_a_source", label
        return "html", "an HTML page (publisher/abstract page, not an article XML)"
    if low.lstrip().startswith("{") and '"error' in low[:400]:
        return "not_a_source", "a JSON error body"
    for needle, label in NOT_A_SOURCE:
        if needle in low and len(head) < 4000:
            return "not_a_source", label
    return "text", None


def peek_xml(data, limit):
    from defusedxml import ElementTree
    try:
        root = ElementTree.fromstring(data)
    except Exception as error:  # noqa: BLE001 - the error is the finding
        return {"kind": "xml", "parse_error": f"{type(error).__name__}: {str(error)[:200]}"}

    def text(node):
        return " ".join("".join(node.itertext()).split()) if node is not None else ""
    out = {"kind": "xml", "root": root.tag, "bytes": len(data)}
    title = root.find(".//article-title")
    if title is not None:
        out["article_title"] = text(title)[:300]
    ids = {node.get("pub-id-type"): text(node) for node in root.iter("article-id")}
    if ids:
        out["article_ids"] = ids
    abstract = root.find(".//abstract")
    if abstract is not None:
        out["abstract_head"] = text(abstract)[:600]
    out["section_titles"] = [text(t)[:80] for t in root.iter("title") if t is not title][:40]
    captions = []
    for tag in ("table-wrap", "fig", "supplementary-material"):
        for node in root.iter(tag):
            label, cap = node.find("label"), node.find("caption")
            captions.append({"kind": tag, "id": node.get("id"), "label": text(label)[:40], "caption": text(cap)[:200]})
    if captions:
        out["captions"] = captions[:30]
    if not out.get("article_title"):
        out["children"] = sorted({child.tag for child in root})[:40]
        out["text_head"] = text(root)[:limit // 3]
    return out


def peek_table(text, name, rows, delimiter=None):
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("##")]
    if not lines:
        return {"kind": "table", "rows": 0}
    if delimiter is None:
        delimiter = "\t" if "\t" in lines[0] else ("," if name.lower().endswith(".csv") or "," in lines[0] else None)
    if delimiter is None:
        return {"kind": "text", "lines": len(lines), "head": "\n".join(lines[:rows])}
    parsed = list(csv.reader(io.StringIO("\n".join(lines[: rows + 1 + 200])), delimiter=delimiter))
    header, body = parsed[0], parsed[1:]
    kinds = []
    for col in range(len(header)):
        values = [r[col] for r in body if col < len(r) and r[col] not in ("", "NA", "NaN", "null")]
        numeric = sum(bool(NUMBER.fullmatch(v)) for v in values)
        kinds.append("numeric" if values and numeric == len(values) else "mixed" if numeric else "text")
    return {"kind": "table", "delimiter": "tab" if delimiter == "\t" else delimiter, "columns": len(header), "rows": len(lines) - 1,
            "header": header[:60], "column_kinds_from_first_200_rows": kinds[:60], "first_rows": body[:rows]}


def key_tree(value, depth=0, max_depth=4):
    if isinstance(value, dict):
        if depth >= max_depth:
            return f"object({len(value)} keys)"
        return {k: key_tree(v, depth + 1, max_depth) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        inner = key_tree(value[0], depth + 1, max_depth) if value else "empty"
        return {"list_length": len(value), "first_item": inner}
    if isinstance(value, str):
        return f"str({len(value)})" if len(value) > 40 else repr(value)
    return type(value).__name__ if value is not None else "null"


def peek_archive(path, member, rows, limit):
    out = {"kind": "archive", "members": []}
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            out["members"] = [{"name": i.filename, "bytes": i.file_size} for i in infos][:200]
            out["member_count"] = len(infos)
            if member:
                with archive.open(member) as stream:
                    return {**out, "member": member, "peek": peek_bytes(stream.read(8 << 20), member, rows, limit)}
            return out
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        out["members"] = [{"name": m.name, "bytes": m.size} for m in members if m.isfile()][:200]
        out["member_count"] = len(members)
        if member:
            stream = archive.extractfile(member)
            return {**out, "member": member, "peek": peek_bytes(stream.read(8 << 20), member, rows, limit)}
    return out


def peek_xlsx(path, rows):
    import openpyxl
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = []
    for sheet in book.worksheets:
        head = []
        for n, row in enumerate(sheet.iter_rows(values_only=True)):
            if n >= rows:
                break
            head.append([("" if v is None else str(v))[:40] for v in row[:30]])
        sheets.append({"title": sheet.title, "dimensions": sheet.calculate_dimension() if hasattr(sheet, "calculate_dimension") else None,
                       "first_rows": head})
    return {"kind": "xlsx", "sheets": sheets, "note": "cell values only; formulas and macros are not evaluated"}


def peek_bytes(data, name, rows, limit, grep=None):
    head = data[:4096].decode("utf-8", errors="replace")
    suffix = Path(name).suffix.lower()
    if data[:2] == b"PK" and suffix in {".xlsx", ".xlsm"}:
        return {"kind": "xlsx", "note": "save to disk and peek the path for sheet heads"}
    if data[:5] == b"%PDF-":
        return {"kind": "pdf", "bytes": len(data), "note": "binary PDF; no parser here. Record the locator and use a text/XML route."}
    if b"\x00" in data[:4096]:
        return {"kind": "binary", "bytes": len(data), "magic": data[:8].hex()}
    kind, label = classify_text(head)
    if kind == "not_a_source":
        return {"kind": "not_a_source", "bytes": len(data), "what": label, "head": head[:300],
                "advice": "do not keep this as a source; try another route and record the failed one with bio work gap"}
    text = data.decode("utf-8", errors="replace")
    if grep:
        pattern = re.compile(grep)
        hits = [{"line": n + 1, "text": line.strip()[:200]} for n, line in enumerate(text.splitlines()) if pattern.search(line)]
        return {"kind": "grep", "pattern": grep, "matches": len(hits), "lines": hits[:60]}
    if kind == "html":
        return {"kind": "html", "bytes": len(data), "what": label, "title": (re.search(r"<title>(.*?)</title>", text, re.S | re.I) or [None, ""])[1][:200]}
    stripped = text.lstrip()
    if suffix in {".xml", ".nxml"} or stripped.startswith("<?xml") or stripped.startswith("<article"):
        return peek_xml(data, limit)
    if suffix == ".json" or stripped[:1] in "{[":
        try:
            return {"kind": "json", "bytes": len(data), "tree": key_tree(json.loads(text))}
        except ValueError as error:
            return {"kind": "text", "json_error": str(error)[:120], "head": text[:limit // 2]}
    if suffix in {".tsv", ".tab", ".csv", ".txt", ".gtf", ".gff", ".bed", ".soft"} or "\t" in head:
        return peek_table(text, name, rows)
    return {"kind": "text", "bytes": len(data), "lines": text.count("\n"), "head": text[:limit // 2]}


def peek(path, *, rows=5, member=None, grep=None, limit=MAX_CHARS):
    path = Path(path)
    if not path.is_file():
        return {"error": "not a regular file", "path": str(path)}
    result = {"path": str(path), "bytes": path.stat().st_size}
    if path.suffix.lower() in {".zip", ".tar", ".tgz"} or (path.suffixes[-2:] == [".tar", ".gz"]) or zipfile.is_zipfile(path):
        if path.suffix.lower() in {".xlsx", ".xlsm"}:
            return {**result, **peek_xlsx(path, rows)}
        return {**result, **peek_archive(path, member, rows, limit)}
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        return {**result, **peek_xlsx(path, rows)}
    stream, logical = _open(path)
    with stream:
        data = stream.read(64 << 20)
    return {**result, **peek_bytes(data, logical.name, rows, limit, grep)}


def render(value, limit):
    text = json.dumps(value, indent=1, ensure_ascii=False, allow_nan=False)
    if len(text) <= limit:
        return text
    note = f'\n… [truncated to {limit} chars; narrow with --rows, --member or --grep]'
    return text[: max(limit - len(note), 0)] + note


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path)
    parser.add_argument("--rows", type=int, default=5)
    parser.add_argument("--member", default=None, help="archive member to peek")
    parser.add_argument("--grep", default=None, help="regex; print matching lines instead of a head")
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS)
    args = parser.parse_args(argv)
    limit, capped = min(args.max_chars, HARD_CAP), args.max_chars > HARD_CAP
    if capped:
        print(f"peek.py: --max-chars {args.max_chars} capped at {HARD_CAP}; narrow with --rows, --member or --grep "
              "instead of reading more of the file", file=sys.stderr)
    result = peek(args.path, rows=args.rows, member=args.member, grep=args.grep, limit=limit)
    if capped:
        result = {"max_chars_capped": f"{args.max_chars} -> {HARD_CAP}; narrow with --rows, --member or --grep", **result}
    print(render(result, limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
