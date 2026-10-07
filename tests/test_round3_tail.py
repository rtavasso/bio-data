"""Round three, the registration and CLI tail: each test names the cohort behaviour it closes."""
import json
import runpy
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daw.bio_cli import app
from daw.catalog import Workspace
from daw.community import Community
from daw.util import DawError
from daw.work import create_question

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / ".agents/skills/bio-research/scripts"
BIO = f"{sys.executable} -m daw.bio_cli"


def helper(name):
    return runpy.run_path(str(SCRIPTS / name))


def no_reserve(root):
    (root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0\n")


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "ws"
    Workspace.create(root).close()
    no_reserve(root)
    ws = Workspace(root)
    question = create_question(ws, "Round three tail")
    ws.close()
    return root, question


def artifact_inputs(root, artifact):
    ws = Workspace(root)
    try:
        return ws.rows("SELECT blob, source_identity FROM artifact_input WHERE artifact_id=?", (artifact,))
    finally:
        ws.close()


# ---- 1. registration from run_analysis.py receipts: agents hand-wrote 12-15 KB plans duplicating them

def _runs(tmp_path, monkeypatch):
    """Two receipts: count.py reads a source table; scale.py reads count.py's output (a batch dependency)."""
    monkeypatch.chdir(tmp_path)
    run = helper("run_analysis.py")["run"]
    scripts, outputs = tmp_path / "q" / "scripts", tmp_path / "q" / "outputs"
    scripts.mkdir(parents=True)
    outputs.mkdir()
    source = tmp_path / "q" / "source.tsv"
    source.write_text("gene\tvalue\nPMP22\t2\nMPZ\t3\n")
    count = scripts / "count.py"
    count.write_text("import sys\nrows = open(sys.argv[1]).read().splitlines()[1:]\n"
                     "open(sys.argv[2], 'w').write(f'n\\t{len(rows)}\\n')\nopen(sys.argv[3], 'w').write('{}\\n')\n")
    scale = scripts / "scale.py"
    scale.write_text("import sys\nn = int(open(sys.argv[1]).read().split()[1])\nopen(sys.argv[2], 'w').write(f'{n * 10}\\n')\n")
    first, side, second = outputs / "count.tsv", outputs / "side.json", outputs / "scaled.txt"
    r1, r2 = outputs / "execution-r001.json", outputs / "execution-r002.json"
    assert run(r1, [first, side], [sys.executable, str(count), str(source), str(first), str(side)], [source]) == 0
    assert run(r2, [second], [sys.executable, str(scale), str(first), str(second)], [first]) == 0
    return {"source": source, "count": count, "scale": scale, "first": first, "side": side, "second": second,
            "r1": r1, "r2": r2}


def test_register_batch_builds_the_plan_from_receipts_and_cites_batch_outputs_by_artifact(workspace, tmp_path,
                                                                                         monkeypatch, capsys):
    root, question = workspace
    files = _runs(tmp_path, monkeypatch)
    main = helper("register_batch.py")["main"]
    receipts = tmp_path / "q" / "outputs" / "registrations.json"
    # Roles given consumer first: the producer is still registered first and cited by artifact ID.
    code = main(["--from-receipt", str(files["r2"]), "--from-receipt", str(files["r1"]),
                 "--role", "scaled.txt=scaled-count", "--role", "count.tsv=row-count", "--title", "count.tsv=Row count",
                 "--question", question["question"], "--receipts", str(receipts), "--bio", BIO, "--workspace", str(root)])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 0 and out["registered"] == 2 and out["failed"] == 0, out
    saved = json.loads(receipts.read_text())
    count_artifact = saved[str(files["first"])]["artifact"]
    scaled_artifact = saved[str(files["second"])]["artifact"]
    assert out["artifacts"] == [count_artifact, scaled_artifact]  # producer first
    assert str(files["side"]) not in saved  # no --role, not registered
    # The source input was bio object add-ed and cited by blob; the batch output by its artifact ID.
    (source_input,) = artifact_inputs(root, count_artifact)
    assert not source_input["source_identity"] and len(source_input["blob"]) == 64
    (batch_input,) = artifact_inputs(root, scaled_artifact)
    assert batch_input["source_identity"] == count_artifact
    argv = saved[str(files["first"])]["argv"]
    assert argv[argv.index("--title") + 1] == "Row count" and argv[argv.index("--output-role") + 1] == "row-count"
    assert json.loads(argv[argv.index("--parameters") + 1])["script_args"][0] == str(files["source"])
    assert str(files["count"].resolve()) == argv[argv.index("--code") + 1]
    # Rerunning the same command registers nothing new.
    assert main(["--from-receipt", str(files["r1"]), "--role", "count.tsv=row-count", "--question", question["question"],
                 "--receipts", str(receipts), "--bio", BIO, "--workspace", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["artifacts"] == [count_artifact]


def test_register_batch_refuses_incomplete_or_stale_receipts_before_registering(workspace, tmp_path, monkeypatch, capsys):
    root, question = workspace
    files = _runs(tmp_path, monkeypatch)
    capsys.readouterr()
    main = helper("register_batch.py")["main"]
    receipts = tmp_path / "q" / "outputs" / "registrations.json"
    args = ["--question", question["question"], "--receipts", str(receipts), "--bio", BIO, "--workspace", str(root)]

    def refused(*extra):
        assert main([*extra, *args]) == 2
        out = json.loads(capsys.readouterr().out)
        assert out["event"] == "registrations_refused"
        return " ".join(out["problems"])

    # A role that names no output lists the outputs there are.
    assert "count.tsv, side.json" in refused("--from-receipt", str(files["r1"]), "--role", "counts.tsv=row-count")
    assert "--role" in refused("--from-receipt", str(files["r1"]))
    # An incomplete run: non-zero exit and an unwritten output.
    bad = dict(json.loads(files["r1"].read_text()), exit_code=1)
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    assert "incomplete run" in refused("--from-receipt", str(tmp_path / "bad.json"), "--role", "count.tsv=row-count")
    unwritten = json.loads(files["r1"].read_text())
    unwritten["outputs"][1]["written"] = False
    (tmp_path / "unwritten.json").write_text(json.dumps(unwritten))
    assert "side.json" in refused("--from-receipt", str(tmp_path / "unwritten.json"), "--role", "count.tsv=row-count")
    changed = dict(json.loads(files["r1"].read_text()), code_unchanged=False)
    (tmp_path / "changed.json").write_text(json.dumps(changed))
    assert "producer changed" in refused("--from-receipt", str(tmp_path / "changed.json"), "--role", "count.tsv=row-count")
    # A producer linted or edited after the run breaks the recorded hash: refused with the rule.
    files["count"].write_text(files["count"].read_text() + "# lint fix\n")
    reason = refused("--from-receipt", str(files["r1"]), "--role", "count.tsv=row-count")
    assert "never edit a script after" in reason and "new version" in reason
    # Nothing was registered by any refused call.
    assert not receipts.exists()


def test_register_batch_plan_mode_still_documents_and_accepts_a_plan():
    doc = helper("register_batch.py")["__doc__"]
    assert "--from-receipt" in doc and '"output_role"' in doc and '"inputs"' in doc and '"code"' in doc


# ---- 2. records.py: each --register made a new artifact version (3 per table in the cohort)

def test_records_register_is_idempotent_and_reports_what_it_supersedes(workspace, capsys):
    root, question = workspace
    main = helper("records.py")["main"]
    base = ["eligibility", "--question", question["question"], "--workspace", str(root), "--bio", BIO]
    assert main(base + ["--add", "dataset=GSE1", "verdict=eligible", "reason=Schwann cells"]) == 0
    assert "registration" not in json.loads(capsys.readouterr().out)  # rows accumulate without registering
    assert main(base + ["--register"]) == 0
    first = json.loads(capsys.readouterr().out)["registration"]
    assert first["artifact"].startswith("artifact_") and "supersedes" not in first
    assert main(base + ["--register"]) == 0
    again = json.loads(capsys.readouterr().out)["registration"]
    assert again["artifact"] == first["artifact"] and again["unchanged"] is True
    assert main(base + ["--add", "dataset=GSE2", "verdict=excluded", "reason=no perturbation", "--register"]) == 0
    second = json.loads(capsys.readouterr().out)["registration"]
    assert second["artifact"] != first["artifact"] and second["supersedes"] == first["artifact"]
    ws = Workspace(root)
    rows = ws.rows("SELECT artifact_id FROM question_artifact WHERE question_id=?", (question["question"],))
    ws.close()
    assert len(rows) == 2


def test_records_unknown_field_suggests_the_nearest_and_note_takes_free_text(workspace, capsys):
    root, question = workspace
    main = helper("records.py")["main"]
    base = ["eligibility", "--question", question["question"], "--workspace", str(root)]
    assert main(base + ["--add", "datset=GSE1", "verdict=eligible", "reason=x"]) == 2
    reason = json.loads(capsys.readouterr().out)["reason"]
    assert "did you mean 'dataset'" in reason and "note=" in reason
    assert main(base + ["--add", "dataset=GSE1", "verdict=eligible", "reason=x", "note=any free text, here"]) == 0


# ---- 3. agents linted registered research scripts because AGENTS.md's ruff line read as applying to them

def test_ruff_instruction_is_for_repository_engineering_and_the_skill_forbids_editing_registered_scripts():
    agents = (ROOT / "AGENTS.md").read_text()
    sentence = next(s for s in agents.split(". ") if "ruff check" in s)
    assert "repository engineering" in sentence and len(agents.split()) < 400
    skill = (ROOT / ".agents/skills/bio-research/SKILL.md").read_text()
    assert ("Never edit a script after registering an output it produced; write a new version and rerun it through "
            "run_analysis.py.") in skill
    assert "--from-receipt" in skill


# ---- 4. `bio work frontier-items Q` failed in 6/11 runs: the question is positional (or --question)

def test_frontier_items_and_gaps_take_the_question_positionally(workspace):
    root, question = workspace
    runner, prefix, q = CliRunner(), ["-w", str(root), "work"], question["question"]
    assert runner.invoke(app, prefix + ["gap", q, "--need", "Cell metadata", "--failed", "GEO soft lacks it",
                                        "--source-or-format", "GEO"]).exit_code == 0
    for command in ("frontier-items", "gaps"):
        positional = runner.invoke(app, prefix + [command, q])
        option = runner.invoke(app, prefix + [command, "--question", q])
        assert positional.exit_code == 0, positional.output
        assert json.loads(positional.output) == json.loads(option.output)
        assert runner.invoke(app, prefix + [command]).exit_code == 0
        conflict = runner.invoke(app, prefix + [command, q, "--question", "q_other"])
        assert isinstance(conflict.exception, DawError) and conflict.exception.reason == "conflicting_question"
    gaps = json.loads(runner.invoke(app, prefix + ["gaps", q]).output)
    assert gaps["matching_events"] == 1


# ---- 5. invalid_search_bounds had an empty detail; forum_dump --limit 500 crashed

def test_search_bounds_errors_name_the_allowed_bounds(workspace, tmp_path):
    root, _ = workspace
    runner = CliRunner()
    listed = runner.invoke(app, ["-w", str(root), "data", "list", "--limit", "500"]).exception
    assert listed.reason == "invalid_search_bounds" and "1..100" in listed.detail
    searched = runner.invoke(app, ["-w", str(root), "data", "search", "--text", "PMP22", "--limit", "500"]).exception
    assert searched.reason == "invalid_search_bounds" and "limit=500" in searched.detail
    from daw.commons import claims
    board = Community.create(tmp_path / "community")
    try:
        with pytest.raises(DawError, match=r"1\.\.200.*limit=500"):
            claims.list_claims(board, limit=500)
    finally:
        board.close()


def test_every_invalid_search_bounds_raise_site_carries_a_detail():
    import re
    sites = []
    for path in (ROOT / "src").rglob("*.py"):
        sites += [(path, m.group(0)) for m in re.finditer(r'DawError\("invalid_search_bounds"[^\n]*', path.read_text())]
    assert sites and all('DawError("invalid_search_bounds",' in text for _, text in sites), sites


def test_forum_dump_clamps_an_oversized_limit_with_a_message(tmp_path, capsys):
    module = helper("forum_dump.py")
    seen = {}
    module["main"].__globals__["dump"] = lambda out, terms, families, shows, bio, limit: seen.setdefault("limit", limit) and []
    assert module["main"](["--out", str(tmp_path / "d"), "--term", "PMP22", "--limit", "500"]) == 0
    captured = capsys.readouterr()
    assert seen["limit"] == 100 and "--limit 500" in captured.err and "using 100" in captured.err


# ---- 6. a claim with scope.dataset was refused without naming the allowed fields

def test_claims_scope_refusal_names_the_allowed_fields(tmp_path):
    from daw.commons.claims import parse_claims
    with pytest.raises(DawError) as error:
        parse_claims([{"text": "PMP22 is higher", "status": "descriptive", "scope": {"dataset": "GSE1"}}])
    assert error.value.reason == "invalid_claims" and "species, context, endpoint, direction" in error.value.detail
    confirm = helper("claims_draft.py")["confirm"]
    claims, problems = confirm([{"text": "PMP22 is higher", "status": "descriptive",
                                 "scope": {"dataset": "GSE1", "species": "human"}}])
    assert claims is None and "dataset" in problems[0] and "species, context, endpoint, direction" in problems[0]


# ---- 7. peek.py --max-chars was raised up to 34,000 in 95/246 uses

def test_peek_hard_caps_max_chars_and_says_how_to_narrow(tmp_path, capsys):
    table = tmp_path / "wide.tsv"
    table.write_text("\t".join(f"column_{i}" for i in range(60)) + "\n"
                     + "\n".join("\t".join(f"value_{r}_{i}" for i in range(60)) for r in range(400)) + "\n")
    main = helper("peek.py")["main"]
    assert main([str(table), "--rows", "400", "--max-chars", "34000"]) == 0
    captured = capsys.readouterr()
    assert len(captured.out) <= 12001 and "capped at 12000" in captured.err and "--grep" in captured.err
    assert '"max_chars_capped"' in captured.out


# ---- 8a. the ceremony tail ended at lint/smoke runs that only mentioned run_analysis.py

def _executed(complete, written):
    return json.dumps({"event": "analysis_executed", "receipt": "r.json", "sha256": "0" * 64, "exit_code": 0,
                       "complete": complete, "outputs_written": written, "outputs_declared": 1, "stdout_tail": "x"})


def test_ceremony_tail_counts_only_complete_analyses_with_outputs(tmp_path):
    from daw.commons.runmetrics import analysis_succeeded, run_metrics
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "events.jsonl").write_text("")
    real = {"name": "terminal", "command": "./bin/python run_analysis.py --receipt r.json -- python scripts/a.py",
            "exit_code": 0, "input": {}, "result_line": 2}
    lint = {"name": "terminal", "command": "ruff check scripts/run_analysis.py", "exit_code": 0, "input": {},
            "result_line": 4}
    smoke = {"name": "terminal", "command": "./bin/python run_analysis.py --receipt s.json -- python scripts/a.py",
             "exit_code": 0, "input": {}, "result_line": 6}
    events = [{"line": 1, "event": {"type": "tool_use", "timestamp": 0}},
              {"line": 2, "event": {"type": "tool_result", "timestamp": 60_000, "output": _executed(True, 2)}},
              {"line": 3, "event": {"type": "tool_use", "timestamp": 600_000}},
              {"line": 4, "event": {"type": "tool_result", "timestamp": 660_000, "output": "All checks passed!"}},
              {"line": 5, "event": {"type": "tool_use", "timestamp": 900_000}},
              {"line": 6, "event": {"type": "tool_result", "timestamp": 960_000, "output": _executed(False, 0)}},
              {"line": 7, "event": {"type": "result", "timestamp": 1_140_000}}]
    m = run_metrics(folder, {"items": [real, lint, smoke], "events": events})
    assert m["minutes_after_last_successful_analysis"] == 18.0  # from line 2, not the lint or incomplete rerun
    run = {"command": "./bin/python .agents/skills/bio-research/scripts/run_analysis.py --receipt r.json -- python a.py",
           "exit_code": 0}
    # Inside a JSON-encoded tool output (Hermes), and truncated after outputs_written: still read.
    line = _executed(True, 1)
    wrapped = json.dumps({"output": line[:line.index("outputs_declared")], "exit_code": 0})
    assert analysis_succeeded(run, wrapped) is True
    assert analysis_succeeded(run, json.dumps({"output": _executed(True, 0)})) is False
    # The analysis_executed line unavailable (no capture, or a crash before it): the exit code decides, as before.
    assert analysis_succeeded(run, "") is True and analysis_succeeded({**run, "exit_code": 1}, "Traceback") is False
    # Naming the file is not running it.
    for command in ("ruff check scripts/run_analysis.py", "cat .agents/skills/bio-research/scripts/run_analysis.py",
                    "sed -n 1,20p run_analysis.py"):
        assert analysis_succeeded({"command": command, "exit_code": 0}, _executed(True, 1)) is False
    assert analysis_succeeded({**run, "command": "cd q && uv run python run_analysis.py --receipt r.json -- python a.py"},
                              _executed(True, 1)) is True
    # The item's own captured line is preferred to the event's.
    assert analysis_succeeded({**run, "aggregated_output": _executed(False, 0)}, _executed(True, 1)) is False


# ---- 8b. Codex input_tokens include cached tokens, Hermes's do not: raw sums inflated Codex ~20x

def test_token_sums_are_normalised_to_uncached_input_per_harness():
    from daw.commons import economics
    codex = {"input_tokens": 2_000_000, "cached_input_tokens": 1_900_000, "output_tokens": 10_000}
    hermes = {"input_tokens": 100_000, "cached_input_tokens": 1_900_000, "output_tokens": 10_000}
    assert economics.normalised_tokens(codex, "codex") == {"uncached_input_tokens": 100_000,
                                                           "cached_input_tokens": 1_900_000, "output_tokens": 10_000,
                                                           "input_includes_cached": True}
    assert economics.normalised_tokens(hermes, "hermes")["uncached_input_tokens"] == 100_000
    assert economics.normalised_tokens(codex, "mcp") is None  # unknown input semantics: not guessed
    assert economics.normalised_tokens({**codex, "cached_input_tokens": None}, "codex") is None
    runs = [{"harness": "codex", "metrics": {"tokens": codex}}, {"harness": "hermes", "metrics": {"tokens": hermes}}]
    group = economics.criteria(runs, {"registered_artifacts": 2})
    assert group["tokens"] == 220_000 and group["tokens_normalised_runs"] == 2
    assert group["token_fields"] == {"uncached_input_tokens": 200_000, "cached_input_tokens": 3_800_000,
                                     "output_tokens": 20_000}
    assert "uncached" in group["tokens_meaning"] and group["tokens_per"]["registered_artifact"] == 110_000
    unknown = economics.criteria(runs + [{"harness": "mcp", "metrics": {"tokens": codex}}])
    assert unknown["tokens"] is None and unknown["tokens_normalised_runs"] == 2
