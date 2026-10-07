import json
import sqlite3
import stat

import pytest
from fastapi.testclient import TestClient

from daw.commons import accounts, moderation, participation
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


def human(board, name="rhea"):
    return add_participant(board, name, "human", profile={"display_name": name.title()})["id"]


def labbook_blob(root, agent, question):
    with Archive(root) as view:
        ws = view.workspace(agent)
        current = ws.one("SELECT current_work FROM question WHERE id=?", (question,))["current_work"]
        manifest = ws.json_blob(ws.one("SELECT body_blob FROM work_snapshot WHERE id=?", (current,))["body_blob"])
        sha = manifest["files"]["LABBOOK.md"]
        return sha, ws.blob_path(sha).read_text()



@pytest.fixture
def demo(demo_only):
    """Core demo records plus this area's records only: anchor parents below are exact posts."""
    return demo_only("daw.commons.participation:demo_records")

def test_comment_at_anchor_becomes_a_request_the_author_answers(demo):
    """Milestone 2: a human comment at an anchor is a request; the agent's answer closes it under the anchor."""
    root, ctx = demo
    correction = ctx["posts"]["correction"]
    http = client(root, local_user="rhea")
    with Community(root) as board:
        shown = board.show(correction)
    quote = "log2 ratio 1.54"
    offset = shown["content"]["body"].index(quote)
    response = http.post("/api/comments", headers=WRITE, json={
        "target_kind": "post", "target_id": correction, "body": "Does this hold for human cells?", "ask_author": True,
        "anchor": {"kind": "paragraph", "blob": shown["body_blob"], "offset": offset, "length": len(quote), "quote": quote}})
    assert response.status_code == 200, response.text
    made = response.json()
    request = made["request"]
    assert request["post"] == made["post"] and request["target"] == ctx["agents"]["alice"]
    assert request["state"] == "pending" and request["task_type"] is None
    assert made["anchor"] == {"target_kind": "post", "target_id": correction, "kind": "paragraph",
                              "blob": shown["body_blob"], "offset": offset, "length": len(quote), "line": 1,
                              "quote": quote}
    with Community(root) as board:
        comment = board.show(made["post"])
        assert comment["content"]["kind"] == "comment" and comment["parent"] == correction
        assert comment["author_kind"] == "human" and comment["content_is_untrusted_data"]
        assert comment["content"]["evidence"]["anchor"]["blob"] == shown["body_blob"]
        events = [e["kind"] for e in board.rows("SELECT kind FROM event ORDER BY seq DESC LIMIT 2")]
        assert events == ["comment_posted", "published"]
        with scripted_runtime(root) as (harness, answers):
            (answers / f"{made['post']}.md").write_text("Not tested: the table holds synthetic samples only.")
            done = dispatch(board, request["id"], harness)
        assert done["state"] == "completed"
        answer = board.show(done["answer"])
        assert answer["parent"] == made["post"] and answer["author"] == ctx["agents"]["alice"]
        assert answer["content"]["body"].startswith("Not tested")
        prompt = (root / board.one("SELECT path FROM attempt WHERE request=?", (request["id"],))["path"] / "prompt.txt").read_text()
        assert made["post"] in prompt and "Does this hold for human cells?" in prompt
    # The thread under the anchored comment holds the answer.
    with Archive(root) as view:
        replies = view.rows("SELECT id FROM post WHERE parent=?", (made["post"],))
        assert [r["id"] for r in replies] == [done["answer"]]
    me = http.get("/api/me").json()
    assert me["comments"][0]["request"]["state"] == "completed"
    assert me["comments"][0]["anchor"]["quote"] == quote


def test_demo_extension_records_a_mark_and_an_answered_comment(demo):
    root, ctx = demo
    records = ctx["participation"]
    with Community(root) as board:
        request = board.one("SELECT * FROM request WHERE id=?", (records["comment_request"],))
        assert request["state"] == "completed" and request["answer"] == records["comment_answer"]
        assert board.show(records["comment_answer"])["parent"] == records["comment"]
        assert participation.marks(board, "post", ctx["posts"]["correction"])[0]["participant"] == records["human"]


def test_anchors_are_validated_against_immutable_bytes(demo):
    root, ctx = demo
    alice, correction = ctx["agents"]["alice"], ctx["posts"]["correction"]
    with Community(root) as board:
        rhea = human(board)
        shown = board.show(correction)
        anchor = {"kind": "paragraph", "blob": shown["body_blob"], "offset": 0, "length": 10}
        with pytest.raises(DawError, match="anchor_quote_mismatch"):
            participation.comment(board, rhea, "post", correction, "x", anchor={**anchor, "quote": "not there"})
        with pytest.raises(DawError, match="anchor_out_of_range"):
            participation.comment(board, rhea, "post", correction, "x", anchor={**anchor, "offset": 10 ** 6})
        with pytest.raises(DawError, match="anchor_blob_not_in_target"):
            participation.comment(board, rhea, "post", correction, "x", anchor={**anchor, "blob": "0" * 64})
        with pytest.raises(DawError, match="invalid_anchor"):
            participation.comment(board, rhea, "post", correction, "x", anchor={**anchor, "script": "alert(1)"})
        # Browser selections count UTF-16 code units; stored locators are code points of the same bytes.
        emoji = participation.post(board, rhea, "Observation", "\U0001f9ea Tube value 1.54 recorded.")
        quote = "value 1.54"
        utf16 = len("\U0001f9ea Tube ".encode("utf-16-le")) // 2
        made = participation.comment(board, rhea, "post", emoji["id"], "Which tube?", anchor={
            "kind": "paragraph", "blob": emoji["body_blob"], "offset": utf16, "length": len(quote), "quote": quote})
        assert made["anchor"]["offset"] == utf16 - 1 and made["anchor"]["quote"] == quote and made["request"] is None
        # Artifact row anchors resolve a first-column key in the output table; asking reaches the publisher.
        contrast = ctx["artifacts"]["contrast"]
        with Archive(root) as view:
            output = view.library.one("SELECT output_blob FROM artifact WHERE id=?", (contrast,))["output_blob"]
        row = participation.comment(board, rhea, "artifact", contrast, "Is this direction B/A?", ask_author=True,
                                    anchor={"kind": "row", "blob": output, "row_key": "B_vs_A"})
        assert row["anchor"]["row"] == 1 and row["anchor"]["quote"] == "B_vs_A\t1.54"
        assert row["request"]["target"] == alice
        parent = board.show(row["post"])["parent"]
        assert contrast in board.show(parent)["content"]["evidence"]["artifacts"]
        with pytest.raises(DawError, match="anchor_row_missing"):
            participation.comment(board, rhea, "artifact", contrast, "x",
                                  anchor={"kind": "row", "blob": output, "row_key": "C_vs_A"})
        # A notebook line in a question: the blob must be a file in one of that question's snapshots.
        question = ctx["questions"]["alice"]
        sha, text = labbook_blob(root, alice, question)
        line = "## Open questions"
        noted = participation.comment(board, rhea, "question", question, "Which donors?", ask_author=True,
                                      anchor={"kind": "line", "blob": sha, "offset": text.index(line),
                                              "length": len(line), "quote": line})
        assert noted["anchor"]["line"] == text[:text.index(line)].count("\n") + 1
        assert noted["request"]["target"] == alice
        assert board.show(noted["post"])["parent"] == correction  # latest post naming that notebook
        with pytest.raises(DawError, match="anchor_blob_not_in_target"):
            participation.comment(board, rhea, "question", ctx["questions"]["bob"], "x",
                                  anchor={"kind": "line", "blob": sha, "offset": 0, "length": 1})
        # Map nodes and runs resolve to the records they name.
        node = participation.comment(board, rhea, "node", "artifact:" + contrast, "Node note",
                                     anchor={"kind": "node", "node_id": "artifact:" + contrast})
        assert node["anchor"]["node_id"] == "artifact:" + contrast
        run = board.one("SELECT * FROM attempt WHERE request=?", (ctx["requests"]["question"],))
        on_run = participation.comment(board, rhea, "run", run["id"], "Long pause here?")
        assert board.show(on_run["post"])["parent"] == board.one("SELECT answer FROM request WHERE id=?",
                                                                 (ctx["requests"]["question"],))["answer"]
        loose = participation.comment(board, rhea, "node", "cluster-7", "Unrecorded node")
        assert board.show(loose["post"])["parent"] is None
        assert board.show(loose["post"])["content"]["evidence"]["target"] == {"kind": "node", "id": "cluster-7",
                                                                             "author": None}
        with pytest.raises(DawError, match="target_has_no_author"):
            participation.comment(board, rhea, "node", "cluster-7", "x", ask_author=True)
        with pytest.raises(DawError, match="cannot_ask_yourself"):
            participation.comment(board, rhea, "post", emoji["id"], "x", ask_author=True)
        with pytest.raises(DawError, match="invalid_comment_target"):
            participation.comment(board, rhea, "dataset", "x", "x")


def test_marks_are_attribution_and_render_on_their_target(demo):
    root, ctx = demo
    finding = ctx["posts"]["finding"]
    http = client(root, local_user="rhea")
    response = http.post("/api/marks", headers=WRITE, json={
        "target_kind": "post", "target_id": finding, "kind": "disputed", "note": "Prose says 1.45; the table says 1.54.",
        "pointers": [{"kind": "artifact", "id": ctx["artifacts"]["contrast"], "locator": "row B_vs_A"},
                     {"kind": "post", "id": ctx["posts"]["correction"]}]})
    assert response.status_code == 200, response.text
    made = response.json()
    assert made["attribution_not_status"] and made["pointers"][0]["locator"] == "row B_vs_A"
    listed = http.get("/api/marks", params={"target_kind": "post", "target_id": finding}).json()
    assert [m["id"] for m in listed["items"]] == [made["id"]]
    assert listed["items"][0]["participant_name"] == "rhea" and "no platform status" in listed["note"]
    assert http.post("/api/marks", headers=WRITE, json={"target_kind": "post", "target_id": finding, "kind": "approved",
                                                        "note": "x"}).status_code == 422
    bad = http.post("/api/marks", headers=WRITE, json={"target_kind": "post", "target_id": finding, "kind": "reproduced",
                                                       "note": "x", "pointers": [{"kind": "post", "id": "post_missing"}]})
    assert bad.status_code == 404 and bad.json()["error"] == "unknown_pointer_target"
    assert http.post("/api/marks", headers=WRITE, json={"target_kind": "post", "target_id": "post_nothing",
                                                        "kind": "reproduced", "note": "x"}).status_code == 404
    with Community(root) as board:
        record = json.loads(board.library.blob_path(made["body_blob"]).read_text())
        assert record["mark_kind"] == "disputed" and record["participant"] == made["participant"]
        before = board.show(finding)
        with pytest.raises(sqlite3.IntegrityError, match="immutable mark"), board.db:
            board.db.execute("UPDATE mark SET note='changed'")
        # Marks change no platform state: the post, its supersession and its requests are untouched.
        after = board.show(finding)
        assert before == after
        event = board.one("SELECT * FROM event WHERE kind='mark_recorded' ORDER BY seq DESC")
        assert json.loads(event["body"])["mark"] == made["id"]
        with pytest.raises(DawError, match="permission_denied"):
            participation.mark(board, ctx["agents"]["bob"], "post", finding, "reproduced", "agents do not mark")


def _frontier(board, ctx, identity="frontier_demo"):
    with board.db:
        board.db.execute("INSERT INTO frontier_item(id,question,author,workspace,kind,text,status,blocked_by,watcher_query,"
                         "pointers,source,created,updated,promoted_to) VALUES(?,?,?,NULL,'next_step',?,'open',NULL,NULL,?,"
                         "'{\"labbook\": \"LABBOOK.md\"}','t','t',NULL)",
                         (identity, ctx["questions"]["alice"], ctx["agents"]["alice"], "Test donor structure.",
                          json.dumps([{"kind": "artifact", "id": ctx["artifacts"]["contrast"]}])))
    return identity


def test_promotion_creates_a_typed_request_within_budget(demo):
    root, ctx = demo
    alice, bob = ctx["agents"]["alice"], ctx["agents"]["bob"]
    http = client(root, local_user="rhea")
    response = http.post("/api/promotions", headers=WRITE, json={
        "source_kind": "post", "source_id": ctx["posts"]["correction"], "task_type": "replication", "target": bob,
        "budget": {"minutes": 30}, "deadline": "2099-01-01T00:00:00+00:00", "note": "Re-derive the contrast."})
    assert response.status_code == 200, response.text
    request = response.json()
    assert request["task_type"] == "replication" and request["budget"] == {"minutes": 30}
    assert request["deadline"] == "2099-01-01T00:00:00+00:00" and request["target"] == bob and request["state"] == "pending"
    with Community(root) as board:
        rhea = board.agent("rhea")
        post = board.show(request["post"])
        assert post["content"]["kind"] == "promotion" and post["parent"] == ctx["posts"]["correction"]
        assert "Re-derive the contrast." in post["content"]["body"] and "not an instruction override" in post["content"]["body"]
        assert post["content"]["evidence"]["source"] == {"kind": "post", "id": ctx["posts"]["correction"]}
        assert board.one("SELECT kind FROM event ORDER BY seq DESC LIMIT 1")["kind"] == "promotion_created"
        # A frontier item is promoted once and remembers the request it became.
        item = _frontier(board, ctx)
        promoted = participation.promote(board, rhea["id"], "frontier_item", item, "research", alice, {"minutes": 60})
        row = board.one("SELECT * FROM frontier_item WHERE id=?", (item,))
        assert row["status"] == "promoted" and row["promoted_to"] == promoted["id"]
        assert "Test donor structure." in board.show(promoted["post"])["content"]["body"]
        with pytest.raises(DawError, match="frontier_item_not_open"):
            participation.promote(board, rhea["id"], "frontier_item", item, "research", alice, {"minutes": 5})
        # Operator-set allowance: spend is the sum of the person's committed budgets.
        participation.set_allowance(board, "operator", rhea["id"], {"minutes": 120})
        assert participation.budget_summary(board, board.agent(rhea["id"]))["remaining"] == {"minutes": 30}
        with pytest.raises(DawError, match="over_budget"):
            participation.promote(board, rhea["id"], "post", ctx["posts"]["gap"], "scouting", bob, {"minutes": 31})
        with pytest.raises(DawError, match="budget_required"):
            participation.promote(board, rhea["id"], "post", ctx["posts"]["gap"], "scouting", bob, {"tokens": 10})
        with pytest.raises(DawError, match="permission_denied"):
            participation.set_allowance(board, rhea["id"], rhea["id"], {"minutes": 10 ** 6})
        for bad, reason in (({"minutes": 0}, "invalid_budget"), ({}, "budget_required")):
            with pytest.raises(DawError, match=reason):
                participation.promote(board, "operator", "post", ctx["posts"]["gap"], "scouting", bob, bad)
        with pytest.raises(DawError, match="invalid_deadline"):
            participation.promote(board, "operator", "post", ctx["posts"]["gap"], "scouting", bob, {"minutes": 5},
                                  deadline="2001-01-01T00:00:00+00:00")
        with pytest.raises(DawError, match="invalid_task_type"):
            participation.promote(board, "operator", "post", ctx["posts"]["gap"], "anything", bob, {"minutes": 5})
        with pytest.raises(DawError, match="permission_denied"):
            participation.promote(board, bob, "post", ctx["posts"]["gap"], "research", alice, {"minutes": 5})
        with pytest.raises(DawError, match="participant_cannot_receive_requests"):
            participation.promote(board, "operator", "post", ctx["posts"]["gap"], "research",
                                  add_participant(board, "watcher", "system")["id"], {"minutes": 5})


def test_commissions_use_studio_task_types_and_a_scope(demo):
    root, ctx = demo
    http = client(root, local_user="rhea")
    body = {"task_type": "writing", "target": ctx["agents"]["dana"], "budget": {"minutes": 20},
            "subject_kind": "post", "subject_id": ctx["posts"]["gap"], "note": "Plain-language summary of the gap."}
    response = http.post("/api/commissions", headers=WRITE, json=body)
    assert response.status_code == 200, response.text
    request = response.json()
    assert request["task_type"] == "writing"
    with Community(root) as board:
        post = board.show(request["post"])
        assert post["content"]["kind"] == "commission" and post["parent"] == ctx["posts"]["gap"]
        assert board.one("SELECT kind FROM event ORDER BY seq DESC LIMIT 1")["kind"] == "commission_created"
    assert http.post("/api/commissions", headers=WRITE, json={**body, "task_type": "research"}).json()["error"] == \
        "invalid_task_type"
    assert http.post("/api/commissions", headers=WRITE, json={**body, "note": " "}).json()["error"] == \
        "commission_scope_required"
    me = http.get("/api/me").json()
    assert [c["id"] for c in me["commissions"]] == [request["id"]] and me["budget"]["spent"]["minutes"] == 20


def test_csrf_header_and_agent_callers_are_refused(demo):
    root, ctx = demo
    http = client(root, local_user="rhea")
    body = {"title": "Note", "body": "A human post."}
    refused = http.post("/api/posts", json=body)
    assert refused.status_code == 403 and "X-Colloquy-Request" in refused.json()["detail"]
    made = http.post("/api/posts", headers=WRITE, json=body)
    assert made.status_code == 200 and made.json()["author_kind"] == "human"
    assert http.post("/api/posts", headers=WRITE, json={**body, "extra": 1}).status_code == 422
    asked = http.post("/api/requests", headers=WRITE, json={"target": ctx["posts"]["gap"], "body": "Any news?"})
    assert asked.status_code == 200 and asked.json()["target"] == ctx["agents"]["dana"]
    with Community(root) as board:
        system = add_participant(board, "exporter", "system")
        token = accounts.issue_token(board, "operator", system["id"], "integration")["token"]
        with pytest.raises(DawError, match="agents_use_the_cli"):
            accounts.issue_token(board, "operator", ctx["agents"]["alice"])
    integration = client(root, mode="accounts")
    bearer = {"Authorization": f"Bearer {token}"}
    assert integration.get("/api/me", headers=bearer).json()["kind"] == "system"
    denied = integration.post("/api/posts", headers=bearer, json=body)
    assert denied.status_code == 403 and "bio CLI" in denied.json()["detail"]


def test_token_login_sessions_and_revocation(demo):
    root, _ = demo
    http = client(root, mode="accounts")
    assert http.get("/api/me").status_code == 401
    assert stat.S_IMODE((root / "secrets" / "session.key").stat().st_mode) == 0o600
    with Community(root) as board:
        rhea = human(board)
        issued = accounts.issue_token(board, "operator", rhea, "laptop")
    token, credential = issued["token"], issued["credential"]["id"]
    raw = (root / "board.sqlite").read_bytes()
    assert token.encode() not in raw and b"laptop" in raw
    assert http.post("/api/session", json={"token": token}).status_code == 403  # login needs the CSRF header too
    assert http.post("/api/session", headers=WRITE, json={"token": token + "x"}).status_code == 401
    login = http.post("/api/session", headers=WRITE, json={"token": token})
    assert login.status_code == 200 and login.json()["name"] == "rhea"
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    me = http.get("/api/me").json()
    assert me["name"] == "rhea" and me["auth"] == "cookie" and me["tokens"][0]["id"] == credential
    assert "token_sha256" not in me["tokens"][0]
    # Cookie-authenticated writes still need the header; bearer writes do not.
    assert http.patch("/api/me", json={"affiliation": "Lab"}).status_code == 403
    assert http.patch("/api/me", headers=WRITE, json={"affiliation": "Lab"}).json()["profile"]["affiliation"] == "Lab"
    bearer = client(root, mode="accounts")
    assert bearer.patch("/api/me", headers={"Authorization": f"Bearer {token}"},
                        json={"orcid": "0000-0002-1825-0097"}).status_code == 200
    assert bearer.get("/api/me", headers={"Authorization": "Bearer colloquy_wrong"}).status_code == 401
    # A forged or tampered cookie is not a session.
    good = http.cookies.get(accounts.COOKIE)
    forged = client(root, mode="accounts")
    forged.cookies.set(accounts.COOKIE, good[:-1] + ("0" if good[-1] != "0" else "1"))
    assert forged.get("/api/me").status_code == 401
    # Humans manage their own tokens; only operators manage other people's.
    with Community(root) as board:
        other = accounts.issue_token(board, "operator", human(board, "sam"))["credential"]["id"]
        with pytest.raises(DawError, match="permission_denied"):
            accounts.revoke_token(board, rhea, other)
        with pytest.raises(DawError, match="permission_denied"):
            accounts.issue_token(board, rhea, "sam")
    revoked = http.delete(f"/api/tokens/{credential}", headers=WRITE)
    assert revoked.status_code == 200 and revoked.json()["revoked"], revoked.text
    assert http.get("/api/me").status_code == 401  # revocation ends sessions made from the token
    assert bearer.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert http.delete("/api/session", headers=WRITE).json() == {"logged_out": True}
    assert client(root).post("/api/session", headers=WRITE, json={"token": token}).json()["error"] == \
        "local_mode_has_no_login"


def test_operator_endpoints_create_people_and_tokens(demo):
    root, _ = demo
    with Community(root) as board:
        token = accounts.issue_token(board, "operator", "operator")["token"]
    op = client(root, mode="accounts")
    auth = {"Authorization": f"Bearer {token}"}
    made = op.post("/api/participants", headers=auth, json={"name": "kai", "kind": "human", "affiliation": "Lab"})
    assert made.status_code == 200 and made.json()["profile"]["affiliation"] == "Lab"
    issued = op.post("/api/tokens", headers=auth, json={"participant": "kai", "label": "first"}).json()
    assert issued["token"].startswith("colloquy_") and issued["credential"]["label"] == "first"
    allowance = op.put(f"/api/participants/{made.json()['id']}/allowance", headers=auth, json={"minutes": 45}).json()
    assert allowance["allowance"] == {"minutes": 45}
    kai = client(root, mode="accounts")
    kai_auth = {"Authorization": f"Bearer {issued['token']}"}
    assert kai.get("/api/me", headers=kai_auth).json()["budget"]["remaining"] == {"minutes": 45}
    assert kai.post("/api/participants", headers=kai_auth, json={"name": "eve"}).status_code == 403
    assert len(op.get("/api/tokens", headers=auth).json()["items"]) == 2
    assert len(kai.get("/api/tokens", headers=kai_auth).json()["items"]) == 1


def test_moderation_hides_and_suspends_without_deleting_bytes(demo):
    root, ctx = demo
    finding = ctx["posts"]["finding"]
    with Community(root) as board:
        rhea = human(board)
        with pytest.raises(DawError, match="permission_denied"):
            moderation.hide(board, rhea, finding, "spam")
        with pytest.raises(DawError, match="moderation_reason_required"):
            moderation.hide(board, "operator", finding, " ")
        row = moderation.hide(board, "operator", finding, "duplicate")
        assert row["state"] == "hidden" and moderation.hidden(board, finding)
        assert board.show(finding)["content"]["title"]  # bytes and post row are kept
        with pytest.raises(DawError, match="moderation_state_unchanged"):
            moderation.hide(board, "operator", finding, "again")
        moderation.unhide(board, "operator", finding, "restored")
        moderation.suspend(board, "operator", rhea, "abuse")
        with pytest.raises(DawError, match="cannot_suspend_operator"):
            moderation.suspend(board, "operator", "operator", "x")
        projection = board.rows("SELECT target_kind,target_id,state,reason,event_seq FROM moderation ORDER BY target_kind")
        assert moderation.rebuild(board) == 2
        assert board.rows("SELECT target_kind,target_id,state,reason,event_seq FROM moderation ORDER BY target_kind") == projection
    http = client(root, local_user="rhea")
    refused = http.post("/api/posts", headers=WRITE, json={"title": "t", "body": "b"})
    assert refused.status_code == 403 and refused.json()["error"] == "participant_suspended"
    assert http.get("/api/me").json()["suspended"] is True  # reading stays allowed
    with Community(root) as board:
        # The board's own post path refuses suspended authors too (agents included).
        with pytest.raises(DawError, match="participant_suspended"):
            board.publish(rhea, "t", "b")
        moderation.suspend(board, "operator", ctx["agents"]["dana"], "paused")
        with pytest.raises(DawError, match="participant_suspended"):
            board.publish(ctx["agents"]["dana"], "t", "b")
    operator_token = None
    with Community(root) as board:
        operator_token = accounts.issue_token(board, "operator", "operator")["token"]
    op = client(root, mode="accounts")
    auth = {"Authorization": f"Bearer {operator_token}"}
    assert op.post("/api/moderation/reinstate", headers=auth, json={"participant": "rhea", "reason": "ok"}).json()["state"] == "active"
    assert op.post("/api/moderation/hide", headers=auth, json={"post": finding, "reason": "x"}).json()["state"] == "hidden"
    assert op.post("/api/moderation/hide", headers=auth, json={"participant": "rhea", "reason": "x"}).status_code == 422
    assert [r["target_id"] for r in op.get("/api/moderation", params={"target_kind": "post"}).json()["items"]] == [finding]
    assert http.post("/api/posts", headers=WRITE, json={"title": "t", "body": "b"}).status_code == 200
    assert http.post("/api/moderation/unhide", headers=WRITE, json={"post": finding, "reason": "x"}).status_code == 403


def test_rate_limits_come_from_the_boards_own_records(demo):
    root, ctx = demo
    (root / "commons.toml").write_text("[limits]\nposts_per_hour = 2\nmarks_per_hour = 1\n")
    http = client(root, local_user="rhea")
    for _ in range(2):
        assert http.post("/api/posts", headers=WRITE, json={"title": "t", "body": "b"}).status_code == 200
    limited = http.post("/api/comments", headers=WRITE, json={"target_kind": "post", "target_id": ctx["posts"]["gap"],
                                                              "body": "c"})
    assert limited.status_code == 429 and limited.json()["error"] == "rate_limited"
    mark = {"target_kind": "post", "target_id": ctx["posts"]["gap"], "kind": "checked_source", "note": "n"}
    assert http.post("/api/marks", headers=WRITE, json=mark).status_code == 200
    assert http.post("/api/marks", headers=WRITE, json=mark).status_code == 429
    # A fresh process sees the same records; operators are not rate limited.
    with Community(root) as board:
        with pytest.raises(DawError, match="rate_limited"):
            participation.post(board, "rhea", "t", "b")
        participation.post(board, "operator", "t", "b")
    (root / "commons.toml").write_text("[limits]\nposts_per_hour = 0\n")
    with Community(root) as board, pytest.raises(DawError, match="invalid_commons_config"):
        participation.post(board, "rhea", "t", "b")


def test_uploads_are_receipted_evidence_never_rendered(demo):
    root, _ = demo
    http = client(root, local_user="rhea")
    data = b"<script>alert(1)</script>"
    made = http.post("/api/uploads", content=data,
                     headers={**WRITE, "X-Filename": "..%2F..%2Fevil%20page.html", "Content-Type": "text/html"})
    assert made.status_code == 200, made.text
    upload = made.json()
    assert upload["name"] == "evil page.html" and upload["size"] == len(data) and upload["media_type"] == "text/html"
    shown = http.get(f"/api/uploads/{upload['id']}").json()
    assert shown["receipt"]["sha256"] == upload["blob"] and shown["receipt"]["uploader"] == upload["uploader"]
    content = http.get(f"/api/uploads/{upload['id']}/content")
    assert content.content == data and content.headers["content-type"] == "application/octet-stream"
    assert content.headers["content-disposition"].startswith("attachment") and content.headers["x-content-type-options"] == "nosniff"
    post = http.post("/api/posts", headers=WRITE, json={"title": "Gel image", "body": "Attached.",
                                                        "upload_ids": [upload["id"]]}).json()
    assert post["content"]["evidence"]["upload"][0]["blob"] == upload["blob"]
    assert http.post("/api/posts", headers=WRITE, json={"title": "t", "body": "b", "upload_ids": ["upload_x"]}).status_code == 404
    assert http.post("/api/uploads", content=b"", headers=WRITE).json()["error"] == "empty_upload"
    (root / "commons.toml").write_text("[limits]\nupload_bytes = 4\n")
    assert http.post("/api/uploads", content=b"12345", headers=WRITE).json()["error"] == "upload_too_large"
    with Community(root) as board:
        assert board.one("SELECT count(*) AS n FROM upload")["n"] == 1
        assert not board.library.one("SELECT id FROM artifact WHERE output_blob=?", (upload["blob"],))
        assert participation.clean_filename("../../.bashrc") == "bashrc"
        with pytest.raises(DawError, match="invalid_media_type"):
            participation.upload(board, "rhea", "x.txt", b"x", "text/html<script>")


def test_me_summarises_the_callers_own_writes(demo):
    root, ctx = demo
    http = client(root, local_user="mira")
    me = http.get("/api/me").json()
    assert me["name"] == "mira" and me["kind"] == "human" and me["mode"] == "local" and me["auth"] == "local"
    assert "promote" in me["permissions"] and "hide" not in me["permissions"]
    assert [m["id"] for m in me["marks"]] == [ctx["participation"]["mark"]]
    assert [c["id"] for c in me["comments"]] == [ctx["participation"]["comment"]]
    assert me["budget"]["unlimited"] and me["inbox"] == [] and me["csrf_header"] == "X-Colloquy-Request"
    assert http.patch("/api/me", headers=WRITE, json={"orcid": "bad"}).json()["error"] == "invalid_orcid"
    assert http.patch("/api/me", headers=WRITE, json={"display_name": ""}).json()["profile"].get("display_name") is None


def test_cli_parity_for_people_without_the_web(demo, monkeypatch):
    from typer.testing import CliRunner

    from daw.commons.cli import app
    root, ctx = demo
    runner = CliRunner()
    monkeypatch.delenv("BIO_AGENT", raising=False)

    def bio(*args):
        result = runner.invoke(app, ["--root", str(root), *args])
        assert result.exit_code == 0, result.output
        return json.loads(result.output)

    issued = bio("token", "create", "mira", "--label", "cli")
    assert issued["token"].startswith("colloquy_")
    assert bio("token", "revoke", issued["credential"]["id"])["revoked"]
    assert bio("mark", "post", ctx["posts"]["gap"], "checked_source", "--note", "read it", "--as", "mira",
               "--pointer", "post:" + ctx["posts"]["gap"])["kind"] == "checked_source"
    made = bio("comment", "post", ctx["posts"]["gap"], "--text", "Which repository?", "--as", "mira", "--ask-author")
    assert made["request"]["target"] == ctx["agents"]["dana"]
    assert bio("promote", "post", ctx["posts"]["gap"], "--task-type", "scouting", "--target", "dana", "--minutes", "15",
               "--as", "mira")["task_type"] == "scouting"
    assert bio("commission", "review", "--target", "bob", "--note", "Review the contrast", "--minutes", "10",
               "--subject-kind", "post", "--subject-id", ctx["posts"]["correction"])["task_type"] == "review"
    assert bio("hide", ctx["posts"]["gap"], "--reason", "test")["state"] == "hidden"
    assert bio("unhide", ctx["posts"]["gap"], "--reason", "test")["state"] == "visible"
    monkeypatch.setenv("BIO_AGENT", ctx["agents"]["alice"])
    refused = runner.invoke(app, ["--root", str(root), "mark", "post", ctx["posts"]["gap"], "reproduced", "--note", "x"])
    assert refused.exit_code != 0
