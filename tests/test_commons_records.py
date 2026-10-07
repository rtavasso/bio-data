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
from daw.commons import evidence_map, graphstore, metrics, records, views
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
    lines = records.compaction_records(harness.get("codex"), folder, {"started": None}, "codex")
    assert lines == [{**lines[0], "available": False}] and "does not expose" in lines[0]["reason"]
    hermes = records.compaction_records(harness.get("hermes"), folder, {}, "hermes")
    assert hermes[0]["available"] is False and hermes[0]["reason"] == "no session database in this run folder"
    claude = records.compaction_records(harness.get("claude"), folder, {}, "claude")
    assert claude[0]["available"] is False and claude[0]["reason"] == "no session transcripts in this run folder"
    assert records.observed_events(claude, request="r", run="x", agent="a", harness="claude") == []


# ---- v3 B10: compactions are events at capture time ---------------------------------------------------------

SECOND_SUMMARY_HOOK = r'''
import os, pathlib, sqlite3, time
trial = pathlib.Path(os.environ.get("HERMES_CWD") or os.getcwd())
db = sqlite3.connect(pathlib.Path(os.environ["HERMES_HOME"]) / "state.db")
db.execute("INSERT INTO messages VALUES(?,?,?)", ("s-early", "[CONTEXT COMPACTION] summary: counted three rows", time.time()))
db.commit()
db.close()
(trial / "scripted-compaction").write_text("fallback")
'''


def test_a_delivery_with_compactions_emits_one_compaction_observed_event_per_summary(demo, monkeypatch):
    root, ctx = demo
    monkeypatch.delenv("BIO_AGENT", raising=False)
    with Community(root) as board:
        request = board.ask(ctx["agents"]["dana"], "operator", "Summarise twice.", request_key="b10-compactions")
    before = len(_events(root, "compaction_observed"))
    assert deliver_scripted(root, request["id"], "Done.", hook=SECOND_SUMMARY_HOOK)["state"] == "completed"
    with Archive(root) as view:
        attempt = view.one("SELECT * FROM attempt WHERE request=?", (request["id"],))
        folder = root / attempt["path"]
    header, items = records.read_compactions(folder)
    assert header["count"] == 2 and header["fallbacks"] == 1
    assert header["fallback_detection"]["method"] == "marker_match"
    assert all(i["fallback_detection"] == "marker_match" for i in items)
    events = [e for e in _events(root, "compaction_observed") if e["run"] == attempt["id"]]
    assert len(_events(root, "compaction_observed")) == before + 2 and len(events) == 2
    # One event per summary: its source row id and its length as captured, the fallback labelled a marker match.
    assert [(e["source_row_id"], e["bytes"], e["sha256"]) for e in events] == [
        (i["message_id"], i["bytes"], i["sha256"]) for i in items]
    assert [e["fallback"] for e in events] == [False, True]
    assert {e["fallback_detection"] for e in events} == {"marker_match"}
    assert {e["source"] for e in events} == {"agent-state/state.db"} and events[0]["request"] == request["id"]
    assert all(e["agent"] == ctx["agents"]["dana"] for e in events)
    with Archive(root) as view:
        timeline = run_timeline(view, attempt["id"])
    assert [s["fallback_detection"] for s in timeline["compaction_summaries"]] == ["marker_match", "marker_match"]


def test_claude_stream_marks_compaction_boundaries_and_its_transcript_holds_the_summary(demo_only):
    """B16/B10: Claude Code emits compact_boundary in stream-json and records the summary in its session
    transcript (isCompactSummary); both are read offline from the stand-in and the run's snapshot."""
    from daw.commons.demo import scripted_runtime
    from daw.community_runtime import add_agent, dispatch
    root, _ = demo_only()
    with Community(root) as board, scripted_runtime(root) as (executable, _answers):
        agent = add_agent(board, "claudia", harness="claude")
        (board.trial(board.agent(agent["id"])) / "scripted-compaction").write_text("summary")
        request = board.ask("claudia", "operator", "One turn")
        dispatch(board, request["id"], executable)
        attempt = board.one("SELECT * FROM attempt WHERE request=?", (request["id"],))
    folder = root / attempt["path"]
    header, items = records.read_compactions(folder)
    assert header["available"] is True and header["source"] == "agent-state/projects" and header["count"] == 1
    assert header["fallbacks"] is None and items[0]["fallback"] is None  # no fallback marker: unavailable, not 0
    (event,) = [e for e in _events(root, "compaction_observed") if e["run"] == attempt["id"]]
    assert event["source_row_id"] == items[0]["message_id"] and event["bytes"] == items[0]["bytes"] > 0
    with Archive(root) as view:
        timeline = run_timeline(view, attempt["id"])
    assert [c["text"] for c in timeline["compactions"]] == ["compact_boundary (trigger auto, pre_tokens 1200)"]
    assert timeline["metrics"]["compactions"] == 1


# ---- v3 V13: turn economics per delivery --------------------------------------------------------------------

def test_a_delivery_records_turn_economics(demo, monkeypatch):
    root, ctx = demo
    monkeypatch.delenv("BIO_AGENT", raising=False)
    with Community(root) as board:
        request = board.ask(ctx["agents"]["dana"], "operator", "Count again.", request_key="v13-economics")
        trial = board.trial(board.agent(ctx["agents"]["dana"]))
    assert deliver_scripted(root, request["id"], "Counted.", hook=SECOND_SUMMARY_HOOK)["state"] == "completed"
    with Archive(root) as view:
        attempt = view.one("SELECT * FROM attempt WHERE request=?", (request["id"],))
        folder = root / attempt["path"]
    record = read_json(folder / "turn_economics.json")
    assert record["kind"] == "turn_economics" and record["run"] == attempt["id"] and record["harness"] == "hermes"
    assert record["tokens"] == {"input_tokens": 1200, "cached_input_tokens": 300, "output_tokens": 450}
    # The stand-in reports turn totals only: context per turn, model calls unavailable (not zero).
    assert record["context"]["unit"] == "turn" and record["model_calls"] is None
    assert record["compactions"] == {"stream_markers": 1, "summaries": 2, "fallbacks": 1,
                                     "fallback_detection": "marker_match"}
    composition = record["composition"]
    # The stand-in's session database has no roles: composition from the stream, the system prompt unmeasured.
    assert composition["basis"] == "stream" and composition["bytes"]["system_prompt"] is None
    assert composition["complete"] is False and composition["shares"] is None
    assert composition["bytes"]["tool_outputs"] > 0 and composition["bytes"]["summaries"] == sum(
        i["bytes"] for i in records.read_compactions(folder)[1])
    assert composition["bytes"]["delivery_prompt"] == (folder / "prompt.txt").stat().st_size
    time_split = record["time"]
    assert time_split["tool_wait_minutes"] > 0 and time_split["generation_minutes"] >= 0
    assert record["orientation"]["by_kind"]["inbox"] == 1 and record["orientation"]["by_kind"]["forum_search"] == 1
    assert record["orientation"]["by_kind"]["labbook_reads"] == 1 and record["orientation"]["help_calls"] == 0
    assert record["ceremony_tail_minutes"] is not None
    staged = sorted(p.name for p in (trial / ".agents" / "skills").iterdir() if (p / "SKILL.md").is_file())
    assert sorted(record["skills"]["versions"] or {}) == staged
    assert record["skills"]["reads"] == {}
    # The dashboard charts it per harness and per skill version.
    with Archive(root) as view:
        dashboard = metrics.dashboard(view)
    hermes = next(g for g in dashboard["panels"]["harness"] if g["key"] == "hermes")
    assert hermes["turn_economics"]["recorded_runs"] >= 1
    assert hermes["turn_economics"]["compactions"]["summaries"] >= 2
    versions = {p["key"]: p for p in dashboard["economics"]["skill_versions"]}
    assert (record["skills"]["version"] or "unrecorded") in versions
    skills = {s["skill"]: s for s in dashboard["economics"]["skills"]["items"]}
    assert skills["bio-research"]["bytes"] > 0 and skills["bio-research"]["budget"] >= skills["bio-research"]["bytes"]


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

@pytest.fixture(scope="module")
def cohort_rw(cohort, tmp_path_factory):
    """One writable copy of the cohort for this module's tests (each copy is about 300 MB), used in file order:
    rebuild one run's records, reindex every run, then build the graph store and add a comment."""
    copy = tmp_path_factory.mktemp("records-cohort") / "commons"
    shutil.copytree(cohort, copy, symlinks=True, ignore=shutil.ignore_patterns("cache"))
    (copy / "library" / "staging").mkdir(exist_ok=True)  # the fixture keeps no operational directories
    return copy


def test_reindexed_clock_samples_come_from_the_stream_only_where_one_gap_can_hold_the_suspension():
    """G3: execution.json, heartbeat.json and the stream's own timestamps; one gap long enough to hold the
    suspension is bracketed by event samples; ambiguous windows get none (nothing is interpolated)."""
    start = datetime(2026, 10, 5, 18, 0, 0).astimezone()
    execution = {"started": start.isoformat(), "wall_seconds": 1300.0, "monotonic_seconds": 300.0}
    heartbeat = {"observed": (start + timedelta(seconds=1290)).isoformat(), "elapsed_seconds": 290.0}
    t0 = start.timestamp()
    stamps = [(t0 + 1, 1), (t0 + 50, 2), (t0 + 100, 3), (t0 + 1150, 4), (t0 + 1200, 5)]  # slept between 3 and 4
    clock = records.reindex_clock(execution, heartbeat, stamps)
    assert [r["source"] for r in clock] == ["execution.json:started", "events.jsonl:3", "events.jsonl:4",
                                            "heartbeat.json", "execution.json:wall_seconds,monotonic_seconds"]
    assert all(r["reindexed"] for r in clock) and [r["n"] for r in clock] == list(range(5))
    before, after = clock[1], clock[2]
    assert before["wall"] == round(t0 + 100, 3) and before["monotonic"] == 100.0  # awake since launch
    assert after["wall"] == round(t0 + 1150, 3) and after["monotonic"] == 150.0  # awake until the heartbeat
    assert "one contiguous suspension assumed" in before["derived"]
    (window,) = records.clock_windows(clock)
    assert window["seconds"] == 1000.0 and window["reindexed"] and window["bracketed_by_events"]
    assert window["sources"] == ["events.jsonl:3", "events.jsonl:4"]
    # Two gaps that could each hold it (or none): no event samples, the window stays as wide as the anchors.
    split = [(t0 + 1, 1), (t0 + 1050, 2), (t0 + 1100, 3), (t0 + 1150, 4)]
    wide = records.reindex_clock({**execution, "wall_seconds": 2400.0, "monotonic_seconds": 1400.0}, None, split)
    assert [r["source"] for r in wide] == ["execution.json:started", "execution.json:wall_seconds,monotonic_seconds"]
    assert records.reindex_clock({"started": start.isoformat()}, heartbeat, stamps) == []


SPLIT_SLEEP = "run_7edb0f52ff1c4feda01bff2f09e9d7c7"  # 4562 s suspended: two host sleeps of 3139 s and 1423 s
ONE_SLEEP = "run_129da0ce09ae4a3a970b603427be0ad1"  # 1423 s, between stream lines 58 and 59


def test_committed_cohort_carries_reindexed_records_and_places_suspensions_between_samples(cohort, cohort_rw):
    """G3: the committed fixture was resettled with `--reindex-runs`; readers see suspensions placed between
    reindexed samples wherever the samples narrow them, and attributed only where they cannot."""
    with Archive(cohort) as view:
        runs = view.rows("SELECT a.id,a.path FROM attempt a ORDER BY a.created")
        timelines = {r["id"]: run_timeline(view, r["id"]) for r in runs}
    assert all((cohort / r["path"] / name).is_file() for r in runs for name in records.RECORD_FILES)
    placed = [s for t in timelines.values() for s in t["suspensions"]]
    between = [s for s in placed if s["placement"] == "reindexed_samples"]
    assert len(between) >= 14 and all(s["attributed"] is False and s["reindexed"] is True for s in between)
    assert all(s["basis"].startswith("placed between reindexed samples") and s["unplaced_seconds"] == 0
               for s in between)
    one = timelines[ONE_SLEEP]
    (suspension,) = one["suspensions"]
    assert suspension["window"]["sources"] == ["events.jsonl:58", "events.jsonl:59"]
    assert "suspension" not in one["attributed"] and one["records"]["clock"]["reindexed"] is True
    assert any("placed between reindexed samples" in line for line in one["limitations"])
    # A window holding two sleeps cannot be narrowed: the position stays attributed, with its rule.
    (split,) = timelines[SPLIT_SLEEP]["suspensions"]
    assert split["attributed"] is True and split["placement"] == "largest_event_gap_within_clock_window"
    # Event samples carry the stream's own timestamps, unchanged.
    path = next(r["path"] for r in runs if r["id"] == ONE_SLEEP)
    lines = (cohort / path / "events.jsonl").read_text().splitlines()
    for sample in records.read_clock(cohort / path):
        assert sample["reindexed"] is True
        if sample["kind"] == "event":
            line = int(sample["source"].split(":")[1])
            assert sample["wall"] == round(json.loads(lines[line - 1])["timestamp"] / 1000, 3)
    # Receipts are the indexed receipt files; compactions are unavailable (the fixture keeps no session databases).
    assert all(r["source"] == "receipt" and r["attributed"] is False for t in timelines.values() for r in t["receipts"])
    assert all(t["records"]["compactions"]["available"] is False for t in timelines.values())
    assert all(read_json(cohort / r["path"] / "turn_economics.json")["reindexed"]["by"] == "operator" for r in runs)
    indexed = _events(cohort, "receipts_indexed")
    assert sorted(e["run"] for e in indexed) == sorted(r["id"] for r in runs)
    assert all(e["reindexed"] is True and e["actor"] == "operator" for e in indexed)
    # The records are derived from the run folder alone: rebuilt from scratch they say the same.
    copy = cohort_rw
    folder = copy / path
    committed = (folder / "clock.jsonl").read_text()
    for name in records.RECORD_FILES:
        (folder / name).unlink()
    shutil.rmtree(folder / "receipts", ignore_errors=True)
    with Community(copy) as board:
        result = records.reindex_run(board, "operator", ONE_SLEEP)
        assert set(result["written"]) == set(records.RECORD_FILES)
        assert result["unavailable"]["compactions.jsonl"] == "no session database in this run folder"
        again = records.reindex_run(board, "operator", ONE_SLEEP)
        assert again["written"] == [] and set(again["kept"]) == set(records.RECORD_FILES)
        with pytest.raises(DawError, match="permission_denied"):
            records.reindex_run(board, board.rows("SELECT id FROM agent WHERE kind='agent' LIMIT 1")[0]["id"],
                                ONE_SLEEP)
    assert (folder / "clock.jsonl").read_text() == committed


def test_cohort_reindex_indexes_receipts_from_checkouts(cohort_rw):
    """Reindexing every run keeps the committed records and indexes each receipt into at most one delivery."""
    copy = cohort_rw
    with Community(copy) as board:
        runs = [r["id"] for r in board.rows("SELECT id FROM attempt WHERE state!='running' ORDER BY created")]
        for run in runs:
            records.reindex_run(board, "operator", run)
    with Archive(copy) as view:
        counted = [(records.read_receipts(view.run_folder(run)[1]) or {"counts": {"receipts": 0}})["counts"]["receipts"]
                   for run in runs]
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


def test_cohort_graph_store_build_update_and_per_node_latency(cohort_rw):
    """Measured on the real board: full build, incremental update, and per-node latency of the map node and
    artifact page (target well under 50 ms; the bound here is generous for CI machines)."""
    copy = cohort_rw
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
