"""Spec v2 V6: record what the timeline attributes (clock, compaction and receipt records) and the persistent
graph store behind the map and the artifact page. Invariants on the synthetic demo; shares, counts and latency
on a private copy of the real cohort board (spec v2 C0)."""
import json
import shutil
import sqlite3
import statistics
import sys
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from daw import agent_capture
from daw.commons import evidence_map, graphstore, records, views
from daw.commons.app import create_app
from daw.commons.archive import Archive
from daw.commons.demo import deliver_scripted
from daw.commons.moderation import Visibility, hide
from daw.commons.participation import comment
from daw.commons.timeline import run_timeline
from daw.community import Community
from daw.util import DawError, file_hash, read_json, write_json


def _events(root, kind):
    with Archive(root) as view:
        return [json.loads(r["body"]) for r in view.rows("SELECT body FROM event WHERE kind=? ORDER BY seq", (kind,))]


def _normal(graph):
    return json.loads(json.dumps({"nodes": graph.nodes, "edges": {"|".join(k): v for k, v in graph.edges.items()}},
                                 sort_keys=True))


def _in_memory(view, vis):
    """The graph replayed from every segment computed in memory (what a commons without a store answers)."""
    graph = evidence_map.replay([op for ops in evidence_map.record_all(view).values() for op in ops], vis)
    for node in graph.nodes.values():
        node["stores"].sort()
    evidence_map._label_superseded(graph)
    evidence_map._label_withheld(vis, graph)
    return _normal(graph)


# ---- clock records (capture layer) ------------------------------------------------------------------------

def test_capture_writes_clock_records_beside_the_untouched_stream(tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("")
    script = "import time, json\nfor i in range(3):\n    print(json.dumps({'type': 'x', 'i': i}), flush=True)\n    time.sleep(0.25)\n"
    result = agent_capture.execute([sys.executable, "-c", script], prompt, tmp_path, tmp_path,
                                   {"PATH": "/usr/bin:/bin"}, clock_seconds=0.2)
    clock = records.read_clock(tmp_path)
    assert result["clock"] == {"file": "clock.jsonl", "cadence_seconds": 0.2, "records": len(clock)}
    assert clock[0]["kind"] == "start" and clock[-1]["kind"] == "finish" and len(clock) >= 4
    assert all(isinstance(r["wall"], float) and isinstance(r["monotonic"], float) for r in clock)
    assert [r["n"] for r in clock] == list(range(len(clock)))
    assert all(b["monotonic"] >= a["monotonic"] for a, b in zip(clock, clock[1:], strict=False))
    # events.jsonl holds only the harness's bytes (its sha256 is the answer's transcript hash).
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert [json.loads(line)["i"] for line in lines] == [0, 1, 2]
    assert records.clock_windows(clock) == []


def test_a_suspension_between_clock_records_is_a_recorded_window(tmp_path, monkeypatch):
    class Clock:
        """Wall time jumps two hours once, mid-run; monotonic time does not (a host sleep)."""
        jumped = 0.0

        def monotonic(self):
            import time as real
            return real.monotonic()

        def time(self):
            import time as real
            if real.monotonic() - started > 0.3:
                self.jumped = 7200.0
            return real.time() + self.jumped

        def sleep(self, seconds):
            import time as real
            real.sleep(seconds)
    import time as real
    started = real.monotonic()
    monkeypatch.setattr(agent_capture, "time", Clock())
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("")
    result = agent_capture.execute([sys.executable, "-c", "import time; time.sleep(0.7)"], prompt, tmp_path, tmp_path,
                                   {"PATH": "/usr/bin:/bin"}, clock_seconds=0.1)
    assert result["host_sleep_detected"]
    (window,) = records.clock_windows(records.read_clock(tmp_path))
    assert 7199 < window["seconds"] < 7201 and window["precise"] and window["sources"] == ["clock.jsonl"]
    summary = records.clock_summary(records.read_clock(tmp_path), read_json(tmp_path / "execution.json"))
    assert summary["unrecorded_seconds"] < 1 and summary["reindexed"] is False


# ---- capture-time records after a delivery ---------------------------------------------------------------

ANALYSIS_HOOK = r'''
import os, pathlib, subprocess, sys
trial = pathlib.Path(os.environ.get("HERMES_CWD") or os.getcwd())
question = sorted((trial / "workspace" / "questions").iterdir())[0]
(question / "scripts").mkdir(exist_ok=True)
(question / "outputs").mkdir(exist_ok=True)
script = question / "scripts" / "count.py"
script.write_text("import pathlib, sys\npathlib.Path(sys.argv[0]).parent.parent.joinpath('outputs', 'count.tsv')"
                  ".write_text('n,3')")
receipt = question / "outputs" / "count-execution-r001.json"
subprocess.run([sys.executable, str(trial / ".agents/skills/bio-research/scripts/run_analysis.py"), "--receipt",
                str(receipt), "--output", str(question / "outputs" / "count.tsv"), "--", sys.executable, str(script)],
               cwd=trial, capture_output=True, check=True)
(trial / "scripted-compaction").write_text("fallback")
'''


def test_delivery_records_compactions_and_receipts_and_the_timeline_draws_them(demo, monkeypatch):
    root, ctx = demo
    monkeypatch.delenv("BIO_AGENT", raising=False)
    with Community(root) as board:
        request = board.ask(ctx["agents"]["dana"], "operator", "Count something.", request_key="v6-records")
        trial = board.trial(board.agent(ctx["agents"]["dana"]))
    row = deliver_scripted(root, request["id"], "Counted.", hook=ANALYSIS_HOOK)
    assert row["state"] == "completed"
    with Archive(root) as view:
        attempt = view.one("SELECT * FROM attempt WHERE request=?", (request["id"],))
        folder = root / attempt["path"]
    # Clock records, compactions recorded from the session database, receipts indexed from the checkout.
    assert len(records.read_clock(folder)) >= 2
    header, items = records.read_compactions(folder)
    assert header["available"] is True and header["source"] == "agent-state/state.db"
    assert header["count"] == 1 and header["fallbacks"] == 1
    (item,) = items
    assert item["fallback"] is True and item["message_id"] is not None and len(item["sha256"]) == 64
    index = records.read_receipts(folder)
    (receipt,) = index["receipts"]
    assert receipt["path"].endswith("outputs/count-execution-r001.json") and receipt["found_by"] == "scan"
    assert receipt["outcome"] == "pass" and receipt["complete"] is True and receipt["exit_code"] == 0
    assert receipt["sha256"] == file_hash(trial / receipt["path"])
    assert (folder / receipt["copy"]).read_bytes() == (trial / receipt["path"]).read_bytes()
    assert receipt["verified"]["producer_now"] == "unchanged" and receipt["verified"]["outputs_now"] == ["unchanged"]
    assert receipt["producer"].endswith("scripts/count.py") and not receipt["producer"].startswith("/")
    assert {c["line"] for c in index["unreceipted_calls"]} and len(index["unreceipted_calls"]) == 2
    (event,) = [e for e in _events(root, "receipts_indexed") if e["run"] == attempt["id"]]
    assert event["receipts"] == 1 and event["pass"] == 1 and event["file_sha256"] == file_hash(folder / "receipts.json")
    # The timeline draws receipts and compaction summaries from the records, not from exit codes.
    with Archive(root) as view:
        timeline = run_timeline(view, attempt["id"])
    (drawn,) = timeline["receipts"]
    assert drawn["source"] == "receipt" and drawn["attributed"] is False and drawn["outcome"] == "pass"
    assert drawn["receipt"]["sha256"] == receipt["sha256"]
    assert len(timeline["unreceipted_analysis_calls"]) == 2
    assert "receipts" not in timeline["attributed"] and "suspension" not in timeline["attributed"]
    (summary,) = timeline["compaction_summaries"]
    assert summary["source"] == "compactions.jsonl" and summary["fallback"] is True and summary["excerpt"]
    assert timeline["records"]["receipts"]["counts"]["receipts"] == 1
    assert timeline["records"]["compactions"]["fallbacks"] == 1 and timeline["records"]["clock"]["records"] >= 2
    # Records are written once: a second capture keeps them and appends no second event.
    with Community(root) as board:
        again = records.record_delivery(board, request["id"], attempt["id"], board.agent(ctx["agents"]["dana"]), None,
                                        folder, trial, read_json(folder / "execution.json"), {"items": []})
    assert again["recorded"] == {} and len([e for e in _events(root, "receipts_indexed")
                                            if e["run"] == attempt["id"]]) == 1


def test_harnesses_without_session_compactions_record_unavailable(tmp_path):
    from daw import harness
    folder = tmp_path / "run"
    folder.mkdir()
    lines = records.compaction_records(harness.get("claude"), folder, {"started": None}, "claude")
    assert lines == [{**lines[0], "available": False}] and "does not expose" in lines[0]["reason"]
    hermes = records.compaction_records(harness.get("hermes"), folder, {}, "hermes")
    assert hermes[0]["available"] is False and hermes[0]["reason"] == "no session database in this run folder"


def test_receipts_outside_the_window_or_from_another_checkout_are_not_indexed(tmp_path):
    trial = tmp_path / "agents" / "agent_aa" / "trial"
    outputs = trial / "workspace" / "questions" / "q_1" / "outputs"
    outputs.mkdir(parents=True)
    start = datetime(2026, 10, 1, 12, 0, 0).astimezone()
    execution = {"started": start.isoformat(), "finished": (start + timedelta(minutes=10)).isoformat()}

    def receipt(name, began, cwd):
        write_json(outputs / name, {"version": 1, "argv": ["python", "scripts/x.py"], "cwd": cwd,
                                    "producer": f"{cwd}/workspace/questions/q_1/scripts/x.py", "code_sha256": "0" * 64,
                                    "started": began.isoformat(), "finished": (began + timedelta(seconds=1)).isoformat(),
                                    "exit_code": 1, "outputs": [], "code_unchanged": True, "complete": False})
    receipt("inside.json", start + timedelta(minutes=1), "/host/agents/agent_aa/trial")
    receipt("before.json", start - timedelta(hours=1), "/host/agents/agent_aa/trial")
    receipt("forked.json", start + timedelta(minutes=2), "/host/agents/agent_bb/trial")
    (outputs / "notes.json").write_text('{"code_sha256": 1}')
    folder = tmp_path / "run"
    folder.mkdir()
    index = records.index_receipts(trial, folder, execution, {"items": []}, agent="agent_aa", run="run_x")
    (only,) = index["receipts"]
    assert only["path"] == "workspace/questions/q_1/outputs/inside.json" and only["outcome"] == "fail"
    assert only["producer"] == "workspace/questions/q_1/scripts/x.py" and only["verified"]["producer_now"] == "missing"
    assert index["scanned"]["skipped"] == {"outside_window": 1, "foreign_checkout": 1, "not_a_receipt": 1,
                                           "unbounded": 0}


def test_timeline_places_a_suspension_by_clock_record(demo):
    """A run with clock records: the suspension sits where consecutive records show wall >> monotonic, and is
    recorded (attributed: false); the axis excludes it."""
    root, _ = demo
    with Archive(root) as view:
        run = view.one("SELECT * FROM attempt WHERE state='completed' ORDER BY created LIMIT 1")
    folder = root / run["path"]
    lines = (folder / "events.jsonl").read_text().splitlines()
    stamped = []
    for n, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
        except ValueError:
            stamped.append(line)
            continue
        if n >= 6:
            event["timestamp"] += 7_200_000  # the host slept between lines 5 and 6
        stamped.append(json.dumps(event))
    (folder / "events.jsonl").write_text("\n".join(stamped) + "\n")
    events = [json.loads(line) for line in stamped if line.startswith("{")]
    first = min(e["timestamp"] for e in events if "timestamp" in e) / 1000
    line5 = json.loads(lines[4])["timestamp"] / 1000
    clock = [{"n": 0, "kind": "start", "wall": first - 1, "monotonic": 0.0},
             {"n": 1, "kind": "tick", "wall": line5 + 0.5, "monotonic": line5 + 0.5 - first + 1},
             {"n": 2, "kind": "tick", "wall": line5 + 1.5 + 7200, "monotonic": line5 + 1.5 - first + 1},
             {"n": 3, "kind": "finish", "wall": first + 7300, "monotonic": 101.0}]
    (folder / "clock.jsonl").write_text("".join(json.dumps(r) + "\n" for r in clock))
    execution = read_json(folder / "execution.json")
    execution.update(wall_seconds=7301.0, monotonic_seconds=101.0)
    write_json(folder / "execution.json", execution)
    with Archive(root) as view:
        timeline = run_timeline(view, run["id"])
    (suspension,) = timeline["suspensions"]
    assert suspension["attributed"] is False and suspension["placement"] == "clock_records"
    assert suspension["records"] == [1, 2] and 7199 < suspension["seconds"] < 7201
    call5 = next(c for c in timeline["calls"] if c["result_line"] == 5)
    # Placed between the two records (0.5 s after line 5, where record 1 was written), not at a heuristic gap.
    assert call5["t_end"] < suspension["at"] <= call5["t_end"] + 1 and suspension["unplaced_seconds"] == 0
    after = next(c for c in timeline["calls"] if c["line"] > 6)
    assert after["t"] - suspension["at"] < 10  # the next call follows on the monotonic axis
    assert timeline["axis"]["duration"] < 120 and "suspension" not in timeline["attributed"]
    assert "clock records" in timeline["limitations"][-3]


# ---- reindexing old runs (the cohort) -------------------------------------------------------------------

def _cohort_copy(cohort, tmp_path):
    copy = tmp_path / "cohort"
    shutil.copytree(cohort, copy, symlinks=True, ignore=shutil.ignore_patterns("cache"))
    (copy / "library" / "staging").mkdir(exist_ok=True)  # the fixture keeps no operational directories
    return copy


def test_cohort_runs_keep_the_attributed_style_until_reindexed(cohort, tmp_path):
    with Archive(cohort) as view:
        runs = view.rows("SELECT a.id,a.path FROM attempt a ORDER BY a.created")
        suspended = [r for r in runs if run_timeline(view, r["id"])["suspensions"]]
        old = run_timeline(view, suspended[0]["id"])
    assert all(not (cohort / r["path"] / name).exists() for r in runs for name in records.RECORD_FILES)
    assert old["suspensions"][0]["attributed"] is True and old["records"]["clock"] is None
    assert all(r["attributed"] for r in old["receipts"])
    copy = _cohort_copy(cohort, tmp_path)
    with Community(copy) as board:
        result = records.reindex_run(board, "operator", suspended[0]["id"])
        assert set(result["written"]) == {"clock.jsonl", "compactions.jsonl", "receipts.json"}
        assert result["unavailable"]["compactions.jsonl"] == "no session database in this run folder"
        again = records.reindex_run(board, "operator", suspended[0]["id"])
        assert again["written"] == [] and set(again["kept"]) == set(records.RECORD_FILES)
        with pytest.raises(DawError, match="permission_denied"):
            records.reindex_run(board, board.rows("SELECT id FROM agent WHERE kind='agent' LIMIT 1")[0]["id"],
                                suspended[0]["id"])
    folder = copy / suspended[0]["path"]
    clock = records.read_clock(folder)
    # Only recorded samples: launch (execution.json), last heartbeat, finish; nothing interpolated.
    assert [r["source"] for r in clock][0] == "execution.json:started" and len(clock) <= 3
    assert all(r["reindexed"] for r in clock)
    header, items = records.read_compactions(folder)
    assert header["available"] is False and items == []
    with Archive(copy) as view:
        timeline = run_timeline(view, suspended[0]["id"])
    (suspension,) = timeline["suspensions"]
    # A window as wide as the run only bounds the suspension: its position stays attributed.
    assert suspension["attributed"] is True and suspension["placement"] in (
        "largest_event_gap_within_clock_window", "before_first_event", "after_last_event")
    assert timeline["records"]["clock"]["reindexed"] is True
    assert all(r["attributed"] is False and r["source"] == "receipt" for r in timeline["receipts"])
    assert timeline["compaction_summaries"] is None and timeline["records"]["compactions"]["available"] is False
    (event,) = _events(copy, "receipts_indexed")
    assert event["reindexed"] is True and event["run"] == suspended[0]["id"] and event["actor"] == "operator"


def test_cohort_reindex_indexes_receipts_from_checkouts(cohort, tmp_path):
    copy = _cohort_copy(cohort, tmp_path)
    with Community(copy) as board:
        runs = [r["id"] for r in board.rows("SELECT id FROM attempt WHERE state!='running' ORDER BY created")]
        results = [records.reindex_run(board, "operator", run) for run in runs]
    counted = [r["receipts"]["receipts"] for r in results if r["receipts"]]
    # The cohort's checkouts hold 179 run_analysis.py receipts; each is indexed into at most one delivery.
    assert sum(counted) > 0
    seen = {}
    with Archive(copy) as view:
        for run in runs:
            index = records.read_receipts(copy / view.run_folder(run)[1].relative_to(copy))
            for receipt in (index or {}).get("receipts", []):
                assert receipt["sha256"] not in seen, (receipt["path"], seen.get(receipt["sha256"]), run)
                seen[receipt["sha256"]] = run
    assert len(seen) == sum(counted)


# ---- the graph store ----------------------------------------------------------------------------------

def test_graph_store_answers_equal_the_in_memory_build(demo):
    root, ctx = demo
    graphstore.refresh(root, full=True)
    with Community(root) as board:
        hide(board, "operator", ctx["posts"]["finding"], "test hide")
    for caller, full in ((None, False), ({"id": "operator", "kind": "operator"}, True)):
        with Archive(root) as view:
            vis = Visibility.of(view, caller, full)
            assert graphstore.reader(view).status()["board:posts"] == "fresh"
            stored = _normal(evidence_map.build(view, vis))
            assert stored == _in_memory(view, vis)
    with Archive(root) as view:
        node = evidence_map.node_record(view, ctx["posts"]["finding"])
        assert node["hidden"] is True and node["map"]["node"]["label"].startswith("hidden post")
        assert "title" not in node["map"]["node"]
        assert not [e for e in node["map"]["edges"] if e["relation"] in ("authored", "evidence")]


def test_graph_store_updates_incrementally_and_reads_never_write(demo):
    root, ctx = demo
    shutil.rmtree(root / "cache" / "graph", ignore_errors=True)
    client = TestClient(create_app(root, static_dir=root / "missing"))
    # Without a store, reads build in memory and create nothing.
    assert client.get("/api/map/store").json()["present"] is False
    artifact = ctx["artifacts"]["contrast"]
    assert client.get(f"/api/map/node/{artifact}").status_code == 200
    assert client.get(f"/api/artifacts/{artifact}").status_code == 200
    assert not (root / "cache" / "graph").exists()
    first = graphstore.refresh(root)
    assert first["rebuilt"] is True
    store = graphstore.location(root)
    stamp = (store.stat().st_mtime_ns, file_hash(store))
    for path in ("/api/map/store", f"/api/map/node/{artifact}", f"/api/artifacts/{artifact}", "/api/map"):
        assert client.get(path).status_code == 200
    assert (store.stat().st_mtime_ns, file_hash(store)) == stamp
    assert client.get("/api/map/store").json()["current"] is True
    # A new post: the posts segment is behind; reads add the delta in memory (no write), equal to a fresh build.
    with Community(root) as board:
        made = comment(board, "operator", "artifact", artifact,
                       "Which column is the contrast?")
    with Archive(root) as view:
        assert graphstore.reader(view).status()["board:posts"] == "behind"
        vis = Visibility.of(view)
        assert _normal(evidence_map.build(view, vis)) == _in_memory(view, vis)
        page = views.artifact_view(view, artifact)
    assert made["post"] in [c["id"] for c in page["comments"]]
    assert (store.stat().st_mtime_ns, file_hash(store)) == stamp
    update = graphstore.refresh(root)
    assert update["rebuilt"] is False and update["segments"]["board:posts"]["action"] == "appended"
    assert update["segments"]["library"]["action"] == "kept"
    assert update["segments"]["merged"]["action"] == "updated"
    # A workspace change without a board event: that catalog segment alone is rebuilt.
    with Community(root) as board:
        trial = board.trial(board.agent(ctx["agents"]["dana"]))
    with sqlite3.connect(trial / "workspace" / "catalog.sqlite") as db:
        db.execute("UPDATE question SET updated='2099-01-01T00:00:00+00:00'")
    with Archive(root) as view:
        reader = graphstore.reader(view)
        assert reader.status()["workspace:" + ctx["agents"]["dana"]] == "stale"
        vis = Visibility.of(view)
        assert _normal(evidence_map.build(view, vis)) == _in_memory(view, vis)
    update = graphstore.refresh(root)
    changed = {k for k, v in update["segments"].items() if v["action"] not in ("kept",)}
    assert changed == {"workspace:" + ctx["agents"]["dana"], "board:notebooks", "merged"}
    # Never authoritative: delete it and every answer is the same.
    with Archive(root) as view:
        with_store = views.artifact_view(view, artifact)
    shutil.rmtree(root / "cache" / "graph")
    with Archive(root) as view:
        assert views.artifact_view(view, artifact) == with_store


def test_a_successful_write_refreshes_the_store_outside_the_get_handler(demo):
    root, ctx = demo
    graphstore.refresh(root, full=True)
    client = TestClient(create_app(root, local_user="rhea", static_dir=root / "missing"))
    response = client.post("/api/comments", headers={"X-Colloquy-Request": "1"},
                           json={"target_kind": "artifact", "target_id": ctx["artifacts"]["contrast"],
                                 "body": "Is the contrast log2?"})
    assert response.status_code < 300, response.text
    assert graphstore.wait(root)
    with Archive(root) as view:
        assert graphstore.reader(view).status()["board:posts"] == "fresh"


def test_cohort_graph_store_build_update_and_per_node_latency(cohort, tmp_path):
    """Measured on the real board: full build, incremental update, and per-node latency of the map node and
    artifact page (target well under 50 ms; the bound here is generous for CI machines)."""
    copy = _cohort_copy(cohort, tmp_path)
    began = time.perf_counter()
    built = graphstore.refresh(copy, full=True)
    full_seconds = time.perf_counter() - began
    assert built["segments"]["merged"]["nodes"] >= 3462
    with Archive(copy) as view:
        vis = Visibility.of(view)
        assert _normal(evidence_map.build(view, vis)) == _in_memory(view, vis)
        artifacts = [r["id"] for r in view.library.rows("SELECT id FROM artifact ORDER BY id LIMIT 30")]
        posts = [r["id"] for r in view.rows("SELECT id FROM post ORDER BY seq LIMIT 30")]
    timings = {"node": [], "artifact": []}
    for identity in artifacts + posts:
        with Archive(copy) as view:
            start = time.perf_counter()
            record = evidence_map.node_record(view, identity)
            timings["node"].append(time.perf_counter() - start)
            assert record["map"]["node"]["id"] == identity
    for identity in artifacts:
        with Archive(copy) as view:
            start = time.perf_counter()
            views.artifact_view(view, identity)
            timings["artifact"].append(time.perf_counter() - start)
    with Community(copy) as board:
        comment(board, "operator", "artifact", artifacts[0], "Checked the bytes.")
    update = graphstore.refresh(copy)
    assert update["segments"]["board:posts"]["action"] == "appended" and update["seconds"] < 30
    print(json.dumps({"full_build_seconds": round(full_seconds, 2), "incremental_seconds": update["seconds"],
                      **{k: {"median_ms": round(statistics.median(v) * 1000, 1), "max_ms": round(max(v) * 1000, 1)}
                         for k, v in timings.items()}}))
    assert statistics.median(timings["node"]) < 0.25 and statistics.median(timings["artifact"]) < 0.25
    assert full_seconds < 120
