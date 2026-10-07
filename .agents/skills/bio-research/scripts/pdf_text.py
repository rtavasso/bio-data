"""Extract a PDF's text page by page with pypdf; print a bounded summary, write the full text to --out.

Examples:
  ./bin/python .agents/skills/bio-research/scripts/pdf_text.py sources/paper.pdf --out outputs/paper.txt
  ./bin/python .agents/skills/bio-research/scripts/pdf_text.py supp.pdf --pages 3-5 --grep "PMP22|Table S2"

Text extraction only: pypdf parses the page content streams; JavaScript, actions, forms and embedded files
are never run or extracted. The summary (pages, characters per page, first lines or grep hits) is capped by
--max-chars (default and maximum 12000). An encrypted PDF that cannot be opened with an empty password, and
pages with no extractable text (scanned images), are reported explicitly: no text is not the same as no
content. --out holds each page's text after a `=== page N ===` line; read it with peek.py --grep.
"""
import argparse
import json
import re
import sys
from pathlib import Path

MAX_CHARS = 12000
FIRST_LINES = 3


def page_range(spec, count):
    """1-based inclusive ranges, `1-5,8`; None means every page."""
    if not spec:
        return list(range(count))
    chosen = []
    for part in spec.split(","):
        part = part.strip()
        match = re.fullmatch(r"(\d+)(?:-(\d+)?)?", part)
        if not match:
            raise ValueError(f"invalid --pages part: {part!r} (use 1-5,8)")
        start = int(match.group(1))
        end = start if match.group(2) is None and "-" not in part else int(match.group(2) or count)
        if start < 1 or end < start:
            raise ValueError(f"invalid --pages range: {part!r}")
        chosen += [i for i in range(start - 1, min(end, count)) if i not in chosen]
    return chosen


def extract(path, pages=None):
    """{"pages", "encrypted", "status", "texts": {index: text}, "errors": {index: message}}."""
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:
        return {"status": "pypdf_unavailable", "error": "pypdf is not installed in this interpreter; use ./bin/python"}
    try:
        reader = PdfReader(str(path), strict=False)
    except (PdfReadError, OSError, ValueError) as error:
        return {"status": "unreadable", "error": f"{type(error).__name__}: {error}"}
    result = {"encrypted": bool(reader.is_encrypted)}
    if reader.is_encrypted:
        try:
            opened = reader.decrypt("")
        except Exception as error:  # noqa: BLE001 - pypdf raises several types for unsupported crypto
            opened, result["error"] = 0, f"{type(error).__name__}: {error}"
        if not opened:
            return {**result, "status": "encrypted", "pages": None,
                    "note": "encrypted PDF: no text extracted without the password"}
    try:
        count = len(reader.pages)
    except (PdfReadError, ValueError) as error:
        return {**result, "status": "unreadable", "error": f"{type(error).__name__}: {error}"}
    result.update(pages=count, texts={}, errors={})
    for index in page_range(pages, count):
        try:
            result["texts"][index] = reader.pages[index].extract_text() or ""
        except Exception as error:  # noqa: BLE001 - a malformed page must not hide the others
            result["errors"][index] = f"{type(error).__name__}: {error}"
    texts = result["texts"]
    with_text = [i for i, t in texts.items() if t.strip()]
    result["status"] = ("ok" if with_text and len(with_text) == len(texts) else
                        "partial_text" if with_text else "no_text")
    if result["status"] == "no_text":
        result["note"] = "no extractable text on the selected pages: likely scanned images (OCR needed), not an empty paper"
    return result


def summary(path, result, grep=None, max_chars=MAX_CHARS, out=None):
    lines = [f"{path}: status={result['status']} pages={result.get('pages')} encrypted={result.get('encrypted')}"]
    for key in ("error", "note"):
        if result.get(key):
            lines.append(f"{key}: {result[key]}")
    texts = result.get("texts") or {}
    if texts:
        empty = [i + 1 for i, t in texts.items() if not t.strip()]
        lines.append("chars per page: " + ", ".join(f"p{i + 1}={len(t)}" for i, t in texts.items()))
        if empty:
            lines.append(f"pages without text (image-only?): {empty}")
        for index, message in (result.get("errors") or {}).items():
            lines.append(f"page {index + 1} extraction failed: {message}")
        if out:
            lines.append(f"full text: {out}")
        if grep:
            pattern, hits = re.compile(grep, re.IGNORECASE), 0
            for index, text in texts.items():
                for number, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        hits += 1
                        lines.append(f"p{index + 1}:{number}: {line.strip()[:300]}")
            lines.append(f"grep hits: {hits}")
        else:
            for index, text in texts.items():
                first = [s.strip() for s in text.splitlines() if s.strip()][:FIRST_LINES]
                if first:
                    lines.append(f"p{index + 1}: " + " | ".join(s[:160] for s in first))
    body = "\n".join(lines)
    if len(body) > max_chars:
        body = body[:max_chars] + f"\n... truncated at {max_chars} characters; use --grep, --pages or read --out"
    return body


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path)
    parser.add_argument("--pages", help="1-based pages, e.g. 1-5 or 1,3,7-")
    parser.add_argument("--grep", help="case-insensitive regex; print matching lines with page:line")
    parser.add_argument("--out", type=Path, help="write the full extracted text here")
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS, help=f"summary cap (at most {MAX_CHARS})")
    args = parser.parse_args(argv)
    if not 0 < args.max_chars <= MAX_CHARS:
        parser.error(f"--max-chars must be between 1 and {MAX_CHARS}")
    if not args.path.is_file():
        parser.error(f"not a file: {args.path}")
    if args.out and args.out.resolve() == args.path.resolve():
        parser.error("--out must not overwrite the PDF")
    try:
        result = extract(args.path, args.pages)
    except ValueError as error:
        parser.error(str(error))
    if args.out and result.get("texts") is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("".join(f"=== page {i + 1} ===\n{t}\n" for i, t in result["texts"].items()))
    print(summary(args.path, result, args.grep, args.max_chars, args.out if result.get("texts") is not None else None))
    print(json.dumps({"event": "pdf_text", "status": result["status"], "pages": result.get("pages"),
                      "chars": sum(len(t) for t in (result.get("texts") or {}).values())}))
    return 0 if result["status"] in ("ok", "partial_text") else 2


if __name__ == "__main__":
    sys.exit(main())
