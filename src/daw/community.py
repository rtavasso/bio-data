"""Local research board: ordinary posts, durable questions, and evidence references.

The channel/author/parent/body design follows AgentHub; unread work follows the
explicit acknowledgment pattern used by OpenAgentForum. Scientific records stay
in bio's existing object store. This module makes no research decisions.
"""
import contextlib
import fcntl
import json
import re
import sqlite3
import uuid
from pathlib import Path

from daw.artifacts import attach_artifact
from daw.catalog import Workspace
from daw.commons import schema
from daw.commons.claims import (claims_document, notify_affected, project_post, publication_warnings,
                                validate_claims)
from daw.exchange import transfer_artifacts
from daw.search import index_document, search
from daw.util import DawError, canonical, now, read_json
from daw.work import question_record, record_event, sync_work

# Provider-side citation syntax never corresponds to a captured tool result in
# this harness; its presence in a post marks an unsupported retrieval claim.
PROVIDER_CITATION = re.compile(r"utm_source=openai|\bturn\d+(?:search|view|news|file)\d+|citeturn", re.IGNORECASE)
SEARCH_FAMILIES = {"forum": "forum", "artifact": "artifact", "work": "work", "claim": "claim", "all": None}


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent (
 id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, trial TEXT UNIQUE,
 native_session TEXT, parent TEXT REFERENCES agent(id), config TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS post (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
 author TEXT NOT NULL REFERENCES agent(id), channel TEXT NOT NULL,
 parent TEXT REFERENCES post(id), supersedes TEXT REFERENCES post(id),
 body_blob TEXT NOT NULL, request_key TEXT UNIQUE, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS request (
 id TEXT PRIMARY KEY, post TEXT UNIQUE NOT NULL REFERENCES post(id),
 target TEXT NOT NULL REFERENCES agent(id), state TEXT NOT NULL,
 active_run TEXT, answer TEXT REFERENCES post(id), created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attempt (
 id TEXT PRIMARY KEY, request TEXT NOT NULL REFERENCES request(id), target TEXT NOT NULL REFERENCES agent(id),
 state TEXT NOT NULL, path TEXT NOT NULL, created TEXT NOT NULL, finished TEXT);
CREATE TABLE IF NOT EXISTS event (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS inbox ON request(target,state,created);
CREATE TRIGGER IF NOT EXISTS immutable_post_update BEFORE UPDATE ON post
 BEGIN SELECT RAISE(ABORT,'immutable post'); END;
CREATE TRIGGER IF NOT EXISTS immutable_post_delete BEFORE DELETE ON post
 BEGIN SELECT RAISE(ABORT,'immutable post'); END;
CREATE TRIGGER IF NOT EXISTS immutable_event_update BEFORE UPDATE ON event
 BEGIN SELECT RAISE(ABORT,'immutable event'); END;
CREATE TRIGGER IF NOT EXISTS immutable_event_delete BEFORE DELETE ON event
 BEGIN SELECT RAISE(ABORT,'immutable event'); END;
PRAGMA user_version=1;
"""


@contextlib.contextmanager
def exclusive(path, *, blocking=False):
    with Path(path).open("a") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as e:
            raise DawError("agent_busy", "this session is already running or being forked") from e
        try:
            yield stream.fileno()
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def evidence_summary(library, evidence):
    """Title, role and derivation key per attached artifact, so a reader can judge fit without a second command.

    `library` is the board library (read-write Workspace or a read-only archive view)."""
    summary = []
    for aid in evidence.get("artifacts", []) if isinstance(evidence, dict) else []:
        row = library.one("SELECT id,derivation_key,output_role,manifest_blob FROM artifact WHERE id=?", (aid,))
        if not row:
            summary.append({"id": aid, "present": False})
            continue
        manifest = read_json(library.blob_path(row["manifest_blob"]))
        summary.append({"id": aid, "present": True, "title": manifest.get("title"), "output_role": row["output_role"],
                        "derivation_key": row["derivation_key"], "summary": (manifest.get("summary") or "")[:300],
                        "limitations": manifest.get("limitations", [])})
    return summary


def posts_naming(owner, artifact):
    """Posts whose evidence lists this artifact; fetch is post-gated, so an unnamed artifact is read-only.

    `owner` is a Community or a read-only `daw.commons.archive.Archive` (rows/one/library)."""
    named = []
    for row in owner.rows("SELECT body FROM event WHERE kind='published' ORDER BY seq"):
        body = json.loads(row["body"])
        if artifact in (body.get("evidence") or {}).get("artifacts", []):
            named.append(body["post"])
    return named


def find(owner, text="", *, limit=20, offset=0, family="forum", full=False, moderate=False, reader=None):
    """Search the shared board. family=artifact|work searches the library's published derivations and
    notebooks; all searches every family. Artifact hits are retrievable with community fetch via the
    posts that name them (listed under `posts`). Compact by default: a 20-hit forum search with full
    2000-character excerpts is ~40 KB of model context and most hits are never opened; full=True
    restores the excerpts and index bookkeeping. `owner` is a Community or a read-only Archive.
    With `moderate` (every agent-facing search), hits on hidden posts and their claims are not served and are
    counted in `withheld_hidden`, and refused write-ups show their placeholder (spec v2 C2, C5); the web read
    models apply the same resolver themselves."""
    if family not in SEARCH_FAMILIES:
        raise DawError("unknown_search_family", "use forum, artifact, work, claim or all")
    result = search(owner.library, text, family=SEARCH_FAMILIES[family], limit=limit, offset=offset)
    for item in result["items"]:
        if item.get("family") == "forum":
            item["superseded_by"] = owner.rows("SELECT id FROM post WHERE supersedes=? ORDER BY seq", (item["subject"],))
            post = owner.one("SELECT author,created,body_blob FROM post WHERE id=?", (item["subject"],))
            if post:
                body = read_json(owner.library.blob_path(post["body_blob"]))
                item.update(author=post["author"], created=post["created"], kind=body.get("kind"),
                            artifacts=len((body.get("evidence") or {}).get("artifacts", [])))
        elif item.get("family") == "artifact":
            item["posts"] = posts_naming(owner, item["subject"])
        elif item.get("family") == "claim":
            claim = owner.one("SELECT post,author,status,withdrawn_by FROM claim WHERE id=?", (item["subject"],))
            if claim:
                item.update(claim)
    if moderate:
        from daw.commons.moderation import Visibility
        vis, kept, withheld = Visibility.of(owner, reader), [], 0
        for item in result["items"]:
            post = item["subject"] if item.get("family") == "forum" else item.get("post")
            if isinstance(post, str) and vis.withheld(post):
                withheld += 1  # serving a hit on a hidden post's text would disclose it
                continue
            if item.get("family") == "forum" and vis.refused(item["subject"]):
                info = vis.refused_writeups[item["subject"]]
                from daw.commons.checks import PLACEHOLDER_TITLE, snippet
                item = {**item, "title": PLACEHOLDER_TITLE, "summary": snippet(info), "withheld": info}
            kept.append(item)
        result["items"], result["withheld_hidden"] = kept, withheld
    if not full:
        keep = ("subject", "family", "title", "author", "created", "kind", "artifacts", "superseded_by", "posts",
                "post", "status", "withdrawn_by", "score", "withheld")
        result["items"] = [{**{k: i[k] for k in keep if k in i}, "snippet": (i.get("summary") or "")[:300],
                            "content_is_untrusted_data": True} for i in result["items"]]
        result["note"] = "compact listing; community show POST reads a post, --full restores excerpts"
    result["family"] = family
    return result


class Community:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        if not (self.root / "board.sqlite").is_file():
            raise DawError("community_not_initialized", str(self.root))
        self.db = sqlite3.connect(self.root / "board.sqlite", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=30000")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (1, schema.BOARD_VERSION):
            self.db.close()
            raise DawError("unsupported_community_version")
        if version == 1 or not schema.current(self.db):
            # Additive upgrade (v1 rows keep their meaning); serialized with every other board write.
            with exclusive(self.root / ".board.lock", blocking=True):
                schema.upgrade(self.db)
        self.library = Workspace(self.root / "library")

    @classmethod
    def create(cls, root):
        root = Path(root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with exclusive(root / ".board.lock", blocking=True):
            if (root / "board.sqlite").exists():
                with sqlite3.connect(root / "board.sqlite") as existing:
                    if existing.execute("PRAGMA user_version").fetchone()[0] not in (1, schema.BOARD_VERSION):
                        raise DawError("unsupported_community_version")
            for name in ("agents", "runs"):
                (root / name).mkdir(exist_ok=True)
            new_library = not (root / "library/catalog.sqlite").exists()
            Workspace.create(root / "library").close()
            if new_library:
                (root / "library/config.toml").write_text(
                    "[budgets]\nasset_bytes=0\nbundle_bytes=0\nrequests=0\nreserve_bytes=5368709120\nreserve_fraction=0\n")
            with contextlib.closing(sqlite3.connect(root / "board.sqlite")) as db:
                if db.execute("PRAGMA user_version").fetchone()[0] == 0:
                    db.executescript(SCHEMA)
                schema.upgrade(db)
                with db:
                    db.execute("INSERT OR IGNORE INTO agent(id,name,trial,native_session,parent,config,created,kind) "
                               "VALUES('operator','operator',NULL,NULL,NULL,'{}',?,'operator')", (now(),))
        return cls(root)

    def close(self):
        self.library.close()
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def writer(self):
        return exclusive(self.root / ".board.lock", blocking=True)

    def one(self, query, values=()):
        row = self.db.execute(query, values).fetchone()
        return dict(row) if row else None

    def rows(self, query, values=()):
        return [dict(row) for row in self.db.execute(query, values)]

    def event(self, kind, body):
        self.db.execute("INSERT INTO event(kind,body,created) VALUES(?,?,?)", (kind, canonical(body).decode(), now()))

    def agent(self, identity):
        row = self.one("SELECT * FROM agent WHERE id=? OR name=?", (identity, identity))
        if not row:
            raise DawError("unknown_community_agent", identity)
        row["config"] = json.loads(row["config"])
        return row

    def trial(self, agent):
        if not agent["trial"]:
            raise DawError("agent_has_no_session", agent["id"])
        relative = Path(agent["trial"])
        path = self.root / relative
        if relative.is_absolute() or ".." in relative.parts or not path.resolve().is_relative_to(self.root / "agents"):
            raise DawError("unsafe_agent_path")
        return path

    def show(self, identity):
        row = self.one("SELECT * FROM post WHERE id=?", (identity,))
        if not row:
            raise DawError("unknown_post", identity)
        from daw.profiles import verify_object
        body = read_json(verify_object(self.library, row["body_blob"]))
        # Board content is untrusted to agents regardless of author; the author's kind is a label, not a trust grant.
        author_kind = self.one("SELECT kind FROM agent WHERE id=?", (row["author"],))["kind"]
        return {**row, "author_kind": author_kind, "content": body, "content_is_untrusted_data": True,
                "evidence_artifacts": self._evidence_summary(body.get("evidence") or {}),
                "superseded_by": self.rows("SELECT id,author,created FROM post WHERE supersedes=? ORDER BY seq", (identity,)),
                "claims": [{**c, "scope": json.loads(c["scope"]), "pointers": json.loads(c["pointers"])} for c in self.rows(
                    "SELECT id,ordinal,text,status,scope,pointers,withdrawn_by FROM claim WHERE post=? ORDER BY ordinal",
                    (identity,))],
                "replies": self.rows("SELECT id,author,created FROM post WHERE parent=? ORDER BY seq", (identity,))}

    def _evidence_summary(self, evidence):
        return evidence_summary(self.library, evidence)

    def read(self, identity, reader=None, *, full=False):
        """`show` as a reader sees it, agents included: one moderation rule for every reader (spec v2 C2).
        A hidden post is `{id, hidden, reason}` (unless the reader holds `hide` and asks for `full`); a refused
        write-up shows its placeholder (C5); hidden replies are stubs and anchor quotes of hidden posts are dropped.
        `show` stays the internal, unmoderated record access for board functions."""
        from daw.commons.moderation import Visibility
        caller = self.agent(reader) if reader else None
        vis = Visibility.of(self, caller, full)
        if not self.one("SELECT id FROM post WHERE id=?", (identity,)):
            raise DawError("unknown_post", identity)
        if vis.withheld(identity):
            return {**vis.stub(identity), "content_is_untrusted_data": True}
        shown = self.show(identity)
        content = {**shown["content"], "evidence": vis.evidence(shown["content"].get("evidence") or {})}
        if vis.refused(identity):
            from daw.commons.checks import PLACEHOLDER_TITLE, snippet
            info = vis.refused_writeups[identity]
            content = {**content, "title": PLACEHOLDER_TITLE, "body": snippet(info)}
            shown = {**shown, "withheld": info, "claims": []}
        if identity in vis.records:
            shown = {**shown, "hidden": True, "reason": vis.reason(identity), "revealed": True}
        replies = [vis.stub(r["id"]) if vis.withheld(r["id"]) else r for r in shown["replies"]]
        return {**shown, "content": content, "replies": replies}

    def verify(self, identity, reader=None, *, full=False):
        """Read back a post and its evidence from immutable library bytes; replaces hand-written readback scripts.
        Moderated like `read` (B15): a hidden post is its stub; its body hash, artifact ids and notebook state are
        its content, and only a reader holding `hide` who asks for `full` verifies it."""
        from daw.commons.moderation import Visibility
        from daw.profiles import verify_object
        vis = Visibility.of(self, self.agent(reader) if reader else None, full)
        if not self.one("SELECT id FROM post WHERE id=?", (identity,)):
            raise DawError("unknown_post", identity)
        if vis.withheld(identity):
            return {**vis.stub(identity), "verified": None, "note": "Hidden by moderation: not read back."}
        shown = self.show(identity)
        artifacts = []
        for item in shown["evidence_artifacts"]:
            ok = item["present"]
            if ok:
                row = self.library.one("SELECT output_blob,manifest_blob FROM artifact WHERE id=?", (item["id"],))
                try:
                    verify_object(self.library, row["output_blob"])
                    verify_object(self.library, row["manifest_blob"])
                except DawError:
                    ok = False
            artifacts.append({"id": item["id"], "verified": ok})
        notebook = shown["content"].get("evidence", {}).get("notebook")
        notebook_ok = None
        if notebook:
            try:
                verify_object(self.library, notebook["manifest_blob"])
                notebook_ok = True
            except DawError:
                notebook_ok = False
        return {"post": identity, "body_sha256": shown["body_blob"], "body_verified": True,
                "artifacts": artifacts, "notebook_verified": notebook_ok,
                "verified": all(a["verified"] for a in artifacts) and notebook_ok is not False,
                "note": "Byte readback only; it establishes neither scientific validity nor reuse."}

    def _index(self, post):
        body = read_json(self.library.blob_path(post["body_blob"]))
        index_document(self.library, key="forum:" + post["id"], family="forum", subject=post["id"],
                       record_id=post["id"], title=body["title"], summary=body["body"][:2000],
                       body_blob=post["body_blob"], detail=body, provider="community", level=3)

    def _post(self, author, title, body, *, channel="research", parent=None, supersedes=None,
              evidence=None, request_key=None, kind="discussion"):
        """Caller holds board and library locks. Immutable post, index is rebuildable."""
        author = self.agent(author)
        if self.one("SELECT 1 FROM moderation WHERE target_kind='participant' AND target_id=? AND state='suspended'",
                    (author["id"],)):
            raise DawError("participant_suspended", author["id"])
        if not title.strip() or not body.strip() or not channel.strip():
            raise DawError("empty_post")
        found = PROVIDER_CITATION.search(body)
        if found:
            raise DawError("provider_citation_syntax",
                           f"{found.group(0)!r} is provider citation syntax, not a captured tool result; "
                           "cite the retrieval receipt or remove the claim")
        if parent:
            self.show(parent)
        if supersedes:
            old = self.show(supersedes)
            if old["author"] != author["id"]:
                raise DawError("cannot_supersede_another_author", "reply with a correction instead")
        running = self.one("SELECT id FROM attempt WHERE target=? AND state='running'", (author["id"],))
        content = {"author": author["id"], "session": author["native_session"],
                   "run": running["id"] if running else None, "title": title,
                   "body": body, "channel": channel, "parent": parent, "supersedes": supersedes,
                   "evidence": evidence or {}, "kind": kind}
        if request_key:
            old = self.one("SELECT * FROM post WHERE request_key=?", (request_key,))
            if old:
                previous = self.show(old["id"])["content"]
                # A resumed session may now have a different native compression tip.
                if any(previous[k] != content[k] for k in content if k not in {"session", "run"}):
                    raise DawError("post_key_conflict")
                self._index(old)
                project_post(self, old)
                return old["id"]
        identity = "post_" + uuid.uuid4().hex
        blob = self.library.put_json(content)
        with self.db:
            self.db.execute("INSERT INTO post(id,author,channel,parent,supersedes,body_blob,request_key,created) "
                            "VALUES(?,?,?,?,?,?,?,?)", (identity, author["id"], channel, parent, supersedes, blob, request_key, now()))
            self.event("published", {"post": identity, "author": author["id"], "evidence": evidence or {}})
        row = self.one("SELECT * FROM post WHERE id=?", (identity,))
        self._index(row)
        # Claim ledger projection (M1.6): the post's own claims, and withdrawal of a superseded post's claims.
        project_post(self, row)
        return identity

    def publish(self, author, title, body, *, artifacts=(), workspace=None, question=None, claims=None,
                frontier=None, **options):
        """Publish prose with selected evidence. `claims` (M1.6) is a list of {text, status, scope, pointers}
        stored as a library blob; every pointer must resolve. `frontier` items (M1.7) are recorded as work
        events in the author's own question first, then named in the post's evidence."""
        evidence = {}
        source = Workspace(workspace) if workspace else None
        if (artifacts or question or frontier) and source is None:
            raise DawError("publication_workspace_required")
        if frontier and not question:
            raise DawError("frontier_question_required", "frontier items belong to a question")
        try:
            # Pointers name immutable records (posts, library artifacts and blobs are never deleted),
            # so checking before the frontier events are written keeps a rejected publication side-effect free.
            checked = validate_claims(self, claims, artifacts) if claims is not None else None
            with source.writer() if source else contextlib.nullcontext():
                items = []
                if frontier:
                    from daw.commons.frontier import parse_items, record_item
                    parsed = parse_items(source, question, frontier)
                    key = options.get("request_key")
                    items = [record_item(source, question, **{**item, "key": item.get("key") or
                                                              (f"{key}:frontier:{n}" if key else None)})
                             for n, item in enumerate(parsed)]
                with self.writer(), self.library.writer():
                    if artifacts:
                        evidence.update(transfer_artifacts(source, self.library, artifacts))
                    if question:
                        snapshot = sync_work(source, question)
                        body_record = read_json(source.blob_path(snapshot["blob"]))
                        # A publication preserves notes/scripts; outputs travel only as selected artifacts.
                        for sha in [snapshot["blob"], *body_record["files"].values()]:
                            if self.library.put_file(source.blob_path(sha), "work") != sha:
                                raise DawError("publication_source_changed", sha)
                        evidence["notebook"] = {"question": question, "snapshot": snapshot["snapshot"],
                                                "manifest_blob": snapshot["blob"]}
                    if checked is not None:
                        evidence["claims_blob"] = self.library.put_json(claims_document(checked))
                    if items:
                        evidence["frontier"] = [{"question": question, "event": item["id"]} for item in items]
                    identity = self._post(author, title, body, evidence=evidence, **options)
                    self._settle_request(identity, options.get("parent"))
            if question or items:
                # The frontier projection is refreshed on the write path, never by a read (v2 C3).
                from daw.commons.frontier import reindex_after_publish
                reindex_after_publish(self, identity)
            if options.get("supersedes"):
                # Flow B: readers who fetched the superseded post's evidence receive a correction notice.
                notify_affected(self, identity)
            shown = self.show(identity)
            # V1: evidence without claims is published, with a non-fatal warning in the output.
            warnings = publication_warnings(evidence, claims)
            return {**shown, "warnings": warnings} if warnings else shown
        finally:
            if source:
                source.close()

    def _settle_request(self, post, parent):
        """A target's reply to a question post answers it; the request must not stay open behind a second channel."""
        if not parent:
            return
        row = self.one("SELECT * FROM post WHERE id=?", (post,))
        request = self.one("SELECT * FROM request WHERE post=? AND target=? AND state IN ('pending','failed')",
                           (parent, row["author"]))
        if request:
            with self.db:
                self.db.execute("UPDATE request SET state='completed',answer=?,updated=? WHERE id=?",
                                (post, now(), request["id"]))
                self.event("answered_by_publication", {"request": request["id"], "answer": post, "target": row["author"]})

    def ask(self, target, author, body, *, parent=None, request_key=None, notify=False):
        """Queue a question. The answer is always visible in inbox --sent; a model turn for the
        asker is queued only when notify=True, so an unchanged conclusion costs no delivery."""
        if target.startswith("post_"):
            parent = target
            target = self.show(target)["author"]
        agent = self.agent(target)
        if agent["kind"] == "agent":
            self.trial(agent)
        elif agent["kind"] not in {"human", "operator"}:
            raise DawError("participant_cannot_receive_requests", agent["kind"])
        with self.writer(), self.library.writer():
            post = self._post(author, "Question for " + agent["name"], body, parent=parent,
                              request_key=request_key, kind="question",
                              evidence={"target": agent["id"], "notify": bool(notify)})
            old = self.one("SELECT * FROM request WHERE post=?", (post,))
            if old:
                return old
            identity = "request_" + uuid.uuid4().hex
            with self.db:
                self.db.execute("INSERT INTO request(id,post,target,state,active_run,answer,created,updated) "
                                "VALUES(?,?,?,'pending',NULL,NULL,?,?)", (identity, post, agent["id"], now(), now()))
                self.event("question_queued", {"request": identity, "post": post, "target": agent["id"]})
        return self.one("SELECT * FROM request WHERE id=?", (identity,))

    def inbox(self, identity, *, all_states=False, sent=False, since=None):
        """Requests for an agent. `since` (an ISO timestamp from a previous call's rows) returns only
        rows updated after it, so a checkpoint check does not re-read unchanged state."""
        agent = self.agent(identity)
        extra, params = "", [agent["id"]]
        if since:
            extra, params = " AND r.updated>?", [agent["id"], since]
        if sent:
            return self.rows("SELECT r.* FROM request r JOIN post p ON r.post=p.id WHERE p.author=?" + extra
                             + " ORDER BY r.created,r.id", params)
        return self.rows("SELECT r.* FROM request r WHERE r.target=?" + ("" if all_states else " AND r.state!='completed'")
                         + extra + " ORDER BY r.created,r.id", params)

    def queue_answer_notifications(self, agents=()):
        """Idempotently notify question authors who asked with notify=True, including answers from older workers.

        Notifications reuse the durable delivery queue. Their acknowledgments are
        not questions, so they cannot generate recursive answer notifications.
        Questions asked without notify are answered in inbox --sent only; no model turn is spent.
        """
        queued = []
        allowed = {self.agent(a)["id"] for a in agents}
        with self.writer(), self.library.writer():
            for request in self.rows(
                "SELECT r.*,p.author FROM request r JOIN post p ON p.id=r.post "
                "JOIN agent a ON a.id=p.author WHERE r.state='completed' AND r.answer IS NOT NULL "
                "AND a.trial IS NOT NULL AND p.author!=r.target ORDER BY r.updated,r.id"
            ):
                if allowed and request["author"] not in allowed:
                    continue
                content = self.show(request["post"])["content"]
                if content["kind"] != "question" or not content.get("evidence", {}).get("notify"):
                    continue
                key = "answer-notification:" + request["id"]
                existing = self.one("SELECT r.id FROM request r JOIN post p ON p.id=r.post WHERE p.request_key=?", (key,))
                if existing:
                    continue
                post = self._post("operator", "Answer available for your question",
                    f"Your question {request['post']} has been answered in {request['answer']}. "
                    "Read that answer and relevant evidence with community show/fetch. Assess whether it changes "
                    "your findings, next step or open questions; update your LABBOOK if useful. "
                    "This is an answer notification, not an instruction to start a new investigation. "
                    "If no change is needed, a brief acknowledgment is sufficient. Do not ask a courtesy "
                    "follow-up; ask only if a consequential uncertainty remains.",
                    parent=request["answer"], kind="answer_notification", request_key=key,
                    evidence={"source_request": request["id"], "answer": request["answer"], "target": request["author"]})
                identity = "request_" + uuid.uuid4().hex
                with self.db:
                    self.db.execute("INSERT INTO request(id,post,target,state,active_run,answer,created,updated) "
                                    "VALUES(?,?,?,'pending',NULL,NULL,?,?)", (identity, post, request["author"], now(), now()))
                    self.event("answer_notification_queued", {"request": identity, "source_request": request["id"],
                               "answer": request["answer"], "target": request["author"]})
                queued.append(identity)
        return queued

    def find(self, text="", *, limit=20, offset=0, family="forum", full=False, reader=None):
        """Board search for participants (the agent CLI and board service): always moderated."""
        return find(self, text, limit=limit, offset=offset, family=family, full=full, moderate=True,
                    reader=reader)

    def _posts_naming(self, artifact):
        return posts_naming(self, artifact)

    def fetch(self, post, workspace, question, *, artifact=None, author="operator"):
        from daw.commons.moderation import Visibility
        if Visibility.of(self, self.agent(author)).withheld(post):
            raise DawError("hidden_by_moderation", post)
        published = self.show(post)
        allowed = published["content"]["evidence"].get("artifacts", [])
        selected = [artifact] if artifact else allowed
        if not selected or any(a not in allowed for a in selected):
            raise DawError("artifact_not_published_in_post")
        agent = self.agent(author)
        # A suspended participant can only read the board; fetching writes its workspace and a board event.
        if self.one("SELECT 1 FROM moderation WHERE target_kind='participant' AND target_id=? AND state='suspended'",
                    (agent["id"],)):
            raise DawError("participant_suspended", agent["id"])
        target = Workspace(workspace)
        try:
            with target.writer():
                question_record(target, question)
                receipt = transfer_artifacts(self.library, target, selected)
                for aid in selected:
                    attach_artifact(target, question, aid, "considered")
                record_event(target, question, "community_evidence_fetched",
                             {"post": post, "author": published["author"], **receipt})
            with self.writer(), self.db:
                self.event("evidence_fetched", {"post": post, "reader": agent["id"], "question": question,
                                                "workspace": str(target.root), **receipt})
            return {**receipt, "question": question, "relationship": "considered",
                    "note": "Retrieval is not analysis or proof of reuse. Inspect applicability before using these artifacts."}
        finally:
            target.close()

    def audit(self):
        return {"agents": self.rows("SELECT id,name,native_session,parent,trial FROM agent ORDER BY created"),
                "requests": self.rows("SELECT * FROM request ORDER BY created"),
                "attempts": self.rows("SELECT * FROM attempt ORDER BY created"),
                "events": [{**row, "body": json.loads(row["body"])} for row in self.rows("SELECT * FROM event ORDER BY seq")],
                "interpretation": "Posts, fetches and successful delivery are operational evidence. Read transcripts and producing receipts to assess scientific reuse."}
