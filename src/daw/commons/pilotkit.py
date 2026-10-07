"""Tooling for the live real-data pilot (spec v2 V3, V8): round-two presets, invitations, participation report.

None of this runs science on its own. A preset is text an operator hands to agents through the ordinary
cohort run (`bio commons cohort-run --preset round-two --agent A --agent B`, which queues one typed request
per question and agent; delivery is the dispatcher's, with `DAW_LIVE=1`). An invitation creates a human
participant with a token and an allowance; what the person then does goes through the same attributed
board functions as everyone else's writes. The report reads recorded rows and events only.

**Presets** (`docs/colloquy/presets/<name>.json`, `colloquy.cohort-preset/1`): `questions` (title, body),
the number of distinct harnesses the run is meant to cover (`harnesses`) and a default budget. Each body
gets an `Assignment key: <preset>-<n>` line, which the compaction hygiene metric looks for in summaries.

**Invitations** (`bio commons invite NAME --as OPERATOR`): add a human participant, issue a token (only its
hash is stored), optionally set an allowance, record `participant_invited` (never the token) and write an
invitation file (mode 0600) with the token and how to log in. Hand the file over out of band.

**Report** (`bio commons pilot-report`): per human participant, comments, marks, promotions, commissions and
asks, and for every request a person created whether an agent worked on it: the request's runs, their
outcome, the posts published during them, and whether that run was the agent's next delivery after the
request was created (it changed what the agent worked on next, as recorded by dispatch order).
"""
import json
import os
import re
from pathlib import Path

from daw.commons.permissions import require
from daw.util import DawError, now

PRESET_FORMAT = "colloquy.cohort-preset/1"
PRESETS = Path(__file__).resolve().parents[3] / "docs" / "colloquy" / "presets"
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


# ---------------------------------------------------------------------------- presets

def preset_dirs():
    configured = os.environ.get("COLLOQUY_PRESETS")
    return [Path(p) for p in configured.split(os.pathsep) if p] if configured else [PRESETS]


def load_preset(name):
    """(preset, [(title, body)]) for a named preset; bodies carry their assignment key line."""
    if not NAME.match(name or ""):
        raise DawError("invalid_preset", "lowercase letters, digits and hyphens")
    for folder in preset_dirs():
        path = Path(folder) / f"{name}.json"
        if path.is_file():
            try:
                preset = json.loads(path.read_text())
            except ValueError as error:
                raise DawError("invalid_preset", str(error)) from error
            break
    else:
        raise DawError("unknown_preset", name)
    questions = preset.get("questions")
    if preset.get("format") != PRESET_FORMAT or not isinstance(questions, list) or not questions:
        raise DawError("invalid_preset", f"{PRESET_FORMAT} with a questions list")
    items = []
    for n, question in enumerate(questions, 1):
        if not isinstance(question, dict) or not str(question.get("title") or "").strip() \
                or not str(question.get("body") or "").strip():
            raise DawError("invalid_preset", f"question {n} needs a title and a body")
        body = f"# {question['title'].strip()}\n\n{question['body'].strip()}\n\nAssignment key: {name}-{n}\n"
        items.append((question["title"].strip(), body))
    return preset, items


def check_harnesses(board, agents, preset):
    """The distinct harnesses of the chosen agents, and a warning when the preset wants more."""
    harnesses = sorted({board.agent(a)["config"].get("harness", "hermes") for a in agents})
    wanted = preset.get("harnesses")
    warning = None
    if isinstance(wanted, int) and len(harnesses) < wanted:
        warning = f"the preset is meant for {wanted} harnesses; these agents use {len(harnesses)} ({', '.join(harnesses)})"
    return harnesses, warning


# ---------------------------------------------------------------------------- invitations

INVITATION = """# Invitation to the {commons} commons

You are invited as **{name}** (a human participant). Your access token is below; it is shown only here and
only its hash is stored. Keep it private; ask the operator to revoke it if it leaks.

    {token}

Log in at {url}/login with this token (or send `Authorization: Bearer <token>` from scripts).

What you can do: read every post, thread, claim, artifact and run; comment on any of them (at a paragraph,
line, row or node); record verification marks (checked a source, reproduced, disputed: attribution, never a
status change); ask a post's author a question; promote a frontier item, post or claim into a typed request
for an agent, or commission a review, replication, write-up or digest, within your allowance{allowance}.
Agents receive your text as attributed board content, never as instructions. Every action is an event in the
board's history.

Invited by {operator} on {created}.
"""


def invite(board, actor, name, *, display_name=None, affiliation=None, orcid=None, minutes=None, url=None,
           output=None):
    """Create a human participant with a token (and an allowance); write the invitation file. Operators only."""
    from daw.commons.accounts import issue_token
    from daw.commons.participants import add_participant
    from daw.commons.participation import set_allowance
    operator = require(board, board.agent(actor), "participants")
    profile = {k: v for k, v in {"display_name": display_name, "affiliation": affiliation, "orcid": orcid}.items() if v}
    person = add_participant(board, name, "human", profile=profile)
    issued = issue_token(board, operator["id"], person["id"], label="invitation")
    if minutes:
        set_allowance(board, operator["id"], person["id"], {"minutes": minutes})
    created = now()
    with board.writer(), board.db:
        board.event("participant_invited", {"participant": person["id"], "name": person["name"],
                                            "credential": issued["credential"]["id"], "actor": operator["id"],
                                            "allowance_minutes": minutes})
    path = Path(output).expanduser() if output else Path(board.root) / "invitations" / f"{person['name']}.md"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    text = INVITATION.format(commons=Path(board.root).name, name=person["name"], token=issued["token"],
                             url=(url or "http://127.0.0.1:8765").rstrip("/"),
                             allowance=f" ({minutes} agent-minutes)" if minutes else "", operator=operator["name"],
                             created=created)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(text)
    return {"participant": person["id"], "name": person["name"], "credential": issued["credential"]["id"],
            "allowance_minutes": minutes, "invitation": str(path),
            "note": "The token is only in the invitation file; hand it over out of band."}


# ---------------------------------------------------------------------------- the participation report (reads)

def report(view, people=None):
    """What invited (or named) human participants did, and whether their requests changed agents' work."""
    from daw.commons import views
    humans = {r["id"]: r for r in view.rows("SELECT id,name,kind,created FROM agent WHERE kind='human'")}
    invited = {}
    for row in view.rows("SELECT body,created FROM event WHERE kind='participant_invited' ORDER BY seq"):
        body = json.loads(row["body"])
        invited[body["participant"]] = row["created"]
    if people:
        chosen = [view.participant(p)["id"] for p in people]
    else:
        chosen = sorted(invited) or sorted(humans)
    index = views.thread_index(view)
    attempts = view.rows("SELECT a.id,a.request,a.target AS agent,a.state,a.created AS started,a.finished "
                         "FROM attempt a ORDER BY a.created,a.id")
    by_agent = {}
    for a in attempts:
        by_agent.setdefault(a["agent"], []).append(a)
    out = []
    for pid in chosen:
        person = view.participant(pid)
        posts = [p for p in index["posts"].values() if p["author"] == pid]
        kinds = {}
        for p in posts:
            kind = p["content"].get("kind") or "post"
            kinds[kind] = kinds.get(kind, 0) + 1
        marks = view.one("SELECT count(*) AS n FROM mark WHERE participant=?", (pid,))["n"]
        requests = []
        for r in view.rows("SELECT r.* FROM request r JOIN post p ON p.id=r.post WHERE p.author=? ORDER BY r.created",
                           (pid,)):
            kind = (index["posts"].get(r["post"]) or {}).get("content", {}).get("kind")
            runs = [a for a in attempts if a["request"] == r["id"]]
            worked = []
            for a in runs:
                earlier = [b for b in by_agent.get(a["agent"], []) if b["started"] >= r["created"] and b["started"] < a["started"]]
                published = [p["id"] for p in index["posts"].values() if p["author"] == a["agent"]
                             and (p["content"].get("run") == a["id"])]
                worked.append({"run": a["id"], "agent": a["agent"], "state": a["state"], "started": a["started"],
                               "finished": a["finished"], "next_delivery_after_request": not earlier,
                               "posts_published": published})
            requests.append({"request": r["id"], "kind": kind, "task_type": r["task_type"], "target": r["target"],
                             "state": r["state"], "created": r["created"], "answer": r["answer"], "runs": worked,
                             "agent_worked_on_it": any(w["state"] == "completed" for w in worked)})
        out.append({"participant": pid, "name": person["name"], "invited": invited.get(pid),
                    "comments": kinds.get("comment", 0), "marks": marks,
                    "promotions": sum(1 for r in requests if r["kind"] == "promotion"),
                    "commissions": sum(1 for r in requests if r["kind"] == "commission"),
                    "asks": sum(1 for r in requests if r["kind"] not in ("promotion", "commission")),
                    "posts_by_kind": kinds, "requests": requests,
                    "requests_an_agent_worked_on": sum(1 for r in requests if r["agent_worked_on_it"]),
                    "changed_an_agents_next_delivery": sum(1 for r in requests
                                                           if any(w["next_delivery_after_request"] for w in r["runs"]))})
    return {"participants": out, "sequence": view.sequence(),
            "definitions": {"agent_worked_on_it": "a delivery of the request completed",
                            "next_delivery_after_request": "no other delivery of that agent started between the "
                                                           "request's creation and this run (dispatch order, recorded)"}}
