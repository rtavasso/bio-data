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
    # The demo harness's token fields are not in the Hermes telemetry shape: unavailable, never zero.
    cost = summary["cost"]
    assert cost["tokens"]["input_tokens"] is None and cost["tokens"]["input_tokens_partial"] is None
    assert cost["amount"] is None and cost["unavailable_reasons"]
    panels = value["panels"]
    assert [g["label"] for g in panels["cohort"]] == ["demo-runs"]
    assert [g["label"] for g in panels["harness"]] == ["hermes"]
    assert [g["label"] for g in panels["task_type"]] == ["peer_question"]
    people = {g["label"]: g for g in panels["participant"]}
    assert {"alice", "bob", "dana", "operator"} <= set(people)
    assert people["bob"]["runs"] == 0 and people["bob"]["board"]["reuse"] == {"backed": 1, "unbacked": 1, "backed_ratio": 0.5}
    alice = people["alice"]["board"]
    assert alice["corrections"] == 1 and alice["posts_superseded"] == 1 and alice["human_marks"] == 1
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
    assert {r["harness"] for r in runs} == {"hermes"} and all(r["metrics"]["tokens"] is None for r in runs)
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
    # Claude-harness telemetry is reported; Hermes demo telemetry is not. No pricing table: no currency.
    assert brief[claude["id"]]["cost"]["tokens"]["input_tokens"] == 1200
    assert brief[alice["id"]]["cost"]["tokens"]["input_tokens"] is None
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
    assert totals[alice["id"]]["cost"]["amount"] is None  # hermes runs have no telemetry
    assert totals[alice["id"]]["calibration"]["total"] == 0
    dashboard = client.get("/api/dashboard").json()
    assert {g["label"] for g in dashboard["panels"]["harness"]} == {"hermes", "claude"}
    assert dashboard["summary"]["cost"]["amount"] is None
    assert dashboard["summary"]["cost"]["amount_partial"] == totals[claude["id"]]["cost"]["amount"]
    assert dashboard["summary"]["cost"]["tokens"]["input_tokens_partial"] == 2400


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
