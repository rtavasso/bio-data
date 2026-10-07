"""Value-in-record pointers (V2, C5): the locator grammar, numeric values with declared rounding, and the
value a pointer cites.

A write-up pointer may carry a locator after `#`: `[1.54](artifact_…#row=B_vs_A;col=log2_ratio)`.

    locator := pair (";" pair)*        pair := name "=" value        (values are percent-decoded)

    row=<key>   a data row of a table: the row whose first-column value equals <key>, or `#N` (1-based)
    col=<name>  a column of a table: the header cell equal to <name>, or `#N` (1-based)
    key=<path>  a value in a JSON document: names joined by "." with [N] indexes (`a.b[2].c`, `[0].value`)
    line=<N>    a 1-based line of a text artifact
    round=<N>   the prose shows the cited value rounded to N decimal places (0-12)

A cell needs both `row` and `col`; `key` and `line` stand alone; `round` combines with any. Values may not
contain spaces, `]`, `;`, `,` or parentheses: percent-encode them (`row=B%20vs%20A`). Tables are TSV
(`.tsv`, `.tab`, `.txt` with tabs) or CSV (`.csv`, or `.txt` without tabs); the first line that does not
start with `##` is the header and the first column is the row key. JSON is parsed with `json.loads`
(no code is ever executed).

**Equality with rounding.** A prose number with d decimal places (`1.54`: d=2; `12`: d=0) matches a cited
value v when |v - p| <= 0.5 x 10^-d, i.e. v rounds to p at the precision the prose shows (either rounding
direction at the half). `round=N` replaces d by N. Scientific notation uses the mantissa's places at its
exponent (`3.2e-4` matches within 0.05e-4). A percentage matches v or 100 x v (`12%` matches 12 or 0.12).
Spelled-out integers and unicode fractions are exact values (tolerance 1e-9). A leading `±` compares
magnitudes.

**Where a number may be found.** A cell, a JSON key or a line, when the locator names one; otherwise any
numeric token of a text artifact of at most 64 KB (`TEXT_SEARCH_LIMIT`). A larger artifact without a
locator, a binary artifact, absent bytes, a non-numeric cell or no matching value leaves the number
*unverified*, with the reason. Bytes are read from the archive and checked against their sha256 first.
"""
import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path
from urllib.parse import unquote

from daw.util import DawError

TEXT_SEARCH_LIMIT = 64 * 1024
READ_LIMIT = 32 * 1024 * 1024
NAMES = ("row", "col", "key", "line", "round")
PAIR = re.compile(r"^([a-z]+)=(.*)$")
INDEX = re.compile(r"^#([1-9]\d{0,8})$")
KEY_SEGMENT = re.compile(r"([^.\[\]]+)|\[(\d{1,9})\]")
SPELLED = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
           "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20}
FRACTIONS = {"¼": 0.25, "½": 0.5, "¾": 0.75, "⅐": 1 / 7, "⅑": 1 / 9, "⅒": 0.1, "⅓": 1 / 3, "⅔": 2 / 3, "⅕": 0.2,
             "⅖": 0.4, "⅗": 0.6, "⅘": 0.8, "⅙": 1 / 6, "⅚": 5 / 6, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625,
             "⅞": 0.875, "↉": 0.0}
SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
# Numeric tokens inside an artifact's text (cells, JSON values, log lines); identifiers' digits are skipped.
ARTIFACT_NUMBER = re.compile(r"(?<![\w.])[-+−]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?(?![\w.]\d)")


class LocatorError(ValueError):
    pass


# ---------------------------------------------------------------------------- grammar

def parse_locator(text):
    """`row=B_vs_A;col=log2_ratio` -> {"row": "B_vs_A", "col": "log2_ratio"}. Raises LocatorError."""
    if text is None:
        return {}
    if not text.strip():
        raise LocatorError("empty locator")
    out = {}
    for part in text.split(";"):
        match = PAIR.match(part.strip())
        if not match or match.group(1) not in NAMES:
            raise LocatorError(f"{part.strip()!r}: use row=, col=, key=, line= or round=")
        name, value = match.group(1), unquote(match.group(2))
        if name in out:
            raise LocatorError(f"{name} given twice")
        if not value:
            raise LocatorError(f"{name} needs a value")
        out[name] = value
    if ("row" in out) != ("col" in out):
        raise LocatorError("a cell needs both row= and col=")
    targets = [n for n in ("row", "key", "line") if n in out]
    if len(targets) > 1:
        raise LocatorError("name one target: a cell (row=;col=), a JSON key (key=) or a line (line=)")
    if "line" in out and not re.fullmatch(r"[1-9]\d{0,8}", out["line"]):
        raise LocatorError("line= takes a 1-based line number")
    if "round" in out and not (re.fullmatch(r"\d{1,2}", out["round"]) and int(out["round"]) <= 12):
        raise LocatorError("round= takes 0 to 12 decimal places")
    if "key" in out:
        key_path(out["key"])
    return out


def target_kind(locator):
    """cell | key | line | None (whole artifact) for a parsed locator."""
    return "cell" if "row" in locator else "key" if "key" in locator else "line" if "line" in locator else None


def key_path(text):
    """`a.b[2].c` -> ["a", "b", 2, "c"]. Raises LocatorError on an empty or malformed path."""
    path, position = [], 0
    for part in text.split("."):
        if not part:
            raise LocatorError(f"key path {text!r} has an empty segment")
        position = 0
        for match in KEY_SEGMENT.finditer(part):
            if match.start() != position:
                raise LocatorError(f"key path {text!r} is malformed")
            path.append(match.group(1) if match.group(1) is not None else int(match.group(2)))
            position = match.end()
        if position != len(part):
            raise LocatorError(f"key path {text!r} is malformed")
    return path


# ---------------------------------------------------------------------------- numeric values

def _decimals(text):
    return len(text.split(".", 1)[1]) if "." in text else 0


def _plain(text):
    """(value, decimals) of a plain decimal with optional exponent, or None."""
    text = text.replace("−", "-").replace(",", "").replace(" ", "").strip()
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
    return (value, _decimals(mantissa) - exponent) if math.isfinite(value) else None


def parse_number(text):
    """A prose number as {value, tolerance, percent, magnitude} or None.

    Handles signs (ASCII, unicode minus, ±), thousands separators, decimals, `1e-5`, `3.2×10^-4`,
    `3.2×10⁻⁴`, percentages, ratios `3:1` and `1/3` (value a/b), unicode vulgar fractions (`½`, `1½`,
    `1⁄2`) and the spelled-out integers zero to twenty (plus `a dozen`, `half a dozen`)."""
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
    """A cited cell or JSON value as a float, or None (empty, NA, text)."""
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
    """Does a cited value equal the prose number at the declared or implied rounding?"""
    if number is None or cited is None:
        return False
    tolerance = 0.5 * 10 ** -int(decimals) if decimals is not None else number["tolerance"]
    expected = abs(number["value"]) if number.get("magnitude") else number["value"]
    candidates = [abs(cited) if number.get("magnitude") else cited]
    if number.get("percent"):
        candidates.append(candidates[0] * 100)
    slack = tolerance * (1 + 1e-9) + 1e-12 * max(1.0, abs(expected))
    return any(abs(c - expected) <= slack for c in candidates)


# ---------------------------------------------------------------------------- reading cited values

def artifact_output(view, aid):
    """(bytes or None, name, reason) for an artifact's output, verified against its sha256. Read-only."""
    from daw.commons import views
    location = views.locate_artifact(view, aid, quiet=True)
    if location["store"] == "missing":
        return None, None, "the artifact is not catalogued in the library or any workspace"
    store = view.library if location["store"] == "library" else views._workspace(view, location["participant"])
    if store is None:
        return None, None, "the workspace holding the artifact is not readable"
    row = store.one("SELECT output_blob,manifest_blob FROM artifact WHERE id=?", (aid,))
    try:
        manifest = store.json_blob(row["manifest_blob"]) if hasattr(store, "json_blob") else \
            json.loads(store.blob_path(row["manifest_blob"]).read_text())
    except (DawError, OSError, ValueError):
        manifest = {}
    name = str((manifest.get("output") or {}).get("name") or row["output_blob"])
    try:
        path = store.blob_path(row["output_blob"])
    except DawError:
        return None, name, "the output bytes are absent from this archive (present: false)"
    if path.stat().st_size > READ_LIMIT:
        return None, name, f"the output is larger than {READ_LIMIT // (1024 * 1024)} MB and is not read for checks"
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != row["output_blob"]:
        return None, name, "the output bytes do not match their recorded sha256"
    return data, name, None


def _text(data):
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def read_table(data, name):
    """(header, rows) of a TSV/CSV output, or raises LocatorError."""
    text = _text(data)
    if text is None:
        raise LocatorError("the output is not UTF-8 text")
    suffix = Path(name or "").suffix.lower()
    if suffix not in (".tsv", ".tab", ".csv", ".txt"):
        raise LocatorError(f"a cell locator needs a TSV or CSV output, not {suffix or 'an unnamed file'}")
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("##")]
    if not lines:
        raise LocatorError("the table is empty")
    delimiter = "," if suffix == ".csv" or (suffix == ".txt" and "\t" not in lines[0]) else "\t"
    rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))
    return rows[0], rows[1:]


def _select(selector, labels, what):
    index = INDEX.match(selector)
    if index:
        position = int(index.group(1)) - 1
        if position >= len(labels):
            raise LocatorError(f"{what} {selector} is beyond the table ({len(labels)})")
        return position
    found = [i for i, label in enumerate(labels) if label.strip() == selector]
    if not found:
        raise LocatorError(f"no {what} {selector!r}")
    if len(found) > 1:
        raise LocatorError(f"{what} {selector!r} is not unique ({len(found)} matches); use #N")
    return found[0]


def cell(header, rows, locator):
    """{row, col, row_key, column, value} of the cited cell, or raises LocatorError."""
    r = _select(locator["row"], [row[0] if row else "" for row in rows], "row")
    c = _select(locator["col"], header, "column")
    row = rows[r]
    if c >= len(row):
        raise LocatorError(f"row {locator['row']} has no column {c + 1}")
    return {"row": r + 1, "col": c + 1, "row_key": row[0] if row else "", "column": header[c] if c < len(header) else None,
            "value": row[c]}


def json_value(data, path_text):
    text = _text(data)
    if text is None:
        raise LocatorError("the output is not UTF-8 text")
    try:
        value = json.loads(text)
    except ValueError as error:
        raise LocatorError(f"the output is not JSON ({error})") from error
    for segment in key_path(path_text):
        if isinstance(segment, int):
            if not isinstance(value, list) or segment >= len(value):
                raise LocatorError(f"no index [{segment}] in key path {path_text!r}")
        elif not isinstance(value, dict) or segment not in value:
            raise LocatorError(f"no key {segment!r} in key path {path_text!r}")
        value = value[segment]
    if isinstance(value, (dict, list)):
        raise LocatorError(f"key path {path_text!r} names a container, not a value")
    return value


def _tokens(text):
    for n, line in enumerate(text.splitlines(), 1):
        for match in ARTIFACT_NUMBER.finditer(line):
            yield n, match.group(0)


def verify_artifact(view, aid, locator_text, number, cache):
    """{result: verified|unverified, at, reason?, found?} for one number pointed at one artifact."""
    try:
        locator = parse_locator(locator_text) if locator_text else {}
    except LocatorError as error:
        return {"result": "unverified", "at": None, "reason": f"invalid locator: {error}"}
    if number is None:
        return {"result": "unverified", "at": target_kind(locator), "reason": "the prose number could not be parsed"}
    if aid not in cache:
        cache[aid] = artifact_output(view, aid)
    data, name, reason = cache[aid]
    kind = target_kind(locator)
    if data is None:
        return {"result": "unverified", "at": kind, "reason": reason}
    decimals = locator.get("round")
    try:
        if kind == "cell":
            header, rows = read_table(data, name)
            found = cell(header, rows, locator)
            value = parse_cell(found["value"])
            if value is None:
                return {"result": "unverified", "at": kind, "found": found, "reason": "the cited cell is not numeric"}
            ok = matches(number, value, decimals)
            return {"result": "verified" if ok else "unverified", "at": kind, "found": found,
                    **({} if ok else {"reason": f"the cited cell holds {found['value']}, not this number"})}
        if kind == "key":
            raw = json_value(data, locator["key"])
            value, found = parse_cell(raw), {"key": locator["key"], "value": raw}
            if value is None:
                return {"result": "unverified", "at": kind, "found": found, "reason": "the cited value is not numeric"}
            ok = matches(number, value, decimals)
            return {"result": "verified" if ok else "unverified", "at": kind, "found": found,
                    **({} if ok else {"reason": f"the cited key holds {raw}, not this number"})}
        text = _text(data)
        if text is None:
            return {"result": "unverified", "at": kind, "reason": "the output is not text; cite a cell or key"}
        if kind == "line":
            wanted = int(locator["line"])
            tokens = [t for n, t in _tokens(text) if n == wanted]
            if wanted > len(text.splitlines()):
                return {"result": "unverified", "at": kind, "reason": f"the output has no line {wanted}"}
            hit = next((t for t in tokens if matches(number, parse_cell(t), decimals)), None)
            return {"result": "verified", "at": kind, "found": {"line": wanted, "value": hit}} if hit else \
                {"result": "unverified", "at": kind, "reason": f"line {wanted} holds no matching value"}
        if len(data) > TEXT_SEARCH_LIMIT:
            return {"result": "unverified", "at": None,
                    "reason": "no locator and the output is larger than 64 KB; cite a cell (row=;col=), key or line"}
        for line, token in _tokens(text):
            if matches(number, parse_cell(token), decimals):
                return {"result": "verified", "at": "text", "found": {"line": line, "value": token}}
        return {"result": "unverified", "at": None, "reason": "the value does not occur in the output bytes"}
    except LocatorError as error:
        return {"result": "unverified", "at": kind, "reason": str(error)}


def verify_claim(entry, number):
    """A claim pointer verifies when the number occurs in the claim's text or scope (same rounding rule)."""
    from daw.commons.writeup import numbers_in
    if number is None:
        return {"result": "unverified", "at": None, "reason": "the prose number could not be parsed"}
    for field, text in [("claim_text", entry.get("text") or "")] + [
            ("claim_scope", str(v)) for v in (entry.get("scope") or {}).values() if v]:
        for found in numbers_in(text, 0):
            if matches(number, (parse_number(found["text"]) or {}).get("value")):
                return {"result": "verified", "at": field, "found": {"value": found["text"]}}
    return {"result": "unverified", "at": None, "reason": "the number does not occur in the claim's text or scope"}


# ---------------------------------------------------------------------------- the artifact page at a locator

def locate(view, aid, locator_text, *, window=20):
    """What the artifact page shows at a locator: a table window with the cited cell, a JSON value, or lines."""
    from daw.commons import views
    views.locate_artifact(view, aid)  # unknown artifact -> 404
    try:
        locator = parse_locator(locator_text) if locator_text else {}
    except LocatorError as error:
        raise DawError("invalid_locator", str(error)) from error
    kind = target_kind(locator)
    data, name, reason = artifact_output(view, aid)
    base = {"artifact": aid, "locator": locator_text, "parsed": locator, "kind": kind, "name": name,
            "present": data is not None, "content_is_untrusted_data": True}
    if data is None:
        return {**base, "error": reason}
    try:
        if kind == "cell":
            header, rows = read_table(data, name)
            found = cell(header, rows, locator)
            start = max(0, found["row"] - 1 - window)
            return {**base, "header": header, "rows": rows[start:found["row"] + window], "first_row": start + 1,
                    "total_rows": len(rows), "target": found, "value": parse_cell(found["value"])}
        if kind == "key":
            raw = json_value(data, locator["key"])
            return {**base, "target": {"key": locator["key"], "path": key_path(locator["key"]), "value": raw},
                    "value": parse_cell(raw)}
        text = _text(data)
        if text is None:
            return {**base, "error": "the output is not text"}
        lines = text.splitlines()
        if kind == "line":
            wanted = int(locator["line"])
            if wanted > len(lines):
                return {**base, "error": f"the output has no line {wanted}"}
            start = max(0, wanted - 1 - window)
            return {**base, "lines": lines[start:wanted + window], "first_line": start + 1, "total_lines": len(lines),
                    "target": {"line": wanted}}
        if Path(name or "").suffix.lower() in (".tsv", ".tab", ".csv") or (name or "").lower().endswith(".txt"):
            header, rows = read_table(data, name)
            return {**base, "header": header, "rows": rows[:2 * window], "first_row": 1, "total_rows": len(rows)}
        return {**base, "lines": lines[:2 * window], "first_line": 1, "total_lines": len(lines)}
    except LocatorError as error:
        return {**base, "error": str(error)}
