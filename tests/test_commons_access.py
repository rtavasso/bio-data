"""Spec v2 V9, private boards and multi-tenant safety: read policy, membership, the operator audit log, per-agent
container uids and disk quotas, and rate limits that survive restarts."""
import json
import os
import shutil
import stat
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from daw.commons import access, accounts, boardservice, participation, sandbox, tenants
from daw.commons.app import ROUTER_MODULES, create_app
from daw.commons.archive import Archive
from daw.commons.participants import add_participant
from daw.community import Community
from daw.util import DawError

WRITE = {"X-Colloquy-Request": "1"}


def client(root, **options):
    return TestClient(create_app(root, static_dir=root / "missing", **options))


def person(root, name, kind="human"):
    with Community(root) as board:
        pid = add_participant(board, name, kind, profile={"display_name": name})["id"]
        return pid, accounts.issue_token(board, "operator", pid, "test")["token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def set_policy(root, value):
    (root / "commons.toml").write_text(f'[access]\nread = "{value}"\n')


def get_routes():
    """Every GET route of the app with its path parameters filled with placeholders."""
    import importlib
    import re
    paths = set()
    for name in ROUTER_MODULES:
        for route in importlib.import_module(name).router.routes:
            if "GET" in getattr(route, "methods", ()):
                paths.add(re.sub(r"\{[^}]+\}", "x", route.path))
    return sorted(paths)


# ---------------------------------------------------------------------------- read policy

def test_policy_comes_from_commons_toml_and_is_validated(tmp_path):
    assert access.policy(tmp_path) == "public"
    set_policy(tmp_path, "members")
    assert access.policy(tmp_path) == "members"
    assert access.policy(tmp_path, "private") == "private"
    set_policy(tmp_path, "secret")
    with pytest.raises(DawError, match="invalid_commons_config"):
        access.policy(tmp_path)
    (tmp_path / "commons.toml").write_text('[access]\nwho = "x"\n')
    with pytest.raises(DawError, match="invalid_commons_config"):
        access.policy(tmp_path)


def test_public_commons_reads_anonymously_as_before(demo):
    root, ctx = demo
    http = client(root, mode="accounts")
    assert http.get("/api/posts").status_code == 200
    assert http.get(f"/api/posts/{ctx['posts']['finding']}").status_code == 200
    assert http.get("/api/access").json()["read"] == "public"


@pytest.mark.parametrize("policy", ["members", "private"])
def test_every_get_route_refuses_anonymous_readers(demo, policy):
    """Every GET route (SSE, blobs, artifact bytes, uploads, exports, federation included) is guarded."""
    root, ctx = demo
    set_policy(root, policy)
    http = client(root, mode="accounts")
    open_paths = {"/api/health", "/api/access"}
    checked = 0
    for path in get_routes():
        if path in open_paths:
            continue
        response = http.get(path)
        assert response.status_code == 401, (path, response.status_code)
        assert response.json()["error"] == "authentication_required" and response.json()["read_policy"] == policy
        checked += 1
    assert checked > 60
    # The concrete byte and stream endpoints, with real identifiers.
    artifact = ctx["artifacts"]["contrast"]
    for path in (f"/api/artifacts/{artifact}/bytes", "/api/events?once=true", "/api/events/log",
                 f"/api/map/node/{ctx['posts']['finding']}", "/api/federation", "/api/exports",
                 "/api/me/inbox/stream?once=true"):
        assert http.get(path).status_code == 401, path
    # Health stays up for container checks but says nothing about the board.
    health = http.get("/api/health").json()
    assert health["ok"] and health["read_policy"] == policy and "sequence" not in health
    # Writes are refused too (the policy guards every /api request).
    assert http.post("/api/posts", headers=WRITE, json={"title": "t", "body": "b"}).status_code == 401


def test_members_policy_admits_any_authenticated_participant(demo):
    root, ctx = demo
    set_policy(root, "members")
    _, token = person(root, "rhea")
    http = client(root, mode="accounts")
    assert http.get("/api/posts", headers=bearer(token)).status_code == 200
    assert http.get(f"/api/artifacts/{ctx['artifacts']['contrast']}/bytes", headers=bearer(token)).status_code == 200
    stream = http.get("/api/events?once=true", headers=bearer(token))
    assert stream.status_code == 200 and "data: " in stream.text
    health = http.get("/api/health", headers=bearer(token)).json()
    assert health["sequence"] > 0
    # Cookie sessions work the same way.
    login = http.post("/api/session", headers=WRITE, json={"token": token})
    assert login.status_code == 200
    assert http.get("/api/posts").status_code == 200
    # A revoked token is refused at the next request.
    with Community(root) as board:
        credential = board.one("SELECT id FROM credential ORDER BY created DESC LIMIT 1")["id"]
        accounts.revoke_token(board, "operator", credential)
    http.cookies.clear()
    assert http.get("/api/posts", headers=bearer(token)).status_code == 401


def test_private_policy_admits_operators_and_granted_members_only(demo):
    root, ctx = demo
    set_policy(root, "private")
    rhea, token = person(root, "rhea")
    ops, ops_token = person(root, "ops", "operator")
    http = client(root, mode="accounts")
    refused = http.get("/api/posts", headers=bearer(token))
    assert refused.status_code == 403 and refused.json()["error"] == "not_a_member"
    # The person can still see who they are and that they are not a member.
    me = http.get("/api/me", headers=bearer(token))
    assert me.status_code == 200 and me.json()["id"] == rhea
    standing = http.get("/api/access", headers=bearer(token)).json()
    assert standing == {**standing, "read": "private", "authenticated": True, "member": False, "reason": "not_a_member"}
    assert http.get("/api/posts", headers=bearer(ops_token)).status_code == 200  # operators always read
    # Operators manage membership through the write path; people cannot.
    assert http.post("/api/members", headers=bearer(token), json={"participant": rhea}).status_code == 403
    granted = http.post("/api/members", headers=bearer(ops_token), json={"participant": "rhea", "reason": "lab member"})
    assert granted.status_code == 200 and granted.json()["state"] == "member"
    assert http.get("/api/posts", headers=bearer(token)).status_code == 200
    assert http.get(f"/api/blobs/library/{'0' * 64}", headers=bearer(token)).status_code != 403
    listed = http.get("/api/members", headers=bearer(ops_token)).json()
    assert [m["participant"] for m in listed["items"]] == [rhea] and listed["read_policy"] == "private"
    assert http.get("/api/members", headers=bearer(token)).status_code == 403
    revoked = http.post(f"/api/members/{rhea}/revoke", headers=bearer(ops_token), json={"reason": "left"})
    assert revoked.status_code == 200 and revoked.json()["state"] == "revoked"
    assert http.get("/api/posts", headers=bearer(token)).status_code == 403
    with Community(root) as board:
        kinds = [r["kind"] for r in board.rows("SELECT kind FROM event WHERE kind LIKE 'member_%' ORDER BY seq")]
        assert kinds == ["member_granted", "member_revoked"]
        # The projection is rebuildable from events.
        before = board.rows("SELECT participant,state,actor,reason,event_seq FROM membership")
        assert access.rebuild(board) == 1
        assert board.rows("SELECT participant,state,actor,reason,event_seq FROM membership") == before
        with pytest.raises(DawError, match="agents_use_the_cli"):
            access.grant(board, ops, ctx["agents"]["alice"])


def test_revocation_ends_an_open_event_stream(demo):
    """The middleware re-checks access while a long response streams and ends it once access is revoked."""
    import asyncio
    root, _ = demo
    set_policy(root, "private")
    rhea, token = person(root, "rhea")
    with Community(root) as board:
        access.grant(board, "operator", rhea)
    settings = SimpleNamespace(root=root.resolve(), mode="accounts", access="private")
    sent, chunks = [], iter([b"one", b"two", b"three"])

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        for chunk in chunks:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
            if chunk == b"one":
                with Community(root) as board:
                    access.revoke(board, "operator", rhea)
            message = await receive()
            if message["type"] == "http.disconnect":
                return
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    from fastapi import FastAPI
    holder = FastAPI()
    holder.state.settings = settings
    scope = {"type": "http", "method": "GET", "path": "/api/events", "root_path": "", "query_string": b"",
             "headers": [(b"authorization", f"Bearer {token}".encode())], "app": holder}
    asyncio.run(access.ReadPolicy(app, settings, recheck_seconds=0)(scope, receive, send))
    bodies = [m.get("body") for m in sent if m["type"] == "http.response.body"]
    assert bodies == [b"one", b""] and sent[-1]["more_body"] is False


def test_local_mode_is_unaffected_by_the_policy(demo):
    root, _ = demo
    set_policy(root, "private")
    http = client(root)  # local mode
    assert http.get("/api/posts").status_code == 200
    assert http.get("/api/access").json()["read"] == "local"


def test_tenants_honour_their_own_read_policy(two_commons, tmp_path):
    a, b, ctx = two_commons
    set_policy(b, "members")
    config = tmp_path / "tenants.toml"
    config.write_text(f'[tenants.lab-a]\nroot = "{a}"\ntitle = "Lab A"\nread = "private"\n'
                      f'[tenants.lab-b]\nroot = "{b}"\ntitle = "Lab B"\n'
                      f'[tenants.lab-c]\nroot = "{tmp_path / "c"}"\ntitle = "Lab C"\n')
    shutil.copytree(a, tmp_path / "c", symlinks=True)
    (tmp_path / "c" / "commons.toml").unlink(missing_ok=True)
    host = TestClient(tenants.create_host_app(tenants.load(config)))
    assert host.get("/c/lab-a/api/posts").status_code == 401
    assert host.get("/c/lab-b/api/posts").status_code == 401
    assert host.get("/c/lab-c/api/posts").status_code == 200
    _, token_b = person(b, "rhea")
    assert host.get("/c/lab-b/api/posts", headers=bearer(token_b)).status_code == 200
    # A lab-b token means nothing in lab-a.
    assert host.get("/c/lab-a/api/posts", headers=bearer(token_b)).status_code == 401
    health = {t["name"]: t for t in host.get("/api/health").json()["tenants"]}
    assert "sequence" not in health["lab-a"] and "sequence" not in health["lab-b"] and "sequence" in health["lab-c"]
    index = host.get("/").text
    assert "Lab A" not in index and "(private)" in index and "Lab C" in index
    config.write_text(f'[tenants.lab-a]\nroot = "{a}"\nread = "secret"\n')
    with pytest.raises(DawError, match="invalid_commons_config"):
        tenants.load(config)


@pytest.fixture
def two_commons(demo_template, tmp_path):
    root, ctx = demo_template
    a, b = tmp_path / "lab-a", tmp_path / "lab-b"
    shutil.copytree(root, a, symlinks=True)
    shutil.copytree(root, b, symlinks=True)
    return a, b, ctx


def test_cohort_copy_private_read_policy(cohort_copy):
    """On the real board: a private copy refuses anonymous reads of every post and serves them to a member."""
    set_policy(cohort_copy, "private")
    rhea, token = person(cohort_copy, "rhea")
    with Community(cohort_copy) as board:
        access.grant(board, "operator", rhea)
        post = board.one("SELECT id FROM post ORDER BY seq LIMIT 1")["id"]
    http = client(cohort_copy, mode="accounts")
    assert http.get(f"/api/posts/{post}").status_code == 401
    assert http.get("/api/map").status_code == 401
    assert http.get(f"/api/posts/{post}", headers=bearer(token)).status_code == 200
    assert http.get("/api/posts?limit=200", headers=bearer(token)).json()["total"] > 0


# ---------------------------------------------------------------------------- audit log

def test_audit_log_is_operator_only_filtered_and_paged(demo):
    root, ctx = demo
    rhea, token = person(root, "rhea")
    _, ops_token = person(root, "ops", "operator")
    with Community(root) as board:
        participation.mark(board, rhea, "post", ctx["posts"]["finding"], "disputed", "n", [])
    http = client(root, mode="accounts")
    assert http.get("/api/audit", headers=bearer(token)).status_code == 403
    assert http.get("/api/audit").status_code == 401
    page = http.get("/api/audit?limit=5", headers=bearer(ops_token)).json()
    with Archive(root) as view:
        total = view.one("SELECT count(*) AS n FROM event")["n"]
        latest = view.sequence()
    assert page["total"] == total and len(page["items"]) == 5 and page["items"][0]["seq"] == latest
    seqs = [e["seq"] for e in page["items"]]
    assert seqs == sorted(seqs, reverse=True)
    following = http.get(f"/api/audit?limit=5&before={page['next_before']}", headers=bearer(ops_token)).json()
    assert following["items"][0]["seq"] < seqs[-1]
    marks = http.get("/api/audit?kind=mark_recorded", headers=bearer(ops_token)).json()
    with Archive(root) as view:
        recorded = view.one("SELECT count(*) AS n FROM event WHERE kind='mark_recorded'")["n"]
    assert {e["kind"] for e in marks["items"]} == {"mark_recorded"} and marks["facets"] == {"mark_recorded": recorded}
    mine = http.get("/api/audit?participant=rhea", headers=bearer(ops_token)).json()
    assert mine["items"] and all(rhea in json.dumps(e["body"]) for e in mine["items"])
    assert http.get("/api/audit?until=2000-01-01T00:00:00Z", headers=bearer(ops_token)).json()["items"] == []
    assert http.get("/api/audit?since=2000-01-01T00:00:00Z", headers=bearer(ops_token)).json()["total"] == total
    assert http.get("/api/audit?since=nonsense", headers=bearer(ops_token)).status_code == 400


def test_audit_log_on_the_cohort(cohort):
    from daw.commons.audit import audit_log
    with Archive(cohort) as view:
        operator = view.participant("operator")
        everything = audit_log(view, operator, limit=500)
        assert everything["total"] == view.one("SELECT count(*) AS n FROM event")["n"]
        assert sum(everything["facets"].values()) == everything["total"]
        published = audit_log(view, operator, kinds=["published"], limit=500)
        assert published["total"] == view.one("SELECT count(*) AS n FROM post")["n"]


# ---------------------------------------------------------------------------- per-agent uids and disk quotas

class Adapter:
    def auth_files(self, env):
        return ()

    def hosts(self, config):
        return ()


def _trial(root, agent):
    with Community(root) as board:
        return board.trial(board.agent(agent))


def test_per_agent_uids_are_deterministic_recorded_and_in_the_argv(demo):
    root, ctx = demo
    alice, bob = ctx["agents"]["alice"], ctx["agents"]["bob"]
    (root / "sandbox.toml").write_text(f'engine = "docker"\nimage = "agent:1"\nagent_uid = "per-agent"\n'
                                       f'uid_base = 300000\nagent_gid = {os.getgid()}\n')
    config = sandbox.load(root)
    first = sandbox.agent_user(config, root, alice)
    second = sandbox.agent_user(config, root, bob)
    assert first["uid"] != second["uid"] and first["uid"] == 300000 + first["index"]
    assert sandbox.agent_user(config, root, alice) == first  # stable
    recorded = json.loads((root / "service" / "sandbox" / "agents.json").read_text())["agents"]
    assert recorded[alice]["index"] == first["index"] and recorded[bob]["index"] == second["index"]
    trial = _trial(root, alice)
    # The checkout is the dispatcher's: not writable by the agent's uid unless group-writable for its gid.
    for path in (trial, trial / "workspace"):
        path.chmod(path.stat().st_mode & ~0o020)
    with pytest.raises(DawError, match="agent_uid_checkout_not_writable") as refused:
        sandbox.preflight(sandbox.policy(root), root, alice, trial)
    assert f"chown -R {first['uid']}:{first['gid']}" in refused.value.detail
    for path in (trial, trial / "workspace"):
        path.chmod(path.stat().st_mode | 0o020)
        os.chown(path, -1, os.getgid())
    decision = sandbox.preflight(sandbox.policy(root), root, alice, trial)
    env = {"BIO_AGENT": alice, "PATH": "/usr/bin"}
    argv, _, receipt = sandbox.apply(decision, ["claude"], env, trial=trial, board_root=root, adapter=Adapter(),
                                     agent_config={}, run="run_uid")
    assert argv[argv.index("--user") + 1] == f"{first['uid']}:{first['gid']}"
    assert receipt["user"] == first
    # The board socket directory is shared with the agents' group, never world-readable.
    socket_dir = boardservice.provision(root, alice, group=os.getgid())["dir"]
    assert stat.S_IMODE(socket_dir.stat().st_mode) == 0o750 and socket_dir.stat().st_gid == os.getgid()


def test_dispatcher_uid_stays_the_default(demo):
    root, ctx = demo
    (root / "sandbox.toml").write_text('engine = "docker"\nimage = "agent:1"\n')
    trial = _trial(root, ctx["agents"]["alice"])
    decision = sandbox.preflight(sandbox.policy(root), root, ctx["agents"]["alice"], trial)
    argv, _, receipt = sandbox.apply(decision, ["claude"], {"BIO_AGENT": ctx["agents"]["alice"], "PATH": "/usr/bin"},
                                     trial=trial, board_root=root, adapter=Adapter(), agent_config={}, run="run_d")
    assert argv[argv.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"
    assert receipt["user"]["policy"] == "dispatcher" and receipt["disk_quota"] is None
    assert "--storage-opt" not in argv
    bad = root / "sandbox.toml"
    for body in ('agent_uid = "root"\n', 'uid_base = 10\n', 'disk_quota_bytes = -1\n', 'disk_quota_method = "magic"\n'):
        bad.write_text(body)
        with pytest.raises(DawError, match="invalid_sandbox_config"):
            sandbox.load(root)


def test_measured_quota_refuses_an_over_quota_checkout_and_records_it(demo):
    from daw.commons.demo import scripted_runtime
    from daw.community_runtime import dispatch
    root, ctx = demo
    alice = ctx["agents"]["alice"]
    trial = _trial(root, alice)
    usage = sandbox.checkout_usage(trial)
    (root / "sandbox.toml").write_text(f'engine = "docker"\nimage = "agent:1"\ndisk_quota_bytes = {usage + 4096}\n')
    decision = sandbox.preflight(sandbox.policy(root), root, alice, trial)
    assert decision["disk_quota"]["usage_before"] == usage and decision["disk_quota"]["method"] == "measure"
    (trial / "workspace" / "filler.bin").write_bytes(b"x" * 8192)
    with pytest.raises(DawError, match="disk_quota_exceeded"):
        sandbox.preflight(sandbox.policy(root), root, alice, trial)
    # Through dispatch: refused before any state change, with a board event.
    with Community(root) as board:
        request = board.ask(alice, "operator", "Quota check.")
        with scripted_runtime(root) as (harness, _):
            with pytest.raises(DawError, match="disk_quota_exceeded"):
                dispatch(board, request["id"], harness)
        assert board.one("SELECT state FROM request WHERE id=?", (request["id"],))["state"] == "pending"
        event = json.loads(board.one("SELECT body FROM event WHERE kind='disk_quota_exceeded'")["body"])
        assert event["agent"] == alice and event["stage"] == "dispatch"
    # After a turn the checkout is measured again.
    receipt, over = sandbox.after_turn({"disk_quota": {"method": "measure", "bytes": usage + 4096}}, trial)
    assert over == receipt["disk_quota"]["usage_after"] > usage + 4096


def test_storage_opt_quota_is_probed_and_refused_where_unsupported(demo):
    root, ctx = demo
    alice = ctx["agents"]["alice"]
    trial = _trial(root, alice)
    (root / "sandbox.toml").write_text('engine = "docker"\nimage = "agent:1"\ndisk_quota_bytes = 1073741824\n'
                                       'disk_quota_method = "storage-opt"\n')

    def engine(driver, backing):
        def run(argv, **_):
            assert argv[:2] == ["docker", "info"]
            info = {"Driver": driver, "DriverStatus": [["Backing Filesystem", backing]]}
            return SimpleNamespace(returncode=0, stdout=json.dumps(info), stderr="")
        return run
    with pytest.raises(DawError, match="disk_quota_unsupported"):
        sandbox.preflight(sandbox.policy(root), root, alice, trial, run=engine("overlay2", "extfs"))
    decision = sandbox.preflight(sandbox.policy(root), root, alice, trial, run=engine("overlay2", "xfs"))
    argv, _, receipt = sandbox.apply(decision, ["claude"], {"BIO_AGENT": alice, "PATH": "/usr/bin"}, trial=trial,
                                     board_root=root, adapter=Adapter(), agent_config={}, run="run_q")
    assert argv[argv.index("--storage-opt") + 1] == "size=1073741824"
    assert receipt["disk_quota"]["method"] == "storage-opt" and "usage_before" in receipt["disk_quota"]


def test_xfs_project_quota_is_verified_or_refused(demo):
    root, ctx = demo
    alice = ctx["agents"]["alice"]
    trial = _trial(root, alice)
    (root / "sandbox.toml").write_text('engine = "docker"\nimage = "agent:1"\ndisk_quota_bytes = 1073741824\n'
                                       'disk_quota_method = "xfs-project"\nxfs_project_base = 70000\n')
    decision = sandbox.policy(root)
    with pytest.raises(DawError, match="disk_quota_unsupported"):
        sandbox.preflight(decision, root, alice, trial, platform="darwin")
    with pytest.raises(DawError, match="disk_quota_not_configured") as refused:
        sandbox.preflight(decision, root, alice, trial, platform="linux", projid=lambda path: 0)
    expected = 70000 + sandbox.agent_index(root, alice)
    assert f"project -s -p {trial} {expected}" in refused.value.detail
    ok = sandbox.preflight(decision, root, alice, trial, platform="linux", projid=lambda path: expected)
    assert ok["disk_quota"]["project"] == expected and ok["disk_quota"]["enforcement"].startswith("hard")


# ---------------------------------------------------------------------------- rate limits persist on the board

def test_every_rate_limit_survives_a_restart(demo):
    """Posts, marks, uploads, saved views and logins are all counted from board records, so a new app process on
    the same board sees the same counts."""
    root, ctx = demo
    (root / "commons.toml").write_text("[limits]\nposts_per_hour = 1\nmarks_per_hour = 1\nuploads_per_hour = 1\n"
                                       "views_per_hour = 1\n[login]\nattempts = 2\nwindow_seconds = 600\n")
    with Community(root) as board:
        add_participant(board, "rhea", "human")
    first = client(root, local_user="rhea")
    assert first.post("/api/posts", headers=WRITE, json={"title": "t", "body": "b"}).status_code == 200
    assert first.post("/api/marks", headers=WRITE, json={"target_kind": "post", "target_id": ctx["posts"]["finding"],
                                                         "kind": "disputed", "note": "n"}).status_code == 200
    assert first.post("/api/uploads", headers={**WRITE, "X-Filename": "a.txt", "Content-Type": "text/plain"},
                      content=b"abc").status_code == 200
    assert first.post("/api/views", headers=WRITE, json={"since": "2020-01-01T00:00:00Z"}).status_code == 200
    accounts_app = client(root, mode="accounts")
    for _ in range(2):
        assert accounts_app.post("/api/session", headers=WRITE, json={"token": "colloquy_wrong"}).status_code == 401
    # Restart: new app objects, same board.
    second = client(root, local_user="rhea")
    assert second.post("/api/posts", headers=WRITE, json={"title": "t2", "body": "b"}).status_code == 429
    assert second.post("/api/marks", headers=WRITE, json={"target_kind": "post", "target_id": ctx["posts"]["reply"],
                                                          "kind": "disputed", "note": "n"}).status_code == 429
    assert second.post("/api/uploads", headers={**WRITE, "X-Filename": "b.txt", "Content-Type": "text/plain"},
                       content=b"abc").status_code == 429
    assert second.post("/api/views", headers=WRITE, json={"since": "2021-01-01T00:00:00Z"}).status_code == 429
    restarted = client(root, mode="accounts")
    assert restarted.post("/api/session", headers=WRITE, json={"token": "colloquy_wrong"}).status_code == 429
    with Archive(root) as view:
        assert view.one("SELECT count(*) AS n FROM login_failure")["n"] >= 2


def test_audit_cli_and_member_cli(demo):
    from typer.testing import CliRunner

    from daw.commons.cli import app
    root, _ = demo
    rhea, _ = person(root, "rhea")
    runner = CliRunner()
    granted = runner.invoke(app, ["--root", str(root), "member", "grant", "rhea", "--reason", "lab"])
    assert granted.exit_code == 0, granted.output
    assert json.loads(granted.output)["state"] == "member"
    listed = json.loads(runner.invoke(app, ["--root", str(root), "member", "list"]).output)
    assert [m["participant"] for m in listed["items"]] == [rhea] and listed["read_policy"] == "public"
    audit = json.loads(runner.invoke(app, ["--root", str(root), "audit-log", "--kind", "member_granted"]).output)
    assert [e["kind"] for e in audit["items"]] == ["member_granted"]
    shown = json.loads(runner.invoke(app, ["--root", str(root), "access"]).output)
    assert shown["read_policy"] == "public"
