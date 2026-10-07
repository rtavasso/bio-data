"""Spec v2 V4, the human workbench: inbox, saved views, reading mode, anchored replies and review requests.

Invariants run on the synthetic demo (exact records); counts on real records run on the committed cohort fixture.
"""
import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from daw.commons import inbox, moderation, participation, savedviews
from daw.commons.app import create_app
from daw.commons.archive import Archive
from daw.commons.demo import scripted_runtime
from daw.commons.participants import add_participant
from daw.community import Community
from daw.community_runtime import dispatch
from daw.util import DawError

WRITE = {"X-Colloquy-Request": "1"}


def client(root, **options):
    return TestClient(create_app(root, static_dir=root / "missing", **options))


@pytest.fixture
def demo(demo_only):
    return demo_only("daw.commons.claims:extend_demo", "daw.commons.participation:demo_records")


def _human(root, name="rhea"):
    with Community(root) as board:
        return add_participant(board, name, "human", profile={"display_name": name.title()})["id"]


def _frames(text):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


# ---------------------------------------------------------------------------- inbox

def test_inbox_items_come_from_recorded_relations(demo):
    """Answers to a person's asks, replies to their comments, corrections to posts they marked."""
    root, ctx = demo
    mira = ctx["participation"]["human"]
    finding, correction = ctx["posts"]["finding"], ctx["posts"]["correction"]
    rhea = _human(root)
    with Community(root) as board:
        # mira marks the finding, which the correction supersedes (a recorded `supersedes` link).
        participation.mark(board, mira, "post", finding, "disputed", "1.45 does not match the table.", [])
        reply = participation.reply_at_anchor(board, rhea, ctx["participation"]["comment"], "Same question here.")
    with Archive(root) as view:
        items = {i["id"]: i for i in inbox.items(view, view.participant(mira))}
    answer = items[f"answer:{ctx['participation']['comment_request']}"]
    assert answer["post"] == ctx["participation"]["comment_answer"] and answer["relation"]["table"] == "request"
    replied = items[f"reply:{reply['post']}"]
    assert replied["to_comment"] and replied["anchored"] and replied["in_reply_to"] == ctx["participation"]["comment"]
    fixed = items[f"correction:{correction}"]
    assert fixed["corrects"] == finding and fixed["relation"]["field"] == "supersedes"
    assert [m["target_id"] for m in fixed["marks"]] == [finding]
    # The answer is not listed again as a reply; every item carries the board seq of its record.
    assert f"reply:{answer['post']}" not in items
    assert all(isinstance(i["seq"], int) for i in items.values())
    # Nothing is inferred: a participant with no asks, posts, marks or promotions has an empty inbox.
    with Archive(root) as view:
        assert inbox.items(view, view.participant(rhea)) == []


def test_inbox_watcher_hits_on_items_the_person_promoted(demo):
    from daw.commons.demo import _no_reserve
    from daw.commons.discovery_demo import ensure_gap_item, recorded_transport
    from daw.commons.watchers import add_watcher, open_workspace, tick
    root, ctx = demo
    rhea = _human(root)
    with Community(root) as board:
        item = ensure_gap_item(board, ctx)
        scratch = open_workspace(board.root)
        scratch.close()
        _no_reserve(scratch.root)
        add_watcher(board, "operator", item, {"query": "demo marker knockdown"}, "europepmc")
        participation.promote(board, rhea, "frontier_item", item, "research", ctx["agents"]["dana"], {"minutes": 30})
        ran = tick(board, now=time.time(), transport=recorded_transport())
    run = next(r["run"] for r in ran["ran"] if "run" in r)
    with Archive(root) as view:
        items = {i["id"]: i for i in inbox.items(view, view.participant(rhea))}
        hit = items[f"watcher_hit:{run}"]
        assert hit["item"] == item and hit["new"] >= 1 and hit["relation"]["kind"] == "watcher_ran"
        # Someone who did not promote the item gets no watcher hit.
        others = inbox.items(view, view.participant(ctx["participation"]["human"]))
        assert not [i for i in others if i["kind"] == "watcher_hit"]


def test_inbox_read_state_is_the_persons_own_write(demo):
    root, ctx = demo
    mira = ctx["participation"]["human"]
    http = client(root, local_user="mira")
    listed = http.get("/api/me/inbox").json()
    assert listed["participant"] == mira and listed["unread"] == len(listed["items"]) >= 1
    key = listed["items"][0]["id"]
    assert http.post("/api/me/inbox/read", json={"items": [key]}).status_code == 403  # CSRF header required
    marked = http.post("/api/me/inbox/read", headers=WRITE, json={"items": [key]})
    assert marked.status_code == 200 and marked.json()["marked"] == [key]
    again = http.get("/api/me/inbox").json()
    assert again["unread"] == listed["unread"] - 1
    assert next(i for i in again["items"] if i["id"] == key)["read"] is True
    assert http.get("/api/me/inbox?unread=true").json()["total"] == again["unread"]
    unknown = http.post("/api/me/inbox/read", headers=WRITE, json={"items": ["answer:request_nope"]})
    assert unknown.status_code == 404
    with Community(root) as board:
        events = board.rows("SELECT body FROM event WHERE kind='inbox_marked_read'")
        assert [json.loads(e["body"])["participant"] for e in events] == [mira]
        with pytest.raises(sqlite3.IntegrityError):
            board.db.execute("DELETE FROM inbox_read")  # read rows are immutable records
    # Another person's "mark read" never touches mira's state.
    _human(root)
    other = client(root, local_user="rhea")
    assert other.post("/api/me/inbox/read", headers=WRITE, json={"items": [key]}).status_code == 404
    assert other.post("/api/me/inbox/read", headers=WRITE, json={"all": True}).json()["marked"] == []
    with Archive(root) as view:
        assert set(inbox.read_state(view, mira)) == {key}


def test_inbox_after_cursor_and_per_caller_sse_stream(demo):
    root, ctx = demo
    http = client(root, local_user="mira")
    listed = http.get("/api/me/inbox").json()
    latest = listed["latest"]
    assert http.get(f"/api/me/inbox?after={latest}").json()["items"] == []
    stream = http.get("/api/me/inbox/stream?once=true&after=0")
    assert stream.status_code == 200 and stream.headers["content-type"].startswith("text/event-stream")
    frames = _frames(stream.text)
    assert {f["id"] for f in frames} == {i["id"] for i in listed["items"]}
    assert all(f["kind"] == "inbox_item" for f in frames)
    ids = [int(line[4:]) for line in stream.text.splitlines() if line.startswith("id: ")]
    assert ids == sorted(ids) and ids[-1] == latest
    resumed = http.get("/api/me/inbox/stream?once=true", headers={"Last-Event-ID": str(latest)})
    assert "data: " not in resumed.text
    # A new reply under mira's comment arrives after the cursor, and only on mira's stream.
    rhea = _human(root)
    with Community(root) as board:
        reply = participation.reply_at_anchor(board, rhea, ctx["participation"]["comment"], "And for donors?")
    fresh = http.get(f"/api/me/inbox/stream?once=true&after={latest}")
    assert [f["id"] for f in _frames(fresh.text)] == [f"reply:{reply['post']}"]
    theirs = client(root, local_user="rhea").get("/api/me/inbox/stream?once=true&after=0")
    assert _frames(theirs.text) == []


def test_ten_inbox_subscribers_and_one_write_cost_one_index_build(demo, monkeypatch):
    """v3 B8: each stream computes its full inbox on connect only; a board change is read as a delta of the events
    since the stream's cursor, from one event window shared by every subscriber. Ten subscribers and one write
    cost one window build and at most one thread index build, and each delta equals the full inbox after the
    cursor."""
    import asyncio

    from daw.commons import views
    from daw.commons.api.workbench import inbox_stream
    root, ctx = demo
    mira = ctx["participation"]["human"]
    people = [mira] + [_human(root, f"reader{n}") for n in range(9)]
    with Archive(root) as view:
        who = [{k: view.participant(p)[k] for k in ("id", "name", "kind")} for p in people]
        before = inbox.inbox(view, who[0], limit=500)["latest"]
    streams = [inbox_stream(root, person, 0, poll=0.01, keepalive=0) for person in who]

    async def turn(stream):
        """Frames of one poll of a stream (each poll ends with a keepalive comment when keepalive=0)."""
        frames = []
        while (chunk := await stream.__anext__()) != ": keepalive\n\n":
            frames += _frames(chunk)
        return frames

    async def scenario():
        for stream in streams:
            assert await stream.__anext__() == "retry: 3000\n\n"
        connected = await asyncio.gather(*(turn(s) for s in streams))  # full inbox, once per connection
        real, builds = views.thread_index, []

        def counting(view):
            if (str(view.root), view.sequence()) not in views._INDEX:
                builds.append(view.sequence())
            return real(view)
        monkeypatch.setattr(views, "thread_index", counting)
        windows = inbox.BUILDS["windows"]
        with Community(root) as board:
            reply = participation.reply_at_anchor(board, people[1], ctx["participation"]["comment"], "Donors?")
        changed = await asyncio.gather(*(turn(s) for s in streams))
        for stream in streams:
            await stream.aclose()
        return connected, changed, inbox.BUILDS["windows"] - windows, builds, reply

    connected, changed, windows, builds, reply = asyncio.run(scenario())
    assert {f["id"] for f in connected[0]} and not any(connected[1:])
    assert windows == 1 and len(builds) <= 1
    assert [f["id"] for f in changed[0]] == [f"reply:{reply['post']}"] and not any(changed[1:])
    # The delta equals the full inbox after the cursor, read state included.
    with Archive(root) as view:
        full = inbox.inbox(view, who[0], after=before)["items"]
    assert changed[0] == [{**item, "kind": "inbox_item"} for item in full]  # the SSE frame names its own kind


def test_hidden_posts_stay_hidden_in_the_inbox(demo):
    root, ctx = demo
    with Community(root) as board:
        moderation.hide(board, "operator", ctx["participation"]["comment_answer"], "test")
    with Archive(root) as view:
        items = inbox.items(view, view.participant(ctx["participation"]["human"]))
    answer = next(i for i in items if i["kind"] == "answer")
    assert answer["hidden"] and answer["title"] is None and answer["author"] is None and answer["reason"] == "test"


def test_inbox_on_the_cohort_counts_recorded_answers(cohort):
    """On the real board: an agent's inbox answers are exactly its requests answered by someone else."""
    with Archive(cohort) as view:
        asker = view.one("SELECT p.author FROM request r JOIN post p ON p.id=r.post WHERE r.answer IS NOT NULL "
                         "GROUP BY p.author ORDER BY count(*) DESC LIMIT 1")["author"]
        expected = view.one("SELECT count(*) AS n FROM request r JOIN post p ON p.id=r.post JOIN post a ON "
                            "a.id=r.answer WHERE p.author=? AND a.author!=?", (asker, asker))["n"]
        items = inbox.items(view, view.participant(asker))
        answers = [i for i in items if i["kind"] == "answer"]
        assert expected > 0 and len(answers) == expected
        assert {i["relation"]["table"] for i in items} <= {"request", "post", "event"}


# ---------------------------------------------------------------------------- saved views

def test_saved_view_is_an_immutable_hash_addressed_record(demo):
    root, ctx = demo
    http = client(root, local_user="mira")
    spec = {"questions": [ctx["questions"]["alice"]], "participants": ["alice"], "since": "2020-01-01T00:00:00Z"}
    saved = http.post("/api/views", headers=WRITE, json=spec)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    expected = {"format": 1, "questions": [ctx["questions"]["alice"]], "participants": [ctx["agents"]["alice"]],
                "since": "2020-01-01T00:00:00+00:00", "until": None}
    assert body["spec"] == expected and body["view"] == savedviews.view_hash(expected) and not body["existing"]
    # The same selection (an id instead of a name, keys in another order) names the same record.
    again = http.post("/api/views", headers=WRITE, json={"participants": [ctx["agents"]["alice"]],
                                                         "questions": [ctx["questions"]["alice"]],
                                                         "since": "2020-01-01T00:00:00+00:00"}).json()
    assert again["view"] == body["view"] and again["existing"]
    shown = http.get(f"/api/views/{body['view']}").json()
    assert shown["spec"] == expected and shown["participant_names"] == {ctx["agents"]["alice"]: "alice"}
    assert http.get("/api/views/" + "0" * 64).status_code == 404
    assert http.post("/api/views", headers=WRITE, json={}).status_code == 400
    assert http.post("/api/views", headers=WRITE, json={"participants": ["nobody"]}).status_code == 404
    assert http.post("/api/views", headers=WRITE, json={"since": "2026-02-01", "until": "2026-01-01"}).status_code == 400
    assert http.post("/api/views", json={"since": "2026-02-01"}).status_code == 403  # write discipline
    with Community(root) as board:
        assert board.one("SELECT count(*) AS n FROM event WHERE kind='view_saved'")["n"] == 1
        with pytest.raises(sqlite3.IntegrityError):
            board.db.execute("UPDATE saved_view SET spec='{}'")


def test_every_list_endpoint_and_the_map_accept_a_view(demo):
    root, ctx = demo
    http = client(root, local_user="mira")
    alice, bob, dana = ctx["agents"]["alice"], ctx["agents"]["bob"], ctx["agents"]["dana"]
    view = http.post("/api/views", headers=WRITE, json={"participants": [bob]}).json()["view"]
    posts = http.get(f"/api/posts?view={view}").json()
    assert posts["view"]["view"] == view and posts["items"]
    assert len(posts["items"]) < len(http.get("/api/posts").json()["items"])
    with Archive(root) as archive:
        authors = {r["id"]: r["author"] for r in archive.rows("SELECT id,author FROM post")}
    assert all(any(authors[m] == bob for m in card["matched"]) for card in posts["items"])
    requests = http.get(f"/api/requests?view={view}").json()["items"]
    assert requests and all(bob in {r.get("asker"), r["target"]} for r in requests)
    runs = http.get(f"/api/runs?view={view}").json()
    with Archive(root) as archive:
        asked = {r["id"] for r in archive.rows("SELECT a.id FROM attempt a JOIN request q ON q.id=a.request JOIN post p "
                                               "ON p.id=q.post WHERE p.author=? OR a.target=?", (bob, bob))}
    assert runs["items"] and {r["id"] for r in runs["items"]} == asked and runs["total"] == len(asked)
    questions = http.get(f"/api/questions?view={view}").json()["items"]
    assert questions and {q["agent"] for q in questions} == {bob}
    claims = http.get(f"/api/claims?view={view}").json()
    assert all(c["author"] == bob for c in claims["items"])
    log = http.get(f"/api/events/log?view={view}").json()["items"]
    assert log and all(bob in json.dumps(e["body"]) for e in log)
    assert http.get(f"/api/search?q=normalization&view={view}").json()["view"]["view"] == view
    for path in ("/api/frontier", "/api/wishlist", "/api/claims/contradictions", "/api/running", "/api/metrics/runs",
                 "/api/me/inbox"):
        response = http.get(f"{path}?view={view}")
        assert response.status_code == 200 and response.json()["view"]["view"] == view, path
    # The map: Bob's neighbourhood; Dana's question is not drawn.
    graph = http.get(f"/api/map?view={view}").json()
    nodes = {n["id"] for n in graph["nodes"]}
    assert bob in nodes and graph["filters"]["view"] == view
    assert not any(n.startswith(f"question:{dana}") for n in nodes)
    # A question view, and a window that excludes every record.
    qview = http.post("/api/views", headers=WRITE, json={"questions": [ctx["questions"]["alice"]]}).json()["view"]
    threads = http.get(f"/api/posts?view={qview}").json()["items"]
    assert threads and all(alice in t["participants"] for t in threads)
    past = http.post("/api/views", headers=WRITE, json={"until": "2000-01-01T00:00:00Z"}).json()["view"]
    assert http.get(f"/api/posts?view={past}").json()["items"] == []
    assert http.get(f"/api/requests?view={past}").json()["items"] == []
    assert http.get("/api/posts?view=nothex").status_code == 400


def test_views_never_match_hidden_post_content(demo):
    root, ctx = demo
    http = client(root, local_user="mira")
    with Community(root) as board:
        moderation.hide(board, "operator", ctx["posts"]["reply"], "test")
    view = http.post("/api/views", headers=WRITE, json={"questions": [ctx["questions"]["bob"]]}).json()["view"]
    items = http.get(f"/api/posts?view={view}").json()["items"]
    assert ctx["posts"]["reply"] not in {m for t in items for m in (t.get("matched") or [])}


def test_saved_views_are_rate_limited_from_board_records(demo):
    root, _ = demo
    (root / "commons.toml").write_text("[limits]\nviews_per_hour = 2\n")
    http = client(root, local_user="mira")
    for year in (2021, 2022):
        assert http.post("/api/views", headers=WRITE, json={"since": f"{year}-01-01T00:00:00Z"}).status_code == 200
    assert http.post("/api/views", headers=WRITE, json={"since": "2029-01-01T00:00:00Z"}).status_code == 429
    # A restart (a new app on the same board) keeps the count: it is read from saved_view rows.
    restarted = client(root, local_user="mira")
    assert restarted.post("/api/views", headers=WRITE, json={"since": "2028-01-01T00:00:00Z"}).status_code == 429


def test_cohort_view_selects_exactly_an_authors_posts(cohort):
    from daw.commons.views import list_posts
    with Archive(cohort) as view:
        author = view.one("SELECT author FROM post GROUP BY author ORDER BY count(*) DESC LIMIT 1")["author"]
        authored = {r["id"] for r in view.rows("SELECT id FROM post WHERE author=?", (author,))}
        spec = savedviews.normalize(view, {"participants": [author]})
        listed = list_posts(view, scope=savedviews.Scope(savedviews.view_hash(spec), spec), limit=200)
        assert {m for t in listed["items"] for m in t["matched"]} == authored


# ---------------------------------------------------------------------------- reading mode

def test_reading_mode_interleaves_posts_corrections_and_claims(demo):
    root, ctx = demo
    reading = client(root).get(f"/api/threads/{ctx['claims']['correction']}/reading").json()
    items = reading["items"]
    assert reading["root"] == ctx["claims"]["summary"]
    assert [i["created"] for i in items] == sorted(i["created"] for i in items)
    assert "correction" in {i.get("post_kind") for i in items if i["type"] == "post"}
    claims = {i["id"]: i for i in items if i["type"] == "claim"}
    assert {ctx["claims"]["withdrawn"], ctx["claims"]["current"]} <= set(claims)
    assert claims[ctx["claims"]["withdrawn"]]["withdrawn_by"] == ctx["claims"]["correction"]
    correction = next(i for i in items if i["id"] == ctx["claims"]["correction"])
    assert correction["supersedes"] == ctx["claims"]["summary"] and correction["evidence"]["artifacts"]
    # Each claim follows its own post.
    order = [i["id"] for i in items]
    assert order.index(ctx["claims"]["current"]) > order.index(ctx["claims"]["correction"])
    reading = client(root).get(f"/api/threads/{ctx['posts']['correction']}/reading").json()
    items = reading["items"]
    numbers = reading["numbers"]
    assert numbers and all(n["status"] in {"verified", "unverified", "post_scoped", "unpointed"} for n in numbers)
    order = [i["id"] for i in items if i["type"] == "post"]
    positions = [order.index(n["post"]) for n in numbers]
    assert positions == sorted(positions) and reading["counts"]["numbers"] == len(numbers)


def test_reading_mode_on_a_cohort_thread(cohort):
    from daw.commons.reading import thread_reading
    with Archive(cohort) as view:
        root = view.one("SELECT p.id FROM post p JOIN post c ON c.parent=p.id GROUP BY p.id ORDER BY count(*) DESC "
                        "LIMIT 1")["id"]
        reading = thread_reading(view, root)
        posts = [i for i in reading["items"] if i["type"] == "post"]
        assert len(posts) >= 2 and all(i["body"] for i in posts)
        assert reading["counts"]["numbers"] == sum(len(p["numbers"]) for p in posts)


def test_reading_mode_withholds_hidden_posts(demo):
    root, ctx = demo
    with Community(root) as board:
        moderation.hide(board, "operator", ctx["posts"]["reply"], "test")
    reading = client(root).get(f"/api/threads/{ctx['posts']['finding']}/reading").json()
    stub = next(i for i in reading["items"] if i["id"] == ctx["posts"]["reply"])
    assert stub["hidden"] and "body" not in stub and "title" not in stub
    assert all(n["post"] != ctx["posts"]["reply"] for n in reading["numbers"])


# ---------------------------------------------------------------------------- anchored replies and reviews

def test_replies_under_an_anchor_stay_anchored(demo):
    root, ctx = demo
    comment = ctx["participation"]["comment"]
    rhea = _human(root)
    http = client(root, local_user="rhea")
    first = http.post(f"/api/comments/{comment}/replies", headers=WRITE, json={"body": "Is donor id in the raw table?"})
    assert first.status_code == 200, first.text
    made = first.json()
    with Community(root) as board:
        root_comment = board.show(comment)
        reply = board.show(made["post"])
    assert reply["parent"] == comment and reply["author"] == rhea and reply["content"]["kind"] == "comment"
    assert reply["content"]["evidence"]["anchor"] == root_comment["content"]["evidence"]["anchor"]
    assert reply["content"]["evidence"]["in_reply_to"] == comment
    # Replying to the author's answer, or to a reply, keeps the thread under the same root and anchor.
    answer = ctx["participation"]["comment_answer"]
    nested = http.post(f"/api/comments/{answer}/replies", headers=WRITE, json={"body": "Thanks."}).json()
    deeper = http.post(f"/api/comments/{made['post']}/replies", headers=WRITE, json={"body": "Follow-up."}).json()
    assert nested["parent"] == deeper["parent"] == comment
    assert nested["in_reply_to"] == answer and deeper["in_reply_to"] == made["post"]
    # The post page lists the replies under the anchor's comment.
    page = http.get(f"/api/posts/{ctx['posts']['correction']}").json()
    group = next(g for g in page["comments"] if any(c["id"] == comment for c in g["comments"]))
    under = next(c for c in group["comments"] if c["id"] == comment)["answers"]
    assert {made["post"], nested["post"], deeper["post"], answer} <= {a["id"] for a in under}
    # Not a comment thread: refused; a hidden comment cannot be replied to.
    assert http.post(f"/api/comments/{ctx['posts']['finding']}/replies", headers=WRITE,
                     json={"body": "x"}).status_code == 400
    with Community(root) as board:
        moderation.hide(board, "operator", comment, "test")
    assert http.post(f"/api/comments/{comment}/replies", headers=WRITE, json={"body": "x"}).status_code == 403


def test_request_review_on_an_anchored_claim_commissions_a_review(demo):
    root, ctx = demo
    with Community(root) as board:
        claim = board.one("SELECT * FROM claim WHERE status != 'withdrawn' ORDER BY created LIMIT 1")
        shown = board.show(claim["post"])
    rhea = _human(root)
    http = client(root, local_user="rhea")
    quote = shown["content"]["body"][:20]
    anchor = {"kind": "paragraph", "blob": shown["body_blob"], "offset": 0, "length": len(quote), "quote": quote}
    made = http.post("/api/reviews", headers=WRITE, json={"claim": claim["id"], "target": ctx["agents"]["bob"],
                                                         "budget": {"minutes": 20}, "anchor": anchor,
                                                         "note": "Check the cited cell."})
    assert made.status_code == 200, made.text
    request = made.json()
    assert request["task_type"] == "review" and request["claim"] == claim["id"]
    assert request["anchor"]["quote"] == quote and request["anchor"]["target_kind"] == "claim"
    with Community(root) as board:
        post = board.show(request["post"])
        assert post["content"]["kind"] == "commission" and post["author"] == rhea
        assert post["content"]["evidence"]["subject"] == {"kind": "claim", "id": claim["id"]}
        note = post["content"]["evidence"]["note"]
        assert quote in note and "Adversarial review" in note and "Check the cited cell." in note
    # From a comment thread at an anchor on the claim's post.
    with Community(root) as board:
        commented = participation.comment(board, rhea, "post", claim["post"], "This number?", anchor=anchor)
    via = http.post("/api/reviews", headers=WRITE, json={"claim": claim["id"], "target": ctx["agents"]["bob"],
                                                        "budget": {"minutes": 20}, "comment": commented["post"]})
    assert via.status_code == 200 and via.json()["anchor_comment"] == commented["post"]
    # An anchor is required; a comment anchored on another post is refused.
    assert http.post("/api/reviews", headers=WRITE, json={"claim": claim["id"], "target": ctx["agents"]["bob"],
                                                         "budget": {"minutes": 20}}).status_code == 400
    with Community(root) as board:
        other = participation.comment(board, rhea, "post", ctx["posts"]["gap"], "Unrelated.")
    refused = http.post("/api/reviews", headers=WRITE, json={"claim": claim["id"], "target": ctx["agents"]["bob"],
                                                            "budget": {"minutes": 20}, "comment": other["post"]})
    assert refused.status_code == 400 and refused.json()["error"] == "anchor_not_on_claim"


def test_review_request_respects_the_allowance(demo):
    root, ctx = demo
    (root / "commons.toml").write_text("[allowance]\nminutes = 10\n")
    _human(root)
    with Community(root) as board:
        claim = board.one("SELECT id FROM claim ORDER BY created LIMIT 1")["id"]
        with pytest.raises(DawError) as refused:
            participation.request_review(board, "rhea", claim, ctx["agents"]["bob"], {"minutes": 30},
                                         anchor={"kind": "node", "node_id": claim})
    assert refused.value.reason == "over_budget"


def test_the_authors_answer_still_closes_an_ask_after_human_replies(demo):
    root, ctx = demo
    rhea = _human(root)
    with Community(root) as board:
        shown = board.show(ctx["posts"]["correction"])
        quote = "log2 ratio 1.54"
        anchor = {"kind": "paragraph", "blob": shown["body_blob"], "offset": shown["content"]["body"].index(quote),
                  "length": len(quote), "quote": quote}
        made = participation.comment(board, rhea, "post", ctx["posts"]["correction"], "Alice?", anchor=anchor,
                                     ask_author=True)
        participation.reply_at_anchor(board, ctx["participation"]["human"], made["post"], "+1")
        assert board.one("SELECT state FROM request WHERE id=?", (made["request"]["id"],))["state"] == "pending"
        with scripted_runtime(root) as (harness, answers):
            (answers / f"{made['post']}.md").write_text("Synthetic: no donors recorded.")
            done = dispatch(board, made["request"]["id"], harness)
    assert done["state"] == "completed"
    with Archive(root) as view:
        items = {i["id"]: i for i in inbox.items(view, view.participant(rhea))}
    assert items[f"answer:{made['request']['id']}"]["post"] == done["answer"]
