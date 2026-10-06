"""Shared plumbing helpers staged with the bio-research skill: receipts, batch registration, forum dumps."""
import http.server
import json
import runpy
import sys
import threading
from pathlib import Path

from daw.catalog import Workspace
from daw.community import Community
from daw.work import create_question

SCRIPTS = Path(__file__).parents[1] / ".agents/skills/bio-research/scripts"


def helper(name):
    return runpy.run_path(str(SCRIPTS / name))


def test_fetch_receipt_records_bytes_hash_and_failures(tmp_path):
    served = tmp_path / "served"
    served.mkdir()
    (served / "table.tsv").write_bytes(b"gene\tvalue\nPMP22\t2\n")
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(served), **k)  # noqa: E731
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        fetch = helper("fetch_receipt.py")["fetch"]
        value, receipt = fetch(base + "/table.tsv", tmp_path / "inputs/table.tsv")
        assert value["status"] == 200 and value["bytes"] == 19 and value["error"] is None
        assert json.loads(receipt.read_text())["sha256"] == value["sha256"]
        assert (tmp_path / "inputs/table.tsv").read_bytes() == b"gene\tvalue\nPMP22\t2\n"
        missing, _ = fetch(base + "/absent.tsv", tmp_path / "inputs/absent.tsv")
        assert missing["status"] == 404 and missing["error"].startswith("HTTP 404") and missing["sha256"] is None
        capped, _ = fetch(base + "/table.tsv", tmp_path / "inputs/capped.tsv", max_bytes=5)
        assert "max-bytes" in capped["error"] and capped.get("partial_bytes_kept", 0) <= 20
    finally:
        server.shutdown()


def no_reserve(root):
    (root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0\n")


def test_register_batch_persists_receipts_and_resumes(tmp_path):
    root = tmp_path / "ws"
    Workspace.create(root).close()
    no_reserve(root)
    ws = Workspace(root)
    question = create_question(ws, "Batch registration")["question"]
    blob = ws.put_bytes(b"gene\tvalue\nPMP22\t2\n")
    ws.close()
    script = tmp_path / "scripts" / "analyze.py"
    script.parent.mkdir()
    script.write_text("print('saved, not executed by the helper')\n")
    first, second = tmp_path / "a.tsv", tmp_path / "b.tsv"
    first.write_text("PMP22\t2\n")
    second.write_text("PMP22\t4\n")
    plan = [{"path": str(first), "title": "A", "summary": "fixture", "output_role": "contrast-table", "inputs": [blob], "code": [str(script)]},
            {"path": str(second), "title": "B", "summary": "fixture", "output_role": "bad.name", "inputs": [blob], "code": [str(script)]}]
    receipts = tmp_path / "registrations.json"
    register_all = helper("register_batch.py")["register_all"]
    bio = f"{sys.executable} -m daw.bio_cli"
    results = register_all(plan, question, receipts, bio, workspace=root)
    assert results[0]["artifact"].startswith("artifact_") and results[0]["exit_code"] == 0
    assert results[1]["exit_code"] != 0 and "invalid_output_role" in results[1]["stdout"]
    saved = json.loads(receipts.read_text())
    assert saved[str(first)]["artifact"] == results[0]["artifact"]
    plan[1]["output_role"] = "contrast-table-r002"
    resumed = register_all(plan, question, receipts, bio, workspace=root)
    assert resumed[0]["skipped"] is True and resumed[1]["artifact"].startswith("artifact_")


def test_forum_dump_saves_hits_and_index(tmp_path, monkeypatch):
    board = Community.create(tmp_path / "community")
    try:
        post = board.publish("operator", "PMP22 composition note", "Composition, not promoter output.")
        board.publish("operator", "Unrelated", "SOX10 only.")
    finally:
        board.close()
    monkeypatch.setenv("BIO_COMMUNITY", str(tmp_path / "community"))
    monkeypatch.delenv("BIO_AGENT", raising=False)
    dump = helper("forum_dump.py")["dump"]
    out = tmp_path / "dump"
    index = dump(out, ["PMP22"], ["forum", "artifact"], [], f"{sys.executable} -m daw.bio_cli")
    assert [e["id"] for e in index] == [post["id"]]
    assert (out / f"{post['id']}.json").is_file() and "PMP22 composition note" in (out / "INDEX.md").read_text()
    assert json.loads((out / "search-artifact-PMP22.json").read_text())["total"] == 0
