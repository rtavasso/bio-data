"""The number checker beyond Studio (spec v2 C5, C11, V2): locator grammar and rounding, verdict records,
number reports on every post, the map's verified pointer counts, the dashboard share and the cohort audit.

Shares and counts are measured on the committed PMP22 cohort fixture (C0); invariants on the synthetic demo."""
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from daw.commons import checks, export, locators, metrics, writeup
from daw.commons.app import create_app
from daw.commons.archive import Archive
from daw.commons.cli import app
from daw.commons.demo import scripted_runtime
from daw.commons.participation import commission
from daw.community import Community
from daw.community_runtime import dispatch
from daw.util import DawError

RECEIPT = Path(__file__).resolve().parents[1] / "docs" / "v3" / "receipts" / "cohort-number-audit.json"


def client(root):
    return TestClient(create_app(root, static_dir=root / "missing"))


def events(root, kind):
    with Archive(root) as view:
        return [json.loads(r["body"]) for r in view.rows("SELECT body FROM event WHERE kind=? ORDER BY seq", (kind,))]


def sequence(root):
    return sqlite3.connect(root / "board.sqlite").execute("SELECT max(seq) FROM event").fetchone()[0]


def deliver_writing(root, ctx, text, task_type="writing"):
    with Community(root) as board, scripted_runtime(root) as (_, answers):
        request = commission(board, ctx["participation"]["human"], task_type, ctx["agents"]["dana"], {"minutes": 10},
                             subject_kind="post", subject_id=ctx["claims"]["correction"], note="checker test")
        post = board.one("SELECT post FROM request WHERE id=?", (request["id"],))["post"]
        (answers / f"{post}.md").write_text(text)
        return dispatch(board, request["id"], str(root / "demo-harness" / "hermes"))


# ---- locator grammar and equality with rounding (pure) -------------------------------------------------

def test_locator_grammar_is_strict():
    assert locators.parse_locator("row=B_vs_A;col=log2_ratio") == {"row": "B_vs_A", "col": "log2_ratio"}
    assert locators.parse_locator("row=B%20vs%20A;col=%232;round=2") == {"row": "B vs A", "col": "#2", "round": "2"}
    assert locators.parse_locator("key=stats.fit[0].value") == {"key": "stats.fit[0].value"}
    assert locators.key_path("stats.fit[0].value") == ["stats", "fit", 0, "value"]
    assert locators.key_path("[2].x") == [2, "x"]
    assert locators.target_kind(locators.parse_locator("line=3")) == "line"
    for bad in ("row=B_vs_A", "col=x", "row=a;col=b;key=c", "line=0", "round=13", "row=a;col=b;row=c", "colour=x",
                "key=a..b", "key=a[x]", "", "row=;col=x"):
        with pytest.raises(locators.LocatorError):
            locators.parse_locator(bad)


def test_equality_uses_the_declared_or_implied_rounding():
    def ok(prose, cited, decimals=None):
        return locators.matches(locators.parse_number(prose), cited, decimals)
    assert ok("1.54", 1.5432) and ok("1.5", 1.5432) and ok("2", 1.5432) and not ok("1.55", 1.5432)
    assert ok("1.54", 1.535) and ok("1.54", 1.545) and not ok("1.54", 1.5451)  # either rounding at the half
    assert ok("1.5", 1.5432, 1) and not ok("1.5", 1.5432, 2)  # round=2: the prose claims two decimals
    assert ok("12%", 12.04) and ok("12%", 0.1204) and not ok("12%", 0.13)
    assert ok("3.2×10^-4", 3.24e-4) and not ok("3.2×10^-4", 3.3e-4) and ok("1e-5", 1.4e-5)
    assert ok("−0.5", -0.5) and not ok("−0.5", 0.5) and ok("±0.2", -0.2)
    assert ok("three", 3) and not ok("three", 3.2) and ok("½", 0.5) and ok("1,000", 1000.4)
    assert locators.parse_cell("NA") is None and locators.parse_cell(" 1.54 ") == 1.54 and locators.parse_cell(2) == 2.0
    assert locators.parse_number("1e999999") is None  # absurd exponents are not numbers, never an overflow


def test_cells_keys_and_lines_are_read_from_the_cited_bytes():
    header, rows = locators.read_table(b"## comment\ncontrast\tlog2_ratio\tq\nB_vs_A\t1.54\t0.003\nC_vs_A\tNA\t1\n",
                                       "t.tsv")
    assert header == ["contrast", "log2_ratio", "q"] and len(rows) == 2
    assert locators.cell(header, rows, {"row": "C_vs_A", "col": "q"})["value"] == "1"
    assert locators.cell(header, rows, {"row": "#1", "col": "#3"})["value"] == "0.003"
    with pytest.raises(locators.LocatorError, match="no row"):
        locators.cell(header, rows, {"row": "D_vs_A", "col": "q"})
    with pytest.raises(locators.LocatorError, match="not unique"):
        locators.cell(["k", "v"], [["a", "1"], ["a", "2"]], {"row": "a", "col": "v"})
    assert locators.read_table(b"k,v\n\"a,b\",2\n", "t.csv") == (["k", "v"], [["a,b", "2"]])
    assert locators.json_value(b'{"stats": {"fit": [{"value": 0.51}]}}', "stats.fit[0].value") == 0.51
    with pytest.raises(locators.LocatorError, match="container"):
        locators.json_value(b'{"stats": {"fit": [1]}}', "stats.fit")
    with pytest.raises(locators.LocatorError, match="TSV or CSV"):
        locators.read_table(b"{}", "x.json")


# ---- verdicts are records (C5) ----------------------------------------------------------------------------

def test_verdict_is_recorded_once_and_rerecorded_only_when_it_changes(demo):
    root, ctx = demo
    claim, contrast = ctx["claims"]["current"], ctx["artifacts"]["contrast"]
    done = deliver_writing(root, ctx, f"The ratio is [1.54]({claim}); the table holds [1.54]({contrast}#row=B_vs_A;"
                                      "col=log2_ratio).")
    [check] = [e for e in events(root, "writeup_check") if e["post"] == done["answer"]]
    assert check["status"] == "rendered" and check["actor"] == "runtime" and check["rules"] == writeup.RULES_VERSION
    assert [n["pointers"] for n in check["numbers"]] == [[claim], [f"{contrast}#row=B_vs_A;col=log2_ratio"]]
    followups = [json.loads(p.read_text()) for p in root.glob("runs/**/studio-followup.json")]
    assert any(f.get("writeup_checks", [{}])[0].get("post") == done["answer"] for f in followups)
    runner = CliRunner()
    again = runner.invoke(app, ["--root", str(root), "writeup", "record", done["answer"]])
    assert again.exit_code == 0, again.output
    assert json.loads(again.output)["created"] is False  # unchanged verdict: no new event
    assert len([e for e in events(root, "writeup_check") if e["post"] == done["answer"]]) == 1
    refused = runner.invoke(app, ["--root", str(root), "writeup", "record", done["answer"], "--as",
                                  ctx["agents"]["alice"]])
    assert refused.exit_code != 0  # recording is an operator action (permission dispatch)
    history = client(root).get(f"/api/writeup-checks/{done['answer']}").json()
    assert [h["status"] for h in history["history"]] == ["rendered"] and history["latest"]["post"] == done["answer"]
    # Reads never write: rendering, the post page and the verdict history append nothing.
    before = sequence(root)
    http = client(root)
    for path in (f"/api/studio/writeups/{done['answer']}", f"/api/posts/{done['answer']}",
                 f"/api/numbers/{done['answer']}", "/api/studio", "/api/map?limit=10000"):
        assert http.get(path).status_code == 200, path
    assert sequence(root) == before


def test_regeneration_is_still_evaluated_at_render_over_a_recorded_verdict(demo):
    root, ctx = demo
    from daw.commons.claims import claim_id
    from daw.commons.demo import Researcher
    contrast = ctx["artifacts"]["contrast"]
    with Community(root) as board:
        alice = Researcher(board, board.agent(ctx["agents"]["alice"]), root / "demo-harness" / "inputs")
        first = alice.publish("Claims", f"Claims ({contrast}).", artifacts=[contrast],
                              claims=[{"text": "log2(B/A) = 1.54.", "status": "supported",
                                       "pointers": [{"kind": "artifact", "id": contrast}]}], request_key="chk-1")
    done = deliver_writing(root, ctx, f"The ratio is [1.54]({claim_id(first['id'], 0)}).")
    with Community(root) as board:
        alice = Researcher(board, board.agent(ctx["agents"]["alice"]), root / "demo-harness" / "inputs")
        alice.publish("Claims, corrected", f"Corrected ({contrast}).", artifacts=[contrast],
                      claims=[{"text": "log2(B/A) = 1.55.", "status": "supported",
                               "pointers": [{"kind": "artifact", "id": contrast}]}], supersedes=first["id"],
                      parent=first["id"], request_key="chk-2")
    rendered = client(root).get(f"/api/studio/writeups/{done['answer']}").json()
    assert rendered["verdict"]["source"] == "recorded" and rendered["status"] == "rendered"
    assert rendered["flagged"] and rendered["regeneration_required"]["claims"][0]["claim"] == claim_id(first["id"], 0)


# ---- number reports on every post (C11, V2) ---------------------------------------------------------------

def test_post_page_separates_verified_unverified_post_scoped_and_unpointed_numbers(demo):
    root, ctx = demo
    http = client(root)
    finding = http.get(f"/api/posts/{ctx['posts']['finding']}").json()  # "log2 ratio 1.45 (artifact_contrast)"
    [number] = [n for n in finding["numbers"] if n["text"] == "1.45"]
    assert number["scope"] == "line" and number["status"] == "unverified"  # the cited table holds 1.54
    assert number["pointers"][0]["artifact"] == ctx["artifacts"]["contrast"]
    assert number["pointers"][0]["reason"] == "the value does not occur in the output bytes"
    correction = http.get(f"/api/posts/{ctx['posts']['correction']}").json()  # "1.54, not 1.45 (artifact)"
    statuses = {n["text"]: (n["scope"], n["status"]) for n in correction["numbers"]}
    assert statuses == {"1.54": ("post", "post_scoped"), "1.45": ("line", "unverified")}
    assert correction["post_scoped_numbers"] == ["1.54"] and correction["unpointed_numbers"] == []
    post_scoped = next(n for n in correction["numbers"] if n["status"] == "post_scoped")
    assert post_scoped["pointers"] and all(p["post_evidence"] for p in post_scoped["pointers"])
    assert correction["number_summary"]["scopes"] == {"cell": 0, "claim": 0, "line": 1, "post": 1, "none": 0}
    with Community(root) as board:
        loose = board.publish(ctx["agents"]["dana"], "Loose", "About forty samples, of which 12 failed.")["id"]
    detail = http.get(f"/api/posts/{loose}").json()
    assert detail["unpointed_numbers"] == ["12"] and detail["post_scoped_numbers"] == []  # forty > twenty: not detected
    # A pointer whose value was found without a locator opens the artifact at the line where it was found.
    done = deliver_writing(root, ctx, f"Means: [32.0]({ctx['artifacts']['measurement']}).")
    [measured] = http.get(f"/api/posts/{done['answer']}").json()["numbers"]
    assert measured["status"] == "verified" and measured["pointers"][0]["at"] == "text"
    assert measured["pointers"][0]["route"] == f"/artifact/{ctx['artifacts']['measurement']}?locator=line%3D3"


def test_export_marks_numbers_and_writes_every_post_report(demo, tmp_path):
    root, ctx = demo
    with Community(root) as board:
        export.export_snapshot(board, "operator", "board", output=tmp_path / "site")
    page = (tmp_path / "site" / f"posts/{ctx['posts']['finding']}.html").read_text()
    assert '<span class="num num-unverified"' in page and ">1.45</span>" in page
    report = json.loads((tmp_path / "site" / f"checks/{ctx['posts']['finding']}.json").read_text())
    assert report["kind"] == "post" and report["status"] == "report"
    [number] = [n for n in report["numbers"] if n["text"] == "1.45"]
    assert number["status"] == "unverified" and number["pointers"][0]["id"] == ctx["artifacts"]["contrast"]


def test_map_claim_nodes_show_verified_pointer_counts(demo):
    root, ctx = demo
    claim = ctx["claims"]["current"]
    before = {n["id"]: n for n in client(root).get("/api/map", params={"limit": 10000}).json()["nodes"]}
    assert before[claim]["verified_pointers"] == 0
    deliver_writing(root, ctx, f"The ratio is [1.54]({claim}), again [1.54]({claim}); not [1.45]({claim}).")
    after = {n["id"]: n for n in client(root).get("/api/map", params={"limit": 10000}).json()["nodes"]}
    assert after[claim]["verified_pointers"] == 2  # recorded verdict: two numbers verified against the claim text


def test_dashboard_reports_number_coverage_per_cohort(demo):
    root, ctx = demo
    deliver_writing(root, ctx, "nothing numeric here")
    value = client(root).get("/api/dashboard").json()
    summary = value["summary"]["board"]["numbers"]
    assert summary["finals"] >= 1 and summary["numbers"] == sum(summary["scopes"].values())
    assert summary["number_level_share"] == round(summary["number_level"] / summary["numbers"], 4)
    with Community(root) as board:
        runs = [r["id"] for r in board.rows("SELECT id FROM attempt ORDER BY created")]
        metrics.create_cohort(board, "operator", "checker-cohort", runs=runs)
    panels = client(root).get("/api/dashboard").json()["panels"]["cohort"]
    panel = next(p for p in panels if p["label"] == "checker-cohort")
    assert panel["board"]["numbers"]["finals"] >= 1 and "number_level_share" in panel["board"]["numbers"]


# ---- the real cohort (C0): shares measured on the committed fixture ------------------------------------------

def test_cohort_number_audit_reproduces_the_committed_receipt(cohort):
    before = sequence(cohort)
    with Archive(cohort) as view:
        result = checks.audit(view)
    receipt = json.loads(RECEIPT.read_text())
    assert result["rules"] == receipt["rules"] and result["totals"] == receipt["totals"]
    assert {r["post"] for r in result["finals"]} == {r["post"] for r in receipt["finals"]}
    totals = result["totals"]["all"]
    assert totals["finals"] == 54 and totals["numbers"] == sum(totals["scopes"].values())
    # The first cohort wrote no pointer at any number: the honest share is zero, and almost everything is
    # covered only by the post's evidence list (C11).
    assert totals["shares"]["number_level_pointer"] == 0.0 and totals["shares"]["resolvable_to_cell"] == 0.0
    assert totals["statuses"]["post_scoped"] > 0.9 * totals["numbers"]
    assert sequence(cohort) == before  # the audit reads; it never writes


def test_cohort_dashboard_and_post_pages_report_the_share(cohort):
    http = client(cohort)
    before = sequence(cohort)
    summary = http.get("/api/dashboard").json()["summary"]["board"]["numbers"]
    totals = json.loads(RECEIPT.read_text())["totals"]["all"]
    assert summary["numbers"] == totals["numbers"] and summary["finals"] == totals["finals"]
    assert summary["number_level_share"] == totals["shares"]["number_level_pointer"]
    post = http.get("/api/posts/post_3f7bd6e66753476fb33ec6d9da9cbcc8").json()
    assert post["numbers"] and post["post_scoped_numbers"] and post["number_summary"]["numbers"] == len(post["numbers"])
    assert all(n["status"] in ("post_scoped", "unpointed") for n in post["numbers"])
    assert sequence(cohort) == before


def test_locate_reports_absent_bytes_on_the_cohort(cohort):
    http = client(cohort)
    absent = "artifact_2898ce0c7c1ac558f70cd34012400744153963aa374c5db9c70d1595dfd5bfa8"  # 171 KB, not in the fixture
    located = http.get(f"/api/artifacts/{absent}/locate", params={"locator": "row=%231;col=%231"}).json()
    assert located["present"] is False and "absent" in located["error"]
    with pytest.raises(DawError):
        with Archive(cohort) as view:
            locators.locate(view, "artifact_" + "0" * 64, None)
