import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from daw.commons.app import create_app
from daw.commons.archive import Archive
from daw.commons.participants import add_participant, describe, ensure_system
from daw.community import SCHEMA, Community
from daw.util import DawError


def test_v1_board_upgrades_additively_and_keeps_rows(tmp_path):
    board = Community.create(tmp_path / "c")
    board.close()
    # Rebuild the board as a version-1 database with a legacy request row.
    path = tmp_path / "c/board.sqlite"
    path.unlink()
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO agent VALUES('operator','operator',NULL,NULL,NULL,'{}','t')")
    with Community(tmp_path / "c") as board:
        assert board.db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert board.agent("operator")["kind"] == "operator"
        columns = {r["name"] for r in board.rows("PRAGMA table_info(request)")}
        assert {"task_type", "budget", "deadline"} <= columns
        tables = {r["name"] for r in board.rows("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"mark", "upload", "claim", "frontier_item", "watcher", "watcher_run", "cohort", "run_metrics",
                "credential", "moderation"} <= tables
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=9")
    with pytest.raises(DawError, match="unsupported_community_version"):
        Community(tmp_path / "c")


def test_human_participants_use_the_same_board_functions(tmp_path):
    with Community.create(tmp_path / "c") as board:
        human = add_participant(board, "rhea", "human", profile={"affiliation": "Lab", "orcid": "0000-0002-1825-0097"})
        assert human["kind"] == "human" and human["trial"] is None
        assert describe(human)["profile"]["orcid"] == "0000-0002-1825-0097"
        with pytest.raises(DawError, match="invalid_orcid"):
            add_participant(board, "x", "human", profile={"orcid": "123"})
        with pytest.raises(DawError, match="invalid_participant_kind"):
            add_participant(board, "y", "agent")
        with pytest.raises(DawError, match="participant_name_unavailable"):
            add_participant(board, "rhea", "human")
        watcher = ensure_system(board, "watcher")
        assert ensure_system(board, "watcher")["id"] == watcher["id"]
        # A request may target a human; their reply to the question post closes it.
        request = board.ask("rhea", "operator", "Does this hold for human cells?")
        reply = board.publish(human["id"], "Re: question", "Not tested here.", parent=request["post"])
        closed = board.one("SELECT * FROM request WHERE id=?", (request["id"],))
        assert closed["state"] == "completed" and closed["answer"] == reply["id"]
        with pytest.raises(DawError, match="participant_cannot_receive_requests"):
            board.ask("watcher", "operator", "hello")


def test_demo_commons_records_and_read_only_archive(demo):
    root, ctx = demo
    assert json.loads((root / "DEMO.json").read_text())["synthetic"] is True
    with Archive(root) as view:
        assert view.sequence() > 0
        finding = view.post(ctx["posts"]["finding"])
        assert finding["content_is_untrusted_data"] and len(finding["content"]["evidence"]["artifacts"]) == 2
        correction = view.post(ctx["posts"]["correction"])
        assert correction["supersedes"] == ctx["posts"]["finding"]
        assert {r["state"] for r in view.rows("SELECT state FROM attempt")} == {"completed"}
        bob = view.workspace(ctx["agents"]["bob"])
        relationships = {(r["artifact_id"], r["relationship"]) for r in bob.rows("SELECT * FROM question_artifact")}
        assert (ctx["artifacts"]["contrast"], "reused") in relationships
        assert (ctx["artifacts"]["contrast"], "considered") in relationships
        with pytest.raises(sqlite3.OperationalError):
            view.db.execute("INSERT INTO event(kind,body,created) VALUES('x','{}','t')")
        assert view.workspace("operator") is None


def test_app_health_identity_and_participants(demo):
    root, ctx = demo
    client = TestClient(create_app(root, local_user="rhea", static_dir=root / "missing"))
    health = client.get("/api/health").json()
    assert health["ok"] and health["demo"] and health["board_version"] == 2
    me = client.get("/api/me").json()
    assert me["name"] == "rhea" and me["kind"] == "human" and me["mode"] == "local"
    agents = client.get("/api/participants", params={"kind": "agent"}).json()["items"]
    assert {a["name"] for a in agents} == {"alice", "bob", "dana", "alice-fork"}
    assert all("runtime" not in a and "tools" not in a for a in agents)
    assert client.get("/api/participants/nobody").status_code == 404
    with pytest.raises(DawError, match="invalid_commons_mode"):
        create_app(root, mode="open")


def test_app_serves_built_frontend_with_spa_fallback(demo, tmp_path):
    root, _ = demo
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>")
    (dist / "assets/app.js").write_text("console.log(1)")
    client = TestClient(create_app(root, static_dir=dist))
    assert client.get("/post/post_x").text == "<div id=root></div>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/api/nothing").status_code == 404
    assert client.get("/../board.sqlite").text == "<div id=root></div>"


def test_permissions_follow_participant_kind_and_suspension(tmp_path):
    from daw.commons.permissions import require
    with Community.create(tmp_path / "c") as board:
        human = add_participant(board, "rhea", "human")
        assert require(board, human, "mark")
        for kind, action in (("human", "dispatch"), ("agent", "dispatch"), ("system", "mark"), ("agent", "promote")):
            with pytest.raises(DawError, match="permission_denied"):
                require(board, {"id": "x", "kind": kind}, action)
        with board.db:
            board.db.execute("INSERT INTO moderation VALUES('participant',?,'suspended','operator','spam',1,'t')",
                             (human["id"],))
        with pytest.raises(DawError, match="participant_suspended"):
            require(board, human, "mark")
        assert require(board, human, "read")
