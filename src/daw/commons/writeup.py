"""Write-ups (M6.1, C5, V2): pointer syntax, the number checker, value-in-record verification and regeneration
flags (Flow B step 5).

A write-up is an ordinary post (usually the answer to a `writing` or `digest` commission). Writers point at
records with Markdown links whose target is a record identifier, `[1.54](claim_…)`, `[text](artifact_…)`,
`[text](post_…)`, or with a bracketed citation `[claim_…]` placed right after the number it supports. An
artifact pointer may carry a locator, `[1.54](artifact_…#row=B_vs_A;col=log2_ratio)` (grammar in
`daw.commons.locators`). Figures are images whose target is an artifact, `![caption](artifact_…)`. A bare
identifier in prose is read as a bracketed citation.

**Coverage is number-granular.** A pointer covers only

- the numbers inside its own link text (`[1.54](claim_…)` covers 1.54; a figure covers its caption), or
- for a bracketed citation or bare identifier, the number immediately preceding it within the same clause:
  the nearest number before the citation in the same sentence (table cell, code line), provided the text
  between them holds no clause boundary (`,` `;` `:` `—` `–` or a spaced hyphen) and no other pointer link,
  code span or URL. Sentence-final punctuation and closing brackets may sit between (`… = 1.54. [claim_…]`).
  Consecutive citations (`1.54 [claim_a] [artifact_b]`) all cover the same number.

So `Means were 11.0 and 32.0 [artifact_…]` covers 32.0 only, and a sentence with two numbers and one pointer
refuses the other number. Post pointers give context only; they never cover a number.

`check` refuses (the write-up is withheld on every surface), listing every location, when

- a number has no claim or artifact pointer (`unpointed_number`);
- a pointer does not resolve: claims must be ledger rows, artifacts catalogued in the library or a
  participant workspace, posts must exist; other identifier kinds are not citable; a locator must parse;
- a figure does not reference a resolving artifact;
- a writing task cites a post that has no ledger claims (`claimless_post_cited`; V1). Digests cite posts as
  the items they summarise, so the rule applies to every write-up except digest deliveries.

Each pointed number is then checked against its record (value-in-record): a claim pointer verifies when the
number occurs in the claim's text or scope; an artifact pointer when the number is at the cited cell, key or
line, at the declared or implied rounding. An artifact pointer without a locator has scope `text` (spec v3 B6):
it verifies only when exactly one numeric token of a text output of at most 64 KB matches, and a `text` match
is shown apart and never counted in `verified_share`. Otherwise the number is `unverified` (with the reason),
which is shown, not refused; it is distinct from `unpointed` and from `verified`.

**Numeric tokens:** optionally signed integers and decimals (thousands separators allowed), scientific
notation (`1e-5`, `3.2×10^-4`, `3.2×10⁻⁴`), percentages, ratios (`3:1`, `1/3`), unicode vulgar fractions
(`½`, `1½`, `1⁄2`), the spelled-out integers zero to twenty (`twenty-one` to `twenty-nine` as one number) and
`a dozen` / `half a dozen`. Heading numbers count like any other number. An integer glued to one lone
lowercase letter is a number with a label, like every other glued form (`n12`, `k5`, the fold multiplier `x2`;
spec v3 B6). **Not numbers:** record identifiers, hashes and URLs; integers glued to an uppercase letter, to two
or more letters, or through one hyphen (identifier characters: `PMP22`, `P1`, `log2`, `GSE1234`, `H3K27me3`,
`IL-6`, `measured-zero`); strand ends `3′`/`5′`
followed by a prime; digits after a digit, underscore or `.`; ordered-list ordinals (Markdown structure);
dates and times in a byline (a paragraph among the first two blocks starting with By / Written by / Prepared
by / Author(s): / Date: / Updated:); spelled `one` after no/the/this/that/each/any/every/which or before
`another`, and spelled numbers in `-sided`, `-tailed` and `-way` compounds. Decimals, exponents and
percentages glued to letters count (`x2.5`, `FC1.54`, `v1.2`). Code spans in prose are prose. Sentences end
at `.`, `!` or `?` followed by whitespace and a character that is not a lowercase letter, except after common
abbreviations (e.g., i.e., et al., Fig., vs., approx.). Bracketed citations at the start of the next sentence
attach to the previous one.

The verdict is a record: at delivery of a writing or digest task the runtime calls
`daw.commons.checks.after_delivery`, which stores the verdict as an immutable `writeup_check` board event
(with every number's location and status) and a verdict blob in the library; every renderer reads it.
A write-up that cites a withdrawn claim (ledger `withdrawn_by`) is flagged for regeneration; the flag is
computed from the ledger at read time, so it needs no write and cannot go stale.

Markdown subset: ATX headings, paragraphs, `-`/`*`/`+` and `1.`/`1)` list items (continuation lines indented),
`>` quotes, fenced code, GFM pipe tables, thematic breaks, inline code, `**strong**` and `*em*`, links and
images. Raw HTML is shown as text; only http(s) and mailto links leave the commons. Everything here reads a
read-only Archive.
"""
import json
import re
from collections import OrderedDict

from daw.commons import evidence_map, federation, locators, views
from daw.util import DawError

RULES_VERSION = "writeup-pointers/3"
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
_TIMES10 = r"(?:\s?[×x]\s?10(?:(?:\^|\*\*)?[-+−]?\d+|[⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+))?"
_VULGAR = "".join(locators.FRACTIONS)
NUMBER = re.compile(rf"(?<![\d_.])(?:[-+−±](?=[\d.{_VULGAR}]))?(?:\d*[{_VULGAR}]|\d+⁄\d+|"
                    rf"{_CORE}{_EXP}{_TIMES10}%?(?:[:/]{_CORE}{_EXP}%?)?)")
_UNITS = "one|two|three|four|five|six|seven|eight|nine"
SPELLED_NUMBER = re.compile(rf"\b(?:half a dozen|a dozen|twenty(?:-(?:{_UNITS}))?|zero|{_UNITS}|ten|eleven|twelve|"
                            r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)\b"
                            r"(?!-(?:sided|tailed|way)\b)", re.I)
NOT_A_COUNT = re.compile(r"(?:\b(?:no|the|this|that|each|any|every|which)\s+)$", re.I)
MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
DATE = re.compile(rf"\b\d{{4}}-\d{{2}}-\d{{2}}(?:[T ]\d{{2}}:\d{{2}}(?::\d{{2}}(?:\.\d+)?)?(?:Z|[+-]\d{{2}}:?\d{{2}})?)?\b"
                  rf"|\b\d{{4}}/\d{{2}}/\d{{2}}\b|\b\d{{1,2}}\s+{MONTH}\s+\d{{4}}\b|\b{MONTH}\s+\d{{1,2}},?\s+\d{{4}}\b"
                  rf"|\b{MONTH}\s+\d{{4}}\b|\b\d{{1,2}}:\d{{2}}(?::\d{{2}})?\s*(?:UTC|Z)?\b")
BYLINE = re.compile(r"^[\s*_]*(?:by|written by|prepared by|authors?:|date:|updated:)\s", re.I)
ABBREVIATIONS = {"e.g", "i.e", "al", "fig", "figs", "vs", "approx", "cf", "eq", "eqs", "no", "ca", "resp", "ref",
                 "refs", "suppl", "sec", "dr", "mr", "ms", "st", "etc"}
SENTENCE_END = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s)")
# A clause boundary between a number and the citation after it: the citation does not cover that number.
CLAUSE = re.compile(r"[;:,—–]|\s[-−]\s")
_LOCATOR = r"(?:\#[a-z]+=[^\]\s;,()]*(?:;[a-z]+=[^\]\s;,()]*)*)?"
# V7: a record of an imported snapshot, `snapshot:<snapshot id>/claim_…` or `…/artifact_…` (daw.commons.federation).
_FOREIGN = r"(?:snapshot:[0-9a-f]{64}/)?"

INLINE = re.compile(rf"""
  (?P<code>`+)(?P<code_text>.+?)(?P=code)
| !\[(?P<alt>[^\]\n]*)\]\((?P<src>[^()\s]*)(?:\s+"[^"\n]*")?\)
| \[(?P<ltext>[^\]\n]+)\]\((?P<href>[^()\s]*)(?:\s+"[^"\n]*")?\)
| \[(?P<cite>{_FOREIGN}(?:claim|artifact|post)_[0-9A-Za-z]+{_LOCATOR}(?:\s*[,;]\s*{_FOREIGN}(?:claim|artifact|post)_[0-9A-Za-z]+{_LOCATOR})*)\](?!\()
| (?P<bare>\b(?:snapshot:[0-9a-f]{{64}}/(?:claim_[0-9a-f]{{32}}|artifact_[0-9a-f]{{64}})|claim_[0-9a-f]{{32}}|post_[0-9a-f]{{32}}|artifact_[0-9a-f]{{64}})\b)
| (?P<url><https?://[^\s<>]+>|\bhttps?://[^\s<>()\[\]]+)
""", re.X | re.S)
CITE_ITEM = re.compile(rf"{_FOREIGN}(?:claim|artifact|post)_[0-9A-Za-z]+{_LOCATOR}")
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
    if target.startswith("snapshot:"):
        return federation.kind_of(target)  # claim or artifact of an imported snapshot; None when malformed
    for kind, pattern in CITABLE.items():
        if pattern.fullmatch(target):
            return kind
    return None


def split_target(target):
    """`artifact_…#row=B;col=x` -> (identifier, locator or None)."""
    identity, mark, locator = target.partition("#")
    return identity, (locator if mark else None)


def _runs(text, index, offsets, style=None):
    """Text runs that are contiguous in the source: a run is split after each line break, because a block's
    continuation lines lose their indentation (and quotes and list items their markers), so offsets past a
    line break do not follow from the run's first offset."""
    out, cursor = [], 0
    while cursor < len(text):
        newline = text.find("\n", cursor)
        stop = len(text) if newline < 0 else newline + 1
        run = {"t": "text", "text": text[cursor:stop], "offset": offsets(index + cursor)}
        if style:
            run["style"] = style
        out.append(run)
        cursor = stop
    return out


def _emphasis(text, offsets, start, end, out):
    """Split plain text into styled runs (**strong**, *em*); identifiers with underscores stay literal."""
    segment, cursor = text[start:end], 0
    for match in EMPHASIS.finditer(segment):
        if match.start() > cursor:
            out.extend(_runs(segment[cursor:match.start()], start + cursor, offsets))
        style = "strong" if match.group("strong") is not None else "em"
        inner = match.group(style)
        out.extend(_runs(inner, start + match.start(style), offsets, style))
        cursor = match.end()
    if cursor < len(segment):
        out.extend(_runs(segment[cursor:], start + cursor, offsets))


def inline(text):
    """Tokens of one block text: text (with style), code, link, pointer, figure, url. Each has its source offset.
    Pointer tokens carry `id` (the record identifier), `locator` (after '#', or None) and `form`."""
    raw, out, cursor = text.text, [], 0
    at = text.at
    for match in INLINE.finditer(raw):
        if match.start() > cursor:
            _emphasis(raw, at, cursor, match.start(), out)
        offset, length = at(match.start()), match.end() - match.start()
        if match.group("code"):
            out.append({"t": "code", "text": match.group("code_text"), "offset": at(match.start("code_text"))})
        elif match.group("src") is not None and match.group(0).startswith("!"):
            target, locator = split_target(match.group("src"))
            out.append({"t": "figure", "id": target, "kind": _pointer_kind(target), "locator": locator,
                        "caption": match.group("alt"), "caption_offset": at(match.start("alt")), "offset": offset,
                        "length": length})
        elif match.group("href") is not None:
            href, label = match.group("href"), match.group("ltext")
            target, locator = split_target(href)
            kind = _pointer_kind(target)
            if kind or POINTER_SHAPE.match(target) or OTHER_IDENTIFIER.match(target) or federation.FOREIGN_SHAPE.match(target):
                out.append({"t": "pointer", "id": target, "kind": kind, "locator": locator, "text": label,
                            "form": "link", "text_offset": at(match.start("ltext")), "offset": offset, "length": length})
            elif re.match(r"^(?:https?://|mailto:)", href, re.I):
                out.append({"t": "link", "href": href, "text": label, "text_offset": at(match.start("ltext")),
                            "offset": offset})
            else:  # relative paths and other schemes are never linked
                out.append({"t": "text", "text": label, "offset": at(match.start("ltext")), "unlinked": href})
        elif match.group("cite"):
            for part in CITE_ITEM.finditer(match.group("cite")):
                start = match.start("cite") + part.start()
                target, locator = split_target(part.group(0))
                out.append({"t": "pointer", "id": target, "kind": _pointer_kind(target), "locator": locator,
                            "text": part.group(0), "form": "citation", "offset": at(start), "length": len(part.group(0))})
        elif match.group("bare"):
            out.append({"t": "pointer", "id": match.group("bare"), "kind": _pointer_kind(match.group("bare")),
                        "locator": None, "text": match.group("bare"), "form": "bare", "offset": offset, "length": length})
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


def _multiplier(masked, start):
    """`x2` / `X10`: a lone x before digits is a fold multiplier, not an identifier letter."""
    return start >= 1 and masked[start - 1] in "xX" and (start < 2 or not masked[start - 2].isalnum())


def _labelled(masked, start):
    """`n12`, `k5`: one lone lowercase letter glued to an integer labels a number (B6); a letter that follows
    another letter, a digit, `_` or `-` is part of an identifier (`log2`, `IL-6`), and uppercase prefixes
    (`P1`, `H3`) name things."""
    if start < 1 or not ("a" <= masked[start - 1] <= "z"):
        return False
    return start < 2 or not (masked[start - 2].isalnum() or masked[start - 2] in "_-−")


def numbers_in(text, offset, *, byline=False, spelled=True):
    """Numeric tokens of a prose string as [{text, offset, length[, spelled]}] (offsets are source code points)."""
    masked = _masked(text, (DATE,) if byline else ())
    found = []
    for match in NUMBER.finditer(masked):
        start, end = match.start(), match.end()
        token = text[start:end]
        if not any(ch.isdigit() or ch in _VULGAR for ch in token):
            continue
        before = masked[start - 1] if start else ""
        if token[0] in "-−" and before.isalpha():  # a hyphen joining a word (IL-6, SARS-CoV-2) is not a sign
            start, token = start + 1, token[1:]
            glued = True
        else:
            glued = before.isalpha()
        separator = re.match(r"\d+[:/]", token) if glued else None
        if separator:  # chr10:49316968, P1/2: the glued integer is an identifier, the rest a number
            start, token, glued = start + separator.end(), token[separator.end():], False
        if glued and token.isdigit() and not _multiplier(masked, start) and not _labelled(masked, start):
            continue  # integer identifier characters: PMP22, log2, GSE1234, H3K27me3
        if token in ("3", "5") and text[end:end + 1] in ("′", "'", "’"):
            continue  # strand ends: 3′ UTR, 5'-end
        found.append({"text": token.strip(), "offset": offset + start, "length": end - start})
    if spelled:
        for match in SPELLED_NUMBER.finditer(masked):
            start = match.start()
            if start >= 2 and masked[start - 1] in "-−" and masked[start - 2].isalpha():
                continue  # hyphen-joined to a word: measured-zero
            word = match.group(0)
            if word.lower() == "one" and (NOT_A_COUNT.search(masked[:start])
                                          or masked[match.end():].lstrip().lower().startswith("another")):
                continue
            found.append({"text": word, "offset": offset + start, "length": len(word), "spelled": True})
        found.sort(key=lambda n: n["offset"])
    return found


def _token_text(token):
    """(text, source offset) of the prose a token shows, or (None, None) for tokens without prose numbers."""
    kind = token["t"]
    if kind in ("text", "code"):
        return token["text"], token["offset"]
    if kind == "link" or (kind == "pointer" and token["form"] == "link"):
        return token["text"], token["text_offset"]
    if kind == "figure":
        return token["caption"], token["caption_offset"]
    return None, None


def _reference(token):
    return {"id": token["id"], "kind": token.get("kind"), "locator": token.get("locator"),
            "form": "figure" if token["t"] == "figure" else token["form"]}


def _scope(pointers):
    """cell (an artifact pointer with a cell or JSON-key locator) > claim > line (an artifact pointer at the number
    with `line=N`, or an invalid locator) > text (an artifact pointer without a locator: a value found anywhere in
    the output, spec v3 B6) > none."""
    artifacts = [p for p in pointers if p["kind"] == "artifact"]
    kinds = set()
    for pointer in artifacts:
        try:
            kinds.add(locators.target_kind(locators.parse_locator(pointer["locator"]) if pointer["locator"] else {}))
        except locators.LocatorError:
            kinds.add("line")  # an invalid locator is refused by the checker; it names a place, not the whole output
    if kinds & {"cell", "key"}:
        return "cell"
    if any(p["kind"] == "claim" for p in pointers):
        return "claim"
    if "line" in kinds:
        return "line"
    return "text" if artifacts else "none"


def cover(tokens, **flags):
    """Numbers of one unit, each with the pointers that cover it (number-granular; see the module docstring)."""
    per_token = []
    for token in tokens:
        text, base = _token_text(token)
        found = []
        for number in numbers_in(text, base, **flags) if text is not None else ():
            item = {**number, "pointers": []}
            if token["t"] == "figure" or (token["t"] == "pointer" and token["form"] == "link"):
                item["pointers"].append(_reference(token))
            found.append((item, number["offset"] - base + number["length"]))
        per_token.append(found)
    for i, token in enumerate(tokens):
        if token["t"] != "pointer" or token["form"] not in ("citation", "bare"):
            continue
        gap = ""
        for j in range(i - 1, -1, -1):
            previous = tokens[j]
            if previous["t"] == "pointer" and previous["form"] in ("citation", "bare"):
                continue
            if per_token[j]:
                item, end = per_token[j][-1]
                if not CLAUSE.search(_token_text(previous)[0][end:] + gap):
                    item["pointers"].append(_reference(token))
                break
            if previous["t"] != "text":
                break
            gap = previous["text"] + gap
            if CLAUSE.search(gap):
                break
    out = []
    for found in per_token:
        for item, _ in found:
            pointers = list({(p["id"], p["locator"]): p for p in item["pointers"]}.values())
            covering = [p for p in pointers if p["kind"] in COVERING]
            scope = _scope(covering)
            entry = {**item, "pointers": pointers, "covered_by": list(dict.fromkeys(p["id"] for p in covering)),
                     "scope": scope}
            if scope == "none":
                entry["reason"] = ("a post pointer gives context only; point the number at a claim or artifact"
                                   if any(p["kind"] == "post" for p in pointers)
                                   else "no claim or artifact pointer at this number")
            out.append(entry)
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
            "numbers": cover(tokens, **flags)}


def _row(n, cells, fallback):
    """A table row is one reported unit; coverage is per cell (a citation covers the number before it in its cell)."""
    tokens = [inline(_text([cell])) for cell in cells]
    flat = [t for cell in tokens for t in cell]
    offset = cells[0][1] if cells else fallback
    unit = _sentence(n, flat or [{"t": "text", "text": "", "offset": offset}])
    numbers = [number for cell in tokens for number in cover(cell)]
    return {"id": unit["id"], "cells": tokens, "pointers": unit["pointers"], "numbers": numbers, "offset": offset}


CODE_IDENTIFIER = re.compile(r"snapshot:[0-9a-f]{64}/(?:claim_[0-9a-f]{32}|artifact_[0-9a-f]{64})|"
                             r"claim_[0-9a-f]{32}|artifact_[0-9a-f]{64}|post_[0-9a-f]{32}")


def _code_numbers(text, offset):
    """In a fenced block an identifier covers the number before it on its own line (same clause rule)."""
    numbers, position = [], offset
    for line in text.split("\n"):
        tokens, cursor = [], 0
        for match in CODE_IDENTIFIER.finditer(line):
            if match.start() > cursor:
                tokens.append({"t": "text", "text": line[cursor:match.start()], "offset": position + cursor})
            tokens.append({"t": "pointer", "id": match.group(0), "kind": _pointer_kind(match.group(0)), "locator": None,
                           "text": match.group(0), "form": "bare", "offset": position + match.start(),
                           "length": len(match.group(0))})
            cursor = match.end()
        if cursor < len(line):
            tokens.append({"t": "text", "text": line[cursor:], "offset": position + cursor})
        numbers += cover(tokens, spelled=False)
        position += len(line) + 1
    return numbers


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
                        "locator": figure["locator"], "caption": figure["caption"],
                        "sentences": [_sentence(next(counter), [figure])]})
        elif kind == "heading":
            tokens = inline(_text(block["parts"]))
            out.append({"type": "heading", "level": block["level"], "offset": block["offset"],
                        "sentences": [_sentence(next(counter), tokens)] if tokens else []})
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
            found_ids = list(CODE_IDENTIFIER.finditer(text))
            out.append({"type": "code", "offset": block["offset"], "text_offset": block["text_offset"],
                        "lang": block["lang"], "text": text,
                        "id": f"s{next(counter)}", "pointers": list(dict.fromkeys(m.group(0) for m in found_ids)),
                        "numbers": _code_numbers(text, block["text_offset"]),
                        "cites": [{"t": "pointer", "id": m.group(0), "kind": _pointer_kind(m.group(0)), "locator": None,
                                   "form": "code", "offset": block["text_offset"] + m.start(), "length": len(m.group(0))}
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


def all_numbers(blocks):
    """(block index, unit, number) for every number in reading order."""
    for n, unit in units(blocks):
        for number in unit["numbers"]:
            yield n, unit, number


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
    return source[start:end if end >= 0 else len(source)][:400], start


def resolve_pointer(view, identity, kind, cache):
    """What a cited identifier opens: claim (ledger row and its own pointers), artifact (location, bytes), post."""
    if identity in cache:
        return cache[identity]
    if identity.startswith("snapshot:"):
        cache[identity] = federation.resolve(view, identity, kind)  # V7: through the federation index
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
        claims = view.one("SELECT count(*) AS n FROM claim WHERE post=?", (identity,))["n"] if row else 0
        if row and vis.withheld(identity):
            entry.update(present=True, hidden=True, reason=vis.reason(identity), claims=claims,
                         route=f"/post/{identity}")
        elif row:
            content = views.content(view, row["body_blob"])
            entry.update(present=True, title=vis.title(identity, content.get("title")), author=row["author"],
                         created=row["created"],
                         post_kind=content.get("kind"), claims=claims, route=f"/post/{identity}")
    cache[identity] = entry
    return entry


def verify_numbers(view, blocks, cache, outputs=None):
    """Value-in-record: annotate every number with `status` (verified | unverified | unpointed) and each covering
    pointer with its `result`, `at`, `reason` and `found` (the cited cell, key, line or claim text)."""
    outputs = {} if outputs is None else outputs
    for _, _, number in all_numbers(blocks):
        value = locators.parse_number(number["text"])
        results = []
        for pointer in number["pointers"]:
            if pointer["kind"] not in COVERING:
                continue
            entry = resolve_pointer(view, pointer["id"], pointer["kind"], cache)
            if not entry["present"]:
                result = {"result": "unverified", "at": None, "reason": "the pointer does not resolve"}
            elif pointer["kind"] == "claim":
                result = locators.verify_claim(entry, value)
            else:
                if entry.get("foreign") and pointer["id"] not in outputs:
                    outputs[pointer["id"]] = federation.artifact_output(view, pointer["id"])  # snapshot bytes
                result = locators.verify_artifact(view, pointer["id"], pointer["locator"], value, outputs)
            pointer.update(result)
            results.append(result)
        number["status"] = ("verified" if any(r["result"] == "verified" for r in results)
                            else "unverified" if results else "unpointed")
    return blocks


def check(view, source, blocks, *, task_type=None):
    """(problems, pointer map). Verifies every pointed number in place. Problems carry kind, offset, length,
    line, the source line as `context` (with `context_start`) and the enclosing unit."""
    problems, cache = [], {}

    def where(offset, length):
        context, start = _context(source, offset, length)
        return {"offset": offset, "length": length, "line": _line(source, offset), "context": context,
                "context_start": start}

    for n, unit, number in all_numbers(blocks):
        if number["scope"] == "none":
            problems.append({"kind": "unpointed_number", "text": number["text"], **where(number["offset"], number["length"]),
                             "block": n, "unit": unit["id"], "reason": number["reason"]})
    for n, token in pointer_tokens(blocks):
        identity, kind = token["id"], token.get("kind")
        span = {**where(token["offset"], token.get("length", len(identity))), "block": n, "pointer": identity}
        if token["t"] == "figure" and kind != "artifact":
            problems.append({"kind": "figure_not_artifact", **span,
                             "reason": "a figure must reference an artifact (![caption](artifact_…))"})
            continue
        if kind is None:
            shape = POINTER_SHAPE.match(identity)
            problems.append({"kind": "unresolved_pointer" if shape else "pointer_kind_not_allowed", **span,
                             "reason": "malformed record identifier" if shape else
                             "only claims, artifacts and (for context) posts can be cited"})
            continue
        if token.get("locator") is not None:
            try:
                if kind != "artifact":
                    raise locators.LocatorError("only artifact pointers take a locator")
                locators.parse_locator(token["locator"])
            except locators.LocatorError as error:
                problems.append({"kind": "invalid_locator", **span, "locator": token["locator"], "reason": str(error)})
        entry = resolve_pointer(view, identity, kind, cache)
        if not entry["present"]:
            problems.append({"kind": "unresolved_pointer", **span, "reason": entry.get("reason") if entry.get("foreign") else {
                "claim": "not a claim in the ledger", "artifact": "not catalogued in the library or any workspace",
                "post": "no such post on this board"}[kind]})
        elif kind == "post" and task_type != "digest" and not entry.get("claims"):
            problems.append({"kind": "claimless_post_cited", **span,
                             "reason": "a writing task does not cite a post without ledger claims; cite the claims "
                                       "or artifacts it rests on"})
    verify_numbers(view, blocks, cache)
    problems.sort(key=lambda p: (p["offset"], p["kind"]))
    return problems, cache


def number_records(source, blocks):
    """Compact per-number locations and statuses (stored in verdicts and served to readers)."""
    out = []
    for n, unit, number in all_numbers(blocks):
        out.append({"text": number["text"], "offset": number["offset"], "length": number["length"],
                    "line": _line(source, number["offset"]), "block": n, "unit": unit["id"],
                    "scope": number["scope"], "status": number.get("status", "unpointed"),
                    **({"reason": number["reason"]} if number.get("reason") else {}),
                    "pointers": [{k: p.get(k) for k in ("id", "kind", "locator", "form", "result", "at", "reason", "found")
                                  if p.get(k) is not None} for p in number["pointers"]]})
    return out


def statistics(records, blocks, pointers):
    counted = [r["status"] for r in records]
    return {"numbers": len(records), "pointed": sum(1 for r in records if r["scope"] != "none"),
            "verified": counted.count("verified"), "unverified": counted.count("unverified"),
            "unpointed": counted.count("unpointed"), "units": sum(1 for _ in units(blocks)), "pointers": len(pointers),
            "scopes": {s: sum(1 for r in records if r["scope"] == s) for s in ("cell", "claim", "line", "text", "none")}}


def overlay(blocks, records):
    """Apply recorded per-number statuses (a stored verdict) to freshly parsed blocks, matched by source offset."""
    by_offset = {r["offset"]: r for r in records}
    for _, _, number in all_numbers(blocks):
        recorded = by_offset.get(number["offset"])
        if not recorded:
            continue
        number["status"], number["scope"] = recorded["status"], recorded["scope"]
        results = {(p["id"], p.get("locator")): p for p in recorded.get("pointers", [])}
        for pointer in number["pointers"]:
            stored = results.get((pointer["id"], pointer.get("locator")))
            if stored:
                pointer.update({k: stored[k] for k in ("result", "at", "reason", "found") if k in stored})
    return blocks


# ---------------------------------------------------------------------------- regeneration and subgraph

def _supersession(view):
    """{post: [direct replacements]} from the immutable post.supersedes column."""
    replaced = {}
    for row in view.rows("SELECT id,supersedes FROM post WHERE supersedes IS NOT NULL ORDER BY seq"):
        replaced.setdefault(row["supersedes"], []).append(row["id"])
    return replaced


def _chain(replaced, post):
    """Every later version of a post (replacements of replacements), oldest first."""
    seen, queue = [], list(replaced.get(post, []))
    while queue:
        current = queue.pop(0)
        if current not in seen:
            seen.append(current)
            queue += replaced.get(current, [])
    return seen


def _producing_questions(view, artifacts):
    """{artifact: {(agent, question): registered at}}: the questions that registered each artifact (`produced`
    links in the agents' own catalogs, timed by their work event; recorded only)."""
    found = {}
    if not artifacts:
        return found
    marks = ",".join("?" * len(artifacts))
    for agent in view.rows("SELECT id FROM agent WHERE trial IS NOT NULL ORDER BY id"):
        try:
            ws = view.workspace(agent["id"])
            links = ws.rows(f"SELECT qa.artifact_id,qa.question_id,e.created FROM question_artifact qa JOIN work_event e "
                            f"ON e.id=qa.event_id WHERE qa.relationship='produced' AND qa.artifact_id IN ({marks})",
                            list(artifacts)) if ws else []
        except DawError:
            continue  # no catalog: this participant produced nothing readable here
        for link in links:
            found.setdefault(link["artifact_id"], {})[(agent["id"], link["question_id"])] = link["created"]
    return found


def _artifact_backing(view, replaced, artifacts):
    """For each artifact: the posts naming it in their evidence, split into superseded and current; the superseded
    publications of the question that produced it; and whether a current ledger claim points at it. Read from
    `published` events, the agents' catalogs and the claim projection (recorded only)."""
    backing = {a: {"superseded": [], "current": [], "producer_superseded": [], "claims": False} for a in artifacts}
    producing = _producing_questions(view, sorted(backing))
    for row in view.rows("SELECT body,created FROM event WHERE kind='published' ORDER BY seq"):
        body = json.loads(row["body"])
        evidence = body.get("evidence") or {}
        named = evidence.get("artifacts") or []
        for artifact in set(named) & set(backing):
            backing[artifact]["superseded" if body.get("post") in replaced else "current"].append(body.get("post"))
        notebook = evidence.get("notebook") if isinstance(evidence.get("notebook"), dict) else {}
        if body.get("post") in replaced and notebook.get("question"):
            # A superseded publication of the producing question, published once the artifact existed.
            source = (body.get("author"), notebook["question"])
            for artifact, questions in producing.items():
                if source in questions and questions[source] <= row["created"]:
                    backing[artifact]["producer_superseded"].append(body.get("post"))
    for row in view.rows("SELECT pointers FROM claim WHERE status!='withdrawn' AND withdrawn_by IS NULL"):
        for pointer in json.loads(row["pointers"] or "[]"):
            if isinstance(pointer, dict) and pointer.get("id") in backing:
                backing[pointer["id"]]["claims"] = True
    return backing


def regeneration(view, post_id, pointers):
    """Why a write-up should be regenerated (Flow B step 5), or None. Three recorded reasons:

    - it cites a withdrawn ledger claim (with the replacement post and its current claims);
    - it cites a post that has been superseded, and cites no later version of it;
    - it cites an artifact named by a superseded publication, or produced by a question that published, once the
      artifact existed, a post that was later superseded (B14). A current publication or claim that re-lists the
      artifact does not clear the flag (a correction may re-list what it corrects); the flag names the
      publications that re-listed it.

    Supersession is read from `post.supersedes`, evidence from `published` events; nothing is matched by meaning."""
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
    replaced = _supersession(view)
    cited = {i for i, e in pointers.items() if e["present"]}
    posts = []
    for entry in pointers.values():
        if entry["kind"] != "post" or not entry["present"] or entry["id"] not in replaced:
            continue
        later = _chain(replaced, entry["id"])
        if not set(later) & cited:
            posts.append({"post": entry["id"], "title": entry.get("title"), "superseded_by": later[-1],
                          "replacements": later})
    artifacts = []
    present = sorted(i for i, e in pointers.items() if e["kind"] == "artifact" and e["present"])
    if present and replaced:
        for artifact, found in _artifact_backing(view, replaced, present).items():
            superseded = sorted(set(found["superseded"]) | set(found["producer_superseded"]))
            if superseded:
                artifacts.append({"artifact": artifact, "superseded_posts": superseded,
                                  "producer_superseded": sorted(set(found["producer_superseded"])),
                                  "replacements": sorted({r for p in superseded for r in _chain(replaced, p)}),
                                  "relisted_by": found["current"], "current_claims": found["claims"]})
    if not (withdrawn or posts or artifacts):
        return None
    lines = ([f"{w['claim']} (withdrawn by {w['withdrawn_by'] or 'its author'})" for w in withdrawn]
             + [f"{p['post']} (superseded by {p['superseded_by']})" for p in posts]
             + [f"{a['artifact']} (from superseded {', '.join(a['superseded_posts'])}"
                + (f"; re-listed by {', '.join(a['relisted_by'])})" if a["relisted_by"] else ")") for a in artifacts])
    reasons = (["cites withdrawn claims"] if withdrawn else []) + (["cites superseded posts"] if posts else []) \
        + (["cites artifacts of superseded publications"] if artifacts else [])
    return {"claims": withdrawn, "posts": posts, "artifacts": artifacts,
            "note": "This write-up " + " and ".join(reasons) + ". It is served only with this flag; commission a "
                    "regeneration from the current ledger. Replacements are listed by recorded supersession, "
                    "not matched by meaning.",
            "commission": {"task_type": "writing", "subject_kind": "post", "subject_id": post_id,
                           "note": f"Regenerate write-up {post_id} from the current ledger. Superseded records it "
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


# ---------------------------------------------------------------------------- the verdict and render

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


def verdict(view, post_id, *, request=None, row=None):
    """The checker's verdict on a write-up: a pure function of the archive (no timestamps), stored at delivery."""
    row = row or view.one("SELECT * FROM post WHERE id=?", (post_id,))
    if not row:
        raise DawError("unknown_post", post_id)
    content = views.content(view, row["body_blob"])
    request = request if request is not None else writing_request(view, post_id)
    task_type = request["task_type"] if request else None
    source = content.get("body") or ""
    blocks = parse(source)
    problems, pointers = check(view, source, blocks, task_type=task_type)
    records = number_records(source, blocks)
    return {"format": "colloquy.writeup-check/1", "rules": RULES_VERSION, "post": post_id, "body_blob": row["body_blob"],
            "request": request["id"] if request else None, "task_type": task_type,
            "status": "refused" if problems else "rendered", "problems": problems, "numbers": records,
            "stats": statistics(records, blocks, pointers)}, blocks, pointers


def render_writeup(view, post_id, *, with_map=True):
    """The rendered write-up, or a refusal listing every location. A stored verdict (`writeup_check`) is the
    record: its status and per-number statuses are what every surface shows. Without one (a post that was not
    delivered as a writing or digest task) the same checker runs now and the response says so.

    Returns {"status": "rendered" | "refused", ...}; callers serve a refusal as HTTP 422."""
    from daw.commons import checks
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
    computed, blocks, pointers = verdict(view, post_id, request=request, row=row)
    stored = checks.recorded(view).get(post_id)
    if stored:
        record = checks.verdict_body(view, stored)
        status, problems, records = record["status"], record["problems"], record["numbers"]
        overlay(blocks, records)
        info = {"source": "recorded", "seq": stored["seq"], "created": stored["created"],
                "verdict_blob": stored["verdict_blob"], "rules": record["rules"]}
    else:
        status, problems, records = computed["status"], computed["problems"], computed["numbers"]
        info = {"source": "computed", "rules": RULES_VERSION,
                "note": "No stored verdict: this post was not delivered as a writing or digest task; checked now."}
    stats = statistics(records, blocks, pointers)
    flag = regeneration(view, post_id, pointers)
    if status == "refused":
        base["post"]["title"] = checks.PLACEHOLDER_TITLE
        return {**base, "status": "refused", "problems": problems, "stats": stats, "verdict": info,
                "placeholder": checks.placeholder(problems), "regeneration_required": flag}
    return {**base, "status": "rendered", "blocks": blocks, "pointers": pointers, "stats": stats, "verdict": info,
            "numbers": records, "regeneration_required": flag, "flagged": flag is not None,
            "evidence_map": subgraph(view, post_id, pointers) if with_map else None}
