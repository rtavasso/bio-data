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


def test_task_vocabulary_and_budgets():
    from daw.commons.tasks import check_deadline, check_task_type, normalize_budget
    assert check_task_type("replication") == "replication"
    with pytest.raises(DawError, match="invalid_task_type"):
        check_task_type("anything")
    assert normalize_budget({"minutes": 30}) == {"minutes": 30}
    for bad in ({"minutes": 0}, {"tokens": True}, {"dollars": 3}):
        with pytest.raises(DawError, match="invalid_budget"):
            normalize_budget(bad)
    assert check_deadline("2026-11-01T00:00:00+00:00")
    with pytest.raises(DawError, match="invalid_deadline"):
        check_deadline("2026-11-01")


def test_notices_are_inbox_requests_from_a_system_participant(demo):
    from daw.commons.notices import notify
    root, ctx = demo
    with Community(root) as board:
        alice = ctx["agents"]["alice"]
        request = notify(board, "watcher", alice, "New evidence may fit gap", "A new accession appeared.", key="n1")
        assert request["task_type"] == "notice" and request["target"] == alice
        assert notify(board, "watcher", alice, "New evidence may fit gap", "A new accession appeared.", key="n1")["id"] == request["id"]
        shown = board.show(request["post"])
        assert shown["content"]["kind"] == "notice" and board.agent(shown["author"])["kind"] == "system"
        assert any(r["id"] == request["id"] for r in board.inbox(alice))


# ---- v2 C3: write-API discipline and read-only reads ------------------------------------------------

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def api_routes(app):
    """Every APIRoute the app serves, flattening included routers (newer FastAPI keeps them nested)."""
    from fastapi.routing import APIRoute

    def flat(routes):
        for route in routes:
            if hasattr(route, "original_router"):
                yield from flat(route.original_router.routes)
            elif isinstance(route, APIRoute):
                yield route
    return list(flat(app.routes))


def concrete(path):
    import re
    return re.sub(r"\{[^}]+\}", "x", path)


def test_every_write_route_requires_the_request_header(demo):
    """v2 C3: every POST/PUT/PATCH/DELETE from ROUTER_MODULES refuses a browser write without X-Colloquy-Request,
    in local mode and with a session cookie, before it touches the board. New routes are covered automatically."""
    import importlib

    from daw.commons import accounts
    from daw.commons.api import deps
    from daw.commons.app import ROUTER_MODULES
    root, _ = demo
    local = create_app(root, local_user="rhea", static_dir=root / "missing")
    routes = [(m, r.path) for r in api_routes(local) for m in sorted(r.methods & WRITE_METHODS)]
    modules = [importlib.import_module(name).router for name in ROUTER_MODULES]
    declared = {(m, r.path) for router in modules for r in router.routes for m in r.methods & WRITE_METHODS}
    assert set(routes) == declared and len(routes) >= 25
    sequence = Archive(root)
    try:
        before = sequence.sequence()
    finally:
        sequence.close()
    http = TestClient(local)
    for method, path in routes:
        response = http.request(method, concrete(path), json={})
        if path == "/api/session" and method == "POST":
            assert response.json()["error"] == "local_mode_has_no_login"  # no login in local mode at all
            continue
        assert response.status_code == 403, (method, path, response.text)
        assert "X-Colloquy-Request" in response.json()["detail"], (method, path)
    # Cookie sessions (accounts mode) need the header too; only bearer requests are exempt.
    with Community(root) as board:
        person = add_participant(board, "kai", "human")
        token = accounts.issue_token(board, "operator", person["id"])["token"]
    cookie = TestClient(create_app(root, mode="accounts", static_dir=root / "missing"))
    assert cookie.post("/api/session", headers={"X-Colloquy-Request": "1"}, json={"token": token}).status_code == 200
    for method, path in routes:
        response = cookie.request(method, concrete(path), json={})
        assert response.status_code == 403, (method, path, response.text)
    with Archive(root) as view:
        written = view.rows("SELECT kind FROM event WHERE seq>?", (before,))
    assert {r["kind"] for r in written} <= {"participant_created", "token_issued"}  # only the setup above
    # No endpoint opens the board through the dependency machinery (a connection used across threads);
    # writes open it in the worker thread with write.call.
    for route in api_routes(local):
        assert all(d.call is not deps.board for d in route.dependant.dependencies), route.path


def _sample_ids(view):
    post = view.one("SELECT id,body_blob FROM post ORDER BY seq LIMIT 1")
    artifact = view.library.one("SELECT id FROM artifact ORDER BY id LIMIT 1")
    run = view.one("SELECT id FROM attempt ORDER BY created LIMIT 1")
    agent = view.one("SELECT id FROM agent WHERE trial IS NOT NULL ORDER BY created LIMIT 1")
    item = view.one("SELECT id FROM frontier_item ORDER BY id LIMIT 1")
    question = None
    workspace = view.workspace(agent["id"])
    if workspace:
        row = workspace.one("SELECT id FROM question ORDER BY created LIMIT 1")
        question = row["id"] if row else None
    return {"post": post["id"], "blob": post["body_blob"], "artifact": artifact["id"] if artifact else "artifact_x",
            "run": run["id"] if run else "run_x", "agent": agent["id"], "item": item["id"] if item else "frontier_x",
            "question": question or "q_0000000000000000"}


def _get_paths(app, ids):
    fill = {"/api/participants/{identity}": ids["agent"], "/api/participants/{identity}/activity": ids["agent"],
            "/api/frontier/{identity}": ids["item"], "/api/map/node/{identity}": ids["post"]}
    for route in api_routes(app):
        if "GET" not in route.methods or route.path in {"/api/events", "/api/me/inbox/stream"}:
            continue  # the live streams are exercised with once=true below
        path = route.path
        if path in fill:
            path = path.replace("{identity}", fill[path])
        path = (path.replace("/posts/{identity}", f"/posts/{ids['post']}")
                .replace("/threads/{identity}", f"/threads/{ids['post']}")
                .replace("/artifacts/{identity}", f"/artifacts/{ids['artifact']}")
                .replace("{post}", ids["post"]).replace("{run}", ids["run"]).replace("{agent}", ids["agent"])
                .replace("{qid}", ids["question"]).replace("{owner}", "library").replace("{sha}", ids["blob"]))
        yield concrete(path)
    yield "/api/events?once=true"
    yield "/api/me/inbox/stream?once=true"
    yield f"/api/marks?target_kind=post&target_id={ids['post']}"
    yield f"/api/requests?task_type=question&target={ids['agent']}"
    yield "/api/search?q=PMP22"


def test_serving_the_cohort_and_every_get_route_leaves_the_fixture_verified(cohort_copy):
    """v2 C3 on real data: start the server on a copy of the committed cohort fixture and request every GET
    route; `fixture verify` stays green on that copy (reads never write).

    The committed fixture is resettled to the current schema and projections (`bio commons fixture
    resettle`), so server startup and every GET must leave every file exactly as recorded."""
    from daw.commons.fixture import verify_fixture
    assert verify_fixture(cohort_copy)["verified"]
    app = create_app(cohort_copy, local_user="local", static_dir=cohort_copy / "missing")
    assert verify_fixture(cohort_copy)["verified"], "server startup wrote to the board"
    http = TestClient(app)
    with Archive(cohort_copy) as view:
        ids = _sample_ids(view)
        before = view.sequence()
    statuses = {}
    for path in _get_paths(app, ids):
        response = http.get(path)
        statuses[path] = response.status_code
        assert response.status_code < 500, (path, response.text[:300])
    assert sum(1 for s in statuses.values() if s == 200) >= 40, statuses
    checked = verify_fixture(cohort_copy)
    assert checked["verified"] and checked["untracked"] == [], checked
    with Archive(cohort_copy) as view:
        assert view.sequence() == before
    assert http.get("/api/frontier").json()["total"] >= 59


# ---- v2 C14: triggers on existing boards ------------------------------------------------------------

def test_existing_v2_board_regains_missing_triggers_on_open(tmp_path):
    from daw.commons import schema
    with Community.create(tmp_path / "c") as board:
        assert schema.current(board.db)
        with board.writer():
            board.db.execute("DROP TRIGGER immutable_mark_update")
            board.db.execute("DROP INDEX IF EXISTS login_failure_key")
        assert not schema.current(board.db)
    with Community(tmp_path / "c") as board:
        assert schema.current(board.db)
        names = {r["name"] for r in board.rows("SELECT name FROM sqlite_master WHERE type='trigger'")}
        assert "immutable_mark_update" in names
        board.db.execute("INSERT INTO mark VALUES('m','operator','post','p','checked_source','n','[]','b','t')")
        with pytest.raises(sqlite3.IntegrityError):
            board.db.execute("UPDATE mark SET note='changed' WHERE id='m'")


def test_permissions_are_the_spec_table_plus_documented_additions():
    from daw.commons.permissions import ACTIONS, ADDITIONS, CORE
    assert CORE["human"] == {"post", "comment", "mark", "promote", "commission"}
    assert CORE["operator"] == {"dispatch", "retry", "recover", "suspend", "budget"}
    assert CORE["agent"] == {"publish", "ask", "fetch", "answer"}
    assert {"review", "watch", "token", "profile", "export"} <= ADDITIONS["human"]
    assert "dispatch" not in ACTIONS["agent"] and "dispatch" not in ACTIONS["human"]
    assert all(ACTIONS[k] == {"read"} | CORE[k] | ADDITIONS[k] for k in CORE)
