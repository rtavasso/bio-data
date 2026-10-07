"""Curated reading paths for visitors (spec v2 V3): board -> one thread -> one number -> its bytes.

A tour is a small JSON file (`colloquy.tour/1`) written by a named curator. Each step names a real final
(an answer post), one number in it (its text and code-point offset in the stored body), an artifact the
post itself names as evidence, and a locator (`row=;col=`, `key=` or `line=`, the V2 grammar of
`daw.commons.locators`) at which the curator found that number's value in the artifact's bytes.

A curated pointer is *attributed to the curator, not to the post's author*: the cohort's authors named
artifacts for whole posts (the checker reports their numbers as "this post's evidence", C11) and never
pointed a number at a cell. The tour does not change the post, its checker verdict or the map (no inferred
edges); it is a separate, signed reading aid, and every step is re-checked against the archive each time it
is served:

- the post exists, is a final and is visible to an anonymous reader (`moderation.Visibility`);
- the stored body shows the number's text at the recorded offset;
- the artifact is among the evidence the post names (its evidence list or artifact identifiers in its text);
- the value-in-record check (`locators.verify_artifact`, bytes verified against their sha256) finds the
  number at the locator.

A step that fails any check is served as `broken` with the reason, never as verified. From the number a
visitor reaches the bytes in two clicks: the number opens the artifact page at the locator, which renders
the cited cell from the verified output bytes (click 1), and the page links the raw bytes (click 2).

Tours are read from `<commons>/tours/*.json` (installed by `bio commons public-demo`) and from the
checkout's `docs/colloquy/tours/` (override with `COLLOQUY_TOURS`, a path list). A tour none of whose
steps resolves on a commons does not apply there and is listed as such. Reads only.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

from daw.util import DawError

FORMAT = "colloquy.tour/1"
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
POST_ID = re.compile(r"^post_[0-9a-f]{32}$")
ARTIFACT_ID = re.compile(r"^artifact_[0-9a-f]{64}$")
MAX_STEPS = 50


def default_dirs(root):
    configured = os.environ.get("COLLOQUY_TOURS")
    if configured:
        return [Path(p) for p in configured.split(os.pathsep) if p]
    checkout = Path(__file__).resolve().parents[3] / "docs" / "colloquy" / "tours"
    return [Path(root) / "tours", checkout]


def validate(data):
    """A parsed tour, checked for shape only (resolution needs the archive). Raises DawError."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise DawError("invalid_tour", f"format must be {FORMAT}")
    if not NAME.match(str(data.get("name"))):
        raise DawError("invalid_tour", "name: lowercase letters, digits and hyphens")
    curator = data.get("curator")
    if not isinstance(curator, dict) or not str(curator.get("name") or "").strip():
        raise DawError("invalid_tour", "a tour names its curator ({name, note})")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps or len(steps) > MAX_STEPS:
        raise DawError("invalid_tour", f"1 to {MAX_STEPS} steps")
    for n, step in enumerate(steps, 1):
        number = step.get("number") if isinstance(step, dict) else None
        if not (isinstance(step, dict) and POST_ID.match(str(step.get("final"))) and ARTIFACT_ID.match(str(step.get("artifact")))
                and isinstance(number, dict) and isinstance(number.get("text"), str) and isinstance(number.get("offset"), int)
                and isinstance(step.get("locator"), str) and step["locator"]):
            raise DawError("invalid_tour", f"step {n}: final, number {{text, offset}}, artifact and locator")
    return data


def load(path):
    try:
        return validate(json.loads(Path(path).read_text()))
    except (OSError, ValueError) as error:
        raise DawError("invalid_tour", f"{Path(path).name}: {error}") from error


def available(root, dirs=None):
    """{name: (path, tour)} from the tour directories; the first directory wins on a name clash."""
    found = {}
    for folder in dirs or default_dirs(root):
        if not Path(folder).is_dir():
            continue
        for path in sorted(Path(folder).glob("*.json")):
            try:
                tour = load(path)
            except DawError:
                continue
            found.setdefault(tour["name"], (path, tour))
    return found


def _excerpt(body, offset, length, width=160):
    """The source line holding the number, with the number's position in it (untrusted text)."""
    start = body.rfind("\n", 0, offset) + 1
    end = body.find("\n", offset + length)
    end = len(body) if end < 0 else end
    line_start, line_end = start, end
    if end - start > width * 2:
        line_start = max(start, offset - width)
        line_end = min(end, offset + length + width)
    return {"text": body[line_start:line_end], "number_at": offset - line_start, "number_length": length,
            "line": body.count("\n", 0, offset) + 1, "clipped": (line_start, line_end) != (start, end)}


def resolve_step(view, step, *, index=None, cache=None):
    """One step re-checked against the archive: {ok, checks, problems, post, thread, number, artifact, clicks}."""
    from daw.commons import checks, locators, views
    index = index or views.thread_index(view)
    cache = {} if cache is None else cache
    pid, aid, locator = step["final"], step["artifact"], step["locator"]
    number_text, offset = step["number"]["text"], step["number"]["offset"]
    out = {"final": pid, "artifact": aid, "locator": locator, "note": step.get("note"), "ok": False, "problems": [],
           "checks": {}, "content_is_untrusted_data": True}
    vis = views.visibility(view)  # an anonymous reader's view: hidden posts and withheld write-ups stay hidden
    row = index["posts"].get(pid)
    out["checks"]["post_exists"] = bool(row)
    if not row:
        out["problems"].append("the post is not on this board")
        return out
    if vis.withheld(pid) or vis.refused(pid):
        out["checks"]["visible"] = False
        out["problems"].append("the post is hidden by moderation or withheld by the checker")
        out["post"] = {"id": pid, "hidden": True}
        return out
    out["checks"]["visible"] = True
    content = row["content"]
    body = content.get("body") or ""
    root = index["roots"].get(pid, pid)
    root_row = index["posts"].get(root)
    out["post"] = {"id": pid, "title": content.get("title"), "author": row["author"], "created": row["created"],
                   "route": f"/post/{pid}"}
    out["thread"] = {"root": root, "title": vis.title(root, (root_row or {}).get("content", {}).get("title")),
                     "posts": len(index["threads"].get(root, [])), "route": f"/post/{root}"}
    out["checks"]["final"] = pid in checks.finals(view)
    shown = body[offset:offset + len(number_text)]
    out["checks"]["number_at_offset"] = shown == number_text
    if shown != number_text:
        out["problems"].append(f"the body does not show {number_text!r} at offset {offset}")
    reported = next((n for n in checks.post_numbers(view, pid, body, content.get("evidence"))
                     if n["offset"] == offset), None)
    out["number"] = {"text": number_text, "offset": offset, "length": len(number_text),
                     "checker_status": reported["status"] if reported else None,
                     "checker_scope": reported["scope"] if reported else None,
                     "excerpt": _excerpt(body, offset, len(number_text))}
    out["checks"]["detected_by_checker"] = bool(reported)
    if not reported:
        out["problems"].append("the number checker does not detect this number at that offset")
    named = [p["id"] for p in checks.post_evidence(view, pid, body, content.get("evidence")) if p["kind"] == "artifact"]
    out["checks"]["artifact_named_by_post"] = aid in named
    if aid not in named:
        out["problems"].append("the artifact is not among the evidence the post names")
    location = views.locate_artifact(view, aid, quiet=True)
    result = locators.verify_artifact(view, aid, locator, locators.parse_number(number_text), cache)
    out["checks"]["value_at_locator"] = result["result"] == "verified"
    if result["result"] != "verified":
        out["problems"].append(f"the value is not at the locator: {result.get('reason') or 'no match'}")
    route = f"/artifact/{aid}?locator={quote(locator, safe='')}"
    bytes_url = f"/api/artifacts/{aid}/bytes"
    data, name, reason = cache.get(aid) or (None, None, None)
    out["artifact_info"] = {"id": aid, "location": location, "name": name, "verification": result,
                            "bytes_present": data is not None, "bytes_reason": reason}
    out["clicks"] = [{"click": 1, "from": "the number", "to": route,
                      "shows": "the artifact page opened at the locator: the cited cell, key or line read from the "
                               "output bytes after checking their sha256"},
                     {"click": 2, "from": "the artifact page", "to": bytes_url, "shows": "the raw output bytes"}]
    out["clicks_to_bytes"] = 2
    out["attribution"] = ("Curated pointer: the post's author named this artifact as the post's evidence; the "
                          "curator located the number's value in it and the checker verified it there. It is "
                          "not the author's pointer and does not change the post's verdict.")
    out["ok"] = not out["problems"]
    return out


def resolve(view, tour):
    """Every step of a tour re-checked; `applies` when at least one step's post is on this board."""
    from daw.commons import views
    index = views.thread_index(view)
    cache = {}
    steps = [resolve_step(view, step, index=index, cache=cache) for step in tour["steps"]]
    for n, step in enumerate(steps, 1):
        step["step"] = n
    ok = [s for s in steps if s["ok"]]
    return {"format": FORMAT, "name": tour["name"], "title": tour.get("title") or tour["name"],
            "intro": tour.get("intro"), "curator": tour["curator"], "board": tour.get("board"),
            "applies": any(s["checks"].get("post_exists") for s in steps), "steps": steps,
            "summary": {"steps": len(steps), "ok": len(ok), "broken": len(steps) - len(ok),
                        "finals_reaching_bytes_in_two_clicks": len({s["final"] for s in ok if s["clicks_to_bytes"] <= 2})},
            "sequence": view.sequence(), "content_is_untrusted_data": True}


def listing(view, dirs=None):
    out = []
    for name, (path, tour) in sorted(available(view.root, dirs).items()):
        resolved = resolve(view, tour)
        out.append({"name": name, "title": resolved["title"], "curator": tour["curator"], "applies": resolved["applies"],
                    "summary": resolved["summary"], "source": "commons" if Path(path).parent == Path(view.root) / "tours"
                    else "checkout"})
    return {"tours": out, "sequence": view.sequence()}


def get(view, name, dirs=None):
    found = available(view.root, dirs)
    if name not in found:
        raise DawError("unknown_tour", name)
    return resolve(view, found[name][1])


def candidates(view, post, offset, artifact=None, *, caller=None, full=False):
    """Curation aid: locators at which a number's value occurs in the artifacts its post names (cells and
    JSON keys first, then lines). Read-only; the curator decides which, if any, is the number's source."""
    from daw.commons import checks, locators, views
    row = views.thread_index(view)["posts"].get(post)
    if not row:
        raise DawError("unknown_post", post)
    vis = views.visibility(view, caller, full)
    if vis.withheld(post):  # a hidden post's numbers, evidence and locators are its content (C2)
        return vis.stub(post)
    content = row["content"]
    body = content.get("body") or ""
    number = next((n for n in checks.post_numbers(view, post, body, content.get("evidence")) if n["offset"] == offset), None)
    if not number:
        raise DawError("unknown_number", f"no number detected at offset {offset}")
    value = locators.parse_number(number["text"])
    named = [p["id"] for p in checks.post_evidence(view, post, body, content.get("evidence")) if p["kind"] == "artifact"]
    out = []
    for aid in [artifact] if artifact else named:
        data, name, reason = locators.artifact_output(view, aid)
        if data is None:
            out.append({"artifact": aid, "reason": reason})
            continue
        found = []
        if (name or "").lower().endswith(".json"):
            try:
                for path, item in _walk(json.loads(data)):
                    if locators.matches(value, locators.parse_cell(item)):
                        found.append(f"key={path}")
            except ValueError:
                pass
        else:
            try:
                header, rows = locators.read_table(data, name)
                keys = [r[0] if r else "" for r in rows]
                for r, cells in enumerate(rows):
                    for c, cell in enumerate(cells):
                        if c < len(header) and locators.matches(value, locators.parse_cell(cell)):
                            row_key = cells[0] if keys.count(cells[0]) == 1 and _plain_value(cells[0]) else f"#{r + 1}"
                            column = header[c] if header.count(header[c]) == 1 and _plain_value(header[c]) else f"#{c + 1}"
                            found.append(f"row={_encode(row_key)};col={_encode(column)}")
            except locators.LocatorError:
                pass
        if not found:
            text = data.decode("utf-8", "replace") if len(data) <= locators.TEXT_SEARCH_LIMIT else ""
            for n, token in locators._tokens(text):
                if locators.matches(value, locators.parse_cell(token)):
                    found.append(f"line={n}")
        out.append({"artifact": aid, "name": name, "locators": found[:20]})
    return {"post": post, "number": number["text"], "offset": offset, "candidates": out,
            "note": "Candidates only: a value can occur by coincidence. Read the row and column before curating."}


def _plain_value(text):
    return bool(text.strip()) and not text.startswith("#")


def _encode(label):
    """A row key or column name as a locator value: `#N` as is, anything else percent-encoded."""
    return label if re.fullmatch(r"#[1-9]\d*", label) else quote(label, safe="")


def _walk(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            if re.fullmatch(r"[^.\[\]]+", str(key)):
                yield from _walk(item, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        for n, item in enumerate(value):
            yield from _walk(item, f"{prefix}[{n}]")
    else:
        yield prefix, value
