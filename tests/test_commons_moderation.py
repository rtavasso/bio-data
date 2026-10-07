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
    # Curation locator (B1): a hidden post's numbers, evidence artifacts and their locators are its content.
    assert api.get("/api/curation/locate", params={"post": post, "offset": 0}).json() == stub
    assert api.get(f"/api/writeup-checks/{post}").json() == stub

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
    (root / "library" / "staging").mkdir(exist_ok=True)  # writes need it; the fixture keeps it (B2)
    target = _check_surfaces(root)
    assert target["post"].startswith("post_")


# Route parameters that carry a post id. A path parameter named `identity` may name a post or something else:
# the route is probed with the hidden post's id, and a route that refuses it as another kind of record
# (`unknown_artifact`, `invalid_view`, ...) does not take posts.
POST_PARAMS = {"post", "post_id", "posts", "target_id"}  # target_id with target_kind=post (/api/marks)


def _post_routes(app):
    """Every GET API route with a parameter that can carry a post id: (path, path params, query params)."""
    from fastapi.routing import APIRoute

    def flat(routes):
        for route in routes:
            if hasattr(route, "original_router"):
                yield from flat(route.original_router.routes)
            elif isinstance(route, APIRoute):
                yield route
    out = []
    for route in flat(app.routes):
        if "GET" not in route.methods:
            continue
        path = [p.name for p in route.dependant.path_params]
        query = [p for p in route.dependant.query_params if p.name in POST_PARAMS]
        if POST_PARAMS & set(path) or query or path == ["identity"]:
            out.append((route, path, query))
    return out


def _contains_stub(value, stub):
    """True when the response carries the post's moderation record: its id (or, in a post-keyed record such as a
    correction state, its `post`) flagged hidden with the public reason."""
    if isinstance(value, dict):
        named = stub["id"] in (value.get("id"), value.get("post"))
        if named and value.get("hidden") is True and value.get("reason") == stub["reason"]:
            return True
        return any(_contains_stub(v, stub) for v in value.values())
    if isinstance(value, list):
        return any(_contains_stub(v, stub) for v in value)
    return False


def _bare_stub(value, post):
    """Every record that names the hidden post (by `id` or `post`) carries no text field (title, body, excerpt,
    note...): a structural check that does not depend on the fixture offering a unique title (v3.1, after a title
    leak through `Visibility.card` passed the secret-string check on both fixtures)."""
    from daw.commons.moderation import TEXT_FIELDS
    allowed = {"label", "reason", "context"}  # a stub's own placeholder label and public reason are not the post's text
    if isinstance(value, dict):
        if post in (value.get("id"), value.get("post")) and value.get("hidden") is True:
            leaked = {k: v for k, v in value.items() if k in TEXT_FIELDS - allowed and isinstance(v, str) and v}
            assert not leaked, (post, leaked)
        for v in value.values():
            _bare_stub(v, post)
    elif isinstance(value, list):
        for v in value:
            _bare_stub(v, post)


def _check_post_routes(root, target):
    """B1: every GET route that takes a post id answers a hidden post with its moderation stub (or refuses it as
    hidden_by_moderation), so a new route cannot be forgotten."""
    from daw.commons import checks
    post, titled = target["post"], target["secrets"]
    stub = {"id": post, "hidden": True, "reason": REASON}
    with Archive(root) as view:
        content = view.post(post)["content"]
        found = checks.post_numbers(view, post, content.get("body") or "", content.get("evidence"))
    # Values for other required query parameters: a real number offset reaches the curation locator's lookup.
    extra = {"offset": found[0]["offset"] if found else 0, "target_kind": "post"}
    app = create_app(root, local_user="local", static_dir=root / "missing")
    api = TestClient(app)
    checked = []
    for route, path, query in _post_routes(app):
        url = route.path
        for name in path:
            url = url.replace("{" + name + "}", post if name in POST_PARAMS | {"identity"} else "x")
        params = {p.name: ([post] if p.name == "posts" else post) for p in query}
        params.update({p.name: extra[p.name] for p in route.dependant.query_params if p.name in extra})
        response = api.get(url, params=params)
        body = response.json()
        _absent(titled, body)  # before any skip: an error body may not carry the secret either (v3.1)
        _bare_stub(body, post)
        if (path == ["identity"] and not query and response.status_code in (400, 404)
                and body.get("error") not in (None, "unknown_post")):
            continue  # this identity names something other than a post (unknown_artifact, invalid_view, ...)
        if response.status_code == 403:
            assert body["error"] == "hidden_by_moderation", route.path
        else:
            assert response.status_code in (200, 422) and _contains_stub(body, stub), (route.path, body)
        checked.append(route.path)
    assert {"/api/posts/{identity}", "/api/curation/locate", "/api/curation/pointers",
            "/api/writeup-checks/{post}", "/api/marks"} <= set(checked)
    return checked


def test_every_get_route_taking_a_post_id_serves_the_stub_demo(demo):
    root, _ = demo
    _check_post_routes(root, _setup(root))


@pytest.mark.skipif(not (FIXTURE / "FIXTURE.json").is_file(), reason="real-data fixture not checked out")
def test_every_get_route_taking_a_post_id_serves_the_stub_cohort(tmp_path):
    root = tmp_path / "cohort"
    shutil.copytree(FIXTURE, root, symlinks=True)
    _check_post_routes(root, _setup(root))


def test_hidden_post_page_withholds_its_notebook_link_but_the_notebook_stays_a_workspace_record(demo):
    """B15: a hide is post-scoped. The hidden post's page (even revealed to an operator) and its verify withhold its
    notebook; the notebook itself is a workspace record and its question page and manifest stay readable."""
    root, ctx = demo
    with Archive(root) as view:
        post = next(p for p, row in views.thread_index(view)["posts"].items()
                    if isinstance((row["content"].get("evidence") or {}).get("notebook"), dict))
        notebook = view.post(post)["content"]["evidence"]["notebook"]
        author = view.post(post)["author"]
    operator = client(root, user="operator")
    assert operator.get(f"/api/posts/{post}").json()["notebook"] == notebook
    with Community(root) as board:
        moderation.hide(board, "operator", post, REASON)
    revealed = operator.get(f"/api/posts/{post}", params={"full": True}).json()
    assert revealed["hidden"] is True and revealed["notebook"] is None
    assert client(root).get(f"/api/posts/{post}").json() == {"id": post, "hidden": True, "reason": REASON}
    page = client(root).get(f"/api/questions/{author}/{notebook['question']}")
    assert page.status_code == 200 and post not in [p["post"] for p in page.json()["posts"]]
    manifest = client(root).get(f"/api/blobs/library/{notebook['manifest_blob']}")
    assert manifest.status_code == 200  # a workspace record, not the post's content


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
        # B15: verify is moderated like show: a hidden post's body hash, artifacts and notebook state are its content.
        blob = board.one("SELECT body_blob FROM post WHERE id=?", (post,))["body_blob"]
        checked = boardservice.execute(root, agent, "verify", {"post": post})
        assert {k: checked[k] for k in ("id", "hidden", "reason")} == {"id": post, "hidden": True, "reason": REASON}
        assert checked["verified"] is None and blob not in json.dumps(checked)
        assert not {"body_sha256", "artifacts", "notebook_verified"} & set(checked)
        assert board.verify(post, "operator")["verified"] is None
        assert board.verify(post, "operator", full=True)["body_sha256"] == blob
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
