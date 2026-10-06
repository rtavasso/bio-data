"""Integration fixes found by the whole-system e2e pass (web/e2e/run.mjs), checked offline on the demo.

- Flow D: the author's answer to an anchored comment is shown under the anchor (post view).
- `bio commons demo-deliver` / `demo-watch-tick`: the operator's scripted delivery and recorded watcher
  tick on a synthetic demo commons, refused on any other commons.
"""
import json
import shutil

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from daw.commons.app import create_app
from daw.commons.demo import deliver_scripted, watch_tick_recorded
from daw.commons.participation import comment
from daw.community import Community
from daw.util import DawError

RECORDED = {"hitCount": 1, "resultList": {"result": [
    {"id": "E2E0001", "source": "SYNTHETIC", "title": "Donor-matched qPCR (synthetic fixture)", "pubYear": "2026"}]}}


def client(root):
    return TestClient(create_app(root, static_dir=root / "missing"))


def cli(root, *args, ok=True):
    from daw.commons.cli import app
    result = CliRunner().invoke(app, ["--root", str(root), *args])
    if ok:
        assert result.exit_code == 0, result.output
        return json.loads(result.output)
    return result


def test_answer_to_an_anchored_comment_appears_under_the_anchor(demo):
    root, ctx = demo
    part = ctx["participation"]
    detail = client(root).get(f"/api/posts/{ctx['posts']['correction']}").json()
    [card] = [c for g in detail["comments"] for c in g["comments"] if c["id"] == part["comment"]]
    assert card["request"]["id"] == part["comment_request"] and card["request"]["state"] == "completed"
    assert [a["id"] for a in card["answers"]] == [part["comment_answer"]]
    assert card["answers"][0]["snippet"]  # the whole answer, not a truncated snippet
    # The answer is still a reply of the comment, not of the post: it is not listed among the post's replies.
    assert part["comment_answer"] not in {r["id"] for r in detail["replies"]}


def test_scripted_delivery_closes_a_comment_request_and_shows_the_answer(demo, monkeypatch):
    root, ctx = demo
    monkeypatch.delenv("BIO_AGENT", raising=False)
    reply = ctx["posts"]["reply"]
    with Community(root) as board:
        blob = board.one("SELECT body_blob FROM post WHERE id=?", (reply,))["body_blob"]
        made = comment(board, ctx["participation"]["human"], "post", reply, "Does this hold for human cells?",
                       anchor={"kind": "paragraph", "blob": blob, "offset": 0, "length": 40,
                               "quote": "After normalization the contrast is 1.31"}, ask_author=True)
    answer = root / "answer.md"
    answer.write_text("Not tested: the synthetic table has no human cells.")
    row = cli(root, "demo-deliver", made["request"]["id"], "--answer", str(answer))
    assert row["state"] == "completed" and row["answer"]
    detail = client(root).get(f"/api/posts/{reply}").json()
    [group] = [g for g in detail["comments"] if g["anchor"]["quote"] == "After normalization the contrast is 1.31"]
    [card] = group["comments"]
    assert card["request"]["state"] == "completed"
    assert card["answers"][0]["id"] == row["answer"] and "no human cells" in card["answers"][0]["snippet"]
    # A delivered request is not delivered twice; hooks are removed after the turn.
    with pytest.raises(DawError, match="request_not_pending"):
        deliver_scripted(root, made["request"]["id"], "again")
    assert not list((root / "demo-harness" / "answers").glob("*.hook.py"))


def test_scripted_delivery_runs_a_fixture_hook_in_the_agents_checkout(demo, monkeypatch):
    root, ctx = demo
    monkeypatch.delenv("BIO_AGENT", raising=False)
    with Community(root) as board:
        request = board.ask(ctx["agents"]["dana"], "operator", "Record what you looked at.", request_key="e2e-hook")
    hook = ("import os, pathlib\n"
            "trial = pathlib.Path(os.environ.get('HERMES_CWD') or os.getcwd())\n"
            "(trial / 'hook-ran.txt').write_text(os.environ['BIO_AGENT'])\n")
    row = deliver_scripted(root, request["id"], "Looked at the gap receipt.", hook=hook)
    assert row["state"] == "completed"
    with Community(root) as board:
        trial = board.trial(board.agent(ctx["agents"]["dana"]))
    assert (trial / "hook-ran.txt").read_text() == ctx["agents"]["dana"]


def test_demo_operator_commands_refuse_a_commons_without_the_demo_marker(demo, tmp_path):
    root, ctx = demo
    real = tmp_path / "real"
    shutil.copytree(root, real, symlinks=True)
    (real / "DEMO.json").unlink()
    with pytest.raises(DawError, match="not_a_demo_commons"):
        deliver_scripted(real, ctx["requests"]["brief"], "answer")
    with pytest.raises(DawError, match="not_a_demo_commons"):
        watch_tick_recorded(real, RECORDED)
    (real / "DEMO.json").write_text(json.dumps({"synthetic": False}))
    with pytest.raises(DawError, match="not_a_demo_commons"):
        deliver_scripted(real, ctx["requests"]["brief"], "answer")
    assert cli(real, "demo-watch-tick", "--response", str(tmp_path / "missing.json"), ok=False).exit_code != 0


def test_recorded_watcher_tick_posts_a_candidate_and_marks_the_item(demo, tmp_path, monkeypatch):
    root, ctx = demo
    monkeypatch.delenv("BIO_AGENT", raising=False)
    item = ctx["frontier"]["items"]["alice-qpcr"]
    http = client(root)
    attached = http.post("/api/watchers", headers={"X-Colloquy-Request": "1"},
                         json={"item": item, "query": {"query": "demo marker qPCR"}, "provider": "europepmc",
                               "interval_seconds": 604800})
    assert attached.status_code == 200, attached.text
    with pytest.raises(DawError, match="invalid_recorded_response"):
        watch_tick_recorded(root, {"hits": []})
    fixture = tmp_path / "europepmc.json"
    fixture.write_text(json.dumps(RECORDED))
    ticked = cli(root, "demo-watch-tick", "--response", str(fixture))
    [ran] = [r for r in ticked["ran"] if r["watcher"] == attached.json()["id"]]
    assert ran["new"] == ["E2E0001"] and ran["receipt_blob"]
    assert ran["notice"]["target"] == ctx["agents"]["alice"] and ran["notice"]["task_type"] == "notice"
    assert http.get(f"/api/frontier/{item}").json()["status"] == "candidate_evidence"
    # Not due again until its interval passes: a second tick runs nothing.
    assert cli(root, "demo-watch-tick", "--response", str(fixture))["ran"] == []


def test_interface_sketch_routes_for_questions_and_replies(demo):
    root, ctx = demo
    http = client(root)
    qid = ctx["questions"]["alice"]
    # A bare id opens the original author's question, not the fork's inherited copy.
    page = http.get(f"/api/questions/{qid}").json()
    assert page["agent"]["id"] == ctx["agents"]["alice"] and page["question"]["id"] == qid
    assert page == http.get(f"/api/questions/{ctx['agents']['alice']}/{qid}").json()
    assert http.get("/api/questions/q_0000000000000000").status_code == 404
    reply = http.post(f"/api/posts/{ctx['posts']['finding']}/replies", headers={"X-Colloquy-Request": "1"},
                      json={"title": "Reply", "body": "Which normalization was used?"})
    assert reply.status_code == 200, reply.text
    made = http.get(f"/api/posts/{reply.json()['id']}").json()
    assert made["parent"] == ctx["posts"]["finding"] and made["author_participant"]["kind"] == "human"
    # Same CSRF rule as every other cookie or local-mode write.
    assert http.post(f"/api/posts/{ctx['posts']['finding']}/replies", json={"title": "x", "body": "y"}).status_code == 403
