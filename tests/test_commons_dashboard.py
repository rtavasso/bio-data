import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from daw.commons import metrics
from daw.commons.app import create_app
from daw.commons.archive import Archive
from daw.commons.demo import SYNTHETIC, scripted_runtime
from daw.commons.participants import add_participant
from daw.community import Community
from daw.community_runtime import add_agent, dispatch
from daw.util import DawError, now

BRIEF = "Investigate whether the demo marker differs between conditions A and B. " + SYNTHETIC
DONORS = "Test whether the demo samples share donors; report what is unmeasured. " + SYNTHETIC


def events(root):
    with Archive(root) as view:
        return view.sequence()


def stored(root):
    with Archive(root) as view:
        return {r["run"]: r for r in view.rows("SELECT * FROM run_metrics")}



@pytest.fixture
def demo(demo_only):
    """Core demo records plus this area's cohort only: the expectations below count exact records."""
    return demo_only("daw.commons.metrics:demo_cohort")

def test_demo_cohort_projection_is_idempotent_and_refreshes_changed_runs(demo):
    root, ctx = demo
    with Archive(root) as view:
        cohort = metrics.cohort(view, ctx["cohorts"]["demo"])
        attempts = [r["id"] for r in view.rows("SELECT id FROM attempt ORDER BY created")]
        assert [e["run"] for e in cohort["body"]["runs"]] == attempts
        assert all(e["assignment_source"] == "request_body_sha256" for e in cohort["body"]["runs"])
        assert {r["projection"] for r in metrics.load_runs(view)} == {"stored"}
    rows = stored(root)
    assert set(rows) == set(attempts) and {r["cohort"] for r in rows.values()} == {cohort["id"]}
    # A second refresh changes nothing and records no event.
    before = events(root)
    with Community(root) as board:
        assert metrics.refresh_metrics(board)["updated"] == []
    assert events(root) == before
    # A run file change marks the row stale; views compute it in memory without writing.
    run = attempts[0]
    folder = root / "runs" / run
    with (folder / "events.jsonl").open("a") as stream:
        stream.write(json.dumps({"type": "tool_use", "name": "terminal", "tool_call_id": "late",
                                 "input": {"command": "./bin/bio community inbox"}, "timestamp": 1}) + "\n")
    with Archive(root) as view:
        current = {r["run"]: r for r in metrics.load_runs(view)}
    assert current[run]["projection"] == "stale"
    assert current[run]["metrics"]["inbox_calls"] == json.loads(rows[run]["metrics"])["metrics"]["inbox_calls"] + 1
    assert stored(root) == rows and events(root) == before
    with Community(root) as board:
        assert metrics.refresh_metrics(board)["updated"] == [run]
    assert events(root) == before + 1
    with Archive(root) as view:
        last = view.one("SELECT kind,body FROM event ORDER BY seq DESC LIMIT 1")
        assert last["kind"] == "metrics_refreshed" and json.loads(last["body"])["runs"] == [run]
        assert {r["projection"] for r in metrics.load_runs(view)} == {"stored"}


def test_cohort_selectors_validation_and_permissions(demo):
    root, ctx = demo
    with Community(root) as board:
        runs = [r["id"] for r in board.rows("SELECT id FROM attempt ORDER BY created")]
        explicit = metrics.create_cohort(board, "operator", "first-run", runs=runs[:1],
                                         assignments={runs[0]: "brief-1"}, note="one run")
        assert explicit["body"]["runs"] == [{"run": runs[0], "request": ctx["requests"]["brief"],
                                             "agent": ctx["agents"]["alice"], "assignment": "brief-1",
                                             "assignment_source": "explicit"}]
        assert board.one("SELECT kind FROM event ORDER BY seq DESC LIMIT 1")["kind"] == "cohort_created"
        windowed = metrics.create_cohort(board, "operator", "today", since="2000-01-01", until="2999-12-31")
        assert len(windowed["body"]["runs"]) == len(runs)
        assert metrics.cohort(board, "today")["id"] == windowed["id"]
        with pytest.raises(DawError, match="empty_cohort"):
            metrics.create_cohort(board, "operator", "future", since="2999-01-01")
        with pytest.raises(DawError, match="empty_cohort"):
            metrics.create_cohort(board, "operator", "nobody", agents=["bob"])
        with pytest.raises(DawError, match="cohort_name_unavailable"):
            metrics.create_cohort(board, "operator", "today", runs=runs)
        with pytest.raises(DawError, match="unknown_run"):
            metrics.create_cohort(board, "operator", "x", runs=["run_missing"])
        with pytest.raises(DawError, match="invalid_time"):
            metrics.create_cohort(board, "operator", "x", since="2026-01-01T00:00:00")
        with pytest.raises(DawError, match="assignment_for_unlisted_run"):
            metrics.create_cohort(board, "operator", "x", runs=runs[:1], assignments={"run_other": "k"})
        with pytest.raises(DawError, match="invalid_cohort_name"):
            metrics.create_cohort(board, "operator", "bad name", runs=runs)
        add_participant(board, "rhea", "human")
        for actor in ("rhea", ctx["agents"]["alice"]):
            with pytest.raises(DawError, match="permission_denied"):
                metrics.create_cohort(board, actor, "y", runs=runs)
            with pytest.raises(DawError, match="permission_denied"):
                metrics.refresh_metrics(board, actor)


def test_dashboard_api_panels_are_read_only_and_never_report_zero_for_unavailable(demo):
    root, ctx = demo
    with Community(root) as board:
        human = add_participant(board, "rhea", "human")
        with board.writer(), board.db:  # a verification mark as the participation write path would record it
            board.db.execute("INSERT INTO mark VALUES(?,?,?,?,?,?,?,?,?)",
                             ("mark_1", human["id"], "post", ctx["posts"]["correction"], "checked_source",
                              "matches the table", "[]", "0" * 64, now()))
    (root / "runs").joinpath(stored(root).popitem()[0], "final.md").write_text("changed after refresh")
    client = TestClient(create_app(root, static_dir=root / "missing"))  # app start may create the local user
    before, rows = events(root), stored(root)
    value = client.get("/api/dashboard").json()
    assert value["projection"]["stale"] == 1 and value["pricing"]["available"] is False
    assert events(root) == before and stored(root) == rows  # GET never writes
    summary = value["summary"]
    assert summary["runs"] == 2 and summary["analysis_receipts"] == 4 and summary["analysis_failures"] == 2
    assert summary["compactions"] == 2 and summary["compaction_fallbacks"] == 0
    assert summary["ceremony_tail_minutes"]["runs"] == 2 and summary["minutes_per_executed_analysis"] is not None
    # The demo harness reports Hermes-native token telemetry; without a pricing table the amount is
    # unavailable, never zero.
    cost = summary["cost"]
    assert cost["tokens"]["input_tokens"] == 2 * 1200
    assert cost["amount"] is None and cost["currency"] is None and cost["pricing"] != "available"
    panels = value["panels"]
    assert [g["label"] for g in panels["cohort"]] == ["demo-runs"]
    assert [g["label"] for g in panels["harness"]] == ["hermes"]
    assert [g["label"] for g in panels["task_type"]] == ["peer_question"]
    people = {g["label"]: g for g in panels["participant"]}
    assert {"alice", "bob", "dana", "operator"} <= set(people)
    assert people["bob"]["runs"] == 0 and people["bob"]["board"]["reuse"] == {"backed": 1, "unbacked": 1, "backed_ratio": 0.5}
    alice = people["alice"]["board"]
    with Archive(root) as view:
        mine = view.rows("SELECT id,supersedes FROM post WHERE author=?", (ctx["agents"]["alice"],))
        superseded = {p["supersedes"] for p in mine if p["supersedes"]}
        human_marks = view.one("SELECT count(*) AS n FROM mark m JOIN agent a ON a.id=m.participant "
                               "WHERE a.kind IN ('human','operator') AND m.target_kind='post' AND m.target_id IN "
                               "(SELECT id FROM post WHERE author=?)", (ctx["agents"]["alice"],))["n"]
    assert alice["corrections"] == len(superseded) >= 1 and alice["posts_superseded"] == len(superseded)
    assert alice["human_marks"] == human_marks >= 1
    assert alice["human_marks_per_post"] == round(1 / alice["posts"], 3)
    assert people["dana"]["board"]["human_marks_per_post"] == 0
    assert people["alice"]["trend"][0]["runs"] == 2
    filtered = client.get("/api/dashboard", params={"participant": "alice", "bucket": "day"}).json()
    assert filtered["summary"]["runs"] == 2 and [g["label"] for g in filtered["panels"]["participant"]] == ["alice"]
    assert len(filtered["summary"]["trend"][0]["bucket"]) == 10
    assert client.get("/api/dashboard", params={"harness": "claude"}).json()["summary"]["runs"] == 0
    assert client.get("/api/dashboard", params={"bucket": "month"}).status_code == 400
    assert client.get("/api/dashboard", params={"participant": "nobody"}).status_code == 404
    listing = client.get("/api/cohorts").json()["items"]
    assert [c["name"] for c in listing] == ["demo-runs"] and listing[0]["runs"] == 2
    shown = client.get(f"/api/cohorts/{ctx['cohorts']['demo']}").json()
    assert shown["summary"]["runs"] == 2 and len(shown["runs"]) == 2
    assert client.get("/api/cohorts/demo-runs").json()["id"] == ctx["cohorts"]["demo"]
    assert client.get("/api/cohorts/cohort_missing").status_code == 404
    runs = client.get("/api/metrics/runs", params={"cohort": "demo-runs"}).json()["items"]
    assert {r["harness"] for r in runs} == {"hermes"} and all(r["metrics"]["tokens"] for r in runs)
    assert client.get("/api/cohorts/compare", params={"ids": ctx["cohorts"]["demo"]}).status_code == 400
    assert events(root) == before and stored(root) == rows


def _two_harness_commons(root):
    """Add carol (a Claude Code harness agent, driven by the scripted harness in Claude stream format, which
    reports token telemetry); alice and carol answer the same two assignments. Returns the two cohorts."""
    with Community(root) as board, scripted_runtime(root) as (harness, _answers):
        add_agent(board, "carol", model="claude-test", harness="claude")
        reporting = harness
        for target, body, executable in (("carol", BRIEF, reporting), ("carol", DONORS, reporting),
                                         ("alice", DONORS, harness)):
            dispatch(board, board.ask(target, "operator", body)["id"], str(executable))
        alice = metrics.create_cohort(board, "operator", "hermes-cohort", agents=["alice"])
        claude = metrics.create_cohort(board, "operator", "claude-cohort", agents=["carol"])
    return alice, claude


def test_cohort_comparison_keeps_criteria_separate_across_harnesses(demo):
    root, ctx = demo
    alice, claude = _two_harness_commons(root)
    client = TestClient(create_app(root, static_dir=root / "missing"))
    value = client.get("/api/cohorts/compare", params={"ids": f"{alice['id']},{claude['name']}"}).json()
    assert [c["harnesses"] for c in value["cohorts"]] == [["hermes"], ["claude"]]
    assert value["criteria"] == ["yield", "calibration", "corrections", "cost"]
    assert value["shared_assignments"] == 2 and len(value["assignments"]) == 3
    assert "score" not in json.dumps(value).replace("No composite score", "")
    rows = {row["excerpt"][:20]: row for row in value["assignments"]}
    brief = rows[BRIEF[:20]]["cells"]
    assert brief[alice["id"]]["harnesses"] == ["hermes"] and brief[claude["id"]]["models"] == ["claude-test"]
    assert brief[claude["id"]]["yield"] == {"posts": 1, "registered_artifacts": 0, "analysis_receipts": 2,
                                            "analysis_failures": 1}
    assert brief[alice["id"]]["calibration"] is None  # the claim ledger has no rows: unavailable, not zero
    # Both harnesses report token telemetry in their own stream shape. No pricing table: no currency.
    assert brief[claude["id"]]["cost"]["tokens"]["input_tokens"] == 1200
    assert brief[alice["id"]]["cost"]["tokens"]["input_tokens"] == 1200 and brief[alice["id"]]["cost"]["amount"] is None
    assert brief[claude["id"]]["cost"]["amount"] is None and brief[claude["id"]]["cost"]["currency"] is None
    # An assignment only one cohort attempted has a missing cell, distinct from zero yield.
    only = [row for row in value["assignments"] if not all(row["cells"].values())]
    assert len(only) == 1 and only[0]["cells"][claude["id"]] is None
    # Operator pricing and ledger claims fill cost and calibration.
    (root / "pricing.toml").write_text('currency = "USD"\n[models."claude-test"]\ninput = 3.0\ncached_input = 0.3\n'
                                       'output = 15.0\ninput_includes_cached = true\n')
    answer = client.get("/api/metrics/runs", params={"cohort": claude["id"]}).json()["items"][0]
    with Community(root) as board, board.writer(), board.db:
        post = [p for p in board.rows("SELECT id,author,body_blob FROM post")
                if board.show(p["id"])["content"].get("run") == answer["run"]][0]
        for ordinal, status in enumerate(("supported", "untestable", "supported")):
            board.db.execute("INSERT INTO claim VALUES(?,?,?,?,?,?,?,?,?,?,NULL)",
                             (f"claim_{ordinal}", post["id"], post["author"], ordinal, "a claim", status, "{}", "[]",
                              "0" * 64, now()))
    value = client.get("/api/cohorts/compare", params={"ids": f"{alice['id']},{claude['id']}"}).json()
    cells = {row["excerpt"][:20]: row["cells"] for row in value["assignments"]}
    run_cell = next(c[claude["id"]] for c in cells.values() if c[claude["id"]] and answer["run"] in c[claude["id"]]["runs"])
    assert run_cell["calibration"]["supported"] == 2 and run_cell["calibration"]["untestable"] == 1
    assert run_cell["cost"]["currency"] == "USD"
    assert run_cell["cost"]["amount"] == round((900 * 3.0 + 300 * 0.3 + 450 * 15.0) / 1e6, 6)
    totals = value["totals"]
    assert totals[claude["id"]]["cost"]["amount"] == round(2 * (900 * 3.0 + 300 * 0.3 + 450 * 15.0) / 1e6, 6)
    assert totals[alice["id"]]["cost"]["amount"] is None  # no price for the Hermes agent's model: unavailable
    assert totals[alice["id"]]["calibration"]["total"] == 0
    dashboard = client.get("/api/dashboard").json()
    assert {g["label"] for g in dashboard["panels"]["harness"]} == {"hermes", "claude"}
    assert dashboard["summary"]["cost"]["amount"] is None
    assert dashboard["summary"]["cost"]["amount_partial"] == totals[claude["id"]]["cost"]["amount"]
    assert dashboard["summary"]["cost"]["tokens"]["input_tokens"] == 1200 * dashboard["summary"]["runs"]


def test_pricing_and_token_rules():
    assert metrics.token_usage({"usage": None, "turns_completed": 1})[0] is None
    zero = {"usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}, "turns_completed": 1}
    assert metrics.token_usage(zero) == (None, "harness reported zero tokens for a completed turn")
    tokens = {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10}
    pricing = {"available": True, "currency": "EUR",
               "models": {"m": {"input": 1.0, "cached_input": 0.5, "output": 2.0, "input_includes_cached": False}}}
    assert metrics.run_cost(tokens, "m", pricing) == round((100 + 20 + 20) / 1e6, 6)
    assert metrics.run_cost(tokens, "other", pricing) is None
    assert metrics.run_cost({**tokens, "cached_input_tokens": None}, "m", pricing) is None


def test_invalid_pricing_is_reported_not_guessed(tmp_path):
    (tmp_path / "pricing.toml").write_text('currency = "USD"\n[models.m]\ninput = 1\ncached_input = 1\noutput = 1\n')
    value = metrics.load_pricing(tmp_path)
    assert value["available"] is False and "input_includes_cached" in value["reason"]
    assert metrics.load_pricing(tmp_path / "none")["available"] is False


def test_cli_cohorts_and_metrics(demo):
    from daw.bio_cli import app
    root, ctx = demo
    runner = CliRunner()
    base = ["commons", "--root", str(root)]
    with Archive(root) as view:
        run = view.one("SELECT id FROM attempt ORDER BY created")["id"]
    created = runner.invoke(app, [*base, "cohort", "create", "picked", "--run", run, "--assignment", f"{run}=brief"])
    assert created.exit_code == 0, created.output
    assert json.loads(created.output)["body"]["runs"][0]["assignment"] == "brief"
    listed = json.loads(runner.invoke(app, [*base, "cohort", "list"]).output)
    assert [c["name"] for c in listed["items"]] == ["demo-runs", "picked"]
    shown = json.loads(runner.invoke(app, [*base, "cohort", "show", "picked"]).output)
    assert shown["summary"]["runs"] == 1 and "runs" not in shown
    compared = json.loads(runner.invoke(app, [*base, "cohort", "compare", "demo-runs", "picked"]).output)
    # The explicit key "brief" is its own assignment, distinct from the request-body hash in demo-runs.
    assert compared["shared_assignments"] == 0 and len(compared["assignments"]) == 3
    refreshed = json.loads(runner.invoke(app, [*base, "metrics", "refresh"]).output)
    assert refreshed == {"runs": 2, "updated": []}
    dashboard = json.loads(runner.invoke(app, [*base, "metrics", "dashboard", "--cohort", "picked"]).output)
    assert dashboard["summary"]["runs"] == 1


def test_audit_report_has_harness_and_task_type_columns(demo, tmp_path):
    from benchmarks.agent.community import report
    root, _ = demo
    value = report(root, tmp_path / "report")
    assert {r["harness"] for r in value["runs"]} == {"hermes"}
    assert {r["task_type"] for r in value["runs"]} == {"peer_question"}
    summary = value["summary"]
    assert summary["analysis_receipts"] == 4 and summary["analysis_failures"] == 2 and summary["inbox_calls"] == 2
    assert "wall_hours" in summary and summary["finals_with_provider_citations"] == 0
    assert "| Harness | Task type |" in (tmp_path / "report" / "report.md").read_text()


# ---- spec v2 C10: honest metrics (None is unavailable, never 0) ---------------------------------

def test_cohort_dashboard_and_audit_reproduce_the_review_numbers(cohort, tmp_path):
    """Spec v2 §0 quotes the review's audit of the real PMP22 board: 23.47 compute hours, 11.65 suspended,
    279 of 440 plumbing scripts, 57 compactions, 13 fallbacks. The committed fixture keeps every stream and
    clock, so the first four reproduce exactly. Fallbacks are read from agent-state/state.db, which the fixture
    excludes (session databases are dropped), so on the fixture they are unavailable: None, never 0."""
    from benchmarks.agent.community import report
    with Archive(cohort) as view:
        summary = metrics.dashboard(view)["summary"]
    assert summary["runs"] == 97 and summary["clock_unavailable_runs"] == 0
    assert round(summary["monotonic_hours"], 2) == 23.47 and round(summary["cost"]["compute_hours"], 2) == 23.47
    assert round(summary["suspended_hours"], 2) == 11.65
    assert (summary["plumbing_scripts"], summary["scripts_written"]) == (279, 440)
    assert summary["compactions"] == 57 and summary["compaction_unavailable_runs"] == 0
    assert summary["compaction_fallbacks"] is None and summary["compaction_summaries"] is None
    audit = report(cohort, tmp_path / "audit")["summary"]
    assert (audit["monotonic_hours"], audit["suspended_hours"]) == (23.47, 11.65)
    assert (audit["plumbing_scripts"], audit["scripts_written"], audit["compactions"]) == (279, 440, 57)
    assert audit["compaction_fallbacks"] is None and audit["compaction_summaries"] is None
    assert "| compaction_fallbacks | unavailable |" in (tmp_path / "audit" / "report.md").read_text()


def test_unavailable_clocks_streams_and_compactions_are_none_not_zero(tmp_path):
    from daw.commons.runmetrics import run_metrics
    from daw.harness import get
    folder = tmp_path / "run"
    folder.mkdir()
    empty = {"items": [], "events": []}
    m = run_metrics(folder, empty)  # no execution.json, no events.jsonl, no final.md
    assert m["wall_seconds"] is None and m["monotonic_seconds"] is None and m["suspended_seconds"] is None
    assert m["tool_calls"] is None and m["compactions"] is None and m["plumbing_scripts"] is None
    assert m["provider_citation_in_final"] is None and m["analysis_failures"] is None
    (folder / "execution.json").write_text(json.dumps({"wall_seconds": 100.0, "monotonic_seconds": 90.0}))
    (folder / "events.jsonl").write_text("")
    m = run_metrics(folder, empty)
    assert m["suspended_seconds"] == 0 and m["tool_calls"] == 0 and m["compactions"] == 0  # measured zero
    assert run_metrics(folder, empty, compactions_reported=False)["compactions"] is None
    # Analyses whose harness reports no exit codes (Claude Code) have unknown, not zero, failures.
    analysis = {"name": "terminal", "command": "./bin/python run_analysis.py x.py", "exit_code": None, "input": {}}
    m = run_metrics(folder, {"items": [analysis], "events": []})
    assert m["analysis_receipts"] == 1 and m["analysis_failures"] is None and m["analysis_exit_codes_unknown"] == 1
    # The capability flag per adapter: Hermes marks compactions in its stream; the others do not.
    assert get("hermes").reports_compactions({}) and not get("claude").reports_compactions({})
    assert not get("codex").reports_compactions({}) and not get("mcp").reports_compactions({})
    assert get("scripted").reports_compactions({}) and not get("scripted").reports_compactions(
        {"harness_options": {"stream_format": "claude"}})
    runs = [{"state": "completed", "metrics": {"monotonic_seconds": None, "wall_seconds": None, "suspended_seconds": None,
                                               "compactions": None, "analysis_receipts": 0, "scripts_written": 0,
                                               "plumbing_scripts": 0, "tool_calls": 3, "inbox_calls": 0,
                                               "analysis_failures": 0}}]
    criteria = metrics.run_criteria(runs)
    assert criteria["suspended_hours"] is None and criteria["suspensions"] is None and criteria["compactions"] is None
    assert criteria["monotonic_hours"] is None and criteria["clock_unavailable_runs"] == 1


def test_claude_runs_report_compactions_unavailable_on_dashboard_and_timeline(demo_only):
    root, _ = demo_only()
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        add_agent(board, "claudia", harness="claude")
        request = board.ask("claudia", "operator", "One turn")
        dispatch(board, request["id"], executable)
        run = board.one("SELECT id FROM attempt WHERE request=?", (request["id"],))["id"]
    client = TestClient(create_app(root, local_user="local", static_dir=root / "missing"))
    timeline = client.get(f"/api/runs/{run}").json()
    assert timeline["compactions"] is None and timeline["metrics"]["compactions"] is None
    dashboard = client.get("/api/dashboard", params={"harness": "claude"}).json()
    assert dashboard["summary"]["compactions"] is None and dashboard["summary"]["compaction_unavailable_runs"] == 1


# ---- spec v2 V1: claims authoring per cohort -----------------------------------------------------------------

def test_dashboard_reports_claims_per_post_and_pointer_scopes(demo_only):
    """V1: claims per post, evidence-carrying posts with claims, and the kind and scope split of claim pointers
    (cell/key/line from the locator grammar, record without a locator), beside the number coverage shares."""
    root, ctx = demo_only("daw.commons.claims:extend_demo", "daw.commons.metrics:demo_cohort")
    with Archive(root) as view:
        claims = view.rows("SELECT post,pointers FROM claim")
        board = metrics.dashboard(view)
    authoring = board["summary"]["board"]["authoring"]
    pointers = [p for c in claims for p in json.loads(c["pointers"])]
    assert authoring["claims"] == len(claims) > 0 and authoring["posts_with_claims"] == len({c["post"] for c in claims})
    assert authoring["claims_per_post"] == round(len(claims) / authoring["posts"], 3)
    assert authoring["pointers"] == len(pointers) == sum(authoring["pointer_scopes"].values())
    assert sum(authoring["pointer_kinds"].values()) == len(pointers)
    assert authoring["pointer_scopes"]["record"] == sum(1 for p in pointers if not p.get("locator"))
    assert 0 <= authoring["evidence_posts_with_claims"] <= authoring["evidence_posts"]
    assert {"claim_share", "cell_share"} <= set(board["summary"]["board"]["numbers"])
    # Per cohort, through the same group function (the demo cohort's runs).
    assert all("authoring" in g["board"] for g in board["panels"]["cohort"])
    assert metrics.pointer_scope({"kind": "locator", "id": "artifact_x", "locator": "row=B;col=v"}) == "cell"
    assert metrics.pointer_scope({"kind": "locator", "id": "artifact_x", "locator": "key=a.b"}) == "key"
    assert metrics.pointer_scope({"kind": "locator", "id": "post_x", "locator": "the third paragraph"}) == "invalid"


def test_cohort_claims_authoring_baseline_is_zero_claims_not_unavailable(cohort):
    """On the real cohort (before V1) agents wrote no claims: zero claims is a measured zero over its posts, and
    the share of evidence-carrying posts with claims is 0.0 (a denominator exists), never None."""
    with Archive(cohort) as view:
        authoring = metrics.dashboard(view)["summary"]["board"]["authoring"]
    assert authoring["claims"] == 0 and authoring["posts"] == 269 and authoring["evidence_posts"] > 0
    assert authoring["evidence_posts_with_claims_share"] == 0.0 and authoring["claims_per_post"] == 0.0
    assert authoring["pointers"] == 0 and authoring["cell_pointer_share"] is None


def test_agent_reads_per_turn_from_captured_commands(tmp_path):
    """V11: inbox, search, overview and frontier calls per turn, counted from each delivery's terminal commands;
    a run without a stream is left out of the mean (unavailable), never counted as zero."""
    from daw.commons.runmetrics import run_metrics
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "events.jsonl").write_text("")
    commands = ["./bin/bio community overview", "./bin/bio community inbox --acts", "./bin/bio community frontier "
                "--mine", "./bin/bio community experiments", "./bin/bio community search --text x"]
    parsed = {"items": [{"name": "terminal", "command": c, "input": {}} for c in commands], "events": []}
    counted = run_metrics(folder, parsed)
    assert (counted["overview_calls"], counted["inbox_calls"], counted["frontier_reads"],
            counted["forum_searches"]) == (1, 1, 2, 1)
    runs = [{"state": "completed", "metrics": counted},
            {"state": "completed", "metrics": {**counted, "overview_calls": 0, "inbox_calls": 3}},
            {"state": "completed", "metrics": {"overview_calls": None, "inbox_calls": None}}]
    reads = metrics.run_criteria(runs)["agent_reads"]
    assert reads["overview_calls"] == 1 and reads["overview_calls_per_turn"] == 0.5
    assert reads["inbox_calls"] == 4 and reads["inbox_calls_per_turn"] == 2.0
    assert metrics.run_criteria(runs[2:])["agent_reads"]["inbox_calls_per_turn"] is None


def test_cohort_dashboard_reports_agent_reads_and_frontier_closure(cohort):
    """On the real cohort: inbox and search calls per turn are measured; no overview or frontier read existed yet
    (a measured zero), and the board-wide frontier closure is present."""
    with Archive(cohort) as view:
        dashboard = metrics.dashboard(view)
    reads = dashboard["summary"]["agent_reads"]
    assert reads["inbox_calls"] > 0 and reads["inbox_calls_per_turn"] > 0 and reads["forum_searches_per_turn"] > 0
    assert reads["overview_calls"] == 0 and reads["frontier_reads"] == 0
    assert dashboard["frontier"]["completed_questions"] > 0
