"""Changes grounded in the 2026-10-07 transcript review of the 97-run PMP22 cohort: each test names the
observed failure it closes (see workspaces/community-validation/analysis/transcript-review/ for the counts)."""
import json
import runpy
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from daw.artifacts import register_artifact
from daw.bio_cli import app
from daw.catalog import Workspace
from daw.community import Community
from daw.substrate_models import ArtifactRegistration, Derivation, ObjectInput
from daw.util import DawError
from daw.work import create_question

SCRIPTS = Path(__file__).parents[1] / ".agents/skills/bio-research/scripts"


def helper(name):
    return runpy.run_path(str(SCRIPTS / name))


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
    path.write_text("gene\tlog2fc\nPMP22\t1.757706\nABCA1\t-0.263582\n")
    imported = ws.local_asset(path, "Synthetic study")
    question = create_question(ws, "PMP22 contrast")
    code = ws.put_bytes(b"# saved analysis\n")
    spec = ArtifactRegistration(title="Named gene contrasts", summary="fixture",
        derivation=Derivation(inputs=[ObjectInput(blob=imported["blob"], source_identity=imported["asset_revision"])],
                              code=[code], parameters={}, references=[], environment={"fixture": True}))
    result = tmp_path / "rna-named-gene-contrasts.tsv"
    result.write_text("gene\tlog2fc\nPMP22\t1.757706\nABCA1\t-0.263582\nABCG1\t-0.941\n")
    artifact = register_artifact(ws, result, spec, question=question["question"], )
    yield ws, question, artifact
    ws.close()


# ---- run_analysis.py: 29 failed receipts hid stderr in a side file (blockers §1); stdout >2 KB was 92% of python bytes

def test_run_analysis_prints_stderr_tail_on_failure_and_a_bounded_stdout_tail(tmp_path):
    scripts, outputs = tmp_path / "scripts", tmp_path / "outputs"
    scripts.mkdir(), outputs.mkdir()
    (scripts / "ok.py").write_text("import sys, pathlib\nfor i in range(100): print('row', i)\n"
                                   "pathlib.Path(sys.argv[1]).write_text('x\\n')\n")
    (scripts / "bad.py").write_text("assert 1 == 2, 'pairing not established'\n")
    run = helper("run_analysis.py")["run"]
    cwd = Path.cwd()
    import os
    os.chdir(tmp_path)
    try:
        ok = subprocess.run([sys.executable, str(SCRIPTS / "run_analysis.py"), "--receipt", "outputs/r1.json", "--output",
                             "outputs/t.tsv", "--tail", "3", "--", sys.executable, "scripts/ok.py", "outputs/t.tsv"],
                            capture_output=True, text=True, check=False)
        event = json.loads(ok.stdout.strip().splitlines()[-1])
        assert ok.returncode == 0 and event["complete"] and event["stdout_tail"] == "row 97\nrow 98\nrow 99"
        assert "stderr_tail" not in event
        bad = subprocess.run([sys.executable, str(SCRIPTS / "run_analysis.py"), "--receipt", "outputs/r2.json", "--output",
                              "outputs/t2.tsv", "--", sys.executable, "scripts/bad.py"], capture_output=True, text=True, check=False)
        event = json.loads(bad.stdout.strip().splitlines()[-1])
        assert bad.returncode == 1 and event["exit_code"] == 1 and "pairing not established" in event["stderr_tail"]
        assert "AssertionError" in event["stderr_tail"] and event["outputs_written"] == 0
    finally:
        os.chdir(cwd)
    assert callable(run)


# ---- peek.py: 169 one-off inspection scripts by 17 agents; 7 challenge pages saved as sources (blockers §1, repeated-work §2)

def test_peek_inspects_without_executing_and_names_non_source_bodies(tmp_path):
    peek = helper("peek.py")["peek"]
    (tmp_path / "a.xml").write_text('<article><front><article-meta><article-id pub-id-type="pmc">PMC1</article-id>'
                                    "<title-group><article-title>PMP22 dosage</article-title></title-group>"
                                    "<abstract><p>Measured.</p></abstract></article-meta></front><body><sec><title>Results</title>"
                                    '<table-wrap id="T1"><label>Table 1</label><caption><p>Fold changes</p></caption></table-wrap>'
                                    "</sec></body></article>")
    xml = peek(tmp_path / "a.xml")
    assert xml["kind"] == "xml" and xml["article_title"] == "PMP22 dosage" and xml["captions"][0]["label"] == "Table 1"
    (tmp_path / "challenge.html").write_text("<html><body>Preparing to download your file</body></html>")
    assert peek(tmp_path / "challenge.html")["kind"] == "not_a_source"
    (tmp_path / "bioc.xml").write_text("No result can be found")
    assert peek(tmp_path / "bioc.xml")["kind"] == "not_a_source"
    (tmp_path / "t.tsv").write_text("gene\tvalue\n" + "\n".join(f"G{i}\t{i}.5" for i in range(500)) + "\n")
    table = peek(tmp_path / "t.tsv", rows=2)
    assert table["kind"] == "table" and table["rows"] == 500 and table["column_kinds_from_first_200_rows"] == ["text", "numeric"]
    assert len(table["first_rows"]) == 2
    (tmp_path / "evil.py").write_text("raise SystemExit('executed')\n")
    assert peek(tmp_path / "evil.py")["kind"] == "text"
    grep = peek(tmp_path / "t.tsv", grep=r"^G49\d\t")
    assert grep["matches"] == 10
    import zipfile
    with zipfile.ZipFile(tmp_path / "supp.zip", "w") as archive:
        archive.writestr("S1.tsv", "a\tb\n1\t2\n")
    assert peek(tmp_path / "supp.zip")["members"] == [{"name": "S1.tsv", "bytes": 8}]
    assert peek(tmp_path / "supp.zip", member="S1.tsv")["peek"]["header"] == ["a", "b"]
    rendered = helper("peek.py")["render"]({"x": "y" * 10000}, 600)
    assert len(rendered) <= 700 and "truncated" in rendered


# ---- CLI: 25 guessed verbs (blockers §1); `reply` was tried by 8 agents before `answer` existed

def test_unknown_commands_name_the_rename_and_the_closest_verbs():
    runner = CliRunner()
    result = runner.invoke(app, ["community", "respond"])
    assert result.exit_code == 2 and "bio community answer REQUEST --body FILE" in result.output and "Commands here:" in result.output
    result = runner.invoke(app, ["community", "register"])
    assert "no community prefix" in result.output
    result = runner.invoke(app, ["data", "study"])
    assert "bio data show SUBJECT" in result.output and "Commands here:" in result.output
    result = runner.invoke(app, ["community", "serch"])
    assert "Closest: search" in result.output
    assert "Usage" in runner.invoke(app, ["community", "reply", "--help"]).output  # hidden alias of answer


# ---- publish: 16/97 runs hit unknown_artifact; 5 peer questions only asked for the bytes (rules §4, proposal 1)

def test_publish_refuses_unreachable_citations_and_publishes_the_authors_own_on_request(board, source):
    ws, question, artifact = source
    aid = artifact["artifact"]
    body = f"The contrast table is {aid}; see also post_{'0' * 32}."
    with pytest.raises(DawError, match="unpublished_citation") as refused:
        board.publish("operator", "Finding", body, workspace=ws.root, question=question["question"])
    assert aid in str(refused.value) and "--publish-cited" in str(refused.value) and "post_" + "0" * 32 in str(refused.value)
    assert board.find("Finding")["total"] == 0  # refused before any write
    body = f"The contrast table is {aid}."
    with pytest.raises(DawError, match="unpublished_citation"):
        board.publish("operator", "Finding", body, workspace=ws.root, question=question["question"])
    post = board.publish("operator", "Finding", body, workspace=ws.root, question=question["question"], publish_cited=True)
    assert post["content"]["evidence"]["artifacts"] == [aid]
    assert board.show(post["id"])["evidence_artifacts"][0]["present"]
    # Once in the library the id is reachable from any later post without evidence.
    assert board.publish("operator", "Follow-up", f"As {aid} showed.")["id"]
    ghost = "artifact_" + "f" * 64
    with pytest.raises(DawError, match="unpublished_citation"):
        board.publish("operator", "Ghost", f"Bytes at {ghost}.")
    assert board.cited_records("nothing cited here")["unreachable"] == []


def test_publish_output_lists_pending_questions_for_the_author(board, source):
    ws, question, artifact = source
    with Community.create(board.root.parent / "unused") as _:
        pass
    board.add_agent = None  # the board fixture has no agents; use operator-to-operator requests
    request = board.ask("operator", "operator", "Which samples did you screen?")
    post = board.publish("operator", "Milestone", "A plan.")
    assert post["pending_for_you"] == [request["id"]] and "community answer" in post["pending_note"]
    reply = board.publish("operator", "Re: question", "GSM1 and GSM2.", parent=request["post"])
    assert "pending_for_you" not in reply
    assert board.one("SELECT state FROM request WHERE id=?", (request["id"],))["state"] == "completed"


# ---- verify: 69 hand-written verify scripts, none compared prose numbers to tables; 3 superseding posts for one
#      transcription error (repeated-work §5)

def test_verify_compares_the_local_body_and_prose_numbers_against_table_cells(board, source, tmp_path):
    ws, question, artifact = source
    aid = artifact["artifact"]
    body = "PMP22 rose by 1.76 log2 units; ABCA1 fell to -0.263582 and ABCG1 to -0.941 (n=3 preparations, GSE177037)."
    post = board.publish("operator", "Contrast", body, workspace=ws.root, artifacts=[aid], question=question["question"])
    verified = board.verify(post["id"], body=body, numbers=True)
    assert verified["body_matches_local"] and verified["verified"]
    numbers = verified["numbers"]
    assert numbers["tables"][0]["artifact"] == aid and numbers["unmatched"] == [] and numbers["matched"] == 3
    wrong = body.replace("1.76", "1.080").replace("-0.263582", "-0.941 and -0.26")
    bad_post = board.publish("operator", "Contrast v2", wrong, workspace=ws.root, artifacts=[aid], question=question["question"])
    check = board.verify(bad_post["id"], body=body, numbers=True)
    assert check["body_matches_local"] is False and check["body_difference"]["line"] == 1
    assert "1.080" in check["numbers"]["unmatched"] and "-0.26" not in check["numbers"]["unmatched"]  # -0.26 rounds to a cell
    assert check["verified"] is False
    runner = CliRunner()
    draft = tmp_path / "draft.md"
    draft.write_text(body)
    out = runner.invoke(app, ["community", "--root", str(board.root), "verify", post["id"], "--body", str(draft), "--numbers"])
    assert out.exit_code == 0 and json.loads(out.output)["numbers"]["matched"] == 3


# ---- full text: EPMC fullTextXML answered 18 calls with HTTP 500; 13 agents wrote their own fetchers (blockers §1, §2)

def jats(paragraphs):
    body = "".join(f"<p>Paragraph {i} about PMP22.</p>" for i in range(paragraphs))
    return ('<?xml version="1.0"?><article><front><article-meta><title-group><article-title>Dosage</article-title>'
            f"</title-group></article-meta></front><body><sec><title>Results</title>{body}</sec></body></article>").encode()


def test_fulltext_falls_through_to_ncbi_routes_and_never_keeps_a_stub(tmp_path):
    from daw.adapters import Sources
    from daw.transport import Transport
    root = tmp_path / "ws"
    Workspace.create(root).close()
    no_reserve(root)
    ws = Workspace(root)
    calls = []

    def serve(request):
        calls.append(request.url.host + request.url.path)
        if "ebi.ac.uk" in request.url.host:
            return httpx.Response(500, content=b'{"errCode":500,"errMsg":"Internal server error"}')
        if "eutils" in request.url.host:
            return httpx.Response(200, content=b"<pmc-articleset>" + jats(3)[len('<?xml version="1.0"?>'):] + b"</pmc-articleset>")
        return httpx.Response(200, content=b"No result can be found")
    try:
        with ws.writer():
            transport = Transport(ws, http_transport=httpx.MockTransport(serve), sleep=lambda _: None)
            fetched = Sources(ws, transport).fulltext("PMC6607759")
        assert fetched["outcome"] == "available_full" and fetched["route"] == "ncbi_efetch" and fetched["paragraphs"] == 3
        assert [r["route"] for r in fetched["routes"]] == ["europepmc", "ncbi_efetch"]
        assert fetched["routes"][0]["outcome"] == "transient_failure"
        assert any("eutils" in c for c in calls) and not any("bionlp" in c for c in calls)

        def stubs(request):
            if "ebi.ac.uk" in request.url.host:
                return httpx.Response(200, content=b"<html><body>Preparing to download</body></html>")
            if "eutils" in request.url.host:
                return httpx.Response(200, content=b"<pmc-articleset><Reply Error='x'/></pmc-articleset>")
            return httpx.Response(200, content=b"No result can be found")
        with ws.writer():
            transport = Transport(ws, http_transport=httpx.MockTransport(stubs), sleep=lambda _: None)
            failed = Sources(ws, transport).fulltext("PMC4643454")
        assert failed["outcome"] in {"malformed_metadata", "no_full_text"} and len(failed["routes"]) == 3
        assert "bio work gap" in failed["note"]
    finally:
        ws.close()


def test_bioc_passages_become_paragraphs():
    from daw.adapters import ET, article_paragraphs
    root = ET.fromstring("<collection><document><passage><infon key='type'>title</infon><text>T</text></passage>"
                         "<passage><infon key='section_type'>RESULTS</infon><infon key='type'>paragraph</infon>"
                         "<text>PMP22 levels fell.</text></passage></document></collection>")
    _, paragraphs = article_paragraphs(root)
    assert paragraphs == [{"locator": "passage[2]", "section": "RESULTS", "text": "PMP22 levels fell.",
                           "sha256": paragraphs[0]["sha256"]}]


# ---- work resume: 129 re-orientation windows cost 161 minutes of inbox/show, --help and output re-reads (repeated-work §5)

def test_work_resume_is_one_bounded_record_of_the_question(tmp_path, monkeypatch):
    from daw.resume import resume_work
    root = tmp_path / "ws"
    Workspace.create(root).close()
    no_reserve(root)
    ws = Workspace(root)
    question = create_question(ws, "PMP22 resume")
    qdir = Path(question["path"])
    (qdir / "scripts" / "contrast.py").write_text('"""Compute the named-gene contrast from GSE177037."""\nprint(1)\n')
    (qdir / "scripts" / "retrieve.py").write_text("# fetch the supplement tables\n")
    (qdir / "outputs" / "contrast-execution-r001.json").write_text(json.dumps(
        {"producer": str(qdir / "scripts/contrast.py"), "exit_code": 0, "complete": True, "finished": "2026-10-05T00:00:00+00:00",
         "outputs": [{"path": str(qdir / "outputs/contrast.tsv"), "written": True}]}))
    (qdir / "outputs" / "contrast.tsv").write_text("gene\tlog2fc\nPMP22\t1.7\n")
    (qdir / "LABBOOK.md").write_text("# Research notebook\n\n## Findings\n\n" + "\n".join(f"line {i}" for i in range(40)))
    ws.close()
    ws = Workspace(root)
    record = resume_work(ws, question["question"], inbox=lambda: [{"id": "request_1", "post": "post_1", "state": "pending"}])
    ws.close()
    assert record["status"] == "open" and record["notebook"]["headings"] == ["# Research notebook", "## Findings"]
    assert record["notebook"]["tail"][-1] == "line 39" and len(record["notebook"]["tail"]) == 12
    assert record["latest_receipts"] == [{"receipt": "contrast-execution-r001.json", "producer": "contrast.py", "exit_code": 0,
                                          "complete": True, "finished": "2026-10-05T00:00:00+00:00", "outputs": ["contrast.tsv"]}]
    scripts = {s["path"]: s for s in record["scripts"]}
    assert scripts["scripts/contrast.py"]["purpose"].startswith("Compute the named-gene contrast") and scripts["scripts/contrast.py"]["has_recent_receipt"]
    assert scripts["scripts/retrieve.py"]["purpose"] == "fetch the supplement tables" and not scripts["scripts/retrieve.py"]["has_recent_receipt"]
    assert record["pending_requests_for_you"] == [{"request": "request_1", "post": "post_1", "state": "pending"}]
    assert any("run_analysis.py" in c for c in record["commands"]) and len(json.dumps(record)) < 8000
    monkeypatch.delenv("BIO_COMMUNITY", raising=False)
    out = CliRunner().invoke(app, ["-w", str(root), "work", "resume", question["question"]])
    assert out.exit_code == 0 and json.loads(out.output)["pending_requests_for_you"] is None


# ---- ANSWER.md: 2 deliveries (2.6 h) exited on a wake-time interrupt with an empty final and were re-run (rules §2)

def test_a_checkpoint_answer_is_posted_when_the_session_ends_without_a_final_message(demo):
    from daw.commons.demo import scripted_runtime
    from daw.community_runtime import dispatch
    root, ctx = demo
    hook = r'''
import os, pathlib
trial = pathlib.Path(os.environ.get("HERMES_CWD") or os.getcwd())
question = sorted((trial / "workspace" / "questions").iterdir())[0]
(question / "outputs").mkdir(exist_ok=True)
(question / "outputs" / "ANSWER.md").write_text("```claims\n[]\n```\nPMP22 fell 1.7 log2 units; checkpoint before verification.\n")
'''
    with Community(root) as board:
        request = board.ask(ctx["agents"]["dana"], "operator", "Report the contrast.", request_key="checkpoint-1")
    with Community(root) as board, scripted_runtime(root) as (harness, answers):
        (answers / f"{request['post']}.md").write_text("")  # the harness ends with no final text
        (answers / f"{request['post']}.hook.py").write_text(hook)
        row = dispatch(board, request["id"], harness)
        answer = board.show(row["answer"])
        assert "checkpoint before verification" in answer["content"]["body"]
        assert "Recovered from `outputs/ANSWER.md`" in answer["content"]["body"]
        assert answer["content"]["evidence"]["recovered_from_checkpoint"]["path"].endswith("outputs/ANSWER.md")
        assert board.one("SELECT 1 FROM event WHERE kind='answer_recovered_from_checkpoint'")
        # A stale checkpoint from before the delivery is never re-posted.
        import os
        import time
        for stale in (board.trial(board.agent(ctx["agents"]["dana"])) / "workspace" / "questions").glob("*/outputs/ANSWER.md"):
            os.utime(stale, (time.time() - 60, time.time() - 60))
        second = board.ask(ctx["agents"]["dana"], "operator", "Anything new?", request_key="checkpoint-2")
        (answers / f"{second['post']}.md").write_text("")
        with pytest.raises(DawError, match="agent_delivery_failed"):
            dispatch(board, second["id"], harness)


# ---- records.py: 23 eligibility tables and 15 locator manifests invented; 16/30 peer questions asked for one (rules §3–4)

def test_records_helper_requires_the_fields_peers_asked_for_and_registers_the_table(tmp_path):
    root = tmp_path / "ws"
    Workspace.create(root).close()
    no_reserve(root)
    ws = Workspace(root)
    question = create_question(ws, "Records")
    ws.close()
    main = helper("records.py")["main"]
    bio = f"{sys.executable} -m daw.bio_cli"
    assert main(["locus", "--question", question["question"], "--workspace", str(root), "--add", "gene=PMP22", "feature=P1",
                 "assembly=GRCh38", "chrom=chr17", "start=1", "end=2"]) == 2  # strand, base and source missing
    assert main(["eligibility", "--question", question["question"], "--workspace", str(root), "--add", "dataset=GSE1",
                 "verdict=maybe", "reason=x"]) == 2
    code = main(["eligibility", "--question", question["question"], "--workspace", str(root), "--bio", bio,
                 "--add", "dataset=GSE177037", "sample=GSM5362321", "verdict=eligible", "reason=matched Schwann cells",
                 "--add", "dataset=GSE115930", "verdict=excluded", "reason=no PMP22 perturbation", "--register"])
    assert code == 0
    qdir = Path(question["path"])
    table = (qdir / "outputs" / "eligibility.tsv").read_text().splitlines()
    assert table[0].startswith("dataset\tverdict\treason\tsample") and len(table) == 3
    ws = Workspace(root)
    rows = ws.rows("SELECT a.output_role FROM artifact a JOIN question_artifact q ON q.artifact_id=a.id WHERE q.question_id=?",
                   (question["question"],))
    ws.close()
    assert [r["output_role"] for r in rows] == ["eligibility"]
    code = main(["locus", "--question", question["question"], "--workspace", str(root), "--add", "gene=PMP22", "feature=P1_promoter",
                 "assembly=GRCh38", "chrom=chr17", "start=15229777", "end=15230777", "strand=-", "base=1-based",
                 "source=PMC6607759 Fig 1A"])
    assert code == 0 and "strand" in (qdir / "outputs" / "locus-map.tsv").read_text().splitlines()[0]


# ---- run metrics: the new counters name the cohort failure modes, unavailable stays None

def test_run_metrics_count_the_reviewed_failure_modes(tmp_path):
    from daw.commons.runmetrics import run_metrics
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "events.jsonl").write_text("")
    (folder / "final.md").write_text("  \n")
    events = [{"event": {"type": "tool_result", "output": "Error: No such command 'reply'"}, "line": 1},
              {"event": {"type": "tool_result", "output": '{"error": "unknown_artifact"}'}, "line": 2},
              {"event": {"type": "tool_result", "output": '{"truncation_note": "Output exceeded the capture window"}'}, "line": 3}]
    items = [{"name": "write_file", "input": {"path": "q/scripts/verify_publication.py"}},
             {"name": "write_file", "input": {"path": "q/scripts/inspect_sources.py"}},
             {"name": "read_file", "input": {"path": "q/LABBOOK.md"}}, {"name": "read_file", "input": {"path": "q/LABBOOK.md"}},
             {"name": "terminal", "command": "./bin/bio work resume q_1", "input": {}}]
    m = run_metrics(folder, {"items": items, "events": events})
    assert (m["no_such_command"], m["unknown_artifact_errors"], m["truncated_terminal_results"]) == (1, 1, 1)
    assert (m["verify_scripts_written"], m["inspection_scripts_written"], m["labbook_reads"], m["resume_calls"]) == (1, 1, 2, 1)
    assert m["empty_final"] is True
    assert run_metrics(tmp_path / "none", {"items": [], "events": []})["empty_final"] is None
