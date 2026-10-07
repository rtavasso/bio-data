import io
import json
import sqlite3
import sys
import tarfile
import uuid
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daw.artifacts import artifact_info, attach_artifact, register_artifact
from daw.bio_cli import app
from daw.catalog import Workspace
from daw.community import Community, exclusive
from daw.community_runtime import add_agent, dispatch, fork_agent, recover, retry
from daw.community_service import pending_deliveries, serve
from daw.exchange import transfer_artifacts
from daw.inspectors import extract_members
from daw.models import Asset
from daw.substrate_models import ArtifactRegistration, Derivation, ObjectInput
from daw.util import DawError, file_hash
from daw.work import create_question


def no_reserve(root):
    (root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0\n")


@pytest.fixture
def board(tmp_path):
    board = Community.create(tmp_path / "community")
    no_reserve(board.library.root)
    board.library.close()
    board.library = Workspace(board.root / "library")
    yield board
    board.close()


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    Workspace.create(root).close()
    no_reserve(root)
    ws = Workspace(root)
    path = tmp_path / "expression.tsv"
    path.write_text("gene\tvalue\nPMP22\t2\nSOX10\t4\n")
    imported = ws.local_asset(path, "Synthetic unrelated sequencing study")
    question = create_question(ws, "PMP22 exploratory measurement")
    code = ws.put_bytes(b"# saved local analysis, never run by the publication tool\n")
    spec = ArtifactRegistration(title="PMP22 expression slice", summary="Fixture; expression is not promoter output",
        derivation=Derivation(inputs=[ObjectInput(blob=imported["blob"], source_identity=imported["asset_revision"])],
                              code=[code], parameters={"selection": "PMP22"}, references=[], environment={"fixture": True}))
    result = tmp_path / "result.tsv"
    result.write_text("gene\tvalue\nPMP22\t2\n")
    artifact = register_artifact(ws, result, spec, question=question["question"])
    yield ws, question, artifact, spec
    ws.close()


def test_selected_publication_survives_source_loss_and_reuses_exact_derivation(board, source, tmp_path):
    ws, question, artifact, spec = source
    secret = ws.put_bytes(b"unpublished unrelated notes")
    post = board.publish("operator", "PMP22 RNA", "An exploratory result with source limits.",
                         workspace=ws.root, artifacts=[artifact["artifact"]], question=question["question"], request_key="first")
    assert board.find("PMP22")["total"] == 1
    assert not board.library.one("SELECT sha256 FROM blob WHERE sha256=?", (secret,))
    assert board.library.rows("PRAGMA foreign_key_check") == []
    assert not board.library.rows("SELECT * FROM current_asset")
    assert not board.library.rows("SELECT * FROM current_curation")
    target = Workspace.create(tmp_path / "reader")
    target.close()
    no_reserve(tmp_path / "reader")
    target = Workspace(tmp_path / "reader")
    q2 = create_question(target, "Follow-up on composition")
    # Neither source folder nor its mutable files are needed to consume the post.
    original = ws.blob_path(artifact["output_blob"])
    original.chmod(0o644)
    original.write_text("changed source")
    receipt = board.fetch(post["id"], target.root, q2["question"])
    info = artifact_info(target, artifact["artifact"])
    assert Path(info["path"]).read_text() == "gene\tvalue\nPMP22\t2\n"
    assert info["manifest"]["derivation"] == spec.derivation.model_dump()
    assert receipt["relationship"] == "considered"
    assert target.one("SELECT relationship FROM question_artifact")["relationship"] == "considered"
    assert target.asset(spec.derivation.inputs[0].source_identity)["blob"] == spec.derivation.inputs[0].blob
    attach_artifact(target, q2["question"], artifact["artifact"], "reused")
    assert target.rows("PRAGMA foreign_key_check") == []
    target.close()


def test_nested_artifact_closure_and_corruption_rejection(board, source, tmp_path):
    ws, _, first, spec = source
    spec = spec.model_copy(update={"derivation": spec.derivation.model_copy(update={
        "inputs": [ObjectInput(blob=first["output_blob"], source_identity=first["artifact"])]})})
    output = tmp_path / "second.tsv"
    output.write_text("PMP22\t4\n")
    second = register_artifact(ws, output, spec)
    with board.library.writer():
        result = transfer_artifacts(ws, board.library, [second["artifact"]])
    assert result["artifacts"] == [second["artifact"]]
    assert len(board.library.rows("SELECT * FROM artifact")) == 2
    bad = ws.blob_path(first["output_blob"])
    bad.chmod(0o644)
    bad.write_text("corrupted")
    before = len(board.rows("SELECT * FROM post"))
    with pytest.raises(DawError, match="integrity"):
        board.publish("operator", "bad", "bad result", workspace=ws.root, artifacts=[second["artifact"]])
    assert len(board.rows("SELECT * FROM post")) == before


def test_publication_preserves_nested_archive_assets_and_bytes(board, source, tmp_path):
    ws, question, _, spec = source

    def archive(name, data):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as bundle:
            item = tarfile.TarInfo(name)
            item.size = len(data)
            bundle.addfile(item, io.BytesIO(data))
        return stream.getvalue()

    table = b"gene\tvalue\nPMP22\t2\n"
    path = tmp_path / "outer.tar"
    path.write_bytes(archive("inner.tar", archive("table.tsv", table)))
    outer = ws.local_asset(path)
    inner = extract_members(ws, outer["asset_revision"], ["inner.tar"])[0]
    member = extract_members(ws, inner["asset_revision"], ["table.tsv"])[0]
    spec = spec.model_copy(update={"derivation": spec.derivation.model_copy(update={
        "inputs": [ObjectInput(blob=member["blob"], source_identity=member["asset_revision"])]})})
    result = tmp_path / "result.tsv"
    result.write_bytes(table)
    registered = register_artifact(ws, result, spec)
    post = board.publish("operator", "Archive-backed result", "Exact extracted source.",
                         workspace=ws.root, question=question["question"], artifacts=[registered["artifact"]])
    for original in (outer, inner, member):
        assert board.library.asset(original["asset_revision"])["blob"] == original["blob"]
        assert board.library.blob_path(original["blob"]).read_bytes() == ws.blob_path(original["blob"]).read_bytes()
    assert board.show(post["id"])["content"]["evidence"]["artifacts"] == [registered["artifact"]]
    assert board.library.rows("PRAGMA foreign_key_check") == []


def test_publication_rejects_mismatched_archive_parent_bytes(board, source, tmp_path):
    ws, _, first, spec = source
    parent = ws.asset(spec.derivation.inputs[0].source_identity)
    member = ws.register_asset(ws.bundle_for(parent), "archive", Asset(native_id="bad-member", name="member.tsv",
        selector={"chain": [{"parent": parent["id"], "blob": ws.put_bytes(b"different bytes"), "member": "member.tsv"}]}),
        blob=parent["blob"])
    spec = spec.model_copy(update={"derivation": spec.derivation.model_copy(update={
        "inputs": [ObjectInput(blob=parent["blob"], source_identity=member)]})})
    registered = register_artifact(ws, ws.blob_path(first["output_blob"]), spec)
    with pytest.raises(DawError, match="archive_parent_blob_mismatch"):
        board.publish("operator", "Invalid source", "Do not publish.", workspace=ws.root, artifacts=[registered["artifact"]])
    assert not board.rows("SELECT * FROM post")


def test_posts_replies_corrections_keys_and_search_rebuild(board):
    first = board.publish("operator", "RNA decay", "Initial limited evidence.", request_key="stable")
    again = board.publish("operator", "RNA decay", "Initial limited evidence.", request_key="stable")
    assert first["id"] == again["id"]
    with pytest.raises(DawError, match="post_key_conflict"):
        board.publish("operator", "RNA decay", "Different evidence.", request_key="stable")
    correction = board.publish("operator", "Correction", "Developmental context does not transfer.", supersedes=first["id"], parent=first["id"])
    assert board.show(first["id"])["replies"][0]["id"] == correction["id"]
    assert board.find("RNA")["items"][0]["superseded_by"] == [{"id": correction["id"]}]
    with pytest.raises(sqlite3.IntegrityError, match="immutable post"), board.db:
        board.db.execute("DELETE FROM post WHERE id=?", (first["id"],))
    with board.library.db:
        board.library.db.execute("DELETE FROM search_fts")
    assert board.find("RNA")["total"] == 0
    result = CliRunner().invoke(app, ["community", "--root", str(board.root), "reindex"])
    assert result.exit_code == 0, result.output
    assert board.find("RNA")["total"] == 1


def test_init_does_not_downgrade_unknown_board_version(board):
    with board.db:
        board.db.execute("PRAGMA user_version=99")
    with pytest.raises(DawError, match="unsupported_community_version"):
        Community.create(board.root)
    assert board.db.execute("PRAGMA user_version").fetchone()[0] == 99


def test_evaluator_does_not_inherit_live_community_identity(tmp_path, monkeypatch):
    from benchmarks.agent.runner import subject_environment
    monkeypatch.setenv("BIO_COMMUNITY", "/existing/research/community")
    monkeypatch.setenv("BIO_AGENT", "existing-researcher")
    env = subject_environment(tmp_path, {"python": sys.executable, "project_environment": "/unused"})
    assert "BIO_COMMUNITY" not in env and "BIO_AGENT" not in env
    assert env["BIO_WORKSPACE"] == str(tmp_path / "workspace")


def fake_hermes(path):
    path.write_text(f"#!{sys.executable}\n" + '''import json, os, sqlite3, sys, uuid
from pathlib import Path
home=Path(os.environ['HERMES_HOME']); trial=Path(os.environ['HERMES_CWD'])
prompt=sys.stdin.read()
assert os.getcwd()==str(trial)
assert os.environ['BIO_AGENT'] in prompt
sid=sys.argv[sys.argv.index('--resume')+1] if '--resume' in sys.argv else 'native_'+uuid.uuid4().hex
db=sqlite3.connect(home/'state.db')
db.execute('CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,cwd TEXT)')
db.execute('CREATE TABLE IF NOT EXISTS messages(session TEXT,body TEXT)')
if '--resume' in sys.argv:
 assert db.execute('SELECT id FROM sessions WHERE id=?',(sid,)).fetchone()
else:
 db.execute('INSERT INTO sessions VALUES(?,?)',(sid,str(trial)))
db.execute('INSERT INTO messages VALUES(?,?)',(sid,prompt)); db.commit()
n=db.execute('SELECT count(*) FROM messages WHERE session=?',(sid,)).fetchone()[0]
print(json.dumps({'type':'system','session_id':sid}))
failed=(trial/'fail-next').exists()
if failed: (trial/'fail-next').unlink()
print(json.dumps({'type':'result','exit_code':1 if failed else 0,'text':f'Fixture answer with {n} stored turns.'}))
db.close()
raise SystemExit(1 if failed else 0)
''')
    path.chmod(0o755)
    return str(path)


def fake_session(executable, home, identity, cwd, *, fork=False):
    with sqlite3.connect(home / "state.db") as db:
        assert db.execute("SELECT id FROM sessions WHERE id=?", (identity,)).fetchone()
        if fork:
            child = "native_" + uuid.uuid4().hex
            db.execute("INSERT INTO sessions VALUES(?,?)", (child, str(cwd)))
            db.execute("INSERT INTO messages SELECT ?,body FROM messages WHERE session=?", (child, identity))
        else:
            child = identity
            db.execute("UPDATE sessions SET cwd=? WHERE id=?", (str(cwd), child))
    return {"session": child, "parent": identity if fork else None, "forked": fork, "cwd": str(cwd)}


def test_delivery_resume_fork_and_isolated_files(board, source, tmp_path, monkeypatch):
    monkeypatch.setenv("DAW_LIVE", "1")
    monkeypatch.setattr("daw.community_runtime.native_session", fake_session)
    ws, question, _, _ = source
    alice = add_agent(board, "alice", seed_workspace=ws.root)
    executable = fake_hermes(tmp_path / "hermes")
    first = board.ask("alice", "operator", "Investigate the fixture.", request_key="ask-one")
    assert board.ask("alice", "operator", "Investigate the fixture.", request_key="ask-one")["id"] == first["id"]
    first = dispatch(board, first["id"], executable)
    assert first["state"] == "completed"
    assert "1 stored turns" in board.show(first["answer"])["content"]["body"]
    alice = board.agent(alice["id"])
    fresh = fork_agent(board, "alice", "fresh")
    assert fresh["native_session"] is None and fresh["parent"] == alice["id"]
    assert (board.trial(fresh) / "workspace/questions" / question["question"] / "LABBOOK.md").is_file()
    child = fork_agent(board, "alice", "child", inherit_conversation=True)
    parent_trial, child_trial = board.trial(alice), board.trial(child)
    notebook = Path("workspace/questions") / question["question"] / "LABBOOK.md"
    original = file_hash(parent_trial / notebook)
    (child_trial / notebook).write_text("Child's independent investigation")
    assert file_hash(parent_trial / notebook) == original
    parent_state = file_hash(parent_trial / ".hermes/state.db")
    child_request = board.ask("child", "operator", "Explore a different hypothesis.")
    assert dispatch(board, child_request["id"], executable)["state"] == "completed"
    assert file_hash(parent_trial / ".hermes/state.db") == parent_state
    child = board.agent(child["id"])
    assert child["native_session"] != alice["native_session"] and child["parent"] == alice["id"]
    follow = board.ask(first["answer"], child["id"], "Explain the scope of your earlier finding.")
    with exclusive(parent_trial.parent / ".session.lock"):
        with pytest.raises(DawError, match="agent_busy"):
            dispatch(board, follow["id"], executable)
        with pytest.raises(DawError, match="agent_busy"):
            fork_agent(board, "alice", "busy-child", inherit_conversation=True)
    follow = dispatch(board, follow["id"], executable)
    assert "2 stored turns" in board.show(follow["answer"])["content"]["body"]
    assert board.agent("alice")["native_session"] == alice["native_session"]
    assert board.inbox("alice") == []
    assert board.inbox("child", sent=True)[0]["answer"] == follow["answer"]
    assert len(board.audit()["attempts"]) == 3
    assert board.rows("SELECT id FROM agent WHERE parent=?", (alice["id"],)).__len__() == 2
    with pytest.raises(DawError, match="request_not_pending"):
        dispatch(board, follow["id"], executable)


def test_failed_attempt_preserves_question_and_explicit_retry(board, source, tmp_path, monkeypatch):
    monkeypatch.setenv("DAW_LIVE", "1")
    monkeypatch.setattr("daw.community_runtime.native_session", fake_session)
    agent = add_agent(board, "a", seed_workspace=source[0].root)
    trial = board.trial(agent)
    (trial / "fail-next").touch()
    request = board.ask("a", "operator", "A pending question")
    executable = fake_hermes(tmp_path / "hermes")
    with pytest.raises(DawError, match="agent_delivery_failed"):
        dispatch(board, request["id"], executable)
    assert board.inbox("a")[0]["state"] == "failed"
    assert board.agent("a")["native_session"]
    retry(board, request["id"])
    result = dispatch(board, request["id"], executable)
    assert result["state"] == "completed"
    assert [a["state"] for a in board.audit()["attempts"]] == ["failed", "completed"]
    for run in board.audit()["attempts"]:
        assert (board.root / run["path"] / "events.jsonl").is_file()


def test_abandoned_recovery_and_live_opt_in(board, source, monkeypatch):
    agent = add_agent(board, "a", seed_workspace=source[0].root)
    request = board.ask("a", "operator", "A pending question")
    monkeypatch.delenv("DAW_LIVE", raising=False)
    with pytest.raises(DawError, match="live_opt_in_required"):
        dispatch(board, request["id"])
    assert board.inbox("a")[0]["state"] == "pending"
    with board.db:
        board.db.execute("UPDATE request SET state='running' WHERE id=?", (request["id"],))
    with exclusive(board.trial(agent).parent / ".session.lock"):
        with pytest.raises(DawError, match="agent_busy"):
            recover(board, request["id"])
    assert recover(board, request["id"])["state"] == "failed"


def test_cli_files_literal_text_and_local_no_credentials(board, tmp_path, monkeypatch):
    monkeypatch.delenv("BIO_AGENT", raising=False)
    body = tmp_path / "post.md"
    body.write_text("A finding with `literal code` and $(literal text).")
    runner = CliRunner()
    result = runner.invoke(app, ["community", "--root", str(board.root), "publish", "Finding", "--body", str(body)])
    assert result.exit_code == 0, result.output
    post = json.loads(result.output)
    assert post["content"]["body"] == body.read_text()
    result = runner.invoke(app, ["community", "--root", str(board.root), "search", "--text", "finding"])
    assert result.exit_code == 0 and json.loads(result.output)["total"] == 1
    monkeypatch.setenv("BIO_AGENT", "fake-agent")
    result = runner.invoke(app, ["community", "--root", str(board.root), "run", "request"])
    assert isinstance(result.exception, DawError)
    assert result.exception.reason == "operator_dispatch_required"


def test_recovery_finishes_published_answer_without_reexecuting(board, source, tmp_path, monkeypatch):
    monkeypatch.setenv("DAW_LIVE", "1")
    agent = add_agent(board, "a", seed_workspace=source[0].root)
    question = board.ask(agent["id"], "operator", "Small question")
    done = dispatch(board, question["id"], fake_hermes(tmp_path / "hermes"))
    with board.db:
        board.db.execute("UPDATE request SET state='running',answer=NULL WHERE id=?", (done["id"],))
        board.db.execute("UPDATE attempt SET state='running',finished=NULL WHERE id=?", (done["active_run"],))
    recovered = recover(board, done["id"])
    assert recovered["state"] == "completed" and recovered["answer"] == done["answer"]
    assert len(board.audit()["attempts"]) == 1


def test_community_report_retains_delivery_and_evidence_traces(board, source, tmp_path, monkeypatch):
    from benchmarks.agent.community import report
    monkeypatch.setenv("DAW_LIVE", "1")
    agent = add_agent(board, "a", seed_workspace=source[0].root)
    request = board.ask(agent["id"], "operator", "Small question")
    dispatch(board, request["id"], fake_hermes(tmp_path / "hermes"))
    output = tmp_path / "audit"
    value = report(board.root, output)
    assert value["runs"][0]["state"] == "completed"
    assert value["runs"][0]["raw_sha256"]
    assert value["artifact_links"]  # Explicitly reported as possibly inherited.
    assert (output / "report.md").is_file()


def test_auto_answer_notification_resume_no_ping_pong_and_no_unstarted_launch(board, tmp_path, monkeypatch):
    monkeypatch.setenv("DAW_LIVE", "1")
    monkeypatch.delenv("BIO_AGENT", raising=False)
    monkeypatch.setattr("daw.community_runtime.native_session", fake_session)
    executable = fake_hermes(tmp_path / "hermes")
    alice, bob, paused = [add_agent(board, name) for name in ("alice", "bob", "paused")]
    for agent in (alice, bob):
        request = board.ask(agent["id"], "operator", "Initial work")
        dispatch(board, request["id"], executable)
    board.ask(paused["id"], "operator", "Prepared but not started")
    board.ask(paused["id"], alice["id"], "Peer mail does not authorize initial assignment")
    operator_task = board.ask(bob["id"], "operator", "Explicit dispatch only")
    question = board.ask(bob["id"], alice["id"], "What are the limitations?", notify=True)
    assert [r["id"] for r in pending_deliveries(board)] == [question["id"]]
    assert pending_deliveries(board, ["alice"]) == []
    assert board.queue_answer_notifications() == []
    completed = dispatch(board, question["id"], executable)
    native_alice = board.agent("alice")["native_session"]
    [notification] = board.queue_answer_notifications()
    assert board.queue_answer_notifications() == []
    note = board.one("SELECT * FROM request WHERE id=?", (notification,))
    assert note["target"] == alice["id"]
    content = board.show(note["post"])["content"]
    assert content["evidence"]["answer"] == completed["answer"]
    assert content["kind"] == "answer_notification"
    done = dispatch(board, notification, executable, refresh_tools=True)
    assert done["state"] == "completed"
    assert board.agent("alice")["native_session"] == native_alice
    assert "2 stored turns" in board.show(done["answer"])["content"]["body"]
    assert board.show(done["answer"])["content"]["kind"] == "answer_review"
    assert board.queue_answer_notifications() == []
    assert pending_deliveries(board) == []
    assert board.one("SELECT state FROM request WHERE id=?", (operator_task["id"],))["state"] == "pending"
    assert board.agent("paused")["native_session"] is None


def test_service_delivers_and_backfills_notifications_after_restart(board, tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setenv("DAW_LIVE", "1")
    monkeypatch.delenv("BIO_AGENT", raising=False)
    monkeypatch.setattr("daw.community_runtime.native_session", fake_session)
    executable = fake_hermes(tmp_path / "hermes")
    for name in ("alice", "bob"):
        add_agent(board, name)
        dispatch(board, board.ask(name, "operator", "Initial work")["id"], executable)
    question = board.ask("bob", "alice", "Please share the saved output.", notify=True)
    original = subprocess.Popen
    launched = []

    def launch(argv, **kwargs):
        if "daw.bio_cli" not in argv:
            return original(argv, **kwargs)
        request_id = argv[argv.index("run") + 1]
        launched.append(request_id)
        # Exercise the real delivery/locks/native resume, replacing only the
        # CLI process boundary so the fake native-session API stays offline.
        with Community(board.root) as worker:
            dispatch(worker, request_id, executable)
        return type("CompletedWorker", (), {"pid": 12345, "returncode": 0, "poll": lambda self: 0})()

    monkeypatch.setattr(subprocess, "Popen", launch)
    serve(board.root, executable, once=True)
    assert launched == [question["id"]]
    serve(board.root, executable, once=True)  # scans older completed deliveries
    assert len(launched) == 2
    serve(board.root, executable, once=True)
    assert len(launched) == 2
    assert board.one("SELECT state FROM request WHERE id=?", (launched[-1],))["state"] == "completed"


def test_notification_publication_crash_reconciles_and_busy_failed_requests_wait(board, tmp_path, monkeypatch):
    monkeypatch.setenv("DAW_LIVE", "1")
    monkeypatch.setattr("daw.community_runtime.native_session", fake_session)
    executable = fake_hermes(tmp_path / "hermes")
    for name in ("alice", "bob"):
        add_agent(board, name)
        dispatch(board, board.ask(name, "operator", "Initial work")["id"], executable)
    question = board.ask("bob", "alice", "Evidence request", notify=True)
    dispatch(board, question["id"], executable)
    original = board._post

    def crash(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("after notification publication")

    monkeypatch.setattr(board, "_post", crash)
    with pytest.raises(RuntimeError):
        board.queue_answer_notifications()
    monkeypatch.setattr(board, "_post", original)
    [notification] = board.queue_answer_notifications()
    assert len(board.rows("SELECT id FROM post WHERE request_key LIKE 'answer-notification:%'")) == 1
    with board.db:
        board.db.execute("UPDATE request SET state='running' WHERE id=?", (notification,))
    board.ask("alice", "bob", "Another question")
    assert pending_deliveries(board) == []
    with board.db:
        board.db.execute("UPDATE request SET state='failed' WHERE id=?", (notification,))
    assert all(r["id"] != notification for r in pending_deliveries(board))
    with exclusive(board.root / ".service.lock"):
        with pytest.raises(DawError, match="agent_busy"):
            serve(board.root, executable, once=True)


def test_service_requires_operator_and_live_opt_in(board, monkeypatch):
    monkeypatch.setenv("BIO_AGENT", "researcher")
    with pytest.raises(DawError, match="operator_dispatch_required"):
        serve(board.root, once=True)
    monkeypatch.delenv("BIO_AGENT")
    monkeypatch.delenv("DAW_LIVE", raising=False)
    with pytest.raises(DawError, match="live_opt_in_required"):
        serve(board.root, once=True)


def test_search_families_show_evidence_summary_and_verify(board, source):
    ws, question, artifact, spec = source
    post = board.publish("operator", "PMP22 RNA slice", "Selected rows; expression is not promoter output.",
                         workspace=ws.root, artifacts=[artifact["artifact"]], question=question["question"])
    shown = board.show(post["id"])
    [summary] = shown["evidence_artifacts"]
    assert summary["id"] == artifact["artifact"] and summary["present"]
    assert summary["title"] == "PMP22 expression slice" and summary["output_role"] == "result"
    assert summary["derivation_key"] == artifact["derivation_key"]
    hits = board.find("PMP22", family="artifact")
    assert hits["family"] == "artifact" and hits["total"] == 1
    assert hits["items"][0]["subject"] == artifact["artifact"] and hits["items"][0]["posts"] == [post["id"]]
    assert board.find("PMP22", family="all")["total"] >= 2
    compact = board.find("PMP22")["items"][0]
    assert compact["superseded_by"] == [] and compact["author"] == "operator" and compact["artifacts"] == 1
    assert "snippet" in compact and "summary" not in compact and "fingerprint" not in compact
    assert "summary" in board.find("PMP22", full=True)["items"][0]
    with pytest.raises(DawError, match="unknown_search_family"):
        board.find("PMP22", family="data")
    verified = board.verify(post["id"])
    assert verified["verified"] and verified["artifacts"] == [{"id": artifact["artifact"], "verified": True}]
    assert verified["notebook_verified"] is True


def test_posts_reject_provider_citation_syntax(board):
    for body in ("See ([pmc](https://pmc.ncbi.nlm.nih.gov/x/?utm_source=openai)).", "as in turn0search1", "citeturn2view0"):
        with pytest.raises(DawError, match="provider_citation_syntax"):
            board.publish("operator", "Claim", body)
    assert board.publish("operator", "Claim", "web.run is not available here; the receipt is receipt-r001.json")["id"]


def test_ask_defaults_to_inbox_only_and_reply_closes_request(board, tmp_path, monkeypatch):
    monkeypatch.setenv("DAW_LIVE", "1")
    monkeypatch.delenv("BIO_AGENT", raising=False)
    monkeypatch.setattr("daw.community_runtime.native_session", fake_session)
    executable = fake_hermes(tmp_path / "hermes")
    for name in ("alice", "bob"):
        add_agent(board, name)
        dispatch(board, board.ask(name, "operator", "Initial work")["id"], executable)
    quiet = board.ask("bob", "alice", "No turn needed for the answer")
    assert board.show(quiet["post"])["content"]["evidence"]["notify"] is False
    dispatch(board, quiet["id"], executable)
    assert board.queue_answer_notifications() == []  # answer is in inbox --sent only
    [sent] = board.inbox("alice", sent=True)
    assert sent["state"] == "completed" and sent["answer"]
    assert board.inbox("alice", sent=True, since=sent["updated"]) == []
    # A target answering through the forum closes the request instead of leaving it pending.
    open_question = board.ask("bob", "alice", "Answered by publication")
    reply = board.publish("bob", "Re: your question", "Here is the matched sample map.", parent=open_question["post"])
    settled = board.one("SELECT * FROM request WHERE id=?", (open_question["id"],))
    assert settled["state"] == "completed" and settled["answer"] == reply["id"]
    assert pending_deliveries(board) == []
    assert any(e["kind"] == "answered_by_publication" for e in board.audit()["events"])


def test_artifact_use_records_considered_unless_reasoned_and_audit_reports_backing(board, source, tmp_path):
    from daw.artifacts import reuse_links
    ws, question, artifact, spec = source
    runner = CliRunner()
    prefix = ["-w", str(ws.root), "artifact", "use", artifact["artifact"], "--question", question["question"]]
    considered = runner.invoke(app, prefix)
    assert considered.exit_code == 0, considered.output
    assert json.loads(considered.output)["relationship"] == "considered"
    reasoned = runner.invoke(app, prefix + ["--reason", "its expression rows are the input matrix for the ratio"])
    assert json.loads(reasoned.output)["relationship"] == "reused"
    rows = {(r["relationship"], r.get("backed")) for r in reuse_links(ws) if r["artifact"] == artifact["artifact"]}
    assert ("considered", None) in rows and ("reused", True) in rows
    bad = runner.invoke(app, ["-w", str(ws.root), "register", str(tmp_path / "result.tsv"), "--question", question["question"],
                              "--input", artifact["artifact"], "--code", str(tmp_path / "result.tsv"), "--output-role", "byte-verification.json"])
    assert bad.exit_code != 0 and isinstance(bad.exception, DawError) and bad.exception.reason == "invalid_output_role"
    gap = runner.invoke(app, ["-w", str(ws.root), "work", "gap", question["question"], "--need", "Full text",
                              "--failed", "browser open returned reCAPTCHA"])
    assert gap.exit_code != 0 and isinstance(gap.exception, DawError) and gap.exception.reason == "evidence_required"
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"url":"https://example.test/x","status":403}')
    ok = runner.invoke(app, ["-w", str(ws.root), "work", "gap", question["question"], "--need", "Full text",
                             "--failed", "HTTP 403 from publisher", "--evidence", str(receipt)])
    assert ok.exit_code == 0, ok.output


def test_audit_report_metrics_separate_sleep_and_ceremony(board, source, tmp_path, monkeypatch):
    from benchmarks.agent.community import report
    monkeypatch.setenv("DAW_LIVE", "1")
    agent = add_agent(board, "a", seed_workspace=source[0].root)
    request = board.ask(agent["id"], "operator", "Small question")
    dispatch(board, request["id"], fake_hermes(tmp_path / "hermes"))
    [attempt] = board.rows("SELECT * FROM attempt")
    folder = board.root / attempt["path"]
    execution = json.loads((folder / "execution.json").read_text())
    execution.update(wall_seconds=4000.0, monotonic_seconds=400.0)
    (folder / "execution.json").write_text(json.dumps(execution))
    (folder / "final.md").write_text("Verified ([pmc](https://x/?utm_source=openai)).")
    value = report(board.root, tmp_path / "audit")
    metrics = value["runs"][0]["metrics"]
    assert metrics["suspended_seconds"] == 3600.0 and metrics["monotonic_seconds"] == 400.0
    assert metrics["provider_citation_in_final"] is True
    assert {"tool_calls", "help_calls", "inbox_calls", "analysis_receipts", "plumbing_scripts", "compactions"} <= metrics.keys()
    assert value["summary"]["suspended_hours"] == 1.0 and "reused_links_backed" in value["summary"]
    assert "| monotonic min |" in (tmp_path / "audit/report.md").read_text()


# ---- spec v2 V1: claims-first authoring ------------------------------------------------------------------

def test_publishing_with_evidence_and_no_claims_warns(board, source, tmp_path, monkeypatch):
    """V1 acceptance: a post with evidence and no claims is published with a non-fatal warning (output JSON and
    stderr); with claims, or without evidence, there is no warning."""
    ws, question, artifact, _ = source
    post = board.publish("operator", "PMP22 RNA", "A result without claims.", workspace=ws.root,
                         artifacts=[artifact["artifact"]], question=question["question"], request_key="no-claims")
    assert [w["code"] for w in post["warnings"]] == ["publication_without_claims"]
    assert post["warnings"][0]["evidence"] == {"artifacts": 1, "notebook": True}
    assert board.show(post["id"])["claims"] == []  # published all the same; nothing was written for the author
    claims = [{"text": "PMP22 value 2 in the fixture slice.", "status": "descriptive",
               "pointers": [{"kind": "locator", "id": artifact["artifact"], "locator": "row=PMP22;col=value"}]}]
    stated = board.publish("operator", "PMP22 RNA with claims", "A result with claims.", workspace=ws.root,
                           artifacts=[artifact["artifact"]], question=question["question"], claims=claims,
                           request_key="claims")
    assert "warnings" not in stated and len(stated["claims"]) == 1
    assert "warnings" not in board.publish("operator", "Discussion", "No evidence, no claims.")
    # The agent CLI prints the same warning on stderr and keeps it in the JSON.
    monkeypatch.delenv("BIO_AGENT", raising=False)
    body = tmp_path / "post.md"
    body.write_text("Another result without claims.")
    result = CliRunner().invoke(app, ["community", "--root", str(board.root), "publish", "Again", "--body", str(body),
                                      "--workspace", str(ws.root), "--artifact", artifact["artifact"]])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["warnings"][0]["code"] == "publication_without_claims"
    assert "warning: publication_without_claims" in result.stderr


def answering_hermes(path):
    """The fixture harness answering with the text in the trial's answer.md (an agent-written final)."""
    source = Path(fake_hermes(path))
    text = source.read_text().replace("'text':f'Fixture answer with {n} stored turns.'",
                                      "'text':(trial/'answer.md').read_text()")
    source.write_text(text)
    return str(source)


def test_final_answer_claims_block_becomes_ledger_claims_or_is_refused(board, source, tmp_path, monkeypatch):
    """V1: the runtime records the agent's own fenced claims block as the answer's claims (as publish --claims);
    an invalid block is refused with a recorded reason and the answer is posted verbatim without claims."""
    monkeypatch.setenv("DAW_LIVE", "1")
    monkeypatch.setattr("daw.community_runtime.native_session", fake_session)
    ws, question, artifact, _ = source
    published = board.publish("operator", "Slice", "The slice.", workspace=ws.root, artifacts=[artifact["artifact"]],
                              question=question["question"], request_key="slice")
    agent = add_agent(board, "a", seed_workspace=ws.root)
    trial = board.trial(agent)
    executable = answering_hermes(tmp_path / "hermes")
    block = [{"text": "PMP22 value is 2 in the slice.", "status": "supported", "scope": {"species": "synthetic"},
              "pointers": [{"kind": "locator", "id": artifact["artifact"], "locator": "row=PMP22;col=value"},
                           {"kind": "post", "id": published["id"]}]},
             {"text": "Donor structure cannot be tested here.", "status": "untestable"}]
    final = "```claims\n" + json.dumps(block, indent=1) + "\n```\n\nThe finding: PMP22 is 2 in the slice.\n"
    (trial / "answer.md").write_text(final)
    request = board.ask("a", "operator", "What is the PMP22 value?")
    done = dispatch(board, request["id"], executable)
    shown = board.show(done["answer"])
    assert shown["content"]["body"] == "The finding: PMP22 is 2 in the slice."
    evidence = shown["content"]["evidence"]
    assert evidence["claims_source"] == "final_answer_block" and evidence["claims_block_removed_from_body"]
    assert [(c["text"], c["status"]) for c in shown["claims"]] == [(b["text"], b["status"]) for b in block]
    run = board.one("SELECT path FROM attempt WHERE request=?", (request["id"],))["path"]
    assert (board.root / run / "final.md").read_text() == final  # the agent's full reply stays in the run
    # An unresolved pointer refuses the block, never repairs it: posted verbatim, reason recorded.
    bad = [{"text": "Invented.", "status": "supported", "pointers": [{"kind": "artifact", "id": "artifact_" + "0" * 64}]}]
    final = "```claims\n" + json.dumps(bad) + "\n```\n\nA reply whose claim points nowhere.\n"
    (trial / "answer.md").write_text(final)
    request = board.ask("a", "operator", "And another?")
    done = dispatch(board, request["id"], executable)
    shown = board.show(done["answer"])
    run = board.one("SELECT path FROM attempt WHERE request=?", (request["id"],))["path"]
    assert shown["content"]["body"] == (board.root / run / "final.md").read_text()
    assert "```claims" in shown["content"]["body"]
    assert shown["claims"] == [] and shown["content"]["evidence"]["claims_refused"]["reason"] == "claim_pointer_unresolved"
    refused = [json.loads(r["body"]) for r in board.rows("SELECT body FROM event WHERE kind='answer_claims_refused'")]
    assert [(r["answer"], r["reason"]) for r in refused] == [(done["answer"], "claim_pointer_unresolved")]
    # Malformed JSON and two blocks are refused the same way; a reply without a block is untouched.
    from daw.commons.claims import final_claims
    with board.writer(), board.library.writer():
        assert final_claims(board, "```claims\n[not json\n```\nprose")[2]["reason"] == "invalid_claims_json"
        two = "```claims\n[]\n```\n\n```claims\n[]\n```\nprose"
        assert final_claims(board, two)[2]["reason"] == "multiple_claims_blocks"
        assert final_claims(board, "plain prose") == ("plain prose", {}, None)


# ---- spec v3 G5, G6, V11: the agent's own view of the commons ------------------------------------------------

def test_agent_reads_of_frontier_acts_and_overview_on_the_cohort(cohort_copy, monkeypatch):
    """G5/G6/V11 acceptance on a private copy of the real cohort: one `community overview` call lists an agent's
    open requests, the human acts on its work, the frontier items it owns and its budget; `community frontier`
    lists the cohort's items with state; `community show` returns marks and anchored comments as attributed
    records; `inbox --acts` lists a mark on the agent's post. Reads write no record; hidden posts are stubs."""
    from daw.commons import agentview
    from daw.commons.boardservice import execute
    from daw.commons.moderation import hide
    from daw.commons.participation import ask, comment, mark, promote
    from daw.community_runtime import _acts_section
    for name in ("BIO_AGENT", "BIO_BOARD_URL", "BIO_COMMUNITY"):
        monkeypatch.delenv(name, raising=False)
    root, runner = cohort_copy, CliRunner()

    def cli(*args):
        result = runner.invoke(app, ["community", "--root", str(root), *args])
        assert result.exit_code == 0, result.output
        return json.loads(result.stdout)

    with Community(root) as board:
        agent = board.agent("pmp22-cis-promoters")
        person = board.one("SELECT id FROM agent WHERE kind='human'")["id"]
        post = board.rows("SELECT id FROM post WHERE author=? ORDER BY seq", (agent["id"],))[-1]["id"]
        shown = board.show(post)
        quote = shown["content"]["body"][:24]
        item = board.one("SELECT id FROM frontier_item WHERE author=? AND status='open'", (agent["id"],))["id"]
        start = board.one("SELECT max(seq) AS n FROM event")["n"]
        marked = mark(board, person, "post", post, "disputed", "The cited source is a different background.")
        commented = comment(board, person, "post", post, "Which promoter does this quote refer to?",
                            anchor={"kind": "paragraph", "blob": shown["body_blob"], "offset": 0,
                                    "length": len(quote), "quote": quote})
        asked = ask(board, person, agent["id"], "Could you state the next computable step for the cis question?")
        promoted = promote(board, person, "frontier_item", item, "scouting", agent["id"], {"minutes": 15})
        written = board.one("SELECT max(seq) AS n FROM event")["n"]
        projection = board.rows("SELECT * FROM frontier_item ORDER BY id")

    overview = cli("overview", "--agent", "pmp22-cis-promoters")
    kinds = {r["record"] for r in overview["records"]}
    assert {"request", "act", "frontier_item", "promotion", "budget"} <= kinds
    assert asked["id"] in {r["id"] for r in overview["records"] if r["record"] == "request"}
    acts = {r["act"]: r for r in overview["records"] if r["record"] == "act"}
    assert acts["mark"]["id"] == marked["id"] and acts["mark"]["kind"] == "disputed"
    assert acts["mark"]["participant"] == person and acts["mark"]["participant_kind"] == "human"
    assert acts["comment"]["id"] == commented["post"] and acts["comment"]["anchor"]["quote"] == quote
    assert acts["promotion"]["id"] == promoted["id"] and acts["promotion"]["target_id"] == item
    owned = {r["id"]: r for r in overview["records"] if r["record"] == "frontier_item"}
    assert owned[item]["status"] == "promoted" and owned[item]["request"]["id"] == promoted["id"]
    assert overview["label"] == agentview.LABEL and overview["acts_after_source"] == "last_turn"
    assert overview["acts_after"] < start  # acts since the agent's last delivered turn

    listed = cli("frontier")
    assert listed["total"] >= 59 and all(i["status"] and i["column"] for i in listed["items"])
    assert listed["by_kind"]["gap"] == listed["total"]
    mine = cli("frontier", "--mine", "--kind", "gap")  # --mine is BIO_AGENT's (unset here: the operator's)
    assert mine["total"] == 0
    assert cli("experiments")["total"] == 0

    shown = cli("show", post)
    by_act = {a["act"]: a for a in shown["acts"]}
    assert by_act["mark"]["note"] == "The cited source is a different background."
    assert by_act["comment"]["note"] == "Which promoter does this quote refer to?" and by_act["comment"]["anchor"]
    assert shown["acts_label"] == agentview.LABEL

    inbox = cli("inbox", "--acts", "--agent", "pmp22-cis-promoters", "--after", str(start))
    assert [a["act"] for a in inbox["acts"]] == ["mark", "comment", "promotion"]
    assert inbox["acts"][0]["id"] == marked["id"] and inbox["latest"] == promoted_seq(root, promoted["id"])
    assert cli("inbox", "--acts", "--agent", "pmp22-cis-promoters", "--after", str(inbox["latest"]))["acts"] == []

    # The board service answers the same reads for the agent itself (sandboxed checkouts).
    served = execute(root, agent["id"], "overview", {"after": start})
    assert {r["record"] for r in served["records"]} >= {"request", "act", "frontier_item", "budget"}
    assert execute(root, agent["id"], "frontier", {"mine": True})["total"] >= 1
    assert len(execute(root, agent["id"], "inbox", {"acts": True, "after": start})["acts"]) == 3

    with Community(root) as board:
        # Reads wrote nothing: no board event, the frontier projection unchanged.
        assert board.one("SELECT max(seq) AS n FROM event")["n"] == written
        assert board.rows("SELECT * FROM frontier_item ORDER BY id") == projection
        # The dispatch prompt lists the acts since the last turn by identity and kind, with the label, no notes.
        section = _acts_section(board, agent)
        assert agentview.LABEL in section and marked["id"] in section and "different background" not in section
        hide(board, "operator", post, "test: withheld")
    hidden = cli("show", post)
    assert hidden["hidden"] is True and "acts" not in hidden
    stubs = cli("inbox", "--acts", "--agent", "pmp22-cis-promoters", "--after", str(start))["acts"]
    assert [a.get("hidden") for a in stubs[:2]] == [True, True]
    assert all("note" not in a and "anchor" not in a for a in stubs[:2])


def promoted_seq(root, request):
    with Community(root) as board:
        return next(r["seq"] for r in board.rows("SELECT seq,body FROM event WHERE kind='promotion_created'")
                    if json.loads(r["body"])["request"] == request)
