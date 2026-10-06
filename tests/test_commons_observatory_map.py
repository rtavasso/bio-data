"""Evidence map, question pages and agent timelines (M4.2–M4.4) on the synthetic demo commons."""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from daw.artifacts import register_artifact
from daw.catalog import Workspace
from daw.commons.app import create_app
from daw.commons.archive import Archive
from daw.commons.evidence_map import evidence_map, layout, question_node
from daw.commons.questions import question_page
from daw.commons.timeline import run_timeline
from daw.substrate_models import ArtifactRegistration, Derivation, ObjectInput
from daw.util import DawError, now, write_json
from daw.work import record_event


def _store(view, name):
    return view.library if name == "library" else view.workspace(name.removeprefix("workspace:"))


def _assert_recorded(view, edge):
    """Each record listed on an edge exists and states exactly this relation."""
    assert edge["records"], edge
    for record in edge["records"]:
        table, relation, source, target = record["table"], edge["relation"], edge["source"], edge["target"]
        if table == "post":
            post = view.post(record["id"])
            evidence = post["content"].get("evidence") or {}
            expected = {"authored": (post["author"], post["id"]), "reply_to": (post["id"], post["parent"]),
                        "supersedes": (post["id"], post["supersedes"])}
            if relation == "evidence":
                assert source == post["id"] and target in evidence["artifacts"]
            elif relation == "notebook":
                assert source == post["id"] and target == question_node(post["author"], evidence["notebook"]["question"])
                assert view.workspace(post["author"]).one("SELECT id FROM work_snapshot WHERE id=?",
                                                          (evidence["notebook"]["snapshot"],))
            else:
                assert (source, target) == expected[relation]
        elif table == "request":
            row = view.one("SELECT * FROM request WHERE id=?", (record["id"],))
            assert relation == "answered_by" and (row["post"], row["answer"]) == (source, target)
        elif table == "event":
            row = view.one("SELECT * FROM event WHERE seq=?", (record["seq"],))
            body = json.loads(row["body"])
            assert row["kind"] == "evidence_fetched" and (body["reader"], body["post"]) == (source, target)
        elif table == "artifact_input":
            row = _store(view, record["store"]).one(
                "SELECT * FROM artifact_input WHERE artifact_id=? AND blob=? AND role=? AND source_identity=?",
                (record["artifact_id"], record["blob"], record["role"], record["source_identity"]))
            assert row and source == row["artifact_id"] and target == (row["source_identity"] or row["blob"])
        elif table == "asset_revision":
            row = _store(view, record["store"]).one("SELECT * FROM asset_revision WHERE id=?", (record["id"],))
            assert (source, target) == (row["id"], row["snapshot_id"])
        elif table == "question_artifact":
            agent = record["store"].removeprefix("workspace:")
            row = view.workspace(agent).one("SELECT * FROM question_artifact WHERE question_id=? AND artifact_id=? "
                                            "AND relationship=? AND event_id=?", (record["question_id"],
                                            record["artifact_id"], record["relationship"], record["event"]))
            assert row and relation == row["relationship"]
            assert (source, target) == (question_node(agent, row["question_id"]), row["artifact_id"])
        elif table == "agent":
            row = view.one("SELECT * FROM agent WHERE id=?", (record["id"],))
            if relation == "fork_of":
                assert (source, target) == (row["id"], row["parent"])
            else:
                _, agent, qid = target.split(":", 2)
                assert relation == "owns" and source == agent == row["id"]
                assert view.workspace(agent).one("SELECT id FROM question WHERE id=?", (qid,))
        elif table == "mark":
            row = view.one("SELECT * FROM mark WHERE id=?", (record["id"],))
            assert (source, target) in {(row["participant"], row["id"]), (row["id"], row["target_id"])}
        else:
            pytest.fail(f"unexpected record table {table}")


def test_map_renders_every_artifact_with_recorded_edges_only(demo):
    root, ctx = demo
    with Archive(root) as view:
        value = evidence_map(view, use_cache=False)
        nodes = {n["id"]: n for n in value["nodes"]}
        artifacts = {r["id"] for r in view.library.rows("SELECT id FROM artifact")}
        for agent in view.rows("SELECT id FROM agent WHERE trial IS NOT NULL"):
            artifacts |= {r["id"] for r in view.workspace(agent["id"]).rows("SELECT id FROM artifact")}
        assert artifacts and artifacts == {n for n, node in nodes.items() if node["kind"] == "artifact"}
        assert all(node["present"] for node in nodes.values())
        for edge in value["edges"]:
            assert edge["source"] in nodes and edge["target"] in nodes
            _assert_recorded(view, edge)
    relations = value["counts"]["edges"]
    for relation in ("evidence", "notebook", "input", "source_receipt", "produced", "considered", "reused", "fetched",
                     "reply_to", "supersedes", "answered_by", "authored", "owns", "fork_of"):
        assert relations.get(relation), relation
    edges = {(e["source"], e["target"], e["relation"]): e for e in value["edges"]}
    bob_q = question_node(ctx["agents"]["bob"], ctx["questions"]["bob"])
    backed = edges[(bob_q, ctx["artifacts"]["contrast"], "reused")]
    unbacked = edges[(bob_q, ctx["artifacts"]["measurement"], "reused")]
    assert backed["backed"] is True and backed["style"] == "solid"
    assert unbacked["backed"] is False and unbacked["style"] == "dashed"
    assert edges[(bob_q, ctx["artifacts"]["contrast"], "considered")]["style"] == "dashed"
    assert (ctx["artifacts"]["normalized"], ctx["artifacts"]["contrast"], "input") in edges
    assert (ctx["posts"]["correction"], ctx["posts"]["finding"], "supersedes") in edges
    assert (ctx["agents"]["bob"], ctx["posts"]["finding"], "fetched") in edges
    # The figure registered from a bare receipt object (no source identity) points at the object itself.
    figure_inputs = [e for e in value["edges"] if e["source"] == ctx["observatory_map"]["figure"]]
    assert [nodes[e["target"]]["kind"] for e in figure_inputs] == ["object"]
    assert set(value["layout"]["positions"]) == set(nodes)


def test_map_filters_layout_cache_and_unrecorded_changes(demo):
    root, ctx = demo
    with Archive(root) as view:
        first = evidence_map(view)
        assert not first["cached"] and evidence_map(view)["cached"]
        assert list((root / "cache" / "map").glob("*.json"))
        again = evidence_map(view, use_cache=False)
        assert again["layout"]["positions"] == first["layout"]["positions"]  # seeded and deterministic
        bob_q = question_node(ctx["agents"]["bob"], ctx["questions"]["bob"])
        focused = evidence_map(view, question=f"bob:{ctx['questions']['bob']}")
        ids = {n["id"] for n in focused["nodes"]}
        assert focused["seeds"] == [bob_q]
        assert {ctx["artifacts"]["contrast"], ctx["artifacts"]["normalized"], ctx["artifacts"]["measurement"]} <= ids
        assert question_node(ctx["agents"]["dana"], ctx["questions"]["dana"]) not in ids
        # A bare qid selects every workspace holding it: Alice and her fork.
        assert len(evidence_map(view, question=ctx["questions"]["alice"])["seeds"]) == 2
        dana = evidence_map(view, participant="dana")
        assert ctx["posts"]["gap"] in {n["id"] for n in dana["nodes"]}
        assert ctx["posts"]["finding"] not in {n["id"] for n in dana["nodes"]}
        sources = evidence_map(view, family="artifacts,sources")
        assert {n["family"] for n in sources["nodes"]} == {"artifacts", "sources"}
        assert {e["relation"] for e in sources["edges"]} <= {"input", "source_receipt"}
        assert evidence_map(view, since="2999-01-01")["nodes"] == []
        limited = evidence_map(view, limit=5)
        assert len(limited["nodes"]) == 5 and limited["truncated"]
        for bad in ({"family": "biology"}, {"question": "q_missing"}, {"since": "yesterday"}, {"limit": 0}):
            with pytest.raises(DawError):
                evidence_map(view, **bad)
        print_before = first["fingerprint"]
    # A registration changes a workspace catalog without a board event; the cache key must change.
    alice = Workspace(root / "agents" / ctx["agents"]["alice"] / "trial" / "workspace")
    try:
        with alice.writer():
            source = alice.one("SELECT output_blob FROM artifact WHERE id=?", (ctx["artifacts"]["contrast"],))["output_blob"]
            (root / "extra.tsv").write_text("x\t1\n")
            spec = ArtifactRegistration(title="Extra", summary="synthetic", output_role="result",
                                        derivation=Derivation(inputs=[ObjectInput(blob=source,
                                                              source_identity=ctx["artifacts"]["contrast"])],
                                                              code=[alice.put_bytes(b"#\n")], parameters={},
                                                              references=[], environment={"test": True}),
                                        limitations=[])
            extra = register_artifact(alice, root / "extra.tsv", spec)["artifact"]
    finally:
        alice.close()
    with Archive(root) as view:
        updated = evidence_map(view)
        assert updated["fingerprint"] != print_before and not updated["cached"]
        assert extra in {n["id"] for n in updated["nodes"]}


def test_layout_is_bounded_and_scales():
    ids = [f"n{i}" for i in range(800)]
    edges = [{"source": f"n{i}", "target": f"n{(i * 7 + 1) % 800}"} for i in range(800)]
    positions = layout(ids, edges)
    assert positions == layout(list(reversed(ids)), edges)
    assert len({tuple(p) for p in positions.values()}) == len(ids)
    assert layout([], []) == {}


def test_question_page_notebook_networks_coverage_and_gaps(demo):
    root, ctx = demo
    dana, qd = ctx["agents"]["dana"], ctx["questions"]["dana"]
    with Archive(root) as view:
        page = question_page(view, "dana", qd)
        assert page["node"] == question_node(dana, qd)
        assert "Mechanism map r1" in page["notebook"]["labbook"] and page["notebook"]["question"].startswith("# Is there")
        assert page["notebook"]["snapshot"] == page["question"]["current_work"]
        assert [r["id"] for r in page["revisions"]][-1] == page["question"]["current_work"]
        oldest = question_page(view, dana, qd, snapshot=page["revisions"][0]["id"])
        assert "Mechanism map" not in oldest["notebook"]["labbook"]
        with pytest.raises(DawError, match="unknown_work_snapshot"):
            question_page(view, dana, qd, snapshot="work_missing")
        networks = page["networks"]
        assert [n["revision"] for n in networks] == [1, 2]
        assert [n["sha256"] for n in networks] == ctx["observatory_map"]["network_blobs"]
        assert all({o["kind"] for o in n["origins"]} == {"notebook_hash", "working_copy"} and n["preserved"]
                   for n in networks)
        assert [e["id"] for e in networks[1]["edges"]] == ["e1", "e2"] and not networks[1]["edges"][1]["dangling"]
        (coverage,) = page["coverage"]
        assert coverage["columns"][5] == "inspection_status"
        unavailable, searched = coverage["rows"]
        assert unavailable["cells"][3] == "" and unavailable["cells"][5] == "unavailable"  # blank, recorded
        assert searched["cells"][6] is None and searched["cells"][5] == "searched"         # missing cell
        (figure,) = page["figures"]
        assert figure["artifact"] == ctx["observatory_map"]["figure"] and figure["output_name"].endswith(".png")
        assert page["gaps"]["matching_events"] == 1 and page["gaps"]["withdrawn_count"] == 0
        assert page["events"][-1]["state"]["snapshot"] == page["question"]["current_work"]
        assert page["events"][-1]["state"]["gaps_open"] == 1
        assert [p["post"] for p in page["posts"]] == [ctx["posts"]["gap"]]
        assert page["scripts"] and page["scripts"][0]["path"] == "scripts/contrast.py"
        sub = page["subgraph"]
        assert {n["id"] for n in sub["nodes"]} >= {page["node"], figure["artifact"]}
        bob = question_page(view, "bob", ctx["questions"]["bob"])
        reused = {o["artifact"]: r for o in bob["outputs"] for r in o["relationships"] if r["relationship"] == "reused"}
        assert reused[ctx["artifacts"]["contrast"]]["backed"] is True
        assert reused[ctx["artifacts"]["measurement"]]["backed"] is False
        sub_edges = {(e["source"], e["target"], e["relation"]) for e in bob["subgraph"]["edges"]}
        assert (ctx["artifacts"]["normalized"], ctx["artifacts"]["contrast"], "input") in sub_edges
        assert (ctx["artifacts"]["contrast"], ctx["artifacts"]["measurement"], "input") in sub_edges
    # A withdrawal and a malformed working-copy revision are reported, not repaired.
    ws = Workspace(root / "agents" / dana / "trial" / "workspace")
    try:
        with ws.writer():
            record_event(ws, qd, "retrieval_gap_withdrawal", {"event": ctx["gap_event"], "reason": "test withdrawal"})
    finally:
        ws.close()
    outputs = root / "agents" / dana / "trial" / "workspace" / "questions" / qd / "outputs"
    (outputs / "mechanisms.r003.json").write_text('{"nodes": [{"id": "a"}, {"label": "no id"}], '
                                                  '"edges": [{"id": "x", "source": "a", "target": "ghost"}]}')
    (outputs / "mechanisms.r004.json").write_text("{not json")
    with Archive(root) as view:
        page = question_page(view, dana, qd)
        assert page["gaps"]["withdrawn_count"] == 1 and page["gaps"]["matching_events"] == 0
        assert page["events"][-1]["kind"] == "retrieval_gap_withdrawal" and page["events"][-1]["state"]["gaps_open"] == 0
        loose = [n for n in page["networks"] if n["name"].endswith(("r003.json", "r004.json"))]
        assert len(loose) == 2 and all(n["origins"][0]["kind"] == "working_copy" and not n["records"] for n in loose)
        partial = next(n for n in loose if n["name"].endswith("r003.json"))
        assert partial["edges"][0]["dangling"] and partial["issues"]
        assert "error" in next(n for n in loose if n["name"].endswith("r004.json"))


def test_question_and_blob_endpoints_serve_only_referenced_bytes_safely(demo):
    root, ctx = demo
    client = TestClient(create_app(root, static_dir=root / "missing"))
    listing = client.get("/api/questions").json()
    assert listing["total"] == 4  # alice, her fork's inherited copy, bob, dana
    page = client.get(f"/api/questions/dana/{ctx['questions']['dana']}").json()
    figure = page["figures"][0]
    response = client.get(figure["blob_url"])
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"].startswith("sandbox")
    owner, sha = ctx["agents"]["dana"], figure["output_blob"]
    html = client.get(f"/api/blobs/{owner}/{sha}?name=page.html")
    assert html.headers["content-type"].startswith("text/plain")
    svg = client.get(f"/api/blobs/{owner}/{sha}?name=figure.svg")
    assert svg.headers["content-disposition"].startswith("attachment")
    # Bytes the notebook cites by hash (bio object add) are parsed into the page, not served raw.
    cited = ctx["observatory_map"]["network_blobs"][0]
    assert client.get(f"/api/blobs/{owner}/{cited}").status_code == 404
    assert client.get(f"/api/blobs/{owner}/not-a-hash").status_code == 400
    script = client.get(page["scripts"][0]["url"])
    assert script.status_code == 200 and script.headers["content-type"].startswith("text/plain")
    contrast = client.get(f"/api/map/node/{ctx['artifacts']['contrast']}").json()
    output = contrast["records"][0]["artifact"]["output_blob"]
    assert client.get(f"/api/blobs/library/{output}?name=contrast.tsv").status_code == 200
    assert client.get("/api/questions/dana/q_missing").status_code == 404
    assert client.get("/api/questions/operator/q_x").status_code == 404
    node = client.get(f"/api/map/node/question:{ctx['agents']['bob']}:{ctx['questions']['bob']}").json()
    assert node["kind"] == "question" and node["record"]["counts"]["reused"] == 2
    assert client.get(f"/api/map/node/{ctx['posts']['finding']}").json()["content_is_untrusted_data"]
    assert client.get(f"/api/map/node/{ctx['agents']['bob']}").json()["record"]["name"] == "bob"
    assert client.get("/api/map/node/artifact_" + "0" * 64).status_code == 404
    body = client.get("/api/map?family=posts").json()
    assert body["nodes"] and {n["kind"] for n in body["nodes"]} == {"post"}
    assert client.get("/api/map?family=genes").status_code == 400


def _suspended_run(root, view):
    """A copy of a demo delivery that slept for two hours mid-run and fell back to a placeholder summary."""
    run = view.one("SELECT * FROM attempt ORDER BY created LIMIT 1")
    folder = root / run["path"]
    execution = json.loads((folder / "execution.json").read_text())
    started = datetime.fromisoformat(execution["started"])
    execution.update(wall_seconds=7300.0, monotonic_seconds=100.0,
                     finished=(started + timedelta(seconds=7300)).isoformat())
    write_json(folder / "execution.json", execution)
    lines = (folder / "events.jsonl").read_text().splitlines()
    rewritten = []
    for n, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
        except ValueError:
            rewritten.append(line)
            continue
        if n >= 6:
            event["timestamp"] += 7_200_000  # the host slept between lines 5 and 6
        if event["type"] == "result":
            event["tokens"] = {"input": 1200, "cache_read": 300, "output": 450}
        rewritten.append(json.dumps(event))
    (folder / "events.jsonl").write_text("\n".join(rewritten) + "\n")
    with sqlite3.connect(folder / "agent-state" / "state.db") as db:
        inside = started.timestamp() + 3600
        db.execute("INSERT INTO messages VALUES(?,?,?)", ("s", "[CONTEXT COMPACTION] deterministic fallback summary", inside))
        db.execute("INSERT INTO messages VALUES(?,?,?)", ("s", "[CONTEXT COMPACTION] earlier delivery", inside - 86400))
    return run["id"], started


def test_timeline_shows_suspension_compactions_fallbacks_and_headline(demo):
    root, ctx = demo
    with Archive(root) as view:
        run, started = _suspended_run(root, view)
        timeline = run_timeline(view, run)
    execution = timeline["execution"]
    assert execution["suspended_seconds"] == 7200.0 and execution["bounded"]
    (suspension,) = timeline["suspensions"]
    assert suspension["placement"] == "largest_event_gap" and suspension["unplaced_seconds"] == 0
    line5 = next(c for c in timeline["calls"] if c["result_line"] == 5)
    assert suspension["at"] == line5["t_end"]
    assert timeline["axis"]["duration"] < 60  # the monotonic axis excludes the sleep
    assert [r["outcome"] for r in timeline["receipts"]] == ["pass", "fail"]
    assert [r["script"] for r in timeline["receipts"]] == ["scripts/contrast.py", "scripts/check.py"]
    assert len(timeline["compactions"]) == 1 and timeline["compactions"][0]["source"] == "stream"
    (summary,) = timeline["compaction_summaries"]  # the earlier delivery's row is outside this run's bounds
    assert summary["fallback"] is True
    assert timeline["metrics"]["compaction_fallbacks"] == 1
    assert timeline["headline"]["lane"] == "terminal:register" and timeline["headline"]["exit_code"] == 0
    assert timeline["inbox_reads"][0]["sent"] is True
    assert timeline["final"]["text"] and timeline["final"]["source"] == "final.md"
    assert timeline["tokens"]["input_tokens"] == 1200 and timeline["tokens"]["reasoning_output_tokens"] == "unavailable"
    lanes = {lane["id"]: lane["count"] for lane in timeline["lanes"]}
    assert lanes["terminal:analysis"] == 2 and lanes["file:read"] == 1 and lanes["terminal:search"] == 1
    client = TestClient(create_app(root, static_dir=root / "missing"))
    raw = client.get(f"/api/runs/{run}/raw")
    assert raw.status_code == 200 and raw.headers["content-type"].startswith("text/plain")
    assert raw.headers["x-content-type-options"] == "nosniff"
    messages = client.get(f"/api/runs/{run}/messages?limit=1").json()
    assert messages["total"] >= 2 and len(messages["items"]) == 1 and messages["content_is_untrusted_data"]
    everything = client.get(f"/api/runs/{run}/messages?limit=200").json()["items"]
    assert not any("earlier delivery" in m["content"] for m in everything)
    assert client.get("/api/runs?agent=alice").json()["total"] == 2
    assert client.get("/api/runs?agent=bob").json()["total"] == 0
    assert client.get("/api/runs/run_missing").status_code == 404


def test_timeline_records_peer_answers_consumed_and_unreported_tokens(demo):
    root, ctx = demo
    with Archive(root) as view:
        answer = view.one("SELECT answer FROM request WHERE id=?", (ctx["requests"]["question"],))["answer"]
    run = "run_" + uuid.uuid4().hex
    folder = root / "runs" / run
    folder.mkdir()
    events = [{"type": "system", "session_id": "native_x"},
              {"type": "tool_use", "name": "terminal", "tool_call_id": "a", "input": {"command": "./bin/bio community inbox --sent"}},
              {"type": "tool_result", "name": "terminal", "tool_call_id": "a",
               "output": json.dumps({"exit_code": 0, "output": json.dumps([{"answer": answer}])})},
              {"type": "tool_use", "name": "terminal", "tool_call_id": "b", "input": {"command": f"./bin/bio community show {answer}"}},
              {"type": "tool_result", "name": "terminal", "tool_call_id": "b", "output": json.dumps({"exit_code": 0, "output": "ok"})},
              {"type": "result", "exit_code": 0, "text": "Noted.", "tokens": {"input": 0, "cache_read": 0, "output": 0}}]
    (folder / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    with sqlite3.connect(root / "board.sqlite") as db:  # test fixture: an attempt row for Bob's delivery
        db.execute("INSERT INTO attempt VALUES(?,?,?,?,?,?,NULL)",
                   (run, ctx["requests"]["question"], ctx["agents"]["bob"], "failed", f"runs/{run}", now()))
    with Archive(root) as view:
        timeline = run_timeline(view, run)
    assert timeline["axis"]["unit"] == "events" and timeline["suspensions"] == []
    assert [c["posts"] for c in timeline["answers_consumed"]] == [[answer], [answer]]
    assert timeline["tokens"]["output_tokens"] == "unavailable" and "zero" in timeline["tokens"]["note"]
    assert timeline["final"]["source"].startswith("stream") and timeline["compaction_summaries"] is None
    assert timeline["headline"] is None
