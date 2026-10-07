"""Claim ledger, contradiction queue, correction propagation, frontier index and wishlist (offline, demo board)."""
import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from daw.catalog import Workspace
from daw.commons import claims, frontier
from daw.commons.app import create_app
from daw.commons.archive import Archive
from daw.commons.participants import add_participant
from daw.community import Community
from daw.util import DawError, read_json

WRITE = {"X-Colloquy-Request": "1"}
CONFIRM = "/api/frontier/clusters/confirm"


def workspace(board, ctx, name):
    return Workspace(board.trial(board.agent(ctx["agents"][name])) / "workspace")


def test_contradiction_queue_surfaces_the_demo_pair_and_never_resolves_it(demo):
    root, ctx = demo
    client = TestClient(create_app(root, local_user="rhea", static_dir=root / "missing"))
    queue = client.get("/api/claims/contradictions").json()
    assert queue["total"] == 1
    pair = queue["items"][0]
    assert {c["id"] for c in pair["claims"]} == {ctx["claims"]["current"], ctx["claims"]["opposed"]}
    assert pair["shared"] == [{"kind": "accession", "id": "GSE000001"}]
    assert {c["author"] for c in pair["claims"]} == {ctx["agents"]["alice"], ctx["agents"]["bob"]}
    assert pair["scope"]["endpoint"] == "same" and pair["reviews"] == []
    # The withdrawn 1.45 claim cites the same accession and direction but is excluded.
    assert ctx["claims"]["withdrawn"] not in json.dumps(queue)
    # A mark is attribution: the queue still proposes the pair and statuses are unchanged.
    with Community(root) as board, board.writer(), board.db:
        board.db.execute("INSERT INTO mark VALUES('mark_1',?, 'claim', ?, 'disputed', 'checked', '[]', ?, 't')",
                         (ctx["agents"]["dana"], ctx["claims"]["opposed"], "0" * 64))
        board.event("mark_recorded", {"mark": "mark_1"})
    again = client.get("/api/claims/contradictions").json()
    assert again["total"] == 1 and {c["status"] for c in again["items"][0]["claims"]} == {"supported"}
    assert any(m["id"] == "mark_1" for c in again["items"][0]["claims"] for m in c["marks"])


def test_direction_comparison_is_conservative():
    assert claims.opposed("higher in B", "lower in B")
    assert claims.opposed("up", "Down") and claims.opposed("increased", "decreased")
    assert not claims.opposed("higher in B than A", "lower in A than B")
    assert not claims.opposed("not higher in B", "lower in B")
    assert not claims.opposed("increased", "unchanged")
    assert not claims.opposed("elevated", "reduced")  # outside the fixed vocabulary: not opposed
    assert not claims.opposed("higher and lower", "lower")
    assert not claims.opposed(None, "lower")


def test_supersede_withdraws_claims_in_the_projection_only(demo):
    root, ctx = demo
    with Community(root) as board:
        withdrawn = board.one("SELECT * FROM claim WHERE id=?", (ctx["claims"]["withdrawn"],))
        assert withdrawn["status"] == "withdrawn" and withdrawn["withdrawn_by"] == ctx["claims"]["correction"]
        # The immutable claims blob still states what the author published.
        assert read_json(board.library.blob_path(withdrawn["claims_blob"]))["claims"][0]["status"] == "supported"
        shown = board.show(ctx["claims"]["summary"])
        assert {c["status"] for c in shown["claims"]} == {"withdrawn"}
        assert shown["content"]["evidence"]["claims_blob"] == withdrawn["claims_blob"]
        before = board.rows("SELECT * FROM claim ORDER BY id")
        summary = claims.rebuild_claims(board)
        assert summary["changed"] is False and board.rows("SELECT * FROM claim ORDER BY id") == before
        with board.db:
            board.db.execute("DELETE FROM claim")
        assert claims.rebuild_claims(board)["changed"] is True
        assert board.rows("SELECT * FROM claim ORDER BY id") == before
        hits = board.find("donor independence", family="claim")
        assert {h["status"] for h in hits["items"]} == {"withdrawn", "untestable"}
        assert all(h["family"] == "claim" and "post" in h for h in hits["items"])
    client = TestClient(create_app(root, static_dir=root / "missing"))
    shown = client.get(f"/api/claims/{ctx['claims']['withdrawn']}").json()
    assert shown["status"] == "withdrawn" and shown["stated_status"] == "supported"
    assert shown["replacement"] == ctx["claims"]["correction"]
    assert client.get("/api/claims/claim_missing").status_code == 404


def test_affected_readers_receive_idempotent_correction_notices(demo):
    root, ctx = demo
    bob = ctx["agents"]["bob"]
    with Community(root) as board:
        notices = [r for r in board.inbox(bob) if r["task_type"] == "notice"]
        # The core demo correction (finding -> correction) and the claims summary correction both reached bob.
        assert len(notices) == 2
        keys = {board.one("SELECT request_key FROM post WHERE id=?", (r["post"],))["request_key"] for r in notices}
        assert keys == {claims.correction_key(ctx["posts"]["correction"], bob),
                        claims.correction_key(ctx["claims"]["correction"], bob)}
        notice = board.show(next(r["post"] for r in notices if claims.correction_key(ctx["claims"]["correction"], bob)
                                 == board.one("SELECT request_key FROM post WHERE id=?", (r["post"],))["request_key"]))
        evidence = notice["content"]["evidence"]
        assert evidence["superseded"] == ctx["claims"]["summary"] and evidence["replacement"] == ctx["claims"]["correction"]
        assert ctx["claims"]["withdrawn"] in evidence["withdrawn_claims"]
        assert board.agent(notice["author"])["name"] == "corrections"
        # The author is never an affected reader of their own post; re-running sends nothing new.
        again = claims.notify_affected(board, ctx["claims"]["correction"])
        assert [r["id"] for r in again] == [r["id"] for r in notices if r["post"] == notice["id"]]
        assert len([r for r in board.inbox(bob) if r["task_type"] == "notice"]) == 2
    client = TestClient(create_app(root, static_dir=root / "missing"))
    view = client.get(f"/api/corrections/{ctx['claims']['summary']}").json()
    assert [a["reader"] for a in view["affected"]] == [bob]
    assert view["affected"][0]["questions"] == [ctx["questions"]["bob"]] and view["affected"][0]["notices"]
    assert {c["id"] for c in view["withdrawn_claims"]} >= {ctx["claims"]["withdrawn"]}
    unsuperseded = client.get(f"/api/corrections/{ctx['claims']['opposite']}").json()
    assert unsuperseded["affected"] == [] and unsuperseded["superseded_by"] == []


def test_pointer_validation_rejects_invented_records(demo):
    root, ctx = demo
    alice = ctx["agents"]["alice"]
    ws_root = None
    with Community(root) as board:
        ws_root = board.trial(board.agent(alice)) / "workspace"
        posts = board.one("SELECT count(*) AS n FROM post")["n"]
        invented = [
            ({"kind": "artifact", "id": "artifact_" + "e" * 64}, "claim_pointer_unresolved"),
            ({"kind": "post", "id": "post_" + "0" * 32}, "claim_pointer_unresolved"),
            ({"kind": "receipt", "id": "f" * 64}, "claim_pointer_unresolved"),
            ({"kind": "accession", "id": "GSE12X"}, "claim_pointer_unresolved"),
            ({"kind": "accession", "id": "my-dataset"}, "claim_pointer_unresolved"),
            ({"kind": "locator", "id": ctx["artifacts"]["contrast"]}, "claim_pointer_unresolved"),
            ({"kind": "browser", "id": "x"}, "invalid_claims"),
        ]
        for pointer, reason in invented:
            with pytest.raises(DawError, match=reason):
                board.publish(alice, "Claims", "Body.", workspace=ws_root,
                              claims=[{"text": "A claim.", "status": "supported", "pointers": [pointer]}])
        with pytest.raises(DawError, match="claim_pointer_required"):
            board.publish(alice, "Claims", "Body.", claims=[{"text": "No pointer.", "status": "descriptive"}])
        with pytest.raises(DawError, match="invalid_claims"):
            board.publish(alice, "Claims", "Body.", claims=[{"text": "x", "status": "proven", "pointers": []}])
        with pytest.raises(DawError, match="invalid_claims"):
            board.publish(alice, "Claims", "Body.", claims=[{"text": "x", "status": "untestable", "scope": {"gene": "X"}}])
        assert board.one("SELECT count(*) AS n FROM post")["n"] == posts
        # Real records pass: a library artifact not in this post's evidence, a post, a library blob, a locator.
        note = board.show(ctx["posts"]["finding"])
        published = board.publish(alice, "Claims with real pointers", "Body.", claims=[
            {"text": "Untestable without donor identity.", "status": "untestable"},
            {"text": "Normalized contrast is 1.31.", "status": "supported", "pointers": [
                {"kind": "artifact", "id": ctx["artifacts"]["normalized"]}, {"kind": "post", "id": ctx["posts"]["reply"]},
                {"kind": "receipt", "id": note["body_blob"]},
                {"kind": "locator", "id": ctx["artifacts"]["normalized"], "locator": "row B_vs_A"}]}])
        assert [c["status"] for c in published["claims"]] == ["untestable", "supported"]
    # Frontier pointers resolve in the author's own workspace.
    with Community(root) as board:
        ws = workspace(board, ctx, "dana")
        try:
            with ws.writer(), pytest.raises(DawError, match="frontier_pointer_unresolved"):
                frontier.record_item(ws, ctx["questions"]["dana"], kind="next_step", text="Use it.",
                                     pointers=[f"artifact:{ctx['artifacts']['contrast']}"])  # not in dana's workspace
        finally:
            ws.close()


def recorded_tick(board, start):
    """Run due watchers against the recorded (synthetic) Europe PMC response: one new accession."""
    from daw.commons.discovery_demo import recorded_transport
    from daw.commons.watchers import open_workspace, tick
    scratch = open_workspace(board.root)
    (scratch.root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0\n")
    scratch.close()
    return tick(board, now=start, transport=recorded_transport())


def projection(board):
    return board.rows("SELECT * FROM frontier_item ORDER BY id")


def test_frontier_rebuild_is_idempotent_and_derives_board_state_from_events(demo):
    """v2 C3: promotion, watcher and candidate-evidence state come from board events, never from the row alone."""
    import time

    from daw.commons import participation
    from daw.commons.watchers import add_watcher, disable_watcher
    root, ctx = demo
    items = ctx["frontier"]["items"]
    with Community(root) as board:
        events = board.one("SELECT count(*) AS n FROM event")["n"]
        first = frontier.rebuild_frontier(board)
        assert first["inserted"] == first["updated"] == first["deleted"] == 0 and first["items"] == 6
        assert board.one("SELECT count(*) AS n FROM event")["n"] == events  # nothing changed: no event
        rows = {r["id"]: r for r in board.rows("SELECT * FROM frontier_item")}
        assert rows[items["bob-spikein"]]["status"] == "closed"
        gap = frontier.item_id(ctx["agents"]["dana"], ctx["gap_event"])
        assert rows[gap]["kind"] == "gap" and rows[gap]["text"] == "Per-sample counts after marker knockdown"
        # Board-owned state is written only through events: a person's promotion and a watcher's hit.
        qpcr, donors, untestable = items["alice-qpcr"], items["alice-donors"], items["dana-untestable"]
        rhea = add_participant(board, "rhea", "human")["id"]
        promoted = participation.promote(board, rhea, "frontier_item", qpcr, "research", ctx["agents"]["alice"],
                                         {"minutes": 30})
        row = board.one("SELECT * FROM frontier_item WHERE id=?", (qpcr,))
        assert row["status"] == "promoted" and row["promoted_to"] == promoted["id"]
        assert json.loads(row["source"])["promotion"]["request"] == promoted["id"]
        watcher = add_watcher(board, rhea, untestable, {"query": "demo marker knockdown"}, "europepmc")
        masked = json.loads(board.one("SELECT watcher_query FROM frontier_item WHERE id=?", (untestable,))["watcher_query"])
        assert masked["watcher"] == watcher["id"]
        ran = recorded_tick(board, time.time() + 1)
        assert any(r.get("watcher") == watcher["id"] and r["new"] for r in ran["ran"])
        row = board.one("SELECT * FROM frontier_item WHERE id=?", (untestable,))
        assert row["status"] == "candidate_evidence"
        candidate = json.loads(row["source"])
        assert candidate["candidate_source"] == "watcher" and candidate["candidate"]["watcher"] == watcher["id"]
        assert candidate["candidate"]["accessions"] == ["DEMO0001"]
        # Disabling the board watcher unmasks the author's own query (none here); the candidate status stays.
        disable_watcher(board, rhea, watcher["id"])
        row = board.one("SELECT * FROM frontier_item WHERE id=?", (untestable,))
        assert row["watcher_query"] is None and row["status"] == "candidate_evidence"
        # A row edited outside the event path is put back; a row no record supports is deleted.
        with board.writer(), board.db:
            board.db.execute("UPDATE frontier_item SET status='open',promoted_to=NULL WHERE id=?", (qpcr,))
            board.db.execute("INSERT INTO frontier_item(id,question,author,workspace,kind,text,status,blocked_by,"
                             "watcher_query,pointers,source,created,updated,promoted_to) VALUES('frontier_orphan',"
                             "'q_0000000000000000',?,NULL,'gap','x','open',NULL,NULL,'[]','{}','t','t',NULL)",
                             (ctx["agents"]["dana"],))
        repaired = frontier.rebuild_frontier(board)
        assert repaired["updated"] == 1 and repaired["deleted"] == 1 and repaired["orphaned"] == ["frontier_orphan"]
        row = board.one("SELECT * FROM frontier_item WHERE id=?", (qpcr,))
        assert row["status"] == "promoted" and row["promoted_to"] == promoted["id"]
        # The agent's closed/withdrawn status wins over promotion; promoted_to stays as the board's record.
        ws = workspace(board, ctx, "alice")
        try:
            with ws.writer():
                frontier.record_status(ws, ctx["questions"]["alice"], ctx["frontier"]["events"]["alice-qpcr"], "withdrawn",
                                       "Superseded by a better-posed experiment.")
                frontier.record_status(ws, ctx["questions"]["alice"], ctx["frontier"]["events"]["alice-donors"],
                                       "candidate_evidence", "A donor table may exist.")
            with ws.writer(), pytest.raises(DawError, match="invalid_frontier_status"):
                frontier.record_status(ws, ctx["questions"]["alice"], ctx["frontier"]["events"]["alice-donors"],
                                       "promoted", "agents cannot promote")
        finally:
            ws.close()
        result = frontier.rebuild_frontier(board)
        assert result["updated"] == 2
        row = board.one("SELECT * FROM frontier_item WHERE id=?", (qpcr,))
        assert row["status"] == "withdrawn" and row["promoted_to"] == promoted["id"]
        row = board.one("SELECT * FROM frontier_item WHERE id=?", (donors,))
        assert row["status"] == "candidate_evidence" and json.loads(row["source"])["candidate_source"] == "author"
        assert frontier.rebuild_frontier(board)["updated"] == 0
        # Gap withdrawal makes the gap item withdrawn.
        ws = workspace(board, ctx, "dana")
        try:
            with ws.writer():
                from daw.work import record_event
                record_event(ws, ctx["questions"]["dana"], "retrieval_gap_withdrawal",
                             {"event": ctx["gap_event"], "reason": "A dataset was found."})
        finally:
            ws.close()
        frontier.rebuild_frontier(board)
        assert board.one("SELECT status FROM frontier_item WHERE id=?", (gap,))["status"] == "withdrawn"
        # Dropping the projection and rebuilding from events and workspaces reproduces it byte for byte.
        before = projection(board)
        with board.writer(), board.db:
            board.db.execute("DELETE FROM frontier_item")
        rebuilt = frontier.rebuild_frontier(board)
        assert rebuilt["inserted"] == len(before) and projection(board) == before


def test_frontier_projection_rebuilds_byte_equal_on_the_cohort(cohort_copy):
    """v2 C3 on real data: drop the cohort board's frontier_item table, rebuild, compare every row."""
    with Community(cohort_copy) as board:
        assert frontier.is_current(board)  # the committed (resettled) projection: current before any rebuild
        assert frontier.rebuild_frontier(board)["inserted"] == 0
        before = projection(board)
        assert len(before) >= 59
        assert {r["kind"] for r in before} >= {"gap"}
        with board.writer(), board.db:
            board.db.execute("DELETE FROM frontier_item")
        rebuilt = frontier.rebuild_frontier(board)
        assert rebuilt["inserted"] == len(before) and rebuilt["deleted"] == 0
        assert projection(board) == before


def test_fork_inherits_items_without_duplicating_them(demo):
    root, ctx = demo
    from daw.commons.demo import scripted_runtime
    from daw.community_runtime import fork_agent
    with Community(root) as board, scripted_runtime(root):
        fork = fork_agent(board, "alice", "alice-second")
        summary = frontier.rebuild_frontier(board)
        assert summary["inherited_skipped"] >= 2 and summary["items"] == 6
        assert not board.rows("SELECT id FROM frontier_item WHERE author=?", (fork["id"],))


def test_clusters_are_exact_term_suggestions_confirmed_only_by_people(demo):
    root, ctx = demo
    items = ctx["frontier"]["items"]
    client = TestClient(create_app(root, local_user="rhea", static_dir=root / "missing"))
    clusters = client.get("/api/frontier/clusters").json()["items"]
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster["items"] == sorted([items["alice-qpcr"], items["bob-qpcr"]])
    assert {"qpcr", "donor", "matched", "marker"} <= set(cluster["shared_terms"])
    assert cluster["pairs"][0]["jaccard"] >= frontier.CLUSTER_THRESHOLD and cluster["confirmations"] == []
    # The confirmation is an HTTP write like any other: Actor discipline, CSRF header required (v2 C3).
    assert client.post(CONFIRM, json={"items": cluster["items"]}).status_code == 403
    confirmed = client.post(CONFIRM, headers=WRITE, json={"items": cluster["items"], "note": "same qPCR design"})
    assert confirmed.status_code == 200 and confirmed.json()["participant"].startswith("human_")
    cluster = client.get("/api/frontier/clusters").json()["items"][0]
    assert cluster["confirmations"][0]["note"] == "same qPCR design"
    # Items are not merged: both remain separate frontier items.
    assert {items["alice-qpcr"], items["bob-qpcr"]} <= {i["id"] for i in client.get("/api/frontier").json()["items"]}
    bad = client.post(CONFIRM, headers=WRITE, json={"items": [items["alice-qpcr"], items["alice-donors"]]})
    assert bad.status_code == 400 and bad.json()["error"] == "invalid_cluster"
    assert client.post(CONFIRM, headers=WRITE, json={"items": [items["alice-qpcr"], "frontier_x"]}).status_code == 404
    with Community(root) as board, pytest.raises(DawError, match="permission_denied"):
        frontier.confirm_cluster(board, ctx["agents"]["bob"], cluster["items"])
    # Unrelated wording does not cluster.
    assert frontier.clusters([
        {"id": "a", "kind": "proposed_experiment", "question": "q1", "status": "open", "text": "Measure marker by qPCR"},
        {"id": "b", "kind": "proposed_experiment", "question": "q2", "status": "open", "text": "Sequence knockdown cells"},
        {"id": "c", "kind": "proposed_experiment", "question": "q1", "status": "open", "text": "Measure marker by qPCR"},
    ]) == []


def test_frontier_browser_groups_filters_and_refreshes_on_the_write_path(demo):
    root, ctx = demo
    items = ctx["frontier"]["items"]
    client = TestClient(create_app(root, static_dir=root / "missing"))
    view = client.get("/api/frontier").json()
    assert view["by_kind"]["proposed_experiment"] == [items["alice-qpcr"], items["bob-qpcr"]]
    assert items["bob-spikein"] in view["by_kind"]["open_question"]  # closed items stay listed with their status
    blockers = {b["blocked_by"]: b["items"] for b in view["by_blocker"]}
    assert blockers["donor identity per sample"] == [items["alice-donors"]]
    by_id = {i["id"]: i for i in view["items"]}
    assert by_id[items["bob-qpcr"]]["watcher_query"] == {"provider": "geo", "text": "demo marker spike-in qPCR"}
    assert by_id[items["bob-qpcr"]]["watch"] == {"watchers": [], "runs": 0, "found": 0, "last_run": None}
    assert by_id[items["alice-qpcr"]]["question_title"].startswith("Does the demo marker")
    assert all(i["content_is_untrusted_data"] for i in view["items"])
    assert {i["id"] for i in client.get("/api/frontier", params={"status": "closed"}).json()["items"]} == {items["bob-spikein"]}
    assert client.get("/api/frontier", params={"author": "dana", "kind": "untestable"}).json()["total"] == 1
    assert client.get("/api/frontier", params={"blocked_by": "DONOR identity"}).json()["total"] == 1
    assert client.get("/api/frontier", params={"kind": "wish"}).status_code == 400
    # A new workspace event is not indexed by a read (reads never write, v2 C3): the GET says the projection is
    # behind; the next publication from that question (the write path) indexes it.
    assert view["projection_current"] is True
    with Community(root) as board:
        ws = workspace(board, ctx, "dana")
        try:
            with ws.writer():
                event = frontier.record_item(ws, ctx["questions"]["dana"], kind="next_step", text="Search ArrayExpress.",
                                             key="k1")
                assert frontier.record_item(ws, ctx["questions"]["dana"], kind="next_step", text="Search ArrayExpress.",
                                            key="k1")["id"] == event["id"]
                with pytest.raises(DawError, match="frontier_key_conflict"):
                    frontier.record_item(ws, ctx["questions"]["dana"], kind="next_step", text="Other.", key="k1")
        finally:
            ws.close()
    new = frontier.item_id(ctx["agents"]["dana"], event["id"])
    sequence = client.get("/api/health").json().get("sequence")
    stale = client.get("/api/frontier").json()
    assert new not in {i["id"] for i in stale["items"]} and stale["projection_current"] is False
    assert client.get(f"/api/frontier/{new}").status_code == 404
    assert client.get("/api/health").json().get("sequence") == sequence  # the reads appended nothing
    with Community(root) as board:
        board.publish(ctx["agents"]["dana"], "Next step", "Searching ArrayExpress next.",
                      workspace=board.trial(board.agent(ctx["agents"]["dana"])) / "workspace",
                      question=ctx["questions"]["dana"])
    fresh = client.get("/api/frontier").json()
    assert new in {i["id"] for i in fresh["items"]} and fresh["projection_current"] is True
    single = client.get(f"/api/frontier/{new}").json()
    assert single["kind"] == "next_step" and single["source"]["event"] == event["id"]
    hits = Archive(root)
    try:
        from daw.search import search
        assert any(h["subject"] == new for h in search(hits.library, "ArrayExpress", family="frontier")["items"])
    finally:
        hits.close()


def test_wishlist_groups_exact_missing_measurements_by_question(demo):
    root, ctx = demo
    client = TestClient(create_app(root, static_dir=root / "missing"))
    wishlist = client.get("/api/wishlist").json()
    groups = {g["normalized"]: g for g in wishlist["items"]}
    donors = groups["donor identity per sample"]
    assert donors["distinct_questions"] == 2
    assert {q["question"] for q in donors["questions"]} == {ctx["questions"]["alice"], ctx["questions"]["bob"]}
    knockdown = groups["per-sample counts after marker knockdown"]
    assert knockdown["distinct_questions"] == 1 and {s["kind"] for s in knockdown["sources"]} == {"gap", "labbook"}
    assert wishlist["items"][0]["normalized"] == "donor identity per sample"  # most-needed first
    assert "no synonym merging" in wishlist["grouping"]


def test_claim_search_filters_and_agent_cli(demo, tmp_path):
    root, ctx = demo
    client = TestClient(create_app(root, static_dir=root / "missing"))
    found = client.get("/api/claims", params={"q": "donor", "status": "untestable"}).json()
    assert found["total"] == 1 and found["items"][0]["post"] == ctx["claims"]["correction"]
    assert client.get("/api/claims", params={"scope": "series GSE000001", "status": "supported"}).json()["total"] == 2
    assert client.get("/api/claims", params={"author": "bob"}).json()["total"] == 1
    assert client.get("/api/claims", params={"post": ctx["claims"]["summary"]}).json()["total"] == 3
    assert client.get("/api/claims", params={"status": "proven"}).status_code == 400
    item = client.get("/api/claims", params={"post": ctx["claims"]["opposite"]}).json()["items"][0]
    assert {p["kind"]: p.get("present") for p in item["pointers"]} == {"accession": None, "artifact": True}

    from daw.bio_cli import app as bio
    runner = CliRunner()
    with Community(root) as board:
        dana = board.agent(ctx["agents"]["dana"])
        ws_root = board.trial(dana) / "workspace"
    env = {"BIO_COMMUNITY": str(root), "BIO_WORKSPACE": str(ws_root), "BIO_AGENT": dana["id"]}
    recorded = runner.invoke(bio, ["work", "frontier", ctx["questions"]["dana"], "--kind", "proposed_experiment",
                                   "--text", "Knock down the marker and count per sample.",
                                   "--missing-measurement", "Per-sample counts after marker knockdown",
                                   "--pointer", "accession:GSE000001", "--watcher-query", '{"text": "knockdown"}'], env=env)
    assert recorded.exit_code == 0, recorded.output
    event = json.loads(recorded.output)["id"]
    status = runner.invoke(bio, ["work", "frontier-status", ctx["questions"]["dana"], event, "--status", "closed",
                                 "--reason", "Out of scope."], env=env)
    assert status.exit_code == 0, status.output
    listed = json.loads(runner.invoke(bio, ["work", "frontier-items", "--question", ctx["questions"]["dana"]], env=env).output)
    assert {i["event"]: i["status"] for i in listed["items"]}[event] == "closed"
    body = tmp_path / "post.md"
    body.write_text("Knockdown counts are still missing.")
    spec = tmp_path / "claims.json"
    spec.write_text(json.dumps([{"text": "No knockdown series is indexed.", "status": "descriptive",
                                 "pointers": [{"kind": "post", "id": ctx["posts"]["gap"]}]}]))
    items = tmp_path / "items.json"
    items.write_text(json.dumps([{"kind": "open_question", "text": "Would a CRISPRi screen include the marker?"}]))
    published = runner.invoke(bio, ["community", "publish", "Knockdown status", "--body", str(body), "--question",
                                    ctx["questions"]["dana"], "--claims", str(spec), "--frontier", str(items),
                                    "--key", "dana-cli"], env=env)
    assert published.exit_code == 0, published.output
    post = json.loads(published.output)
    assert post["claims"][0]["status"] == "descriptive" and len(post["content"]["evidence"]["frontier"]) == 1
    listed = json.loads(runner.invoke(bio, ["community", "claims", "--post", post["id"]], env=env).output)
    assert listed["total"] == 1
    # The publication indexed the new items on the write path; the operator rebuild (and its alias) find nothing new.
    with Archive(root) as view:
        indexed = {r["source"] for r in view.rows("SELECT source FROM frontier_item WHERE author=?",
                                                  (ctx["agents"]["dana"],))}
    assert any(event in source for source in indexed)
    for command in ("rebuild", "reindex"):
        rebuilt = runner.invoke(bio, ["commons", "--root", str(root), "frontier", command])
        assert rebuilt.exit_code == 0, rebuilt.output
        assert json.loads(rebuilt.output)["inserted"] == json.loads(rebuilt.output)["updated"] == 0
    assert json.loads(runner.invoke(bio, ["commons", "--root", str(root), "claims", "reindex"]).output)["changed"] is False


def test_human_posts_cannot_launder_claim_pointers(demo):
    root, ctx = demo
    with Community(root) as board:
        rhea = add_participant(board, "rhea", "human")
        with pytest.raises(DawError, match="claim_pointer_unresolved"):
            board.publish(rhea["id"], "Note", "Body.", claims=[{"text": "x", "status": "supported",
                                                                "pointers": [{"kind": "artifact", "id": "artifact_" + "1" * 64}]}])
