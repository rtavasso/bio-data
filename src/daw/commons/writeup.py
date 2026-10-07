"""Studio write-ups (M6.1): pointer syntax, the number check, and regeneration flags (Flow B step 5).

A write-up is an ordinary post (usually the answer to a `writing` commission). Writers point at
records with Markdown links whose target is a record identifier, `[1.54](claim_…)`,
`[text](artifact_…)`, `[text](post_…)`, or with a bracketed citation `[claim_…]` placed in or
directly after the sentence it supports. Figures are images whose target is an artifact,
`![caption](artifact_…)`. A bare identifier in prose is tolerated as a citation.

`render_writeup(view, post)` parses the Markdown (a documented subset, below) into HTML-safe
blocks and refuses, listing every location, when

- a numeric token in prose is neither inside a claim/artifact pointer link nor in a sentence (or
  table row, heading, code block) that cites at least one claim or artifact. Post pointers give
  context only; they never cover a number;
- a pointer does not resolve: claims must be rows of the ledger, artifacts must be catalogued in
  the library or a participant workspace (their bytes are served by /api/artifacts/{id}/bytes),
  posts must exist; other identifier kinds (questions, runs, requests…) are not citable;
- a figure does not reference a resolving artifact.

Numeric tokens: optionally signed integers and decimals (thousands separators allowed),
scientific notation (`1e-5`, `3.2×10^-4`), percentages and ratios (`3:1`, `1/3`). Not numbers:
digits inside identifiers (a token preceded by a letter, digit, underscore or '.', or by a
hyphen that follows a letter: PMP22, log2, GSE1234, v1.2, IL-6), record identifiers, hashes and
URLs; ordered-list ordinals; heading numbering (`## 2.1 Methods`); and dates or times in a byline
(a paragraph among the first two blocks starting with By / Written by / Prepared by / Author(s): /
Date: / Updated:). A digit followed by letters still counts (`5mg`, `2nd`). Code spans in prose
are prose. Sentences end at `.`, `!` or `?` followed by whitespace and a character that is not a
lowercase letter, except after common abbreviations (e.g., i.e., et al., Fig., vs., approx.).
Bracketed citations at the start of the next sentence attach to the previous one.

A write-up that cites a withdrawn claim (ledger `withdrawn_by`) is flagged for regeneration: the
response carries `regeneration_required` with each withdrawn claim, its replacement post and
that post's current claims; the renderer never serves such a write-up without the flag. The flag
is computed from the ledger at read time, so it needs no write and cannot go stale.

Markdown subset: ATX headings, paragraphs, `-`/`*`/`+` and `1.`/`1)` list items (continuation
lines indented), `>` quotes, fenced code, GFM pipe tables, thematic breaks, inline code,
`**strong**` and `*em*`, links and images. Raw HTML is shown as text; only http(s) and mailto
links leave the commons. Everything here reads a read-only Archive.
"""
import json
import re
from collections import OrderedDict

from daw.commons import evidence_map, views
from daw.util import DawError

RULES_VERSION = "writeup-pointers/1"
CITABLE = {"claim": re.compile(r"claim_[0-9a-f]{32}"), "artifact": re.compile(r"artifact_[0-9a-f]{64}"),
           "post": re.compile(r"post_[0-9a-f]{32}")}
COVERING = ("claim", "artifact")
# Any record-identifier shape (prefix, underscore, hex/alphanumerics): digits inside are identifier characters.
IDENTIFIER_LIKE = re.compile(r"\b[a-z][a-z0-9]*_[0-9a-f]{6,}\b|\bq_[0-9a-f]{16}\b")
POINTER_SHAPE = re.compile(r"^(claim|artifact|post)_[0-9A-Za-z]+$")
OTHER_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*_[0-9a-f]{6,}$")
HEX = re.compile(r"\b[0-9a-f]{40,128}\b")
URL = re.compile(r"<[A-Za-z][A-Za-z0-9+.-]*:[^\s<>]+>|\b(?:https?|ftp)://[^\s<>()\[\]]+|\bmailto:[^\s<>()\[\]]+")

_CORE = r"(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
_EXP = r"(?:[eE][-+−]?\d+)?"
_TIMES10 = r"(?:\s?[×x]\s?10(?:\^|\*\*)?[-+−]?\d+)?"
NUMBER = re.compile(rf"(?<![\w.])(?<![A-Za-z_][-−])[-+−±]?{_CORE}{_EXP}{_TIMES10}%?(?:[:/]{_CORE}{_EXP}%?)?")
MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
DATE = re.compile(rf"\b\d{{4}}-\d{{2}}-\d{{2}}(?:[T ]\d{{2}}:\d{{2}}(?::\d{{2}}(?:\.\d+)?)?(?:Z|[+-]\d{{2}}:?\d{{2}})?)?\b"
                  rf"|\b\d{{4}}/\d{{2}}/\d{{2}}\b|\b\d{{1,2}}\s+{MONTH}\s+\d{{4}}\b|\b{MONTH}\s+\d{{1,2}},?\s+\d{{4}}\b"
                  rf"|\b{MONTH}\s+\d{{4}}\b|\b\d{{1,2}}:\d{{2}}(?::\d{{2}})?\s*(?:UTC|Z)?\b")
BYLINE = re.compile(r"^[\s*_]*(?:by|written by|prepared by|authors?:|date:|updated:)\s", re.I)
HEADING_NUMBER = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[IVXLC]+\.)(?=\s)")
ABBREVIATIONS = {"e.g", "i.e", "al", "fig", "figs", "vs", "approx", "cf", "eq", "eqs", "no", "ca", "resp", "ref",
                 "refs", "suppl", "sec", "dr", "mr", "ms", "st", "etc"}
SENTENCE_END = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s)")

INLINE = re.compile(r"""
  (?P<code>`+)(?P<code_text>.+?)(?P=code)
| !\[(?P<alt>[^\]\n]*)\]\((?P<src>[^()\s]*)(?:\s+"[^"\n]*")?\)
| \[(?P<ltext>[^\]\n]+)\]\((?P<href>[^()\s]*)(?:\s+"[^"\n]*")?\)
| \[(?P<cite>(?:claim|artifact|post)_[0-9A-Za-z]+(?:\s*[,;]\s*(?:claim|artifact|post)_[0-9A-Za-z]+)*)\](?!\()
| (?P<bare>\b(?:claim_[0-9a-f]{32}|post_[0-9a-f]{32}|artifact_[0-9a-f]{64})\b)
| (?P<url><https?://[^\s<>]+>|\bhttps?://[^\s<>()\[\]]+)
""", re.X | re.S)
EMPHASIS = re.compile(r"\*\*(?P<strong>.+?)\*\*|\*(?P<em>[^\s*](?:.*?[^\s*])?)\*", re.S)

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([^`\s]*)[^`]*$")
HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*#*[ \t]*$")
ITEM = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])[ \t]+(.*)$")
QUOTE = re.compile(r"^ {0,3}> ?(.*)$")
RULE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
TABLE_DELIMITER = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")
IMAGE_ONLY = re.compile(r"^\s*!\[[^\]\n]*\]\([^()\s]*(?:\s+\"[^\"\n]*\")?\)\s*$")


class Text:
    """A block's text with the absolute source offset of every character (quotes and lists strip prefixes)."""

    def __init__(self):
        self.chars, self.offsets = [], []

    def add(self, text, offset):
        self.chars.append(text)
        self.offsets.extend(range(offset, offset + len(text)))

    def newline(self):
        if self.offsets:
            self.chars.append("\n")
            self.offsets.append(self.offsets[-1] + 1)

    @property
    def text(self):
        return "".join(self.chars)

    def at(self, index):
        if not self.offsets:
            return 0
        return self.offsets[min(index, len(self.offsets) - 1)] + (1 if index >= len(self.offsets) else 0)


# ---------------------------------------------------------------------------- block structure

def _lines(source):
    out, position = [], 0
    for line in source.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        out.append((stripped, position))
        position += len(line)
    return out


def _cells(line, offset):
    """Split a pipe-table row into (text, offset) cells; escaped pipes stay in the cell."""
    start = len(line) - len(line.lstrip())
    body = line.rstrip()
    if body[start:start + 1] == "|":
        start += 1
    end = len(body) - 1 if body.endswith("|") and not body.endswith("\\|") else len(body)
    cells, begin, i = [], start, start
    while i <= end:
        if i == end or (body[i] == "|" and body[i - 1:i] != "\\"):
            cell = body[begin:i]
            lead = len(cell) - len(cell.lstrip())
            cells.append((cell.strip(), offset + begin + lead))
            begin = i + 1
        i += 1
    return cells


def blocks_of(source):
    """Line-level structure: [{type, ...raw parts with offsets}]. Inline parsing happens later."""
    lines, blocks, i = _lines(source), [], 0
    while i < len(lines):
        line, offset = lines[i]
        if not line.strip():
            i += 1
            continue
        fence = FENCE.match(line)
        if fence:
            marker, body, j = fence.group(1), [], i + 1
            while j < len(lines) and not (lines[j][0].strip().startswith(marker[0] * len(marker))
                                          and not lines[j][0].strip().strip(marker[0])):
                body.append(lines[j])
                j += 1
            text = "\n".join(t for t, _ in body)
            blocks.append({"type": "code", "lang": fence.group(2) or None, "offset": offset,
                           "text": text, "text_offset": body[0][1] if body else offset + len(line)})
            i = j + 1
            continue
        heading = HEADING.match(line)
        if heading:
            content = heading.group(2) or ""
            start = offset + (line.index(content) if content else len(line))
            blocks.append({"type": "heading", "level": len(heading.group(1)), "offset": offset, "parts": [(content, start)]})
            i += 1
            continue
        if RULE.match(line):
            blocks.append({"type": "rule", "offset": offset})
            i += 1
            continue
        if "|" in line and i + 1 < len(lines) and TABLE_DELIMITER.match(lines[i + 1][0]) and "-" in lines[i + 1][0]:
            rows, j = [_cells(line, offset)], i + 2
            while j < len(lines) and lines[j][0].strip() and "|" in lines[j][0]:
                rows.append(_cells(*lines[j]))
                j += 1
            blocks.append({"type": "table", "offset": offset, "header": rows[0], "rows": rows[1:]})
            i = j
            continue
        if QUOTE.match(line):
            parts, j = [], i
            while j < len(lines) and lines[j][0].strip() and QUOTE.match(lines[j][0]):
                inner = QUOTE.match(lines[j][0])
                parts.append((inner.group(1), lines[j][1] + inner.start(1)))
                j += 1
            blocks.append({"type": "quote", "offset": offset, "parts": parts})
            i = j
            continue
        item = ITEM.match(line)
        if item:
            items, j = [], i
            ordered = item.group(2)[0].isdigit()
            while j < len(lines):
                current = ITEM.match(lines[j][0])
                if not current or current.group(2)[0].isdigit() != ordered:
                    break
                parts = [(current.group(3), lines[j][1] + current.start(3))]
                marker = current.group(2)
                j += 1
                while j < len(lines) and lines[j][0].strip() and not ITEM.match(lines[j][0]) \
                        and lines[j][0][:1] in (" ", "\t"):
                    text = lines[j][0].lstrip()
                    parts.append((text, lines[j][1] + len(lines[j][0]) - len(text)))
                    j += 1
                items.append({"depth": len(current.group(1).expandtabs(4)) // 2, "marker": marker,
                              "ordinal": int(marker[:-1]) if ordered else None, "offset": parts[0][1], "parts": parts})
                while j < len(lines) and not lines[j][0].strip() and j + 1 < len(lines) and ITEM.match(lines[j + 1][0]) \
                        and ITEM.match(lines[j + 1][0]).group(2)[0].isdigit() == ordered:
                    j += 1  # loose list: a blank line between items of the same list
            blocks.append({"type": "list", "ordered": ordered, "offset": offset, "items": items})
            i = j
            continue
        parts, j = [], i
        while j < len(lines) and lines[j][0].strip():
            text = lines[j][0]
            if j > i and (FENCE.match(text) or HEADING.match(text) or QUOTE.match(text) or ITEM.match(text)
                          or RULE.match(text)):
                break
            lead = len(text) - len(text.lstrip())
            parts.append((text.strip(), lines[j][1] + lead))
            j += 1
        figure = len(parts) == 1 and IMAGE_ONLY.match(parts[0][0])
        blocks.append({"type": "figure" if figure else "paragraph", "offset": offset, "parts": parts})
        i = j
    return blocks


def _text(parts):
    text = Text()
    for n, (part, offset) in enumerate(parts):
        if n:
            text.newline()
        text.add(part, offset)
    return text


# ---------------------------------------------------------------------------- inline tokens

def _pointer_kind(target):
    for kind, pattern in CITABLE.items():
        if pattern.fullmatch(target):
            return kind
    return None


def _emphasis(text, offsets, start, end, out):
    """Split plain text into styled runs (**strong**, *em*); identifiers with underscores stay literal."""
    segment, cursor = text[start:end], 0
    for match in EMPHASIS.finditer(segment):
        if match.start() > cursor:
            out.append({"t": "text", "text": segment[cursor:match.start()], "offset": offsets(start + cursor)})
        style = "strong" if match.group("strong") is not None else "em"
        inner = match.group(style)
        out.append({"t": "text", "text": inner, "style": style, "offset": offsets(start + match.start(style))})
        cursor = match.end()
    if cursor < len(segment):
        out.append({"t": "text", "text": segment[cursor:], "offset": offsets(start + cursor)})


def inline(text):
    """Tokens of one block text: text (with style), code, link, pointer, figure, url. Each has its source offset."""
    raw, out, cursor = text.text, [], 0
    at = text.at
    for match in INLINE.finditer(raw):
        if match.start() > cursor:
            _emphasis(raw, at, cursor, match.start(), out)
        offset, length = at(match.start()), match.end() - match.start()
        if match.group("code"):
            out.append({"t": "code", "text": match.group("code_text"), "offset": at(match.start("code_text"))})
        elif match.group("src") is not None and match.group(0).startswith("!"):
            target = match.group("src")
            out.append({"t": "figure", "id": target, "kind": _pointer_kind(target), "caption": match.group("alt"),
                        "caption_offset": at(match.start("alt")), "offset": offset, "length": length})
        elif match.group("href") is not None:
            target, label = match.group("href"), match.group("ltext")
            kind = _pointer_kind(target)
            if kind or POINTER_SHAPE.match(target) or OTHER_IDENTIFIER.match(target):
                out.append({"t": "pointer", "id": target, "kind": kind, "text": label, "form": "link",
                            "text_offset": at(match.start("ltext")), "offset": offset, "length": length})
            elif re.match(r"^(?:https?://|mailto:)", target, re.I):
                out.append({"t": "link", "href": target, "text": label, "text_offset": at(match.start("ltext")),
                            "offset": offset})
            else:  # relative paths and other schemes are never linked
                out.append({"t": "text", "text": label, "offset": at(match.start("ltext")), "unlinked": target})
        elif match.group("cite"):
            for part in re.finditer(r"(?:claim|artifact|post)_[0-9A-Za-z]+", match.group("cite")):
                start = match.start("cite") + part.start()
                out.append({"t": "pointer", "id": part.group(0), "kind": _pointer_kind(part.group(0)),
                            "text": part.group(0), "form": "citation", "offset": at(start), "length": len(part.group(0))})
        elif match.group("bare"):
            out.append({"t": "pointer", "id": match.group("bare"), "kind": _pointer_kind(match.group("bare")),
                        "text": match.group("bare"), "form": "bare", "offset": offset, "length": length})
        else:
            url = match.group("url").strip("<>")
            out.append({"t": "link", "href": url, "text": url, "text_offset": at(match.start()), "offset": offset,
                        "autolink": True})
        cursor = match.end()
    if cursor < len(raw):
        _emphasis(raw, at, cursor, len(raw), out)
    return out


# ---------------------------------------------------------------------------- sentences

def _boundaries(token_text):
    """Indices just after sentence-ending punctuation within one text token."""
    ends = []
    for match in SENTENCE_END.finditer(token_text):
        word = re.search(r"([A-Za-z.]+)$", token_text[:match.start()])
        if word and word.group(1).lower().rstrip(".") in ABBREVIATIONS:
            continue
        rest = token_text[match.end():].lstrip()
        if rest and rest[0].islower():
            continue
        ends.append(match.end())
    return ends


def _is_citation(token):
    return token["t"] == "pointer" and token["form"] == "citation"


def sentences(tokens):
    """Split a token stream into sentences; leading bracketed citations attach to the previous sentence."""
    groups, current = [], []
    for n, token in enumerate(tokens):
        if token["t"] != "text":
            current.append(token)
            continue
        text, cursor = token["text"], 0
        for end in _boundaries(text):
            following = text[end:].lstrip()
            if not following and n + 1 < len(tokens):
                nxt = tokens[n + 1]
                first = (nxt.get("text") or nxt.get("caption") or nxt.get("id") or " ")[:1]
                if nxt["t"] == "text" and first.islower():
                    continue
            current.append({**token, "text": text[cursor:end], "offset": token["offset"] + cursor})
            groups.append(current)
            current, cursor = [], end
        if cursor < len(text):
            current.append({**token, "text": text[cursor:], "offset": token["offset"] + cursor})
    if current:
        groups.append(current)
    merged = []
    for group in groups:
        lead = 0
        while lead < len(group) and (_is_citation(group[lead]) or (group[lead]["t"] == "text"
                                                                    and not group[lead]["text"].strip())):
            lead += 1
        if merged and lead and any(_is_citation(t) for t in group[:lead]):
            merged[-1].extend(group[:lead])
            group = group[lead:]
        if group and any(t["t"] != "text" or t["text"].strip() for t in group):
            merged.append(group)
        elif group and merged:
            merged[-1].extend(group)
    return merged


# ---------------------------------------------------------------------------- numbers

def _masked(text, extra=()):
    """Replace identifiers, hashes, URLs (and byline dates) with identifier characters so digits there are ignored."""
    masked = list(text)
    for pattern in (URL, IDENTIFIER_LIKE, HEX, *extra):
        for match in pattern.finditer(text):
            masked[match.start():match.end()] = "_" * (match.end() - match.start())
    return "".join(masked)


def numbers_in(text, offset, *, byline=False, heading=False):
    """Numeric tokens of a prose string as [{text, offset, length}] (offsets are source code points)."""
    masked = _masked(text, (DATE,) if byline else ())
    if heading:
        stripped = masked.lstrip()
        numbering = HEADING_NUMBER.match(stripped)
        if numbering:
            start = len(masked) - len(stripped)
            masked = masked[:start] + "_" * numbering.end() + masked[start + numbering.end():]
    found = []
    for match in NUMBER.finditer(masked):
        token = text[match.start():match.end()]
        if any(ch.isdigit() for ch in token):
            found.append({"text": token.strip(), "offset": offset + match.start(), "length": match.end() - match.start()})
    return found


def _token_numbers(token, **flags):
    if token["t"] in ("text", "code"):
        return [(n, None) for n in numbers_in(token["text"], token["offset"], **flags)]
    if token["t"] == "link":
        return [(n, None) for n in numbers_in(token["text"], token["text_offset"], **flags)]
    if token["t"] == "pointer" and token["form"] == "link":
        return [(n, token) for n in numbers_in(token["text"], token["text_offset"], **flags)]
    if token["t"] == "figure":
        return [(n, token) for n in numbers_in(token["caption"], token["caption_offset"], **flags)]
    return []


def check_unit(tokens, **flags):
    """Numbers in one unit (sentence, row, heading) with the pointers that cover each, or None."""
    pointers = [t for t in tokens if t["t"] in ("pointer", "figure")]
    covering = [t["id"] for t in pointers if t.get("kind") in COVERING]
    context = [t["id"] for t in pointers if t.get("kind") == "post"]
    out = []
    for number, inside in (pair for token in tokens for pair in _token_numbers(token, **flags)):
        if inside is not None and inside.get("kind") in COVERING:
            out.append({**number, "covered_by": [inside["id"]], "scope": "pointer"})
        elif covering:
            out.append({**number, "covered_by": list(dict.fromkeys(covering)), "scope": "sentence"})
        else:
            out.append({**number, "covered_by": [], "scope": "none",
                        "reason": "only post pointers (context) in this sentence" if context
                        else "no claim or artifact pointer in this sentence"})
    return out


# ---------------------------------------------------------------------------- parse

def _sentence(n, tokens, **flags):
    first = next((t for t in tokens if t["t"] != "text" or t["text"].strip()), tokens[0])
    last = tokens[-1]
    start = first["offset"] + (len(first["text"]) - len(first["text"].lstrip()) if first["t"] == "text" else 0)
    end = last["offset"] + len(last.get("text") or "") if last["t"] in ("text", "code") else \
        last["offset"] + last.get("length", len(last.get("text") or ""))
    clean = [t for t in tokens if not (t["t"] == "text" and not t["text"])]
    return {"id": f"s{n}", "offset": start, "length": max(0, end - start), "tokens": clean,
            "pointers": list(dict.fromkeys(t["id"] for t in tokens if t["t"] in ("pointer", "figure"))),
            "numbers": check_unit(tokens, **flags)}


def _row(n, cells, fallback):
    """A table row is one checked unit: a number in any cell needs a claim or artifact pointer in the row."""
    tokens = [inline(_text([cell])) for cell in cells]
    flat = [t for cell in tokens for t in cell]
    offset = cells[0][1] if cells else fallback
    unit = _sentence(n, flat or [{"t": "text", "text": "", "offset": offset}])
    return {"id": unit["id"], "cells": tokens, "pointers": unit["pointers"], "numbers": unit["numbers"], "offset": offset}


def parse(source):
    """Blocks with sentences, tokens, numbers and pointers. Pure function of the Markdown source."""
    counter = iter(range(1, 10 ** 9))
    out = []
    for position, block in enumerate(blocks_of(source)):
        kind = block["type"]
        if kind == "paragraph":
            text = _text(block["parts"])
            byline = position < 2 and bool(BYLINE.match(text.text))
            groups = sentences(inline(text))
            out.append({"type": "paragraph", "offset": block["offset"], "byline": byline,
                        "sentences": [_sentence(next(counter), g, byline=byline) for g in groups]})
        elif kind == "figure":
            tokens = inline(_text(block["parts"]))
            figure = next(t for t in tokens if t["t"] == "figure")
            out.append({"type": "figure", "offset": block["offset"], "id": figure["id"], "kind": figure["kind"],
                        "caption": figure["caption"], "sentences": [_sentence(next(counter), [figure])]})
        elif kind == "heading":
            tokens = inline(_text(block["parts"]))
            out.append({"type": "heading", "level": block["level"], "offset": block["offset"],
                        "sentences": [_sentence(next(counter), tokens, heading=True)] if tokens else []})
        elif kind == "quote":
            groups = sentences(inline(_text(block["parts"])))
            out.append({"type": "quote", "offset": block["offset"],
                        "sentences": [_sentence(next(counter), g) for g in groups]})
        elif kind == "list":
            items = []
            for item in block["items"]:
                groups = sentences(inline(_text(item["parts"])))
                items.append({"depth": item["depth"], "ordinal": item["ordinal"], "offset": item["offset"],
                              "sentences": [_sentence(next(counter), g) for g in groups]})
            out.append({"type": "list", "ordered": block["ordered"], "offset": block["offset"], "items": items})
        elif kind == "table":
            out.append({"type": "table", "offset": block["offset"],
                        "header": _row(next(counter), block["header"], block["offset"]),
                        "rows": [_row(next(counter), r, block["offset"]) for r in block["rows"]]})
        elif kind == "code":
            text = block["text"]
            found_ids = list(re.finditer(r"claim_[0-9a-f]{32}|artifact_[0-9a-f]{64}|post_[0-9a-f]{32}", text))
            cites = [m.group(0) for m in found_ids]
            covering = [c for c in dict.fromkeys(cites) if _pointer_kind(c) in COVERING]
            found = []
            for number in numbers_in(text, block["text_offset"]):
                found.append({**number, "covered_by": covering, "scope": "block" if covering else "none",
                              **({} if covering else {"reason": "no claim or artifact identifier in this code block"})})
            out.append({"type": "code", "offset": block["offset"], "lang": block["lang"], "text": text,
                        "id": f"s{next(counter)}", "pointers": list(dict.fromkeys(cites)), "numbers": found,
                        "cites": [{"t": "pointer", "id": m.group(0), "kind": _pointer_kind(m.group(0)), "form": "code",
                                   "offset": block["text_offset"] + m.start(), "length": len(m.group(0))}
                                  for m in found_ids]})
        else:
            out.append({"type": "rule", "offset": block["offset"]})
    return out


def units(blocks):
    """Every checked unit (sentence, table row, code block) with its block index."""
    for n, block in enumerate(blocks):
        if block["type"] == "list":
            for item in block["items"]:
                for sentence in item["sentences"]:
                    yield n, sentence
        elif block["type"] == "table":
            for row in [block["header"], *block["rows"]]:
                yield n, row
        elif block["type"] == "code":
            yield n, block
        else:
            for sentence in block.get("sentences", []):
                yield n, sentence


def pointer_tokens(blocks):
    for n, block in enumerate(blocks):
        cells = [block["header"], *block["rows"]] if block["type"] == "table" else []
        token_lists = ([s["tokens"] for _, s in units([block]) if "tokens" in s]
                       + [cell for row in cells for cell in row["cells"]] + [block.get("cites", [])])
        for tokens in token_lists:
            for token in tokens:
                if token["t"] in ("pointer", "figure"):
                    yield n, token


# ---------------------------------------------------------------------------- resolution

def _line(source, offset):
    return source.count("\n", 0, offset) + 1


def _context(source, offset, length):
    start = source.rfind("\n", 0, offset) + 1
    end = source.find("\n", offset + length)
    return source[start:end if end >= 0 else len(source)][:400]


def resolve_pointer(view, identity, kind, cache):
    """What a cited identifier opens: claim (ledger row and its own pointers), artifact (location, bytes), post."""
    if identity in cache:
        return cache[identity]
    entry = {"id": identity, "kind": kind, "present": False}
    if kind == "claim":
        row = view.one("SELECT * FROM claim WHERE id=?", (identity,))
        if row:
            from daw.commons.claims import describe_claim
            claim = describe_claim(view, row)
            if claim.get("hidden") and "text" not in claim:
                # A claim of a post hidden by moderation resolves, but its text is withheld (C2).
                entry.update(present=True, hidden=True, reason=claim["reason"], post=claim["post"], text=None,
                             status=None, pointers=[], withdrawn_by=None, route=f"/post/{claim['post']}")
                cache[identity] = entry
                return entry
            for pointer in claim["pointers"]:
                if pointer["kind"] == "artifact" or (pointer["kind"] == "locator" and CITABLE["artifact"].fullmatch(
                        pointer["id"])):
                    pointer.update(route=f"/artifact/{pointer['id']}", bytes_url=f"/api/artifacts/{pointer['id']}/bytes")
                elif pointer["kind"] == "post":
                    pointer["route"] = f"/post/{pointer['id']}"
            entry.update(present=True, text=claim["text"], status=claim["status"], stated_status=claim["stated_status"],
                         post=claim["post"], post_title=claim["post_title"], author=claim["author"],
                         author_name=claim["author_name"], scope=claim["scope"], pointers=claim["pointers"],
                         withdrawn_by=claim["withdrawn_by"], marks=claim["marks"], route=f"/claims?post={claim['post']}")
    elif kind == "artifact":
        location = views.locate_artifact(view, identity, quiet=True)
        if location["store"] != "missing":
            store = view.library if location["store"] == "library" else view.workspace(location["participant"])
            row = store.one("SELECT id,derivation_key,output_role,output_blob,manifest_blob FROM artifact WHERE id=?",
                            (identity,))
            manifest = store.json_blob(row["manifest_blob"])
            output = manifest.get("output") or {}
            name = output.get("name") or ""
            owner = "library" if location["store"] == "library" else location["participant"]
            entry.update(present=True, location=location, title=manifest.get("title"), output_role=row["output_role"],
                         derivation_key=row["derivation_key"], sha256=row["output_blob"], name=name,
                         size=output.get("bytes"), route=f"/artifact/{identity}",
                         bytes_url=f"/api/artifacts/{identity}/bytes",
                         image_url=(f"/api/blobs/{owner}/{row['output_blob']}?name={name}"
                                    if name.lower().endswith((".png", ".jpg", ".jpeg")) else None))
    elif kind == "post":
        row = view.one("SELECT id,author,created,body_blob FROM post WHERE id=?", (identity,))
        vis = views.visibility(view)
        if row and vis.withheld(identity):
            entry.update(present=True, hidden=True, reason=vis.reason(identity), route=f"/post/{identity}")
        elif row:
            content = views.content(view, row["body_blob"])
            entry.update(present=True, title=content.get("title"), author=row["author"], created=row["created"],
                         post_kind=content.get("kind"), route=f"/post/{identity}")
    cache[identity] = entry
    return entry


def check(view, source, blocks):
    """(problems, pointer map). Problems carry kind, offset, length, line, quote and the enclosing unit."""
    problems, cache = [], {}
    for n, unit in units(blocks):
        for number in unit["numbers"]:
            if number["scope"] == "none":
                problems.append({"kind": "unpointed_number", "text": number["text"], "offset": number["offset"],
                                 "length": number["length"], "line": _line(source, number["offset"]), "block": n,
                                 "unit": unit["id"], "reason": number["reason"],
                                 "context": _context(source, number["offset"], number["length"])})
    for n, token in pointer_tokens(blocks):
        identity, kind = token["id"], token.get("kind")
        where = {"offset": token["offset"], "length": token.get("length", len(identity)),
                 "line": _line(source, token["offset"]), "block": n, "pointer": identity,
                 "context": _context(source, token["offset"], token.get("length", len(identity)))}
        if token["t"] == "figure" and kind != "artifact":
            problems.append({"kind": "figure_not_artifact", **where,
                             "reason": "a figure must reference an artifact (![caption](artifact_…))"})
            continue
        if kind is None:
            shape = POINTER_SHAPE.match(identity)
            problems.append({"kind": "unresolved_pointer" if shape else "pointer_kind_not_allowed", **where,
                             "reason": "malformed record identifier" if shape else
                             "only claims, artifacts and (for context) posts can be cited"})
            continue
        entry = resolve_pointer(view, identity, kind, cache)
        if not entry["present"]:
            problems.append({"kind": "unresolved_pointer", **where, "reason": {
                "claim": "not a claim in the ledger", "artifact": "not catalogued in the library or any workspace",
                "post": "no such post on this board"}[kind]})
    problems.sort(key=lambda p: (p["offset"], p["kind"]))
    return problems, cache


# ---------------------------------------------------------------------------- regeneration and subgraph

def regeneration(view, post_id, pointers):
    """Withdrawn claims a write-up cites, with their replacement posts and those posts' current claims."""
    withdrawn = []
    for entry in pointers.values():
        if entry["kind"] != "claim" or not entry["present"] or not (entry.get("withdrawn_by") or entry["status"] == "withdrawn"):
            continue
        replacement = entry.get("withdrawn_by")
        vis = views.visibility(view)
        claims = view.rows("SELECT id,ordinal,text,status FROM claim WHERE post=? ORDER BY ordinal", (replacement,)) \
            if replacement else []
        if replacement and vis.withheld(replacement):
            claims = [{"id": c["id"], "ordinal": c["ordinal"], "hidden": True} for c in claims]
        title = None
        if replacement and not vis.withheld(replacement):
            row = view.one("SELECT body_blob FROM post WHERE id=?", (replacement,))
            title = views.content(view, row["body_blob"]).get("title") if row else None
        withdrawn.append({"claim": entry["id"], "text": entry["text"], "withdrawn_by": replacement,
                          "replacement_title": title, "replacement_claims": claims,
                          "same_ordinal": next((c["id"] for c in claims if c["ordinal"] == _ordinal(view, entry["id"])),
                                               None)})
    if not withdrawn:
        return None
    lines = [f"{w['claim']} (withdrawn by {w['withdrawn_by'] or 'its author'})" for w in withdrawn]
    return {"claims": withdrawn,
            "note": "This write-up cites withdrawn claims. It is served only with this flag; commission a "
                    "regeneration from the current ledger. Replacement claims are listed by post, not matched by meaning.",
            "commission": {"task_type": "writing", "subject_kind": "post", "subject_id": post_id,
                           "note": f"Regenerate write-up {post_id} from the current ledger. Withdrawn claims it "
                                   "cites: " + "; ".join(lines) + "."}}


def _ordinal(view, claim):
    row = view.one("SELECT ordinal FROM claim WHERE id=?", (claim,))
    return row["ordinal"] if row else None


_MAPS: "OrderedDict[tuple, dict]" = OrderedDict()


def subgraph(view, post_id, pointers):
    """The evidence map restricted to the write-up, its cited records, cited claims' posts and claim artifacts,
    plus the recorded derivation closure upstream of every artifact. Recorded edges only."""
    cited = sorted(i for i, e in pointers.items() if e["present"])
    key = (str(view.root), view.sequence(), evidence_map.fingerprint(view), post_id, tuple(cited))
    if key in _MAPS:
        _MAPS.move_to_end(key)
        return _MAPS[key]
    graph = evidence_map.build(view)
    keep = {post_id, *cited}
    for entry in pointers.values():
        if entry["kind"] == "claim" and entry["present"]:
            keep.add(entry["post"])
            keep |= {p["id"] for p in entry["pointers"] if p["kind"] in ("artifact", "post")}
    upstream = {}
    for edge in graph.edges.values():
        if edge["relation"] in evidence_map.DERIVATION:
            upstream.setdefault(edge["source"], set()).add(edge["target"])
    stack = [n for n in keep if n in upstream]
    while stack:
        for parent in upstream.get(stack.pop(), ()):
            if parent not in keep:
                keep.add(parent)
                stack.append(parent)
    keep &= set(graph.nodes)
    nodes = [graph.nodes[n] for n in sorted(keep)]
    edges = sorted((e for e in graph.edges.values() if e["source"] in keep and e["target"] in keep),
                   key=lambda e: (e["source"], e["target"], e["relation"]))
    value = {"nodes": nodes, "edges": edges, "positions": evidence_map.layout([n["id"] for n in nodes], edges),
             "seeds": [post_id], "note": "Recorded relations among the cited records and their derivation closure; "
                                         "prose citations are listed as pointers, not drawn as edges."}
    _MAPS[key] = value
    while len(_MAPS) > 32:
        _MAPS.popitem(last=False)
    return value


# ---------------------------------------------------------------------------- render

def writing_request(view, post_id):
    """The writing/digest request this post answers or was published during, when there is one."""
    row = view.one("SELECT * FROM request WHERE answer=? AND task_type IS NOT NULL", (post_id,))
    if row:
        return row
    for event in view.rows("SELECT body FROM event WHERE kind='task_outcome' ORDER BY seq DESC"):
        body = json.loads(event["body"])
        if post_id in (body.get("criteria") or {}).get("posts_published", []):
            return view.one("SELECT * FROM request WHERE id=?", (body["request"],))
    return None


def render_writeup(view, post_id, *, with_map=True):
    """The rendered write-up, or a refusal listing every unpointed number and unresolved pointer.

    Returns {"status": "rendered" | "refused", ...}; callers serve a refusal as HTTP 422."""
    row = view.one("SELECT * FROM post WHERE id=?", (post_id,))
    if not row:
        raise DawError("unknown_post", post_id)
    hidden = views.visibility(view)
    if hidden.hidden(post_id):
        # Hidden by moderation: refused on every surface, operators included; the post is its id and reason.
        request = writing_request(view, post_id)
        return {"post": hidden.stub(post_id),
                "request": {k: request[k] for k in ("id", "task_type", "state", "post", "target")} if request else None,
                "rules": RULES_VERSION, "content_is_untrusted_data": True, "status": "refused",
                "problems": [{"kind": "post_hidden", "reason": hidden.reason(post_id), "offset": 0, "length": 0,
                              "line": 1}], "source": None}
    content = view.library.json_blob(row["body_blob"], verify=True)
    author = view.one("SELECT id,name,kind FROM agent WHERE id=?", (row["author"],)) or {"id": row["author"]}
    request = writing_request(view, post_id)
    base = {"post": {"id": post_id, "title": content.get("title"), "author": author, "created": row["created"],
                     "kind": content.get("kind"), "body_blob": row["body_blob"], "parent": row["parent"]},
            "request": {k: request[k] for k in ("id", "task_type", "state", "post", "target")} if request else None,
            "rules": RULES_VERSION, "content_is_untrusted_data": True}
    source = content.get("body") or ""
    blocks = parse(source)
    problems, pointers = check(view, source, blocks)
    counted = [n for _, unit in units(blocks) for n in unit["numbers"]]
    stats = {"numbers": len(counted), "pointed": sum(1 for n in counted if n["scope"] != "none"),
             "units": sum(1 for _ in units(blocks)), "pointers": len(pointers)}
    flag = regeneration(view, post_id, pointers)
    if problems:
        return {**base, "status": "refused", "problems": problems, "source": source, "stats": stats,
                "regeneration_required": flag}
    return {**base, "status": "rendered", "blocks": blocks, "pointers": pointers, "stats": stats,
            "regeneration_required": flag, "flagged": flag is not None,
            "evidence_map": subgraph(view, post_id, pointers) if with_map else None}
