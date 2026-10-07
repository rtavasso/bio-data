"""One moderation rule for every reader (spec v2 C2).

Hide one post, then check that no reader surface serves its content: the post, its thread, the map node,
the map build, the run list (and run timeline), the running strip, the SSE backlog and an export, plus the
other read models that name posts (search, requests, participant pages, claims, question pages, Studio).
A reader gets `{id, hidden: true, reason}` and nothing else; an operator who asks for `full` sees the
content. The same check runs on the synthetic demo and on a private copy of the real PMP22 cohort board.
"""
import json
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daw.commons import moderation, participation, views
from daw.commons.app import create_app
from daw.commons.archive import Archive
from daw.commons.export import export_snapshot
from daw.commons.moderation import Visibility
from daw.commons.participants import add_participant
from daw.community import Community
from daw.util import now

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pmp22-cohort"
REASON = "visibility acceptance test"


def client(root, user="local"):
    return TestClient(create_app(root, local_user=user, static_dir=root / "missing"))


def _unique_line(text, others):
    """The longest line of `text` (at least 24 characters) that occurs in no other post: a secret to look for."""
    lines = sorted({line.strip() for line in text.splitlines() if len(line.strip()) >= 24}, key=lambda s: (-len(s), s))
    for line in lines:
        if not any(line in other for other in others):
            return line[:300]
    raise AssertionError("no distinctive line in the target post")


def _pick_target(root):
    """A request post with a recorded delivery and an answer, preferring one whose title is unique on the board
    (its title is then also a secret no surface may serve)."""
    with Archive(root) as view:
        index = views.thread_index(view)
        titles = [row["content"].get("title") for row in index["posts"].values()]
        rows = view.rows("SELECT r.post,r.id AS request,a.id AS run FROM attempt a JOIN request r ON r.id=a.request "
                         "WHERE r.answer IS NOT NULL ORDER BY a.created,a.id")
        rows.sort(key=lambda r: titles.count(index["posts"][r["post"]]["content"].get("title")) != 1)
        for row in rows:
            content = index["posts"][row["post"]]["content"]
            others = [p["content"].get("title", "") + "\n" + p["content"].get("body", "")
                      for pid, p in index["posts"].items() if pid != row["post"]]
            try:
                secret = _unique_line(content["body"], others)
            except AssertionError:
                continue
            unique = titles.count(content.get("title")) == 1 and not any(content["title"] in o for o in others)
            return {**row, "title": content["title"], "secret": secret, "body": content["body"],
                    "secrets": [secret] + ([content["title"]] if unique else []),
                    "blob": index["posts"][row["post"]]["body_blob"]}
    raise AssertionError("no delivered request post with a distinctive line")


def _setup(root):
    """Comment on the target at an anchor (quoting its bytes), mark the delivery running, then hide the target."""
    target = _pick_target(root)
    quote = target["secret"]
    with Community(root) as board:
        person = add_participant(board, "visibility-" + uuid.uuid4().hex[:8], "human")
        commented = participation.comment(
            board, person["id"], "post", target["post"], "REPLY-MARKER does this hold?",
            anchor={"kind": "paragraph", "blob": target["blob"], "offset": target["body"].index(quote),
                    "length": len(quote), "quote": quote})
        run = "run_" + uuid.uuid4().hex
        with board.writer(), board.db:
            board.db.execute("INSERT INTO attempt VALUES(?,?,?,'running',?,?,NULL)",
                             (run, target["request"], board.one("SELECT target FROM request WHERE id=?",
                                                                (target["request"],))["target"], f"runs/{run}", now()))
        (root / "runs" / run).mkdir(parents=True)
        (root / "runs" / run / "heartbeat.json").write_text(json.dumps({"observed": now(), "elapsed_seconds": 5.0,
                                                                         "stdout_bytes": 10}))
        moderation.hide(board, "operator", target["post"], REASON)
    return {**target, "comment": commented["post"], "running": run, "person": person["id"]}


def _absent(secrets, *values):
    for value in values:
        text = value if isinstance(value, str) else json.dumps(value)
        for secret in secrets:
            assert secret not in text, secret


def _check_surfaces(root):
    target = _setup(root)
    post, secrets, titled = target["post"], [target["secret"]], target["secrets"]
    stub = {"id": post, "hidden": True, "reason": REASON}
    api = client(root)

    # 1. Post.
    assert api.get(f"/api/posts/{post}").json() == stub
    assert api.get(f"/api/posts/{post}", params={"full": True}).json() == stub  # full needs `hide`
    # A visible comment anchored on the hidden post keeps its own text but not the quote of the hidden bytes.
    comment = api.get(f"/api/posts/{target['comment']}").json()
    assert "REPLY-MARKER" in comment["content"]["body"]
    assert comment["content"]["evidence"]["anchor"]["quote"] is None
    _absent(secrets, comment)

    # 2. Thread.
    thread = api.get(f"/api/threads/{post}").json()

    def find(node):
        if node["id"] == post:
            return node
        for child in node.get("children", []) + node.get("corrections", []):
            found = find(child)
            if found:
                return found
    node = find(thread["tree"])
    assert {k: v for k, v in node.items() if k not in ("children", "corrections")} == stub
    _absent(titled, thread)

    # 3. Map node.
    record = api.get(f"/api/map/node/{post}").json()
    assert record["record"] == stub and record["hidden"] is True
    _absent(titled, record)
    _absent(secrets, api.get(f"/api/map/node/{target['comment']}").json())

    # 4. Map build.
    graph = api.get("/api/map").json()
    [drawn] = [n for n in graph["nodes"] if n["id"] == post]
    assert drawn["hidden"] is True and drawn["reason"] == REASON and "title" not in drawn and "author" not in drawn
    assert not [e for e in graph["edges"] if e["target"] == post and e["relation"] == "authored"]
    assert not [e for e in graph["edges"] if e["source"] == post and e["relation"] in ("evidence", "notebook")]
    _absent(titled, graph)

    # 5. Run list and run timeline.
    runs = api.get("/api/runs", params={"limit": 500}).json()["items"]
    mine = [r for r in runs if r["request_post"] == post]
    assert mine and all(r["request_title"] is None and r["request_kind"] is None and r["reason"] == REASON
                        for r in mine)
    _absent(titled, runs)
    timeline = api.get(f"/api/runs/{target['run']}").json()
    assert timeline["request"]["title"] is None and timeline["request"]["hidden"] is True
    assert api.get(f"/api/runs/{target['run']}/messages").status_code == 403
    assert api.get(f"/api/runs/{target['run']}/raw").status_code == 403

    # 6. Running strip.
    strip = api.get("/api/running").json()["items"]
    [live] = [r for r in strip if r["run"] == target["running"]]
    assert live["title"] is None and live["post_hidden"] is True and live["reason"] == REASON
    _absent(titled, strip)

    # 7. SSE backlog (and the JSON event log), replayed after the hide.
    backlog = api.get("/api/events", params={"once": True}).text
    assert f'"post":"{target["comment"]}"' in backlog  # the comment's events are framed, without the quote
    _absent(secrets, backlog)
    log = api.get("/api/events/log", params={"limit": 1000}).json()
    while log["items"]:
        _absent(secrets, log)
        if len(log["items"]) < 1000:
            break
        log = api.get("/api/events/log", params={"after": log["next_after"], "limit": 1000}).json()

    # Other read models that name posts.
    listing = api.get("/api/posts", params={"limit": 200}).json()
    _absent(titled, listing)
    search = api.get("/api/posts", params={"q": target["title"].split()[-1]}).json()
    assert all(h["post"] != post for item in search["items"] for h in item.get("hits", []))
    found = api.get("/api/search", params={"q": target["secret"].split()[0], "family": "forum", "limit": 100}).json()
    assert all(item["subject"] != post for item in found["items"])
    _absent(secrets, found)
    requests = api.get("/api/requests", params={"limit": 500}).json()["items"]
    assert [r for r in requests if r["post"] == post][0]["title"] is None
    _absent(titled, requests)
    with Archive(root) as view:
        author = view.one("SELECT author FROM post WHERE id=?", (post,))["author"]
        target_agent = view.one("SELECT target FROM request WHERE id=?", (target["request"],))["target"]
    for who in {author, target_agent, target["person"]}:
        _absent(titled, api.get(f"/api/participants/{who}/activity").json())
    _absent(titled, api.get("/api/studio").json(), api.get("/api/claims").json())

    # The operator reads through the hide only when asking for full content.
    operator = client(root, user="operator")
    assert operator.get(f"/api/posts/{post}").json() == stub
    revealed = operator.get(f"/api/posts/{post}", params={"full": True}).json()
    assert revealed["content"]["title"] == target["title"] and revealed["hidden"] is True
    assert revealed["moderation"]["reason"] == REASON
    assert operator.get(f"/api/map/node/{post}", params={"full": True}).json()["record"]["title"] == target["title"]
    assert operator.get(f"/api/runs/{target['run']}", params={"full": True}).json()["request"]["title"] == target["title"]

    # 8. Export: the hidden post is its id and moderation event; replies to it lose their bodies.
    with Community(root) as board:
        result = export_snapshot(board, "operator", "thread", post)
    site = root / result["location"]
    texts = {p.relative_to(site).as_posix(): p.read_bytes().decode("utf-8", "replace")
             for p in site.rglob("*") if p.is_file()}
    for name, text in texts.items():
        assert not [s for s in titled + ["REPLY-MARKER"] if s in text], name
    page = texts[f"posts/{post}.html"]
    assert REASON in page and "content is not exported" in page
    snapshot = json.loads(texts["snapshot.json"])
    assert [m["post"] for m in snapshot["moderation"]] == [post] and snapshot["moderation"][0]["reason"] == REASON
    assert "a reply to a post hidden by moderation" in texts[f"posts/{target['comment']}.html"].casefold()
    # Bytes are never deleted: the archive still holds the post and its body.
    with Archive(root) as view:
        assert view.post(post)["content"]["title"] == target["title"]
    return target


def test_hidden_post_is_redacted_on_every_surface_demo(demo):
    root, _ = demo
    _check_surfaces(root)


@pytest.mark.skipif(not (FIXTURE / "FIXTURE.json").is_file(), reason="real-data fixture not checked out")
def test_hidden_post_is_redacted_on_every_surface_cohort(tmp_path):
    """Hide a real cohort post in a private copy (the shared session copy is left untouched)."""
    root = tmp_path / "cohort"
    shutil.copytree(FIXTURE, root, symlinks=True)
    (root / "library" / "staging").mkdir()  # the fixture omits empty working directories; writes need it
    target = _check_surfaces(root)
    assert target["post"].startswith("post_")


def test_unhide_restores_display_and_events_are_framed_at_read_time(demo):
    root, ctx = demo
    target = _setup(root)
    api = client(root)
    assert target["secret"] not in api.get("/api/events", params={"once": True}).text
    with Community(root) as board:
        moderation.unhide(board, "operator", target["post"], "restored after review")
    shown = api.get(f"/api/posts/{target['post']}").json()
    assert shown["hidden"] is False and shown["content"]["title"] == target["title"]
    # Frames are redacted when they are sent: after unhide the backlog carries the quote again.
    assert target["secret"] in api.get("/api/events", params={"once": True}).text


def test_hidden_post_cannot_be_quoted_into_a_promotion(demo):
    root, ctx = demo
    from daw.util import DawError
    with Community(root) as board:
        person = add_participant(board, "promoter", "human")
        moderation.hide(board, "operator", ctx["posts"]["reply"], "withheld")
        with pytest.raises(DawError) as refused:
            participation.promote(board, person["id"], "post", ctx["posts"]["reply"], "research", ctx["agents"]["bob"],
                                  {"minutes": 10})
        assert refused.value.reason == "hidden_by_moderation"


def test_visibility_resolver_rules(demo):
    root, ctx = demo
    reply = ctx["posts"]["reply"]
    with Community(root) as board:
        moderation.hide(board, "operator", reply, "rule check")
        blob = board.one("SELECT body_blob FROM post WHERE id=?", (reply,))["body_blob"]
        human = add_participant(board, "reader", "human")
        operator = board.agent("operator")
    with Archive(root) as view:
        reader = Visibility.of(view)
        assert reader.withheld(reply) and reader.stub(reply) == {"id": reply, "hidden": True, "reason": "rule check"}
        assert reader.card(reply, {"title": "x", "seq": 1}, keep=("seq",)) == {**reader.stub(reply), "seq": 1}
        assert reader.card("post_other", {"title": "x"}) == {"title": "x", "hidden": False}
        assert not Visibility.of(view, human, full=True).reveal  # full needs `hide`
        full = Visibility.of(view, operator, full=True)
        assert full.reveal and not full.withheld(reply) and full.card(reply, {"title": "x"})["revealed"] is True
        assert reader.anchor({"blob": blob, "quote": "secret"})["quote"] is None
        assert reader.anchor({"blob": "other", "quote": "fine"}, {"kind": "post", "id": reply})["quote"] is None
        assert reader.anchor({"blob": "other", "quote": "fine"})["quote"] == "fine"
        event = {"seq": 1, "kind": "comment_posted", "body": {"post": "post_c", "target_id": reply,
                                                              "anchor": {"quote": "secret", "offset": 3}}}
        framed = reader.event(event)
        assert framed["body"]["anchor"] == {"quote": None, "offset": 3} and framed["redacted"]
        hide_event = {"seq": 2, "kind": "post_hidden", "body": {"target_id": reply, "reason": "rule check"}}
        assert reader.event(hide_event) == hide_event
        assert reader.claim({"id": "claim_x", "post": reply, "text": "t"}) == {
            "id": "claim_x", "post": reply, "hidden": True, "reason": "rule check"}
        assert views.hidden_posts(view)[reply]["reason"] == "rule check"


def _check_agent_reads(root):
    """Agents are readers too (C2): the bio community CLI paths (Community.read/find/fetch), the sandbox board
    service, delivery and the answer path never serve a hidden post's text to an agent."""
    from daw.commons import boardservice
    from daw.util import DawError
    target = _setup(root)
    post, secrets = target["post"], target["secrets"]
    with Community(root) as board:
        agent = board.one("SELECT target FROM request WHERE id=?", (target["request"],))["target"]
        assert board.read(post, agent) == {"id": post, "hidden": True, "reason": REASON,
                                           "content_is_untrusted_data": True}
        assert board.read(post, agent, full=True)["hidden"] is True  # agents cannot hold `hide`: still a stub
        assert target["secret"] in json.dumps(board.read(post, "operator", full=True))
        comment = board.read(target["comment"], agent)
        _absent(secrets, comment)
        assert comment["content"]["evidence"]["anchor"]["quote_withheld"] is True
        words = " ".join(target["secret"].split()[:4])
        found = board.find(words, reader=agent, full=True)
        _absent(secrets, found)
        assert all(hit["subject"] != post for hit in found["items"])
        for operation in ("show", "search"):
            payload = {"post": post} if operation == "show" else {"text": words, "full": True}
            _absent(secrets, boardservice.execute(root, agent, operation, payload))
        with pytest.raises(DawError) as refused:
            board.fetch(post, root, "q_unused", author=agent)
        assert refused.value.reason == "hidden_by_moderation"
    return target


def test_agent_side_reads_withhold_hidden_posts_demo(demo, monkeypatch):
    root, ctx = demo
    _check_agent_reads(root)
    # A hidden request is never delivered: the service skips it and a dispatch refuses before any state change.
    from daw.community_runtime import dispatch
    from daw.community_service import pending_deliveries
    from daw.util import DawError
    with Community(root) as board:
        person = add_participant(board, "asker-" + uuid.uuid4().hex[:6], "human")
        request = board.ask(ctx["agents"]["alice"], ctx["agents"]["bob"], "SECRET-ASK which donors overlap?")
        moderation.hide(board, "operator", request["post"], REASON)
        assert request["id"] not in {r["id"] for r in pending_deliveries(board)}
        monkeypatch.setenv("DAW_LIVE", "1")
        with pytest.raises(DawError) as refused:
            dispatch(board, request["id"], ctx["harness"])
        assert refused.value.reason == "hidden_by_moderation"
        assert board.one("SELECT state FROM request WHERE id=?", (request["id"],))["state"] == "pending"
        from daw.commons import boardservice
        answered = boardservice.answer(board, ctx["agents"]["alice"], request["id"], "Not recorded.")
        assert "SECRET-ASK" not in json.dumps(answered) and "which donors" not in answered["content"]["title"]
        assert person


@pytest.mark.skipif(not (FIXTURE / "FIXTURE.json").is_file(), reason="real-data fixture not checked out")
def test_agent_side_reads_withhold_hidden_posts_cohort(tmp_path):
    root = tmp_path / "cohort"
    shutil.copytree(FIXTURE, root, symlinks=True)
    (root / "library" / "staging").mkdir(exist_ok=True)
    assert _check_agent_reads(root)["post"].startswith("post_")
