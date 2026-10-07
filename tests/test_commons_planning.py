"""Spec v2 V5: the frontier as the planning surface (board view, shared experiments, wishlist proposal, scouting)."""
import json
import runpy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from daw.bio_cli import app as bio
from daw.catalog import Workspace
from daw.commons import frontier, planning
from daw.commons.app import create_app
from daw.commons.archive import Archive, ReadOnlyWorkspace
from daw.commons.participants import add_participant
from daw.commons.participation import promote
from daw.community import Community
from daw.util import DawError
from daw.work import create_question, record_event, sync_work

WRITE = {"X-Colloquy-Request": "1"}


def client(root, user="rhea"):
    return TestClient(create_app(root, local_user=user, static_dir=root / "missing"))


def workspace(board, ctx, name):
    return Workspace(board.trial(board.agent(ctx["agents"][name])) / "workspace")


def column_ids(view):
    return {c["key"]: sorted(i["id"] for i in c["items"]) for c in view["columns"]}


def test_board_view_columns_budgets_targets_and_promotion_from_a_card(demo):
    root, ctx = demo
    items = ctx["frontier"]["items"]
    http = client(root)
    view = http.get("/api/frontier/board").json()
    assert [c["key"] for c in view["columns"]] == ["open", "blocked", "candidate_evidence", "promoted", "closed"]
    columns = column_ids(view)
    # Blocked is an open item with a recorded blocker; closed items stay on the board in their own column.
    assert items["alice-donors"] in columns["blocked"] and items["dana-untestable"] in columns["blocked"]
    assert items["alice-qpcr"] in columns["open"] and items["bob-spikein"] in columns["closed"]
    assert sum(view["by_column"].values()) == view["total"] + view["experiments"]
    # Promotion from the card is the ordinary attributed write (CSRF header, allowance, budget).
    body = {"source_kind": "frontier_item", "source_id": items["alice-qpcr"], "task_type": "scouting",
            "target": ctx["agents"]["bob"], "budget": {"minutes": 20, "tokens": 5000}}
    assert http.post("/api/promotions", json=body).status_code == 403
    request = http.post("/api/promotions", json=body, headers=WRITE).json()
    view = http.get("/api/frontier/board").json()
    promoted = next(c for c in view["columns"] if c["key"] == "promoted")
    card = next(i for i in promoted["items"] if i["id"] == items["alice-qpcr"])
    assert card["request"]["id"] == request["id"] and card["request"]["target"] == ctx["agents"]["bob"]
    assert card["request"]["budget"] == {"minutes": 20, "tokens": 5000} and card["request"]["task_type"] == "scouting"
    assert promoted["budget"] == {"minutes": 20, "tokens": 5000} and promoted["targets"][0]["requests"] == 1
    # The reader's own allowance: a local human without one spends the demo's commons default (B13).
    assert view["allowance"]["allowance"] == {"minutes": 600} and view["allowance"]["remaining"]["minutes"] == 580
    # Filters narrow the board; reads never write.
    with Archive(root) as before:
        sequence = before.sequence()
    narrowed = http.get(f"/api/frontier/board?question={ctx['questions']['dana']}").json()
    assert {i["question"] for c in narrowed["columns"] for i in c["items"]} == {ctx["questions"]["dana"]}
    with Archive(root) as after:
        assert after.sequence() == sequence


def test_cluster_confirmation_creates_a_promotable_shared_experiment_that_merges_nothing(demo):
    root, ctx = demo
    items = ctx["frontier"]["items"]
    http = client(root)
    cluster = http.get("/api/frontier/clusters").json()["items"][0]
    confirmed = http.post("/api/frontier/clusters/confirm", headers=WRITE,
                          json={"items": cluster["items"], "note": "same qPCR design"}).json()
    identity = confirmed["shared_experiment"]
    assert confirmed["questions"] == sorted([ctx["questions"]["alice"], ctx["questions"]["bob"]])
    experiment = http.get(f"/api/frontier/experiments/{identity}").json()
    assert experiment["column"] == "open" and experiment["questions"] == confirmed["questions"]
    assert [m["id"] for m in experiment["items"]] == sorted([items["alice-qpcr"], items["bob-qpcr"]])
    assert experiment["confirmations"][0]["note"] == "same qPCR design"
    # Nothing merged: both items remain, unchanged, on the board.
    board_items = {i["id"] for c in http.get("/api/frontier/board").json()["columns"] for i in c["items"]}
    assert {items["alice-qpcr"], items["bob-qpcr"]} <= board_items
    # A second confirmation adds to the same record; the projection is rebuildable byte for byte from events.
    http.post("/api/frontier/clusters/confirm", headers=WRITE, json={"items": cluster["items"], "note": "agreed"})
    with Community(root) as board:
        before = board.rows("SELECT * FROM shared_experiment ORDER BY id")
        assert len(before) == 1 and len(json.loads(before[0]["confirmations"])) == 2
        with board.writer(), board.db:
            board.db.execute("DELETE FROM shared_experiment")
        frontier.rebuild_frontier(board, reason="test")
        assert board.rows("SELECT * FROM shared_experiment ORDER BY id") == before
    # Promotable like an item: the request quotes the member items; a second promotion waits for the first.
    body = {"source_kind": "shared_experiment", "source_id": identity, "task_type": "research",
            "target": ctx["agents"]["alice"], "budget": {"minutes": 30}}
    request = http.post("/api/promotions", headers=WRITE, json=body).json()
    again = http.post("/api/promotions", headers=WRITE, json=body)
    assert again.status_code == 400 and again.json()["error"] == "shared_experiment_not_open"
    promoted = http.get(f"/api/frontier/experiments/{identity}").json()
    assert promoted["column"] == "promoted" and promoted["request"]["id"] == request["id"]
    with Community(root) as board:
        text = board.show(board.one("SELECT post FROM request WHERE id=?", (request["id"],))["post"])["content"]["body"]
        assert "Shared experiment" in text and items["alice-qpcr"] in text and "not merged" in text
        source = json.loads(board.one("SELECT source FROM shared_experiment WHERE id=?", (identity,))["source"])
        assert source["promotions"][0]["request"] == request["id"]
    view = http.get("/api/frontier/board").json()
    assert identity in [e["id"] for c in view["columns"] if c["key"] == "promoted" for e in c["experiments"]]
    # Agents cannot confirm (attribution by people), and unknown ids are 404.
    with Community(root) as board, pytest.raises(DawError, match="permission_denied"):
        frontier.confirm_cluster(board, ctx["agents"]["bob"], cluster["items"])
    assert http.get("/api/frontier/experiments/experiment_unknown").status_code == 404


def test_shared_experiments_read_from_events_on_a_board_without_the_table(demo):
    """A board snapshot built before the table existed (like the committed cohort fixture) is read through the
    same projection computed in memory from events; the read writes nothing."""
    import sqlite3
    root, ctx = demo
    with Community(root) as board:
        frontier.confirm_cluster(board, add_participant(board, "rhea", "human")["id"],
                                 [ctx["frontier"]["items"]["alice-qpcr"], ctx["frontier"]["items"]["bob-qpcr"]])
        stored = board.rows("SELECT * FROM shared_experiment ORDER BY id")
    with sqlite3.connect(root / "board.sqlite") as db:
        db.execute("DROP TABLE shared_experiment")
    before = (root / "board.sqlite").read_bytes()
    with Archive(root) as view:
        assert planning.stored_experiments(view) == stored
        assert planning.experiments(view)[0]["column"] == "open"
    assert (root / "board.sqlite").read_bytes() == before


def test_wishlist_exports_a_lab_ready_proposal_linking_every_requirement_to_its_questions(demo, tmp_path):
    root, ctx = demo
    with Community(root) as board:  # an agent-written requirement that tries to inject markup
        ws = workspace(board, ctx, "dana")
        try:
            with ws.writer():
                frontier.record_item(ws, ctx["questions"]["dana"], kind="next_step", text="Measure <b>it</b>.",
                                     missing_measurement="<script>alert(1)</script> [link](http://x) per sample")
        finally:
            ws.close()
        frontier.rebuild_frontier(board)
    http = client(root)
    markdown = http.get("/api/wishlist/export?format=md")
    assert markdown.status_code == 200 and markdown.headers["content-type"].startswith("text/markdown")
    text = markdown.text
    wish = http.get("/api/wishlist").json()
    assert text.count("\n## ") == wish["total"] and "board sequence" in text
    for group in wish["items"]:  # every requirement lists every question that needs it, linked to its page
        for q in group["questions"]:
            assert f"http://testserver/question/{q['author']}/{q['question']}" in text
    assert "Needed by 2 questions" in text and "untrusted" in text
    assert "[link](http://x)" not in text and "\\[link\\]\\(http://x\\)" in text
    page = http.get("/api/wishlist/export?format=html&download=true")
    assert page.headers["content-type"].startswith("text/html") and "default-src 'none'" in page.headers[
        "content-security-policy"]
    assert "attachment" in page.headers["content-disposition"]
    assert "<script>" not in page.text and "&lt;script&gt;" in page.text
    assert 'href="http://testserver/question/' in page.text
    assert http.get("/api/wishlist/export?format=pdf").status_code == 400
    # The operator CLI writes the same document (links only when told the commons URL); deterministic.
    out = tmp_path / "proposal.md"
    runner = CliRunner()
    result = runner.invoke(bio, ["commons", "--root", str(root), "wishlist", "export", "--out", str(out),
                                 "--base-url", "http://testserver"])
    assert result.exit_code == 0, result.output
    assert out.read_text() == text
    plain = runner.invoke(bio, ["commons", "--root", str(root), "wishlist", "export", "--format", "html"])
    assert plain.exit_code == 0 and "<a href" not in plain.stdout and "<h1>" in plain.stdout


def test_scouting_fills_items_with_inspected_datasets_before_analysis_is_promoted(demo):
    """Scouting deliverables: inspected datasets (eligible or rejected with reasons) recorded as work events or in
    the scouting answer's datasets block; eligible ones make the item candidate evidence, then analysis is promoted."""
    from daw.commons.demo import deliver_scripted
    root, ctx = demo
    items, events = ctx["frontier"]["items"], ctx["frontier"]["events"]
    qpcr = items["alice-qpcr"]
    with Community(root) as board:
        rhea = add_participant(board, "rhea", "human")["id"]
        scouting = promote(board, rhea, "frontier_item", qpcr, "scouting", ctx["agents"]["bob"], {"minutes": 15})
        assert board.one("SELECT status FROM frontier_item WHERE id=?", (qpcr,))["status"] == "promoted"
        ws = workspace(board, ctx, "bob")
        try:
            with ws.writer():
                receipt = ws.put_bytes(b"inspection receipt: GSE000002 series matrix opened, 12 samples")
                question = ctx["questions"]["bob"]
                with pytest.raises(DawError, match="frontier_dataset_not_inspected"):
                    frontier.record_dataset(ws, question, item=qpcr, accession="GSE000003", eligible="yes",
                                            reason="not opened", receipt=f"receipt:{receipt}", inspected=False)
                with pytest.raises(DawError, match="frontier_pointer_unresolved"):
                    frontier.record_dataset(ws, question, item=qpcr, accession="GSE000003", eligible="no",
                                            reason="x", receipt="receipt:" + "0" * 64)
                rejected = frontier.record_dataset(ws, question, item=qpcr, accession="GSE000002", eligible="no",
                                                   reason="No donor identity per sample.", receipt=f"receipt:{receipt}")
        finally:
            ws.close()
        # The scouting answer lists one more dataset in its block; delivery indexes both on the write path.
        block = [{"item": qpcr, "accession": "GSE000004", "inspected": True, "eligible": True,
                  "reason": "Donor-matched qPCR, 6 donors.", "receipt": f"receipt:{receipt}"}]
    answer = "Two datasets inspected.\n\n```datasets\n" + json.dumps(block) + "\n```\n"
    done = deliver_scripted(root, scouting["id"], answer)
    assert done["state"] == "completed"
    with Community(root) as board:
        row = board.one("SELECT * FROM frontier_item WHERE id=?", (qpcr,))
        source = json.loads(row["source"])
        assert row["status"] == "candidate_evidence" and source["candidate_source"] == "scouting"
        assert [(d["accession"], d["eligible"], d["source"]) for d in source["datasets"]] == [
            ("GSE000002", False, "work_event"), ("GSE000004", True, "answer_block")]
        assert source["datasets"][0]["event"] == rejected["id"] and source["datasets"][1]["post"] == done["answer"]
        outcome = [json.loads(r["body"]) for r in board.rows("SELECT body FROM event WHERE kind='task_outcome'")][-1]
        # The run's own deliverables: the answer block (the work event above predates this delivery's run).
        assert outcome["criteria"]["datasets_recorded"] == [] and outcome["criteria"]["datasets_eligible"] == 1
        assert outcome["criteria"]["datasets_in_answer"] == 1 and outcome["criteria"]["dataset_problems"] == []
        assert f"datasets_block:{done['answer']}" in outcome["deliverables_found"]
    # The item page and card show which datasets were inspected and rejected, with reasons.
    http = client(root)
    shown = http.get(f"/api/frontier/{qpcr}").json()
    assert shown["datasets_summary"] == {"inspected": 2, "eligible": 1, "rejected": 1, "withheld": 0}
    assert shown["datasets"][0]["reason"] == "No donor identity per sample."
    assert shown["candidate_evidence"]["set_by"] == "scouting"
    card = next(i for c in http.get("/api/frontier/board").json()["columns"] if c["key"] == "candidate_evidence"
                for i in c["items"] if i["id"] == qpcr)
    assert card["datasets_summary"]["eligible"] == 1
    # Analysis is promoted from the candidate-evidence card; the item is promoted again.
    analysis = http.post("/api/promotions", headers=WRITE, json={
        "source_kind": "frontier_item", "source_id": qpcr, "task_type": "research", "target": ctx["agents"]["alice"],
        "budget": {"minutes": 30}}).json()
    with Community(root) as board:
        row = board.one("SELECT * FROM frontier_item WHERE id=?", (qpcr,))
        assert row["status"] == "promoted" and row["promoted_to"] == analysis["id"]
        # Drop-and-rebuild reproduces the projection, datasets included.
        before = board.rows("SELECT * FROM frontier_item ORDER BY id")
        with board.writer(), board.db:
            board.db.execute("DELETE FROM frontier_item")
        frontier.rebuild_frontier(board)
        assert board.rows("SELECT * FROM frontier_item ORDER BY id") == before
    assert events  # the demo's own items were recorded by their authors


def test_scouting_that_finds_nothing_eligible_returns_the_item_to_its_author(demo):
    root, ctx = demo
    item = ctx["frontier"]["items"]["dana-untestable"]
    with Community(root) as board:
        rhea = add_participant(board, "rhea", "human")["id"]
        promote(board, rhea, "frontier_item", item, "scouting", ctx["agents"]["dana"], {"minutes": 15})
        ws = workspace(board, ctx, "dana")
        try:
            with ws.writer():
                receipt = ws.put_bytes(b"inspection receipt")
                frontier.record_dataset(ws, ctx["questions"]["dana"], item=ctx["frontier"]["events"]["dana-untestable"],
                                        accession="PXD000001", eligible=False, reason="No knockdown arm.",
                                        receipt=f"receipt:{receipt}")
        finally:
            ws.close()
        frontier.rebuild_frontier(board)
        row = board.one("SELECT * FROM frontier_item WHERE id=?", (item,))
        assert row["status"] == "open" and json.loads(row["source"])["datasets"][0]["eligible"] is False


def test_frontier_board_and_wishlist_export_on_the_cohort(cohort):
    """Real data: kinds and states as recorded by the cohort's agents (gaps only, so every card is blocked by its
    retrieval failure) and a proposal listing every wishlist requirement."""
    with Archive(cohort) as view:
        board = planning.board_view(view)
        total = view.one("SELECT count(*) AS n FROM frontier_item")["n"]
        assert board["total"] == total >= 59
        assert board["by_kind"]["gap"] == total and board["by_column"]["blocked"] + board["by_column"]["closed"] \
            + board["by_column"]["open"] == total
        text, _ = planning.export_wishlist(view, "md")
        assert text.count("\n## ") == frontier.wishlist(view)["total"] > 0


# ---- spec v3 G1: frontier-first closure (producer side) ------------------------------------------------------

DRAFT = Path(__file__).parents[1] / ".agents/skills/bio-research/scripts/frontier_draft.py"
FIRST_ROUND = ("pmp22-cis-promoters", "pmp22-regulator-turnover", "pmp22-rna-fate", "pmp22-translation-stress",
               "pmp22-proteostasis", "pmp22-state-compartments", "pmp22-redox-causality", "pmp22-human-dosage",
               "pmp22-axon-mechanics", "pmp22-lipid-hormones")


def helper():
    return runpy.run_path(str(DRAFT))


def test_frontier_draft_proposes_non_gap_items_for_every_first_round_cohort_question(cohort):
    """Acceptance (G1): run over the ten first-round question folders of the real cohort, the agent-side helper
    proposes at least one non-gap item for each, from that agent's own records only; nothing is confirmed until
    the author sets the kind and rewrites the text, and the confirmed list validates as `publish --frontier`."""
    draft = helper()
    with Archive(cohort) as view:
        agents = {a["name"]: a for a in view.rows("SELECT * FROM agent WHERE name IN (%s)" % ",".join("?" * 10),
                                                  FIRST_ROUND)}
    assert sorted(agents) == sorted(FIRST_ROUND)
    for name in FIRST_ROUND:
        root = cohort / agents[name]["trial"] / "workspace"
        [question] = [p.name for p in (root / "questions").iterdir()]
        document = draft["draft"](root, question)
        assert document["status"] == "completed" and document["already_recorded"] == []
        suggested = [i["draft"]["suggested_kind"] for i in document["items"]]
        assert any(k != "gap" for k in suggested), name
        assert set(suggested) <= set(draft["KINDS"]) and all(i["kind"] == "EDIT" for i in document["items"])
        assert all(i["text"].startswith("EDIT:") for i in document["items"])
        assert {i["draft"]["source"] for i in document["items"]} <= {"retrieval_gap", "labbook_section", "labbook_line",
                                                                      "sealed_prediction", "proposal_post"}
        _, problems = draft["confirm"](document)
        assert len(problems) == 2 * len(document["items"])  # kind and text, per row
        row = next(i for i in document["items"] if i["draft"]["suggested_kind"] != "gap")
        edited = {**row, "kind": row["draft"]["suggested_kind"], "text": "Author's own wording of the open item."}
        items, problems = draft["confirm"]({"items": [edited]})
        assert problems == [] and "draft" not in items[0]
        ws = ReadOnlyWorkspace(root)
        try:
            assert frontier.parse_items(ws, question, items)[0]["kind"] == row["draft"]["suggested_kind"]
        finally:
            ws.close()


def test_frontier_draft_reads_gaps_predictions_proposals_and_labbook_sections(tmp_path):
    """Each source the spec names, and only open records: a withdrawn gap, an unsealed or testable prediction
    and a section without a frontier heading propose nothing."""
    draft = helper()
    root = tmp_path / "ws"
    Workspace.create(root).close()
    (root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0\n")
    ws = Workspace(root)
    try:
        with ws.writer():
            question = create_question(ws, "Closure sources")["question"]
            folder = root / "questions" / question
            (folder / "LABBOOK.md").write_text(
                "# Notebook\n\n## Findings\n\nA finding, not an open item.\n\n## Discriminating test\n\n"
                "- Knock down X and measure Y.\n- Repeat in donors.\n\n## Notes\n\nNext step: rerun the contrast.\n")
            (folder / "PROPOSAL.md").write_text("# Proposal: matched assay\n\nMeasure total RNA in matched cultures.\n")
            (folder / "outputs" / "discoveries.json").write_text(json.dumps({"revision": 1, "candidates": [
                {"id": "sealed-untestable", "prediction_lock": "outputs/p.json", "prediction_sha256": "0" * 64,
                 "status": "unresolved", "validation_result": "untestable: no matched arm", "next_test": "Matched arm"},
                {"id": "unsealed", "prediction_lock": None, "status": "unresolved", "validation_result": "untestable"},
                {"id": "tested", "prediction_lock": "outputs/q.json", "status": "supported_in_scope",
                 "validation_result": "passed"}]}))
            kept = record_event(ws, question, "retrieval_gap", {"desired_information": "Donor table",
                                                                "why_current_tools_failed": "not indexed"})
            gone = record_event(ws, question, "retrieval_gap", {"desired_information": "Old table",
                                                                "why_current_tools_failed": "typo"})
            record_event(ws, question, "retrieval_gap_withdrawal", {"event": gone["id"], "reason": "my error"})
            sync_work(ws, question)
    finally:
        ws.close()
    document = draft["draft"](root, question)
    rows = [(i["draft"]["source"], i["draft"]["suggested_kind"], i["text"]) for i in document["items"]]
    assert rows == [
        ("retrieval_gap", "next_step", "EDIT: What becomes computable once this is retrieved: Donor table"),
        ("sealed_prediction", "untestable", "EDIT: sealed-untestable: Matched arm"),
        ("proposal_post", "proposed_experiment", "EDIT: Proposal: matched assay: Measure total RNA in matched cultures."),
        ("labbook_section", "proposed_experiment", "EDIT: Knock down X and measure Y."),
        ("labbook_section", "proposed_experiment", "EDIT: Repeat in donors."),
        ("labbook_line", "next_step", "EDIT: rerun the contrast.")]
    gap = document["items"][0]
    assert gap["draft"]["event"] == kept["id"] and gap["missing_measurement"] == "Donor table"
    # The synced LABBOOK's bytes are in the workspace, so its rows point at their lines.
    assert document["items"][3]["pointers"][0]["locator"] == "line=9" and document["notes"] == []


def test_sync_to_completed_without_a_non_gap_item_warns(tmp_path):
    """G1: `bio work sync --status completed` warns (stderr and JSON) when only gaps are recorded, as publishing
    evidence without claims does; a recorded non-gap item (not withdrawn) clears it."""
    root = tmp_path / "ws"
    Workspace.create(root).close()
    (root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0\n")
    ws = Workspace(root)
    try:
        with ws.writer():
            question = create_question(ws, "Closure")["question"]
            record_event(ws, question, "retrieval_gap", {"desired_information": "A table",
                                                         "why_current_tools_failed": "not indexed"})
    finally:
        ws.close()
    runner = CliRunner()
    result = runner.invoke(bio, ["--workspace", str(root), "work", "sync", question, "--status", "completed"])
    assert result.exit_code == 0, result.output
    assert "warning: completion_without_frontier" in result.stderr
    assert json.loads(result.stdout)["warnings"][0]["evidence"] == {"question": question, "open_gaps": 1}
    assert "warnings" not in json.loads(runner.invoke(bio, ["--workspace", str(root), "work", "sync", question]).stdout)
    item = json.loads(runner.invoke(bio, ["--workspace", str(root), "work", "frontier", question, "--kind",
                                          "next_step", "--text", "Rerun with the table."]).stdout)
    result = runner.invoke(bio, ["--workspace", str(root), "work", "sync", question, "--status", "completed"])
    assert "warnings" not in json.loads(result.stdout) and "completion_without_frontier" not in result.stderr
    runner.invoke(bio, ["--workspace", str(root), "work", "frontier-status", question, item["id"], "--status",
                        "withdrawn", "--reason", "wrong"])
    result = runner.invoke(bio, ["--workspace", str(root), "work", "sync", question, "--status", "completed"])
    assert json.loads(result.stdout)["warnings"][0]["code"] == "completion_without_frontier"


def test_dashboard_frontier_closure_on_the_cohort(cohort):
    """G1 dashboard: items per completed question by kind and finals whose stated next step has a matching item.
    The cohort recorded gaps only, so the measured share is zero (not unavailable)."""
    from daw.commons import metrics
    with Archive(cohort) as view:
        closure = metrics.frontier_closure(view)
    assert closure["completed_questions"] >= 10 and closure["completed_with_non_gap_item"] == 0
    assert closure["completed_with_non_gap_share"] == 0.0
    assert set(closure["items_by_kind"]) == set(frontier.KINDS) and closure["items_by_kind"]["gap"] > 0
    assert all(v == 0 for k, v in closure["items_by_kind"].items() if k != "gap")
    assert closure["finals_stating_next_step"] > 0 and closure["finals_next_step_matched"] == 0
