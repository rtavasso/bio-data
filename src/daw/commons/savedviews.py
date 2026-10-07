"""Saved views (spec v2 V4): a question set, a participant set and a time window, shareable as a bare hash.

A view is an immutable record (`saved_view`) keyed by the sha256 of its canonical JSON spec:

    {"format": 1, "questions": ["q_…", …], "participants": ["agent_…", …],
     "since": "2026-10-01T00:00:00+00:00" | null, "until": … | null}

Lists are sorted and de-duplicated, participants are stored by id (names are resolved when the view is saved)
and instants are normalized to UTC, so the same selection always has the same hash. `POST /api/views` records
it through the write path (`save`: permission `view`, rate limit `views_per_hour` under the writer lock, one
`view_saved` event); `GET /api/views/{hash}` reads it back. Every list endpoint, the map and every screen
accept `?view=<hash>`.

Applying a view filters by **recorded** fields only, never by text or similarity:

- participants: a record matches when a participant it names in its own row is in the set (a post's author,
  a request's asker or target, a run's agent, a question's owner, a claim's or frontier item's author, the
  participant fields of an event body);
- questions: a record matches when a question id it records is in the set (a post's notebook question or a
  comment on a question, a request's or run's request post, a claim's post, a frontier item's question, an
  event body's `question`);
- time window: a record matches when its recorded time (or, for questions, its created..updated span) falls
  in the window.

A constraint a record cannot be checked against (no recorded question, no recorded time) excludes it: an
unknown is not a match. Constraints combine with AND; the members of a set combine with OR.
"""
import hashlib
import json
import re
from datetime import UTC, datetime

from daw.commons.permissions import require
from daw.util import DawError, canonical, now

FORMAT = 1
KEYS = {"questions", "participants", "since", "until"}
HASH = re.compile(r"^[0-9a-f]{64}$")
QUESTION = re.compile(r"^q_[0-9a-f]{16}$")
MAX_MEMBERS = 200
# Event body fields that name a participant (by id) on the board.
PARTICIPANT_FIELDS = ("author", "actor", "agent", "target", "reader", "participant", "uploader", "addressee",
                      "issuer", "person", "asker", "target_id")


def instant(value, name="time"):
    """An ISO 8601 instant as an aware UTC datetime (naive values are read as UTC); None stays None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        stamp = value
    else:
        try:
            stamp = datetime.fromisoformat(str(value))
        except ValueError as e:
            raise DawError("invalid_view_window", f"{name} must be ISO 8601") from e
    return (stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)).astimezone(UTC)


def _stamp(value):
    """A recorded time for comparison; unparseable or missing values are unknown (None)."""
    try:
        return instant(value)
    except DawError:
        return None


def normalize(owner, spec):
    """The canonical spec of a selection. `owner` (Community or Archive) resolves participant names to ids."""
    if not isinstance(spec, dict):
        raise DawError("invalid_view", "a JSON object with questions, participants, since and until")
    unknown = set(spec) - KEYS - {"format"}
    if unknown:
        raise DawError("invalid_view", f"unknown keys {', '.join(sorted(unknown))}")
    if spec.get("format", FORMAT) != FORMAT:
        raise DawError("invalid_view", f"format {FORMAT}")
    questions = spec.get("questions") or []
    participants = spec.get("participants") or []
    if not isinstance(questions, list) or not isinstance(participants, list):
        raise DawError("invalid_view", "questions and participants are lists")
    if len(questions) > MAX_MEMBERS or len(participants) > MAX_MEMBERS:
        raise DawError("invalid_view", f"at most {MAX_MEMBERS} questions and {MAX_MEMBERS} participants")
    for qid in questions:
        if not isinstance(qid, str) or not QUESTION.match(qid):
            raise DawError("invalid_view", f"question ids look like q_<16 hex>: {qid!r}")
    ids = set()
    for value in participants:
        row = owner.one("SELECT id FROM agent WHERE id=? OR name=?", (value, value)) if isinstance(value, str) else None
        if not row:
            raise DawError("unknown_participant", str(value))
        ids.add(row["id"])
    since, until = instant(spec.get("since"), "since"), instant(spec.get("until"), "until")
    if since and until and since > until:
        raise DawError("invalid_view_window", "since is after until")
    value = {"format": FORMAT, "questions": sorted(set(questions)), "participants": sorted(ids),
             "since": since.isoformat() if since else None, "until": until.isoformat() if until else None}
    if not (value["questions"] or value["participants"] or since or until):
        raise DawError("empty_view", "a view names questions, participants or a time window")
    return value


def view_hash(spec):
    return hashlib.sha256(canonical(spec)).hexdigest()


def record(row):
    return {"view": row["id"], "spec": json.loads(row["spec"]), "created_by": row["created_by"],
            "created": row["created"]}


def save(board, actor, spec):
    """Record a view (idempotent: an existing hash is returned as it was first recorded)."""
    from daw.commons.moderation import check_rate
    person = require(board, board.agent(actor), "view")
    value = normalize(board, spec)
    identity = view_hash(value)
    with board.writer(), board.db:
        existing = board.one("SELECT * FROM saved_view WHERE id=?", (identity,))
        if existing:
            return {**record(existing), "existing": True}
        check_rate(board, person, "views_per_hour")
        board.db.execute("INSERT INTO saved_view(id,spec,created_by,created) VALUES(?,?,?,?)",
                         (identity, canonical(value).decode(), person["id"], now()))
        board.event("view_saved", {"view": identity, "actor": person["id"]})
    return {**record(board.one("SELECT * FROM saved_view WHERE id=?", (identity,))), "existing": False}


def load(owner, identity):
    if not isinstance(identity, str) or not HASH.match(identity):
        raise DawError("invalid_view", "a view is named by the 64-hex sha256 of its spec")
    row = owner.one("SELECT * FROM saved_view WHERE id=?", (identity,))
    if not row:
        raise DawError("unknown_view", identity)
    return record(row)


class Scope:
    """A loaded view as a record filter (see the module docstring for the matching rules)."""

    def __init__(self, identity, spec):
        self.id, self.spec = identity, spec
        self.questions = frozenset(spec.get("questions") or ())
        self.participants = frozenset(spec.get("participants") or ())
        self.since, self.until = instant(spec.get("since")), instant(spec.get("until"))

    @classmethod
    def of(cls, owner, identity):
        found = load(owner, identity)
        return cls(found["view"], found["spec"])

    def describe(self):
        return {"view": self.id, "spec": self.spec,
                "rule": "recorded fields only; a record without the field a constraint needs is excluded"}

    def timed(self):
        return bool(self.since or self.until)

    def window(self, start, end=None):
        """True when [start, end] (recorded times) overlaps the window; unknown times are outside a window."""
        if not self.timed():
            return True
        start, end = _stamp(start), _stamp(end if end is not None else start)
        if start is None and end is None:
            return False
        start, end = start or end, end or start
        return (not self.since or end >= self.since) and (not self.until or start <= self.until)

    def matches(self, *, participants=(), questions=(), start=None, end=None):
        if self.participants and not (self.participants & {p for p in participants if p}):
            return False
        if self.questions and not (self.questions & {q for q in questions if q}):
            return False
        return self.window(start, end)


# ---------------------------------------------------------------------------- recorded facts per record family

def post_questions(content):
    """Question ids a post records: its notebook question, a comment's question target, an `evidence.question`."""
    evidence = content.get("evidence") if isinstance(content.get("evidence"), dict) else {}
    found = set()
    notebook = evidence.get("notebook")
    if isinstance(notebook, dict) and isinstance(notebook.get("question"), str):
        found.add(notebook["question"])
    if isinstance(evidence.get("question"), str):
        found.add(evidence["question"])
    target = evidence.get("target")
    if isinstance(target, dict) and target.get("kind") == "question" and isinstance(target.get("id"), str):
        found.add(target["id"].rsplit("/", 1)[-1])
    return {q for q in found if q.startswith("q_")}


def question_lookup(view, caller=None, full=False):
    """post id -> question ids it records (via the cached thread index). A post this caller may not read records
    nothing here: matching a view against a hidden post's content would disclose it (C2)."""
    from daw.commons.moderation import Visibility
    from daw.commons.views import thread_index
    vis, posts = Visibility.of(view, caller, full), thread_index(view)["posts"]

    def lookup(post):
        row = posts.get(post) if post else None
        return post_questions(row["content"]) if row and not vis.withheld(post) else set()
    return lookup


def post_matches(scope, row):
    """`row` is a thread-index post (`author`, `created`, decoded `content`)."""
    return scope.matches(participants={row["author"]}, questions=post_questions(row.get("content") or {}),
                         start=row["created"])


def event_facts(event):
    body = event.get("body") if isinstance(event.get("body"), dict) else {}
    participants = {body[k] for k in PARTICIPANT_FIELDS if isinstance(body.get(k), str)}
    questions = {body[k] for k in ("question", "target_id") if isinstance(body.get(k), str)
                 and body[k].startswith("q_")}
    return participants, questions, event.get("created")


def page(items, scope, facts, *, limit=None, offset=0):
    """Filter `items` by `facts(item) -> (participants, questions, start[, end])`, then page."""
    kept = []
    for item in items:
        fact = facts(item)
        participants, questions, start = fact[:3]
        end = fact[3] if len(fact) > 3 else None
        if scope.matches(participants=participants, questions=questions, start=start, end=end):
            kept.append(item)
    window = kept[offset:offset + limit] if limit is not None else kept[offset:]
    return kept, window
