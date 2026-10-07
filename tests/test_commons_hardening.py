"""Pilot hardening (Milestone 6): tenancy (M7.4), the agent board service, login rate limits, base paths."""
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daw.commons import accounts, boardservice, moderation, sandbox, tenants
from daw.commons.app import create_app, render_index
from daw.commons.boardservice import BoardClient, BoardService
from daw.commons.metrics import create_cohort
from daw.commons.participants import add_participant
from daw.commons.permissions import ACTIONS
from daw.commons.ratelimit import AttemptLimiter, login_limits
from daw.community import Community
from daw.util import DawError

WRITE = {"X-Colloquy-Request": "1"}
INDEX = ('<!doctype html><html><head><meta name="colloquy-base" content="/" />'
         '<script type="module" crossorigin src="./assets/index-x.js"></script>'
         '<link rel="stylesheet" crossorigin href="./assets/index-x.css"></head><body><div id="root"></div></body></html>')


@pytest.fixture
def dist(tmp_path):
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text(INDEX)
    (folder / "assets" / "index-x.js").write_text("export {};\n")
    return folder


@pytest.fixture
def two_commons(demo_template, tmp_path):
    root, ctx = demo_template
    a, b = tmp_path / "tenants" / "lab-a", tmp_path / "tenants" / "lab-b"
    shutil.copytree(root, a, symlinks=True)
    shutil.copytree(root, b, symlinks=True)
    return a, b, ctx


def write_config(tmp_path, body):
    path = tmp_path / "tenants.toml"
    path.write_text(body)
    return path


def person_token(root, name):
    with Community(root) as board:
        person = add_participant(board, name, "human", profile={"display_name": name})["id"]
        return accounts.issue_token(board, "operator", person, "test")["token"]


# ---- M7.4 tenancy ---------------------------------------------------------------------------------

def test_tenant_config_is_validated(two_commons, tmp_path):
    a, b, _ = two_commons
    good = tenants.load(write_config(tmp_path, '[tenants.lab-a]\nroot = "tenants/lab-a"\ntitle = "Lab A"\n'
                                               f'[tenants.lab-b]\nroot = "{b}"\nlogin = {{ attempts = 3 }}\n'))
    assert [(t.name, t.root, t.base) for t in good.tenants] == [("lab-a", a.resolve(), "/c/lab-a/"),
                                                                ("lab-b", b.resolve(), "/c/lab-b/")]
    assert good.tenants[1].login == {"attempts": 3}
    bad = {
        '[tenants.Lab_A]\nroot = "tenants/lab-a"\n': "invalid_tenant_name",
        '[tenants.lab-a]\nroot = "tenants/lab-a"\nshared_db = true\n': "invalid_tenants_config",
        '[tenants.lab-a]\nroot = "tenants/missing"\n': "community_not_initialized",
        f'[tenants.lab-a]\nroot = "{a}"\n[tenants.lab-b]\nroot = "{a}"\n': "tenant_roots_overlap",
        f'[tenants.lab-a]\nroot = "{a}"\n[tenants.nested]\nroot = "{a / "agents"}"\n': "community_not_initialized",
        '[host]\nmode = "local"\n[tenants.lab-a]\nroot = "tenants/lab-a"\n': "invalid_tenants_config",
        "": "invalid_tenants_config",
    }
    for body, reason in bad.items():
        with pytest.raises(DawError, match=reason):
            tenants.load(write_config(tmp_path, body))
    nested = tmp_path / "tenants" / "lab-a" / "inner"
    shutil.copytree(b, nested, symlinks=True)
    with pytest.raises(DawError, match="tenant_roots_overlap"):
        tenants.load(write_config(tmp_path, f'[tenants.lab-a]\nroot = "{a}"\n[tenants.inner]\nroot = "{nested}"\n'))


def test_host_serves_isolated_tenants_under_path_prefixes(two_commons, tmp_path, dist):
    a, b, ctx = two_commons
    token_a, token_b = person_token(a, "ana"), person_token(b, "ben")
    config = tenants.load(write_config(tmp_path, f'[host]\nstatic_dir = "{dist}"\n[tenants.lab-a]\nroot = "{a}"\n'
                                                 f'[tenants.lab-b]\nroot = "{b}"\n'))
    http = TestClient(tenants.create_host_app(config))
    health = http.get("/api/health").json()
    assert health["ok"] and [t["name"] for t in health["tenants"]] == ["lab-a", "lab-b"]
    assert 'href="/c/lab-a/"' in http.get("/").text and 'href="/c/lab-b/"' in http.get("/").text
    redirect = http.get("/c/lab-a", follow_redirects=False)
    assert redirect.status_code in {301, 302, 307} and redirect.headers["location"] == "/c/lab-a/"
    assert http.get("/c/nobody").status_code == 404
    # Each tenant is its own commons in accounts mode.
    assert http.get("/c/lab-a/api/health").json()["mode"] == "accounts"
    assert http.get("/c/lab-a/api/me").status_code == 401
    # Tokens and cookies never cross tenants.
    bearer_a = {"Authorization": f"Bearer {token_a}"}
    assert http.get("/c/lab-a/api/me", headers=bearer_a).json()["name"] == "ana"
    assert http.get("/c/lab-b/api/me", headers=bearer_a).status_code == 401
    login = http.post("/c/lab-a/api/session", headers=WRITE, json={"token": token_a})
    assert login.status_code == 200 and "path=/c/lab-a/" in login.headers["set-cookie"].lower()
    assert http.get("/c/lab-a/api/me").json()["auth"] == "cookie"
    cookie = {"Cookie": f"{accounts.COOKIE}={login.cookies[accounts.COOKIE]}"}
    assert TestClient(tenants.create_host_app(config)).get("/c/lab-b/api/me", headers=cookie).status_code == 401
    # A write in one tenant is invisible to the other.
    made = http.post("/c/lab-a/api/posts", headers=bearer_a, json={"title": "Only in A", "body": "Tenant A note."})
    assert made.status_code == 200, made.text
    post = made.json()["id"]
    assert http.get(f"/c/lab-a/api/posts/{post}").status_code == 200
    assert http.get(f"/c/lab-b/api/posts/{post}", headers={"Authorization": f"Bearer {token_b}"}).status_code == 404
    with Community(b) as board:
        assert board.one("SELECT 1 FROM post WHERE id=?", (post,)) is None
    seq_a = http.get("/c/lab-a/api/health").json()["sequence"]
    assert seq_a > http.get("/c/lab-b/api/health").json()["sequence"]
    # Separate secrets per root.
    assert (a / "secrets" / "session.key").read_bytes() != (b / "secrets" / "session.key").read_bytes()
    # The web app is served under each prefix with its base announced.
    page = http.get("/c/lab-b/post/xyz")
    assert page.status_code == 200 and '<meta name="colloquy-base" content="/c/lab-b/" />' in page.text
    assert 'src="/c/lab-b/assets/index-x.js"' in page.text and "./assets" not in page.text
    assert http.get("/c/lab-b/assets/index-x.js").text == "export {};\n"
    assert http.get("/c/lab-b/api/nothing").status_code == 404


def test_tenant_login_limits_are_independent(two_commons, tmp_path):
    a, b, _ = two_commons
    token_b = person_token(b, "ben")
    config = tenants.load(write_config(tmp_path, f'[tenants.lab-a]\nroot = "{a}"\nlogin = {{ attempts = 2 }}\n'
                                                 f'[tenants.lab-b]\nroot = "{b}"\n'))
    http = TestClient(tenants.create_host_app(config))
    for _ in range(2):
        assert http.post("/c/lab-a/api/session", headers=WRITE, json={"token": "colloquy_guess"}).status_code == 401
    limited = http.post("/c/lab-a/api/session", headers=WRITE, json={"token": "colloquy_other"})
    assert limited.status_code == 429 and limited.json()["error"] == "rate_limited"
    assert 0 < int(limited.headers["retry-after"]) <= 300
    assert http.post("/c/lab-b/api/session", headers=WRITE, json={"token": "colloquy_guess"}).status_code == 401
    assert http.post("/c/lab-b/api/session", headers=WRITE, json={"token": token_b}).status_code == 200


def test_host_command_records_tenancy_for_every_tenant(two_commons, tmp_path, monkeypatch):
    import uvicorn
    from typer.testing import CliRunner

    from daw.commons.cli import app
    a, b, _ = two_commons
    served = {}
    monkeypatch.setattr(uvicorn, "run", lambda application, **options: served.update(app=application, **options))
    config = write_config(tmp_path, f'[tenants.lab-a]\nroot = "{a}"\n[tenants.lab-b]\nroot = "{b}"\n')
    result = CliRunner().invoke(app, ["host", "--config", str(config), "--host", "0.0.0.0", "--port", "9000"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["tenants"]["lab-b"]["base"] == "/c/lab-b/"
    assert served["host"] == "0.0.0.0" and served["port"] == 9000
    assert sandbox.tenancy(a) == sandbox.tenancy(b) == "accounts"


# ---- login rate limits ------------------------------------------------------------------------------

def test_attempt_limiter_is_bounded_and_windowed():
    clock = [0.0]
    limiter = AttemptLimiter(3, 60, max_keys=4, clock=lambda: clock[0])
    for _ in range(3):
        assert limiter.retry_after("ip:a") == 0
        limiter.failed("ip:a", "token:t")
    assert limiter.retry_after("ip:a") == 60 and limiter.retry_after("ip:b", "token:t") == 60
    assert limiter.retry_after("ip:b") == 0
    clock[0] = 30
    assert limiter.retry_after("ip:a") == 30
    clock[0] = 61
    assert limiter.retry_after("ip:a") == 0
    for n in range(10):
        limiter.failed(f"ip:{n}")
    assert len(limiter) == 4  # least recently touched keys are evicted


def test_login_is_rate_limited_per_address_and_per_token(demo):
    root, _ = demo
    (root / "commons.toml").write_text("[login]\nattempts = 3\nwindow_seconds = 120\n")
    assert login_limits(root) == {"attempts": 3, "window_seconds": 120}
    good = person_token(root, "rhea")
    http = TestClient(create_app(root, mode="accounts", static_dir=root / "missing"))
    for n in range(3):
        assert http.post("/api/session", headers=WRITE, json={"token": f"colloquy_wrong{n}"}).status_code == 401
    refused = http.post("/api/session", headers=WRITE, json={"token": good})
    assert refused.status_code == 429  # this address is limited even with a valid token
    other = TestClient(create_app(root, mode="accounts", static_dir=root / "missing"), client=("10.0.0.9", 1))
    assert other.post("/api/session", headers=WRITE, json={"token": good}).status_code == 200
    # The same wrong token from many addresses is limited too.
    app = create_app(root, mode="accounts", static_dir=root / "missing")
    for n in range(3):
        assert TestClient(app, client=(f"10.1.0.{n}", 1)).post(
            "/api/session", headers=WRITE, json={"token": "colloquy_same"}).status_code == 401
    assert TestClient(app, client=("10.1.0.9", 1)).post(
        "/api/session", headers=WRITE, json={"token": "colloquy_same"}).status_code == 429
    (root / "commons.toml").write_text("[login]\nattempts = 0\n")
    with pytest.raises(DawError, match="invalid_commons_config"):
        login_limits(root)


def test_single_commons_serves_the_web_app_at_root(demo, dist):
    root, _ = demo
    http = TestClient(create_app(root, static_dir=dist))
    page = http.get("/board").text
    assert '<meta name="colloquy-base" content="/" />' in page and 'src="/assets/index-x.js"' in page
    assert http.get("/index.html").text == page
    assert render_index("<html><head></head></html>", "/c/x/").count('content="/c/x/"') == 1
    with pytest.raises(DawError, match="invalid_base_path"):
        create_app(root, base="/c/../x/")


# ---- operator cohort permission -----------------------------------------------------------------

def test_cohorts_need_the_operator_cohort_permission(demo):
    root, ctx = demo
    assert "cohort" in ACTIONS["operator"] and "cohort" not in ACTIONS["human"] | ACTIONS["agent"]
    with Community(root) as board:
        person = add_participant(board, "hana", "human")["id"]
        with pytest.raises(DawError, match="permission_denied"):
            create_cohort(board, person, "denied", agents=[ctx["agents"]["alice"]])
        assert create_cohort(board, "operator", "allowed", agents=[ctx["agents"]["alice"]])["name"] == "allowed"


# ---- board service for sandboxed agents ---------------------------------------------------------

@pytest.fixture
def service(demo):
    root, ctx = demo
    running = BoardService(root)
    started = running.refresh()
    yield root, ctx, running, started
    running.close()


def agent_client(root, agent):
    endpoint = boardservice.provision(root, agent)
    return BoardClient(endpoint["url"], endpoint["token"])


def test_board_service_round_trip_runs_agent_operations(service):
    root, ctx, running, started = service
    alice, bob = ctx["agents"]["alice"], ctx["agents"]["bob"]
    assert {s["agent"] for s in started} >= {alice, bob}
    with Community(root) as board:
        alice_ws = board.trial(board.agent(alice)) / "workspace"
        bob_ws = board.trial(board.agent(bob)) / "workspace"
    a = agent_client(root, alice)
    shown = a.call("show", {"post": ctx["posts"]["finding"]})
    assert shown["id"] == ctx["posts"]["finding"] and shown["content_is_untrusted_data"]
    assert a.call("verify", {"post": ctx["posts"]["finding"]})["verified"]
    assert a.call("search", {"text": "contrast"})["items"]
    assert "items" in a.call("claims", {"q": ""})
    published = a.call("publish", {"title": "Service publication", "body": "Published through the board service.",
                                   "workspace": str(alice_ws), "artifacts": [ctx["artifacts"]["contrast"]],
                                   "key": "svc-1"})
    assert published["author"] == alice and published["evidence_artifacts"][0]["id"] == ctx["artifacts"]["contrast"]
    asked = a.call("ask", {"target": bob, "body": "Does normalization change the sign?"})
    assert asked["target"] == bob and asked["state"] == "pending"
    b = agent_client(root, bob)
    assert any(r["id"] == asked["id"] for r in b.call("inbox", {}))
    answered = b.call("answer", {"request": asked["id"], "body": "No; it shrinks the magnitude only."})
    assert answered["parent"] == asked["post"] and answered["author"] == bob
    with Community(root) as board:
        assert board.one("SELECT state,answer FROM request WHERE id=?", (asked["id"],)) == \
            {"state": "completed", "answer": answered["id"]}
    fetched = a.call("fetch", {"post": ctx["posts"]["reply"], "question": ctx["questions"]["alice"],
                               "workspace": str(alice_ws)})
    assert fetched["relationship"] == "considered"
    log = [json.loads(line) for line in (root / "service" / "board-service.jsonl").read_text().splitlines()]
    assert {(entry["agent"], entry["operation"], entry["outcome"]) for entry in log} >= {
        (alice, "publish", "ok"), (bob, "answer", "ok"), (alice, "fetch", "ok")}
    assert "Published through the board service" not in (root / "service" / "board-service.jsonl").read_text()
    assert bob_ws.is_dir()


def test_board_service_binds_each_socket_to_one_agent(service, tmp_path):
    root, ctx, running, _ = service
    alice, bob = ctx["agents"]["alice"], ctx["agents"]["bob"]
    a_end, b_end = boardservice.provision(root, alice), boardservice.provision(root, bob)
    assert stat.S_IMODE(a_end["socket"].stat().st_mode) == 0o600
    assert stat.S_IMODE(a_end["dir"].stat().st_mode) == 0o700
    assert stat.S_IMODE(boardservice.token_path(root, alice).stat().st_mode) == 0o600
    assert a_end["token"] != b_end["token"]
    # Alice's token does not open Bob's socket, and Alice cannot claim Bob's identity on her own.
    with pytest.raises(DawError, match="authentication_required"):
        BoardClient(b_end["url"], a_end["token"]).call("inbox", {})
    a = BoardClient(a_end["url"], a_end["token"])
    with pytest.raises(DawError, match="agent_identity_mismatch"):
        a.call("publish", {"title": "x", "body": "y", "author": bob})
    with pytest.raises(DawError, match="agent_identity_mismatch"):
        a.call("inbox", {"agent": bob})
    asked = agent_client(root, bob).call("ask", {"target": "dana", "body": "Any knockdown data yet?"})
    with pytest.raises(DawError, match="permission_denied"):
        a.call("answer", {"request": asked["id"], "body": "Not mine to answer."})
    # Only the agent's own checkout may be read or written.
    with Community(root) as board:
        alice_trial, bob_trial = (board.trial(board.agent(x)) for x in (alice, bob))
    with pytest.raises(DawError, match="workspace_outside_checkout"):
        a.call("fetch", {"post": ctx["posts"]["finding"], "question": "q", "workspace": str(bob_trial / "workspace")})
    (alice_trial / "borrowed").symlink_to(bob_trial / "workspace")
    with pytest.raises(DawError, match="workspace_outside_checkout"):
        a.call("publish", {"title": "x", "body": "y", "workspace": str(alice_trial / "borrowed"),
                           "artifacts": [ctx["artifacts"]["normalized"]]})
    fake = alice_trial / "fake-ws"
    fake.mkdir()
    (fake / "catalog.sqlite").symlink_to(bob_trial / "workspace" / "catalog.sqlite")
    with pytest.raises(DawError, match="workspace_outside_checkout"):
        a.call("publish", {"title": "x", "body": "y", "workspace": str(fake), "artifacts": ["artifact_x"]})
    # Unknown operations, operator commands and extra fields are refused; suspension applies.
    with pytest.raises(DawError, match="unknown_board_operation"):
        a.call("dispatch", {"request": asked["id"]})
    with pytest.raises(DawError, match="invalid_board_request"):
        a.call("show", {"post": ctx["posts"]["finding"], "path": "/etc/passwd"})
    with Community(root) as board:
        moderation.moderate(board, "operator", "suspend", alice, "test")
    with pytest.raises(DawError, match="participant_suspended"):
        a.call("ask", {"target": bob, "body": "Still here?"})
    # A missing token file refuses everything (rotation: delete it while the agent is idle).
    boardservice.token_path(root, bob).unlink()
    with pytest.raises(DawError, match="authentication_required"):
        BoardClient(b_end["url"], b_end["token"]).call("inbox", {})
    with pytest.raises(DawError, match="board_service_unavailable"):
        BoardClient(f"unix://{tmp_path / 'none.sock'}", "t").call("inbox", {})


def test_sandboxed_checkout_uses_the_board_service_without_the_board(service, monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from daw.community_cli import app
    root, ctx, _, _ = service
    alice = ctx["agents"]["alice"]
    endpoint = boardservice.provision(root, alice)
    monkeypatch.setenv("BIO_BOARD_URL", endpoint["url"])
    monkeypatch.setenv("BIO_BOARD_TOKEN", endpoint["token"])
    monkeypatch.setenv("BIO_AGENT", alice)
    monkeypatch.setenv("BIO_COMMUNITY", str(tmp_path / "not-mounted"))  # the board is absent in the container
    body = tmp_path / "note.md"
    body.write_text("A note from inside the sandbox.")
    runner = CliRunner()
    published = runner.invoke(app, ["publish", "Sandbox note", "--body", str(body)])
    assert published.exit_code == 0, published.output
    assert json.loads(published.output)["author"] == alice
    shown = runner.invoke(app, ["show", ctx["posts"]["finding"]])
    assert json.loads(shown.output)["id"] == ctx["posts"]["finding"]
    listed = runner.invoke(app, ["agents"])
    assert alice in {row["id"] for row in json.loads(listed.output)}
    for command in (["audit"], ["reindex"], ["init", str(tmp_path / "other")], ["add-agent", "eve"]):
        refused = runner.invoke(app, command)
        assert refused.exit_code != 0 and refused.exception.reason == "board_service_only", command


def test_sandbox_argv_mounts_only_the_agent_socket_never_the_board(demo):
    root, ctx = demo
    alice = ctx["agents"]["alice"]
    with Community(root) as board:
        trial = board.trial(board.agent(alice))
    (root / "sandbox.toml").write_text('engine = "docker"\nimage = "agent:1"\n')
    config = sandbox.load(root)
    endpoint = boardservice.provision(root, alice)
    env = {"BIO_AGENT": alice, "BIO_COMMUNITY": str(root), "BIO_BOARD_TOKEN": "operator-env", "PATH": "/usr/bin"}
    argv, client = sandbox.container_argv(config, ["claude", "-p"], env, trial=trial, board_root=root, name="c",
                                          board=endpoint)
    mounts = [argv[i + 1] for i, a in enumerate(argv) if a == "--mount"]
    assert f"type=bind,src={endpoint['dir']},dst={endpoint['dir']},readonly" in mounts
    assert f"type=bind,src={trial},dst={trial}" in mounts
    assert not any(m.startswith(f"type=bind,src={root},") for m in mounts)
    assert not any("readonly" not in m and m.split(",")[1] not in {f"src={trial}"} for m in mounts)
    assert endpoint["token"] not in " ".join(argv) and client["BIO_BOARD_TOKEN"] == endpoint["token"]
    assert client["BIO_BOARD_URL"] == endpoint["url"] and "--env" in argv and "BIO_BOARD_TOKEN" in argv
    with pytest.raises(DawError, match="unsafe_agent_path"):
        sandbox.container_argv(config, ["x"], env, trial=root.parent, board_root=root, name="c")
    # Through dispatch: the receipt records the service endpoint and no board mount; the token stays out of it.
    decision = sandbox.policy(root)

    class Adapter:
        def auth_files(self, env):
            return ()

        def hosts(self, config):
            return ()
    wrapped, client, receipt = sandbox.apply(decision, ["claude"], env, trial=trial, board_root=root,
                                             adapter=Adapter(), agent_config={}, run="run_1")
    assert receipt["board_mounted"] is False and receipt["board_service"]["url"] == endpoint["url"]
    assert endpoint["token"] not in json.dumps(receipt) and "BIO_BOARD_TOKEN" in receipt["environment_names"]
    # sandbox.json records the short socket and the symlink left at the old in-commons location.
    assert receipt["board_service"]["link"] == str(root / "service" / "board" / alice / "board.sock")
    assert receipt["board_service"]["socket"] == str(endpoint["socket"]) and receipt["board_service"]["index"] >= 1


# ---- spec v2 C1: short socket directory (macOS sun_path is 104 bytes) and C14 agents listing ------

def test_board_sockets_bind_under_a_short_per_commons_directory(tmp_path, monkeypatch):
    monkeypatch.delenv(boardservice.SOCKET_ROOT_ENV, raising=False)
    root = tmp_path / ("a-very-long-commons-directory-name-" * 4)  # the commons path itself is never in the socket
    root.mkdir()
    first, second = boardservice.provision(root, "agent_one"), boardservice.provision(root, "agent_two")
    digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:12]
    base = (boardservice.socket_root() / digest).resolve()
    assert first["socket"] == base / "1" / "1.sock" and second["socket"] == base / "2" / "2.sock"
    assert len(os.fsencode(first["socket"])) < 104 and first["url"] == f"unix://{first['socket']}"
    assert first["dir"] == base / "1" and stat.S_IMODE(first["dir"].stat().st_mode) == 0o700
    # The old in-commons location is a symlink to the short socket; indexes are stable and recorded.
    assert first["link"] == root / "service" / "board" / "agent_one" / "board.sock"
    assert first["link"].is_symlink() and Path(os.readlink(first["link"])) == first["socket"]
    assert boardservice.provision(root, "agent_one")["socket"] == first["socket"]
    state = boardservice.socket_state(root)["agents"]
    assert {k: v["index"] for k, v in state.items()} == {"agent_one": 1, "agent_two": 2}
    # The service's own environment is authoritative; dispatch reuses the recorded path.
    monkeypatch.setenv(boardservice.SOCKET_ROOT_ENV, str(tmp_path / "s"))
    bound = boardservice.provision(root, "agent_one", bind=True)
    assert bound["socket"] == (tmp_path / "s").resolve() / digest / "1" / "1.sock"
    monkeypatch.delenv(boardservice.SOCKET_ROOT_ENV)
    assert boardservice.provision(root, "agent_one")["socket"] == bound["socket"]
    assert Path(os.readlink(bound["link"])) == bound["socket"]


def test_socket_paths_over_the_platform_limit_are_refused_by_name(demo, tmp_path, monkeypatch):
    assert boardservice.socket_limit("darwin") == 104 and boardservice.socket_limit("freebsd14") == 104
    assert boardservice.socket_limit("linux") == 108
    folder = Path("/colloquy-no-such-directory")  # absent, so not resolved: the arithmetic is host-independent
    room = 103 - len(os.fsencode(folder)) - 1  # bytes left for the name under a 104-byte limit (NUL included)
    assert boardservice.check_socket_path(folder / ("s" * room), "darwin") == folder / ("s" * room)
    with pytest.raises(DawError, match="socket_path_too_long"):
        boardservice.check_socket_path(folder / ("s" * (room + 1)), "darwin")
    boardservice.check_socket_path(folder / ("s" * (room + 4)), "linux")  # 108 on Linux
    with pytest.raises(DawError, match="socket_path_too_long"):
        boardservice.check_socket_path(folder / ("s" * (room + 5)), "linux")
    root, _ = demo
    monkeypatch.setenv(boardservice.SOCKET_ROOT_ENV, str(tmp_path / ("long" * 30)))
    with pytest.raises(DawError, match="socket_path_too_long") as refused:
        BoardService(root)  # refused at startup, before any agent is served
    assert boardservice.SOCKET_ROOT_ENV in refused.value.detail


def test_board_service_agents_returns_public_fields_only(service):
    root, ctx, _, _ = service
    alice = ctx["agents"]["alice"]
    rows = agent_client(root, alice).call("agents", {})
    assert {r["id"] for r in rows} >= set(ctx["agents"].values())
    listed = json.dumps(rows)
    with Community(root) as board:
        for row in board.rows("SELECT trial,native_session FROM agent WHERE trial IS NOT NULL"):
            assert row["trial"] not in listed and (not row["native_session"] or row["native_session"] not in listed)
    assert str(root) not in listed
    assert all(set(r) <= {"id", "name", "kind", "parent", "created", "harness", "model", "effort", "started", "profile"}
               for r in rows)
