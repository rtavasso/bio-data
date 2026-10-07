#!/usr/bin/env python3
"""Offline verifier for a Colloquy preprint or snapshot (spec v2 V7). Python 3.10+ standard library only.

    python3 verify.py [DIRECTORY] [--expect SNAPSHOT_ID] [--json]

This file is copied verbatim into every preprint export as `verify.py`. It never executes, imports or
evaluates anything from the directory it checks: it reads bytes, hashes them and parses JSON and text.

1. Snapshot integrity. `snapshot.json` must be canonical JSON (sorted keys, compact separators, UTF-8);
   the snapshot ID is its sha256. Every listed file must be present with its size and sha256, and no
   unlisted file, link or special file may be present (`snapshot.id` is a convenience copy of the ID).
2. The prose. `preprint.json` names the write-up's Markdown source (`source/<post>.md`) and the board record
   it came from (`records/<post>.json`, the exact bytes of the post's content blob): the record's sha256
   must equal the recorded `body_blob` and its `body` must equal the Markdown source.
3. Every number. Each recorded number must occur at its recorded offset (Unicode code points) in the
   source. Each pointer is re-checked against the included bytes, value in record: an artifact pointer
   reads the cited cell (`row=;col=`), JSON key (`key=`) or line (`line=`) of the artifact's output bytes,
   or, without a locator, any numeric token of a text output of at most 64 KB; a claim pointer reads the
   claim's text and scope. The prose number matches a cited value at the precision the prose shows
   (`1.54` matches values within 0.005; `round=N` declares N places; `12%` matches 12 or 0.12). The
   recomputed status (verified / unverified / post_scoped / unpointed) must equal the status the
   commons' checker recorded.

Exit status 0 when every hash matches and every recomputed status equals the recorded one; 1 otherwise;
2 when the directory is not a snapshot. The rules mirror `daw.commons.locators` (rules version in
`preprint.json`); a parity test in the commons' repository keeps the two in step.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

FORMAT = "colloquy.snapshot/1"
PREPRINT = "colloquy.preprint/1"
MANIFEST = "snapshot.json"
SIDECARS = {"snapshot.id"}
TEXT_SEARCH_LIMIT = 64 * 1024
NAMES = ("row", "col", "key", "line", "round")
PAIR = re.compile(r"^([a-z]+)=(.*)$")
INDEX = re.compile(r"^#([1-9]\d{0,8})$")
KEY_SEGMENT = re.compile(r"([^.\[\]]+)|\[(\d{1,9})\]")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SPELLED = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
           "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20}
FRACTIONS = {"¼": 0.25, "½": 0.5, "¾": 0.75, "⅐": 1 / 7, "⅑": 1 / 9, "⅒": 0.1, "⅓": 1 / 3, "⅔": 2 / 3, "⅕": 0.2,
             "⅖": 0.4, "⅗": 0.6, "⅘": 0.8, "⅙": 1 / 6, "⅚": 5 / 6, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625,
             "⅞": 0.875, "↉": 0.0}
SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
ARTIFACT_NUMBER = re.compile(r"(?<![\w.])[-+−]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?(?![\w.]\d)")
# Numbers inside a claim's text (prose): signs, thousands separators, decimals, exponents, percentages.
CLAIM_NUMBER = re.compile(r"(?<![\w.])[-+−±]?(?:\d{1,3}(?:,\d{3})+|\d+)?(?:\.\d+)?(?:[eE][-+−]?\d+)?%?")


class Problem(Exception):
    pass


# ---------------------------------------------------------------------------- canonical JSON and hashes

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_listed(path):
    if not isinstance(path, str) or not path or "\\" in path or path in (MANIFEST, *SIDECARS):
        return False
    pure = PurePosixPath(path)
    return not pure.is_absolute() and all(p not in ("", ".", "..") and not p.startswith(".") for p in pure.parts)


def check_snapshot(directory, expect=None):
    """(snapshot id, manifest, problems) after checking every listed file's size and sha256."""
    directory = Path(directory)
    path = directory / MANIFEST
    if not path.is_file() or path.is_symlink():
        raise Problem(f"{MANIFEST} is missing")
    data = path.read_bytes()
    try:
        manifest = json.loads(data)
    except ValueError as error:
        raise Problem(f"{MANIFEST} is not JSON: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT or not isinstance(manifest.get("files"), list):
        raise Problem(f"{MANIFEST} is not a {FORMAT} manifest")
    problems = []
    if canonical(manifest) != data:
        problems.append(f"{MANIFEST} is not canonical JSON; its hash would not be a stable identity")
    snapshot = hashlib.sha256(data).hexdigest()
    sidecar = directory / "snapshot.id"
    if sidecar.is_file() and sidecar.read_text().strip() not in ("", snapshot):
        problems.append("snapshot.id does not equal sha256(snapshot.json)")
    if expect and expect != snapshot:
        problems.append(f"expected snapshot {expect}, snapshot.json hashes to {snapshot}")
    listed = {}
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or not safe_listed(entry.get("path")) or entry["path"] in listed \
                or not HEX64.match(str(entry.get("sha256"))) or not isinstance(entry.get("bytes"), int):
            problems.append(f"bad file entry {str(entry)[:200]}")
            continue
        listed[entry["path"]] = entry
    for root, dirs, files in os.walk(directory):
        for name in dirs + files:
            full = Path(root) / name
            relative = full.relative_to(directory).as_posix()
            mode = os.lstat(full).st_mode
            if stat.S_ISLNK(mode):
                problems.append(f"link present: {relative}")
            elif stat.S_ISREG(mode):
                if relative not in listed and relative != MANIFEST and relative not in SIDECARS:
                    problems.append(f"unlisted file: {relative}")
            elif not stat.S_ISDIR(mode):
                problems.append(f"special file present: {relative}")
    for relative, entry in sorted(listed.items()):
        full = directory / relative
        if not full.is_file() or full.is_symlink():
            problems.append(f"missing file: {relative}")
        elif full.stat().st_size != entry["bytes"] or sha256_file(full) != entry["sha256"]:
            problems.append(f"hash or size mismatch: {relative}")
    return snapshot, manifest, problems


# ---------------------------------------------------------------------------- locators and numbers

def parse_locator(text):
    if text is None:
        return {}
    if not text.strip():
        raise Problem("empty locator")
    out = {}
    for part in text.split(";"):
        match = PAIR.match(part.strip())
        if not match or match.group(1) not in NAMES:
            raise Problem(f"{part.strip()!r}: use row=, col=, key=, line= or round=")
        name, value = match.group(1), unquote(match.group(2))
        if name in out or not value:
            raise Problem(f"{name} given twice or empty")
        out[name] = value
    if ("row" in out) != ("col" in out):
        raise Problem("a cell needs both row= and col=")
    if len([n for n in ("row", "key", "line") if n in out]) > 1:
        raise Problem("name one target: a cell, a JSON key or a line")
    if "line" in out and not re.fullmatch(r"[1-9]\d{0,8}", out["line"]):
        raise Problem("line= takes a 1-based line number")
    if "round" in out and not (re.fullmatch(r"\d{1,2}", out["round"]) and int(out["round"]) <= 12):
        raise Problem("round= takes 0 to 12 decimal places")
    if "key" in out:
        key_path(out["key"])
    return out


def target_kind(locator):
    return "cell" if "row" in locator else "key" if "key" in locator else "line" if "line" in locator else None


def key_path(text):
    path = []
    for part in text.split("."):
        if not part:
            raise Problem(f"key path {text!r} has an empty segment")
        position = 0
        for match in KEY_SEGMENT.finditer(part):
            if match.start() != position:
                raise Problem(f"key path {text!r} is malformed")
            path.append(match.group(1) if match.group(1) is not None else int(match.group(2)))
            position = match.end()
        if position != len(part):
            raise Problem(f"key path {text!r} is malformed")
    return path


def _plain(text):
    text = text.replace("−", "-").replace(",", "").replace(" ", "").strip()
    match = re.fullmatch(r"([-+]?)(\d*\.?\d+)(?:[eE]([-+]?\d+))?", text)
    if not match:
        return None
    mantissa = match.group(2)
    exponent = int(match.group(3)) if match.group(3) else 0
    if abs(exponent) > 300 or len(mantissa) > 300:
        return None
    try:
        value = float(f"{match.group(1)}{mantissa}e{exponent}")
    except (OverflowError, ValueError):
        return None
    decimals = len(mantissa.split(".", 1)[1]) if "." in mantissa else 0
    return (value, decimals - exponent) if math.isfinite(value) else None


def parse_number(text):
    """A prose number as {value, tolerance, percent, magnitude} or None (the checker's rules)."""
    raw = text.strip()
    lowered = raw.lower()
    if lowered in ("a dozen", "half a dozen"):
        return {"value": 12.0 if lowered == "a dozen" else 6.0, "tolerance": 1e-9, "percent": False, "magnitude": False}
    words = re.fullmatch(r"([a-z]+)(?:[-\s]([a-z]+))?", lowered)
    if words and words.group(1) in SPELLED:
        value = SPELLED[words.group(1)] + (SPELLED.get(words.group(2), 0) if words.group(2) else 0)
        return {"value": float(value), "tolerance": 1e-9, "percent": False, "magnitude": False}
    magnitude = raw.startswith("±")
    body = raw.lstrip("±").strip()
    percent = body.endswith("%")
    body = body.rstrip("%").strip()
    fraction = re.fullmatch(r"([-+−]?)(\d*)\s?([" + "".join(FRACTIONS) + r"])", body)
    if fraction:
        value = (int(fraction.group(2)) if fraction.group(2) else 0) + FRACTIONS[fraction.group(3)]
        return {"value": -value if fraction.group(1) in "-−" and fraction.group(1) else value, "tolerance": 1e-9,
                "percent": percent, "magnitude": magnitude}
    slash = re.fullmatch(r"([-+−]?\d+)⁄(\d+)", body)
    if slash and int(slash.group(2)):
        return {"value": int(slash.group(1).replace("−", "-")) / int(slash.group(2)), "tolerance": 1e-9,
                "percent": percent, "magnitude": magnitude}
    times = re.fullmatch(r"(.+?)\s?[×x]\s?10(?:\^|\*\*)?([-+−]?\d+|[⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)", body)
    if times:
        base = _plain(times.group(1))
        if not base:
            return None
        exponent = int(times.group(2).translate(SUPERSCRIPT).replace("−", "-"))
        if abs(exponent) > 300 or abs(exponent - base[1]) > 300:
            return None
        return {"value": base[0] * 10.0 ** exponent, "tolerance": 0.5 * 10 ** (exponent - base[1]),
                "percent": percent, "magnitude": magnitude}
    ratio = re.fullmatch(r"(.+?)\s?[:/]\s?(.+)", body)
    if ratio:
        left, right = _plain(ratio.group(1).rstrip("%")), _plain(ratio.group(2).rstrip("%"))
        if not left or not right or right[0] == 0:
            return None
        return {"value": left[0] / right[0], "tolerance": 0.5 * 10 ** -max(left[1], right[1], 2) / right[0],
                "percent": False, "magnitude": magnitude, "ratio": True}
    plain = _plain(body)
    if not plain:
        return None
    return {"value": plain[0], "tolerance": 0.5 * 10 ** -plain[1], "percent": percent, "magnitude": magnitude}


def parse_cell(text):
    if isinstance(text, bool) or text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text) if math.isfinite(text) else None
    cleaned = str(text).strip().rstrip("%").strip()
    plain = _plain(cleaned)
    if plain:
        return plain[0]
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def matches(number, cited, decimals=None):
    if number is None or cited is None:
        return False
    tolerance = 0.5 * 10 ** -int(decimals) if decimals is not None else number["tolerance"]
    expected = abs(number["value"]) if number.get("magnitude") else number["value"]
    candidates = [abs(cited) if number.get("magnitude") else cited]
    if number.get("percent"):
        candidates.append(candidates[0] * 100)
    slack = tolerance * (1 + 1e-9) + 1e-12 * max(1.0, abs(expected))
    return any(abs(c - expected) <= slack for c in candidates)


def _text(data):
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def read_table(data, name):
    text = _text(data)
    if text is None:
        raise Problem("the output is not UTF-8 text")
    suffix = PurePosixPath(name or "").suffix.lower()
    if suffix not in (".tsv", ".tab", ".csv", ".txt"):
        raise Problem(f"a cell locator needs a TSV or CSV output, not {suffix or 'an unnamed file'}")
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("##")]
    if not lines:
        raise Problem("the table is empty")
    delimiter = "," if suffix == ".csv" or (suffix == ".txt" and "\t" not in lines[0]) else "\t"
    rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))
    return rows[0], rows[1:]


def _select(selector, labels, what):
    index = INDEX.match(selector)
    if index:
        position = int(index.group(1)) - 1
        if position >= len(labels):
            raise Problem(f"{what} {selector} is beyond the table ({len(labels)})")
        return position
    found = [i for i, label in enumerate(labels) if label.strip() == selector]
    if not found:
        raise Problem(f"no {what} {selector!r}")
    if len(found) > 1:
        raise Problem(f"{what} {selector!r} is not unique ({len(found)} matches); use #N")
    return found[0]


def cell(header, rows, locator):
    r = _select(locator["row"], [row[0] if row else "" for row in rows], "row")
    c = _select(locator["col"], header, "column")
    row = rows[r]
    if c >= len(row):
        raise Problem(f"row {locator['row']} has no column {c + 1}")
    return {"row": r + 1, "col": c + 1, "value": row[c]}


def json_value(data, path_text):
    text = _text(data)
    if text is None:
        raise Problem("the output is not UTF-8 text")
    try:
        value = json.loads(text)
    except ValueError as error:
        raise Problem(f"the output is not JSON ({error})") from error
    for segment in key_path(path_text):
        if isinstance(segment, int):
            if not isinstance(value, list) or segment >= len(value):
                raise Problem(f"no index [{segment}] in key path {path_text!r}")
        elif not isinstance(value, dict) or segment not in value:
            raise Problem(f"no key {segment!r} in key path {path_text!r}")
        value = value[segment]
    if isinstance(value, (dict, list)):
        raise Problem(f"key path {path_text!r} names a container, not a value")
    return value


def _tokens(text):
    for n, line in enumerate(text.splitlines(), 1):
        for match in ARTIFACT_NUMBER.finditer(line):
            yield n, match.group(0)


def verify_bytes(data, name, locator_text, number):
    """{result: verified|unverified, at, found?, reason?} for one number pointed at an artifact's output bytes."""
    try:
        locator = parse_locator(locator_text) if locator_text else {}
    except Problem as error:
        return {"result": "unverified", "at": None, "reason": f"invalid locator: {error}"}
    kind = target_kind(locator)
    if number is None:
        return {"result": "unverified", "at": kind, "reason": "the prose number could not be parsed"}
    if data is None:
        return {"result": "unverified", "at": kind, "reason": "the output bytes are not in this snapshot"}
    decimals = locator.get("round")
    try:
        if kind == "cell":
            header, rows = read_table(data, name)
            found = cell(header, rows, locator)
            value = parse_cell(found["value"])
            ok = value is not None and matches(number, value, decimals)
            return {"result": "verified" if ok else "unverified", "at": kind, "found": found}
        if kind == "key":
            raw = json_value(data, locator["key"])
            value = parse_cell(raw)
            ok = value is not None and matches(number, value, decimals)
            return {"result": "verified" if ok else "unverified", "at": kind, "found": {"key": locator["key"], "value": raw}}
        text = _text(data)
        if text is None:
            return {"result": "unverified", "at": kind, "reason": "the output is not text"}
        if kind == "line":
            wanted = int(locator["line"])
            hit = next((t for n, t in _tokens(text) if n == wanted and matches(number, parse_cell(t), decimals)), None)
            return {"result": "verified" if hit else "unverified", "at": kind, "found": {"line": wanted, "value": hit}}
        if len(data) > TEXT_SEARCH_LIMIT:
            return {"result": "unverified", "at": None, "reason": "no locator and the output is larger than 64 KB"}
        for line, token in _tokens(text):
            if matches(number, parse_cell(token), decimals):
                return {"result": "verified", "at": "text", "found": {"line": line, "value": token}}
        return {"result": "unverified", "at": None, "reason": "the value does not occur in the output bytes"}
    except Problem as error:
        return {"result": "unverified", "at": kind, "reason": str(error)}


def verify_claim_text(claim, number, recorded_found=None):
    """A claim pointer verifies when the number occurs in the claim's text or scope."""
    if number is None:
        return {"result": "unverified", "reason": "the prose number could not be parsed"}
    texts = [claim.get("text") or ""] + [str(v) for v in (claim.get("scope") or {}).values() if v]
    candidates = []
    if recorded_found and isinstance(recorded_found.get("value"), str):
        candidates.append(recorded_found["value"])
    for text in texts:
        candidates += [m.group(0) for m in CLAIM_NUMBER.finditer(text) if any(ch.isdigit() for ch in m.group(0))]
    for token in candidates:
        if any(token in text for text in texts) and matches(number, (parse_number(token) or {}).get("value")):
            return {"result": "verified", "found": {"value": token}}
    return {"result": "unverified", "reason": "the number does not occur in the claim's text or scope"}


# ---------------------------------------------------------------------------- the preprint

def read_listed(directory, listed, path):
    if path not in listed:
        return None
    return (Path(directory) / path).read_bytes()


def verify_preprint(directory, listed):
    """Re-run the value-in-record checks of every number against the snapshot's own bytes."""
    directory = Path(directory)
    problems, rows = [], []
    data = read_listed(directory, listed, "preprint.json")
    if data is None:
        return None, ["preprint.json is not listed: this snapshot is not a preprint (hashes only)"], rows
    preprint = json.loads(data)
    if preprint.get("format") != PREPRINT:
        return preprint, [f"preprint.json is not {PREPRINT}"], rows
    post = preprint["post"]
    source_bytes = read_listed(directory, listed, preprint["source"])
    record_bytes = read_listed(directory, listed, preprint["record"])
    if source_bytes is None or record_bytes is None:
        return preprint, ["the Markdown source or the post record is not listed"], rows
    source = source_bytes.decode("utf-8")
    if hashlib.sha256(record_bytes).hexdigest() != post["body_blob"]:
        problems.append("the post record's sha256 is not the recorded body_blob")
    try:
        record = json.loads(record_bytes)
    except ValueError:
        record = {}
    if record.get("body") != source:
        problems.append("the Markdown source is not the body of the post record")
    artifacts, claims = preprint.get("artifacts") or {}, preprint.get("claims") or {}
    outputs = {}
    for n in preprint.get("numbers") or []:
        shown = source[n["offset"]:n["offset"] + n["length"]]
        row = {"text": n["text"], "line": n["line"], "recorded": n["status"], "pointers": []}
        if shown.strip() != n["text"]:
            problems.append(f"line {n['line']}: the source does not show {n['text']!r} at offset {n['offset']}")
        value = parse_number(n["text"])
        results = []
        for p in n.get("pointers") or []:
            if p.get("post_evidence") or p.get("kind") not in ("claim", "artifact"):
                continue
            key = p.get("ref") or p["id"]
            if p["kind"] == "artifact":
                entry = artifacts.get(key)
                if not entry:
                    result = {"result": "unverified", "reason": "the artifact is not described in preprint.json"}
                elif not entry.get("path"):
                    result = {"result": "unverified", "reason": entry.get("absent") or "the output bytes are not in this snapshot"}
                else:
                    if key not in outputs:
                        blob = read_listed(directory, listed, entry["path"])
                        if blob is not None and hashlib.sha256(blob).hexdigest() != entry["sha256"]:
                            problems.append(f"{entry['path']}: bytes do not hash to the artifact's output sha256")
                            blob = None
                        outputs[key] = blob
                    result = verify_bytes(outputs[key], entry.get("name") or entry["path"], p.get("locator"), value)
            else:
                entry = claims.get(key)
                result = verify_claim_text(entry, value, p.get("found")) if entry else \
                    {"result": "unverified", "reason": "the claim is not described in preprint.json"}
            results.append(result)
            if result["result"] != p.get("result"):
                problems.append(f"line {n['line']} {n['text']!r} -> {key}: recorded {p.get('result')}, "
                                f"recomputed {result['result']} ({result.get('reason') or 'value found'})")
            row["pointers"].append({"id": key, "locator": p.get("locator"), **result})
        if results:
            status = "verified" if any(r["result"] == "verified" for r in results) else "unverified"
        else:
            status = n["status"] if n["status"] in ("post_scoped", "unpointed") else "unpointed"
        row["recomputed"] = status
        if status != n["status"]:
            problems.append(f"line {n['line']} {n['text']!r}: recorded {n['status']}, recomputed {status}")
        rows.append(row)
    return preprint, problems, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify a Colloquy snapshot or preprint offline.")
    parser.add_argument("directory", nargs="?", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--expect", help="the snapshot ID you were given (sha256 of snapshot.json)")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)
    try:
        snapshot, manifest, problems = check_snapshot(args.directory, args.expect)
    except Problem as error:
        print(f"not a snapshot: {error}", file=sys.stderr)
        return 2
    listed = {entry["path"]: entry for entry in manifest["files"] if isinstance(entry, dict) and "path" in entry}
    preprint, number_problems, rows = verify_preprint(args.directory, listed) if not problems else (None, [], [])
    if preprint is None and number_problems and not problems:
        number_problems = []  # an ordinary snapshot: hashes only
    problems += number_problems
    counts = {}
    for row in rows:
        counts[row["recomputed"]] = counts.get(row["recomputed"], 0) + 1
    result = {"snapshot": snapshot, "files": len(listed), "preprint": bool(preprint), "numbers": len(rows),
              "statuses": counts, "ok": not problems, "problems": problems, "rows": rows}
    if args.json:
        print(json.dumps(result, indent=1, ensure_ascii=False))
    else:
        print(f"snapshot {snapshot}")
        print(f"{len(listed)} listed files: {'all present with matching sha256' if not problems else 'see problems'}")
        if preprint:
            print(f"{len(rows)} numbers re-checked against the included bytes: "
                  + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        for problem in problems:
            print(f"PROBLEM: {problem}")
        print("OK" if not problems else "FAILED")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
