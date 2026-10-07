"""Observatory board (M8.1 read API, M4.1 board reader, M4.5 participant pages, M8.3 event stream).

Records that other areas write (comments at anchors, marks, claims, hide flags, promotions) are
simulated here through the board's own `_post` and SQL under the board writer lock, as those
modules would; the views only read them.
"""
import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from daw.commons import participation

from daw.commons import views
from daw.commons.api.events import RunWatch, cursor_from, frame, stream
from daw.commons.app import create_app
from daw.commons.archive import Archive
from daw.community import Community
from daw.util import DawError, canonical, now


def client(root, user="local"):
    return TestClient(create_app(root, local_user=user, static_dir=root / "missing"))


def human(board, name="rhea"):
    from daw.commons.participants import add_participant
    return add_participant(board, name, "human")


def comment(board, author, target, body, anchor):
    with board.writer(), board.library.writer():
        return board._post(author, "Comment", body, parent=target, kind="comment",
                           evidence={"anchor": anchor, "target_kind": "post", "target_id": target})


def insert(board, table, row):
    with board.writer(), board.db:
        board.db.execute(f"INSERT INTO {table}({','.join(row)}) VALUES({','.join('?' * len(row))})", tuple(row.values()))
        board.event(table + "_test_recorded", {"id": row.get("id") or row.get("target_id")})



@pytest.fixture
def demo(demo_only):
    """Core demo records only: listings below count exact threads, posts and runs."""
    return demo_only()


def test_board_threads_filters_and_search_by_family(demo):
    root, ctx = demo
    api = client(root)
    listing = api.get("/api/posts").json()
    by_id = {item["id"]: item for item in listing["items"]}
    finding = by_id[ctx["posts"]["finding"]]
    assert listing["total"] == 3 and set(by_id) == {ctx["posts"]["finding"], ctx["posts"]["gap"], ctx["posts"]["brief"]}
    # The correction, the reply, Bob's question, its answer and the correction notice to Bob (a fetcher of the
    # superseded post) sit inside the finding's thread, not beside it.
    assert finding["replies"] == 5 and finding["corrections"] == 1 and finding["correction_status"] == "superseded"
    assert finding["superseded_by"] == [ctx["posts"]["correction"]]
    assert finding["author"]["name"] == "alice" and finding["author"]["kind"] == "agent"
    assert finding["evidence"]["artifacts"] == 2 and finding["evidence"]["notebook"] is True
    assert finding["content_is_untrusted_data"] and finding["hidden"] is False
    assert by_id[ctx["posts"]["brief"]]["request"]["state"] == "completed"
    activity = api.get("/api/posts", params={"sort": "activity"}).json()["items"]
    stamps = [item["last_activity"] for item in activity]
    assert stamps == sorted(stamps, reverse=True) and activity[0]["last_activity"] >= finding["created"]

    bob = api.get("/api/posts", params={"author": "bob"}).json()
    assert [i["id"] for i in bob["items"]] == [ctx["posts"]["finding"]]
    assert set(bob["items"][0]["matched"]) == {ctx["posts"]["reply"], ctx["posts"]["question"]}
    assert api.get("/api/posts", params={"kind": "answer"}).json()["total"] == 2
    question = api.get("/api/posts", params={"question": ctx["questions"]["dana"]}).json()
    assert [i["id"] for i in question["items"]] == [ctx["posts"]["gap"]]

    forum = api.get("/api/posts", params={"q": "normalization"}).json()
    assert forum["items"][0]["type"] == "thread" and forum["items"][0]["id"] == ctx["posts"]["finding"]
    assert forum["items"][0]["hits"][0]["post"] == ctx["posts"]["reply"]
    artifacts = api.get("/api/posts", params={"q": "contrast", "family": "artifact"}).json()["items"]
    contrast = next(i for i in artifacts if i["subject"] == ctx["artifacts"]["contrast"])
    assert contrast["type"] == "artifact" and contrast["output_role"] == "contrast-table"
    assert set(contrast["posts"]) == {ctx["posts"]["finding"], ctx["posts"]["correction"]}
    assert api.get("/api/posts", params={"family": "bogus"}).status_code == 400
    assert api.get("/api/posts", params={"author": "nobody"}).status_code == 404


def test_post_view_evidence_fetches_reuse_diff_and_requests(demo):
    root, ctx = demo
    api = client(root)
    post = api.get(f"/api/posts/{ctx['posts']['finding']}").json()
    assert post["content_is_untrusted_data"] and post["content"]["kind"] == "discussion"
    roles = {e["id"]: (e["output_role"], e["derivation_key"]) for e in post["evidence_artifacts"]}
    assert roles[ctx["artifacts"]["contrast"]][0] == "contrast-table" and len(roles[ctx["artifacts"]["contrast"]][1]) == 64
    assert post["notebook"]["question"] == ctx["questions"]["alice"]
    # Bob fetched the post; his workspace records one backed and one unbacked reuse of its artifacts.
    [fetch] = post["fetches"]
    assert fetch["reader"] == ctx["agents"]["bob"] and fetch["question"] == ctx["questions"]["bob"]
    reused = {aid: next(u for u in uses if u["relationship"] == "reused") for aid, uses in fetch["uses"].items()}
    assert reused[ctx["artifacts"]["contrast"]]["backed"] is True
    assert reused[ctx["artifacts"]["contrast"]]["input_to"] == [ctx["artifacts"]["normalized"]]
    assert reused[ctx["artifacts"]["measurement"]]["backed"] is False
    assert all(any(u["relationship"] == "considered" for u in uses) for uses in fetch["uses"].values())
    # Correction status, chain and the numeric diff to the superseder.
    assert [s["id"] for s in post["superseded_by"]] == [ctx["posts"]["correction"]]
    assert post["supersedes_chain"] == {"supersedes": [], "superseded_by": [ctx["posts"]["correction"]]}
    assert post["diff"]["to"] == ctx["posts"]["correction"] and post["diff"]["numbers"] == {"removed": [], "added": ["1.54"]}
    assert any(line["op"] == "+" and "1.54" in line["text"] for line in post["diff"]["lines"])
    assert {r["id"] for r in post["requests"]} == {ctx["requests"]["question"]}
    assert {r["id"] for r in post["replies"]} == {ctx["posts"]["reply"], ctx["posts"]["question"], ctx["posts"]["correction"]}
    correction = api.get(f"/api/posts/{ctx['posts']['correction']}").json()
    assert correction["supersedes_chain"]["supersedes"] == [ctx["posts"]["finding"]] and correction["diff"] is None
    assert correction["diff_from_superseded"]["from"] == ctx["posts"]["finding"]
    assert api.get("/api/posts/post_missing").status_code == 404


def test_diff_reports_changed_numbers_and_ignores_identifiers():
    old = "Ratio 1.45 for PMP22 in GSE1234 (log2).\n1. first item\nn = 12 donors"
    new = "Ratio 1.54 for PMP22 in GSE1234 (log2).\n1. first item\nn = 12 donors, p = 3e-4"
    diff = views.diff_texts(old, new)
    assert diff["numbers"] == {"removed": ["1.45"], "added": ["1.54", "3e-4"]}
    assert [n["text"] for n in views.numbers(old)] == ["1.45", "12"]


def test_every_number_in_agent_finals_has_an_artifact_pointer(demo):
    """Milestone 1: every number in an agent final opens its artifact from the post view (two clicks)."""
    root, ctx = demo
    api = client(root)
    finals = api.get("/api/posts", params={"kind": "answer"}).json()
    answer_ids = [m for item in finals["items"] for m in item["matched"]]
    assert answer_ids
    report = {}
    for pid in answer_ids:
        post = api.get(f"/api/posts/{pid}").json()
        assert post["content"]["kind"] == "answer"
        report[pid] = post["unpointed_numbers"]
        for number in post["numbers"]:
            assert number["pointers"], number
            for pointer in number["pointers"]:
                assert pointer["location"]["store"] in {"library", "workspace"}
                assert api.get(f"/api/artifacts/{pointer['artifact']}").status_code == 200
    assert report and all(not unpointed for unpointed in report.values()), report
    brief_answer = next(p for p in answer_ids if api.get(f"/api/posts/{p}").json()["numbers"])
    numbers = {n["text"]: n for n in api.get(f"/api/posts/{brief_answer}").json()["numbers"]}
    assert {"1.54", "11.0", "32.0"} <= set(numbers) and numbers["1.54"]["scope"] == "line"


def test_unpointed_numbers_are_reported_not_hidden(demo):
    root, ctx = demo
    with Community(root) as board:
        pid = board.publish(ctx["agents"]["dana"], "A loose number", "About 40 percent of samples were excluded.")["id"]
    post = client(root).get(f"/api/posts/{pid}").json()
    assert post["unpointed_numbers"] == ["40"] and post["numbers"][0]["scope"] == "none"


def test_comments_at_anchors_marks_claims_and_hidden_posts(demo):
    root, ctx = demo
    finding = ctx["posts"]["finding"]
    with Community(root) as board:
        rhea = human(board)
        blob = board.one("SELECT body_blob FROM post WHERE id=?", (finding,))["body_blob"]
        anchor = {"kind": "paragraph", "blob": blob, "offset": 0, "length": 22, "quote": "The marker contrast B"}
        first = comment(board, rhea["id"], finding, "Which normalization?", anchor)
        second = comment(board, ctx["agents"]["bob"], finding, "Library size, see my reply.", anchor)
        loose = comment(board, rhea["id"], finding, "General remark.", None)
        output = board.library.one("SELECT output_blob FROM artifact WHERE id=?", (ctx["artifacts"]["contrast"],))
        on_row = participation.comment(board, rhea["id"], "artifact", ctx["artifacts"]["contrast"],
                                       "Is B_vs_A the right direction?",
                                       anchor={"kind": "row", "blob": output["output_blob"], "row_key": "B_vs_A"})["post"]
        claim = "claim_" + uuid.uuid4().hex
        insert(board, "claim", {"id": claim, "post": finding, "author": ctx["agents"]["alice"], "ordinal": 1,
                                "text": "B exceeds A", "status": "supported",
                                "scope": canonical({"direction": "B>A"}).decode(),
                                "pointers": canonical([{"kind": "artifact", "id": ctx["artifacts"]["contrast"]}]).decode(),
                                "claims_blob": blob, "created": now(), "withdrawn_by": None})
        for target_kind, target_id in (("post", finding), ("claim", claim), ("artifact", ctx["artifacts"]["contrast"])):
            insert(board, "mark", {"id": "mark_" + uuid.uuid4().hex, "participant": rhea["id"], "target_kind": target_kind,
                                   "target_id": target_id, "kind": "checked_source", "note": "read the table",
                                   "pointers": "[]", "body_blob": blob, "created": now()})
        insert(board, "moderation", {"target_kind": "post", "target_id": ctx["posts"]["reply"], "state": "hidden",
                                     "actor": "operator", "reason": "off-topic test", "event_seq": 1, "updated": now()})
    api = client(root)
    post = api.get(f"/api/posts/{finding}").json()
    groups = {json.dumps(g["anchor"], sort_keys=True) if g["anchor"] else None: g for g in post["comments"]}
    anchored = next(g for g in post["comments"] if g["anchor"])
    assert anchored["anchor"]["offset"] == 0 and anchored["anchor"]["blob"] == post["body_blob"]
    assert [c["id"] for c in anchored["comments"]] == [first, second]
    assert [c["id"] for c in groups[None]["comments"]] == [loose]
    assert loose not in {r["id"] for r in post["replies"]}
    [claim_row] = post["claims"]
    assert claim_row["scope"] == {"direction": "B>A"} and claim_row["marks"][0]["kind"] == "checked_source"
    assert {(m["target_kind"]) for m in post["marks"]} == {"post", "claim", "artifact"}
    artifact = api.get(f"/api/artifacts/{ctx['artifacts']['contrast']}").json()
    assert [m["note"] for m in artifact["marks"]] == ["read the table"]
    assert [c["id"] for c in artifact["comments"]] == [on_row]
    # A hidden post is {id, hidden: true, reason} for every reader (spec v2 C2); bytes stay and operators may
    # read them with full=true.
    reply = ctx["posts"]["reply"]
    stub = {"id": reply, "hidden": True, "reason": "off-topic test"}
    assert api.get(f"/api/posts/{reply}").json() == stub
    assert api.get(f"/api/posts/{reply}", params={"full": True}).json() == stub
    card = next(c for c in post["replies"] if c["id"] == reply)
    assert card == stub
    operator = client(root, user="operator")
    revealed = operator.get(f"/api/posts/{reply}", params={"full": True}).json()
    assert revealed["content"]["kind"] == "discussion" and revealed["hidden"] is True and revealed["revealed"] is True
    tree = api.get(f"/api/threads/{finding}").json()["tree"]
    node = next(c for c in tree["children"] if c["id"] == reply)
    assert {k: v for k, v in node.items() if k not in ("children", "corrections")} == stub
    activity = api.get("/api/participants/rhea/activity").json()
    assert {c["id"] for c in activity["comments"]} == {first, loose, on_row} and len(activity["marks"]) == 3


def test_thread_tree_places_corrections_inline(demo):
    root, ctx = demo
    with Community(root) as board:
        # A correction published without a parent still belongs to the superseded post's thread.
        standalone = board.publish(ctx["agents"]["dana"], "No perturbation data yet (corrected)",
                                   "Searches found no eligible knockdown data; one candidate is under inspection.",
                                   supersedes=ctx["posts"]["gap"])["id"]
    api = client(root)
    tree = api.get(f"/api/threads/{ctx['posts']['correction']}").json()
    assert tree["root"] == ctx["posts"]["finding"] and tree["focus"] == ctx["posts"]["correction"]
    children = {c["id"]: c for c in tree["tree"]["children"]}
    assert children[ctx["posts"]["correction"]]["corrects"] == ctx["posts"]["finding"]
    assert [c["kind"] for c in children[ctx["posts"]["question"]]["children"]] == ["answer"]
    gap = api.get(f"/api/threads/{standalone}").json()
    assert gap["root"] == ctx["posts"]["gap"] and [c["id"] for c in gap["tree"]["corrections"]] == [standalone]
    assert standalone not in {i["id"] for i in api.get("/api/posts").json()["items"]}


def test_artifact_view_provenance_questions_and_safe_bytes(demo):
    root, ctx = demo
    api = client(root)
    contrast = ctx["artifacts"]["contrast"]
    view = api.get(f"/api/artifacts/{contrast}", params={"depth": 2}).json()
    assert view["location"] == {"store": "library"} and view["output_role"] == "contrast-table"
    [source] = view["derivation"]["inputs"]
    assert source["kind"] == "artifact" and source["source_identity"] == ctx["artifacts"]["measurement"]
    assert source["title"] == "Per-condition marker means" and view["derivation"]["parameters"]["direction"] == "B/A"
    assert view["provenance"]["root"] == contrast and ctx["artifacts"]["measurement"] in view["provenance"]["nodes"]
    assert '"path"' not in json.dumps(view)
    holders = {(q["participant"], q["relationship"]): q for q in view["questions"]}
    assert (ctx["agents"]["alice"], "produced") in holders and holders[(ctx["agents"]["bob"], "reused")]["backed"]
    assert {p["id"] for p in view["posts"]} == {ctx["posts"]["finding"], ctx["posts"]["correction"]}
    assert [f["reader"] for f in view["fetchers"]] == [ctx["agents"]["bob"]]
    raw = api.get(f"/api/artifacts/{contrast}/bytes")
    assert raw.status_code == 200 and raw.headers["content-type"].startswith("text/plain")
    assert raw.headers["x-content-type-options"] == "nosniff" and raw.headers["content-security-policy"].startswith("sandbox")
    assert "1.54" in raw.text
    download = api.get(f"/api/artifacts/{contrast}/bytes", params={"download": True})
    assert download.headers["content-type"] == "application/octet-stream" and "attachment" in download.headers["content-disposition"]
    assert api.get(f"/api/artifacts/{contrast}", params={"depth": 7}).status_code == 422
    assert api.get("/api/artifacts/artifact_" + "0" * 64).status_code == 404


def test_html_artifact_is_never_served_as_html(demo):
    from daw.commons.demo import Researcher
    root, ctx = demo
    with Community(root) as board:
        dana = Researcher(board, board.agent(ctx["agents"]["dana"]), root / "demo-harness" / "inputs")
        source = dana.source("page-source.txt", "synthetic page source\n")
        registered = dana.register(ctx["questions"]["dana"], "page.html", "<script>alert(1)</script>",
                                   title="A page", summary="HTML output.", role="figure", parameters={},
                                   inputs=[{"blob": source["blob"], "source_identity": source["asset_revision"]}])
    api = client(root)
    view = api.get(f"/api/artifacts/{registered['artifact']}").json()
    assert view["location"] == {"store": "workspace", "participant": ctx["agents"]["dana"]}
    raw = api.get(f"/api/artifacts/{registered['artifact']}/bytes")
    assert raw.headers["content-type"] == "application/octet-stream" and "attachment" in raw.headers["content-disposition"]


def test_participant_pages_requests_and_running(demo):
    root, ctx = demo
    api = client(root)
    alice = api.get("/api/participants/alice/activity").json()
    assert alice["participant"]["kind"] == "agent" and len(alice["assignments"]) == 2 and len(alice["runs"]) == 2
    assert [f["name"] for f in alice["forks"]] == ["alice-fork"] and alice["open_requests"] == []
    bob = api.get("/api/participants/bob/activity").json()
    assert bob["reuse"]["reused"] == 2 and bob["reuse"]["backed"] == 1 and bob["reuse"]["backed_ratio"] == 0.5
    assert [r["id"] for r in bob["asked"]] == [ctx["requests"]["question"]]
    with Community(root) as board:
        rhea = human(board)
        request = board.ask(ctx["agents"]["dana"], rhea["id"], "Re-run the scoped search next month.")
        with board.writer(), board.db:
            board.db.execute("UPDATE request SET task_type='scouting',budget='{\"minutes\":30}',state='running' WHERE id=?",
                             (request["id"],))
            run = "run_" + uuid.uuid4().hex
            board.db.execute("INSERT INTO attempt VALUES(?,?,?,'running',?,?,NULL)",
                             (run, request["id"], ctx["agents"]["dana"], f"runs/{run}", now()))
        (root / "runs" / run).mkdir()
        (root / "runs" / run / "heartbeat.json").write_text(json.dumps({"observed": now(), "elapsed_seconds": 31.0,
                                                                         "stdout_bytes": 2048, "pid": 1}))
    human_page = api.get("/api/participants/rhea/activity").json()
    assert [r["task_type"] for r in human_page["promotions"]] == ["scouting"]
    assert human_page["promotions"][0]["budget"] == {"minutes": 30} and human_page["reuse"] is None
    dana = api.get("/api/participants/dana/activity").json()
    assert [r["id"] for r in dana["open_requests"]] == [request["id"]]
    assert {r["id"] for r in api.get("/api/requests", params={"task_type": "scouting"}).json()["items"]} == {request["id"]}
    assert ctx["requests"]["question"] in {r["id"] for r in api.get("/api/requests", params={"task_type": "question"}).json()["items"]}
    assert api.get("/api/requests", params={"target": "dana", "state": "completed"}).json()["items"] == []
    [live] = api.get("/api/running").json()["items"]
    assert live["run"] == run and live["agent"] == ctx["agents"]["dana"] and live["task_type"] == "scouting"
    assert live["heartbeat"] == {"observed": live["heartbeat"]["observed"], "elapsed_seconds": 31.0, "stdout_bytes": 2048}


def test_event_stream_backlog_cursor_and_named_messages(demo):
    root, ctx = demo
    api = client(root)
    with Archive(root) as view:
        last = view.sequence()
    text = api.get("/api/events", params={"once": True}).text
    assert text.startswith("retry: 3000") and f"id: {last}\n" in text and "event: published\n" in text
    resumed = api.get("/api/events", params={"once": True, "after": 0}, headers={"Last-Event-ID": str(last - 1)}).text
    assert resumed.count("\nid: ") + resumed.startswith("id: ") == 1 and f"id: {last}\n" in resumed
    unnamed = api.get("/api/events", params={"once": True, "after": last - 1, "named": False}).text
    assert "event:" not in unnamed and '"kind":' in unnamed
    log = api.get("/api/events/log", params={"after": last - 2, "limit": 1}).json()
    assert [e["seq"] for e in log["items"]] == [last - 1] and log["next_after"] == last - 1
    assert api.get("/api/events", params={"once": True}, headers={"Last-Event-ID": "x"}).status_code == 400
    assert cursor_from(5, None) == 5 and cursor_from(5, "9") == 9
    assert frame("delivery_heartbeat", {"run": "r"}).startswith("event: delivery_heartbeat\n")


def test_live_stream_reports_new_events_heartbeats_and_receipts(demo):
    root, ctx = demo
    with Archive(root) as view:
        start = view.sequence()
    with Community(root) as board:
        request = board.ask(ctx["agents"]["dana"], "operator", "A live check.")

    async def collect():
        out = []
        gen = stream(root, start, poll=0.01, keepalive=0.0)
        async for message in gen:
            out.append(message)
            if len(out) == 3:      # retry, question post, question_queued
                with Community(root) as board, board.writer(), board.db:
                    run = "run_" + uuid.uuid4().hex
                    (root / "runs" / run).mkdir()
                    board.db.execute("UPDATE request SET state='running',active_run=? WHERE id=?", (run, request["id"]))
                    board.db.execute("INSERT INTO attempt VALUES(?,?,?,'running',?,?,NULL)",
                                     (run, request["id"], ctx["agents"]["dana"], f"runs/{run}", now()))
                    board.event("delivery_started", {"request": request["id"], "run": run, "agent": ctx["agents"]["dana"]})
                (root / "runs" / run / "execution.json").write_text("{}")
                (root / "runs" / run / "heartbeat.json").write_text('{"elapsed_seconds": 30}')
            if any("run_receipt" in m for m in out) and any("delivery_heartbeat" in m for m in out):
                break
            if len(out) > 40:
                break
        await gen.aclose()
        return out

    messages = asyncio.run(collect())
    started = next(m for m in messages if "event: delivery_started" in m)
    assert started.startswith("id: ")
    beat = next(m for m in messages if "event: delivery_heartbeat" in m)
    receipt = next(m for m in messages if "event: run_receipt" in m)
    assert not beat.startswith("id:") and not receipt.startswith("id:")
    assert json.loads(receipt.split("data: ", 1)[1])["receipt"] == "execution.json"
    assert any(m.startswith(": keepalive") for m in messages)


def test_run_watch_baseline_is_silent_for_existing_runs(demo):
    root, ctx = demo
    with Archive(root) as view:
        watch = RunWatch()
        finished = [r["id"] for r in view.rows("SELECT id FROM attempt")]
        assert watch.poll(view, finished) == []          # completed runs present at connect: baseline only
        assert watch.poll(view) == [] and watch.runs == {}


def test_thread_index_is_cached_by_sequence_and_views_are_read_only(demo):
    root, ctx = demo
    with Archive(root) as view:
        first = views.thread_index(view)
        assert views.thread_index(view) is first
    with Community(root) as board:
        board.ask(ctx["agents"]["bob"], "operator", "Another question.")
    with Archive(root) as view:
        assert views.thread_index(view) is not first and views.thread_index(view)["sequence"] > first["sequence"]
        with pytest.raises(DawError, match="unknown_post"):
            views.post_view(view, "post_nothing")
