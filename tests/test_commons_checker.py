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
TOUR = Path(__file__).resolve().parents[1] / "docs" / "colloquy" / "tours" / "pmp22-cohort.json"
CURATION_RECEIPT = Path(__file__).resolve().parents[1] / "docs" / "v3" / "receipts" / "cohort-curation.json"


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
    assert number["scope"] == "text" and number["status"] == "unverified"  # the cited table holds 1.54
    assert number["pointers"][0]["artifact"] == ctx["artifacts"]["contrast"]
    assert number["pointers"][0]["reason"] == "the value does not occur in the output bytes"
    correction = http.get(f"/api/posts/{ctx['posts']['correction']}").json()  # "1.54, not 1.45 (artifact)"
    statuses = {n["text"]: (n["scope"], n["status"]) for n in correction["numbers"]}
    assert statuses == {"1.54": ("post", "post_scoped"), "1.45": ("text", "unverified")}
    assert correction["post_scoped_numbers"] == ["1.54"] and correction["unpointed_numbers"] == []
    post_scoped = next(n for n in correction["numbers"] if n["status"] == "post_scoped")
    assert post_scoped["pointers"] and all(p["post_evidence"] for p in post_scoped["pointers"])
    assert correction["number_summary"]["scopes"] == {"cell": 0, "claim": 0, "line": 0, "text": 1, "curated": 0,
                                                      "post": 1, "none": 0}
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


def test_refused_writeups_are_resolved_by_the_visibility_resolver_and_hidden_stays_a_stub(demo):
    """C5 x C2: one resolver decides what is withheld. A refused write-up is a placeholder (author and time kept);
    hiding it as well makes it the moderation stub; a caller holding `hide` asking for `full` reads it."""
    from daw.commons.moderation import Visibility, hide
    root, ctx = demo
    done = deliver_writing(root, ctx, "Zebrafinch: the ratio is 4.")
    post = done["answer"]
    with Archive(root) as view:
        reader = Visibility.of(view)
        assert reader.refused(post) and not reader.withheld(post)
        assert reader.card(post, {"id": post, "title": "x", "snippet": "y"})["title"] == checks.PLACEHOLDER_TITLE
        operator = Visibility.of(view, view.participant("operator"), True)
        assert not operator.refused(post)
    http = client(root)
    shown = http.get(f"/api/posts/{post}").json()
    assert shown["content"] is None and shown["withheld"]["status"] == "refused" and shown["author"]
    run = http.get(f"/api/runs/{shown['run']}").json()
    assert run["final"]["text"] is None and run["final"]["title"] == checks.PLACEHOLDER_TITLE
    with Community(root) as board:
        hide(board, "operator", post, "checker test")
    stub = http.get(f"/api/posts/{post}").json()
    assert stub == {"id": post, "hidden": True, "reason": "checker test"}


def test_refused_writeup_is_a_placeholder_for_agents_and_in_raw_run_streams(demo):
    """C5 on the remaining surfaces: an agent reading the refused write-up (CLI/board service) gets the
    placeholder, and the run's raw stream and model messages, which carry the prose verbatim, are withheld."""
    from daw.commons import boardservice
    root, ctx = demo
    done = deliver_writing(root, ctx, "Zebrafinch: the ratio is 4.")
    post = done["answer"]
    with Community(root) as board:
        read = board.read(post, ctx["agents"]["bob"])
        assert read["content"]["title"] == checks.PLACEHOLDER_TITLE and "Zebrafinch" not in json.dumps(read)
        served = boardservice.execute(root, ctx["agents"]["bob"], "show", {"post": post})
        assert "Zebrafinch" not in json.dumps(served)
        assert board.read(post, "operator", full=True)["content"]["body"].startswith("Zebrafinch")
    http = client(root)
    run = http.get(f"/api/posts/{post}").json()["run"]
    for path in ("raw", "messages"):
        refused = http.get(f"/api/runs/{run}/{path}")
        assert refused.status_code == 403 and refused.json()["error"] == "writeup_withheld"


# ---- spec v3 B6: a text-anywhere match is its own scope -------------------------------------------------------

def test_a_text_anywhere_match_is_scope_text_unique_only_and_excluded_from_verified_share(demo):
    # Without a locator a value verifies only when exactly one numeric token of the (small, text) output matches.
    cache = {"t": (b"k\tv\nx\t0.51\ny\t0.51\nz\t7\n", "t.tsv", None)}
    twice = locators.verify_artifact(None, "t", None, locators.parse_number("0.51"), cache)
    assert twice["result"] == "unverified" and twice["at"] == "text" and twice["found"]["occurrences"] == 2
    assert "unique" in twice["reason"] and twice["found"]["lines"] == [2, 3]
    once = locators.verify_artifact(None, "t", None, locators.parse_number("7"), cache)
    assert once["result"] == "verified" and once["at"] == "text" and once["found"]["line"] == 4
    # n12 is a number like every other glued form; identifier characters and letter-bounded words (e2e) are not.
    found = [n["text"] for n in writeup.numbers_in("n12 of PMP22 and P1 (log2, IL-6, GSE1234, H3K27me3) at x2 in e2e", 0)]
    assert found == ["12", "2"]
    root, ctx = demo
    measurement, contrast = ctx["artifacts"]["measurement"], ctx["artifacts"]["contrast"]
    done = deliver_writing(root, ctx, f"Means: [32.0]({measurement}); the ratio is [1.54]({contrast}#row=B_vs_A;"
                                      "col=log2_ratio).")
    [check] = [e for e in events(root, "writeup_check") if e["post"] == done["answer"]]
    assert check["rules"] == "writeup-pointers/3" and [n["scope"] for n in check["numbers"]] == ["text", "cell"]
    report = client(root).get(f"/api/posts/{done['answer']}").json()
    assert {n["text"]: (n["scope"], n["status"]) for n in report["numbers"]} == {"32.0": ("text", "verified"),
                                                                                 "1.54": ("cell", "verified")}
    summary = report["number_summary"]
    assert summary["statuses"]["verified"] == 2 and summary["author_verified"] == 1 and summary["text_verified"] == 1
    assert summary["verified_share"] == 0.5 and summary["number_level"] == 2  # shown verified, never in the share
    coverage = metrics.number_coverage({"numbers": {done["answer"]: summary}}, [{"id": done["answer"]}])
    assert coverage["verified_share"] == 0.5 and coverage["text_verified"] == 1 and coverage["scopes"]["text"] == 1


# ---- spec v3 G2: people curate pointers; the platform never authors them -------------------------------------

def test_a_curated_pointer_is_scope_curated_attributed_and_never_author_verified(cohort_copy, tmp_path):
    from daw.commons import curation
    from daw.commons.fixture import record_curation, verify_fixture
    from daw.commons.participants import add_participant
    from daw.commons.participation import comment
    root = cohort_copy
    step = json.loads(TOUR.read_text())["steps"][0]
    post, offset, artifact, locator = step["final"], step["number"]["offset"], step["artifact"], step["locator"]
    with Community(root) as board:
        add_participant(board, "rhea", "human", profile={"display_name": "Rhea"})
        agent = board.one("SELECT id FROM agent WHERE kind='agent' ORDER BY created LIMIT 1")["id"]
        with pytest.raises(DawError, match="permission_denied"):  # agents never author pointers
            curation.curate(board, agent, post, offset, artifact=artifact, locator=locator, note="mine")
        with pytest.raises(DawError, match="value_not_at_locator"):  # checked against the bytes before recording
            curation.curate(board, "rhea", post, offset, artifact=artifact, locator="key=primary[0].ci95_low", note="x")
        with pytest.raises(DawError, match="invalid_locator"):  # a curator names the place, never "anywhere"
            curation.curate(board, "rhea", post, offset, artifact=artifact, locator="round=2", note="x")
        with pytest.raises(DawError, match="unknown_number"):
            curation.curate(board, "rhea", post, offset + 1, artifact=artifact, locator=locator, note="x")
    http = TestClient(create_app(root, local_user="rhea", static_dir=root / "missing"))
    body = {"post": post, "offset": offset, "artifact": artifact, "locator": locator,
            "note": "primary[0].effect_log2 of the paired audit summary"}
    assert http.post("/api/curation/pointers", json=body).status_code == 403  # the write discipline (CSRF header)
    made = http.post("/api/curation/pointers", json=body, headers={"X-Colloquy-Request": "1"})
    assert made.status_code == 200, made.text
    assert made.json()["kind"] == "pointer_curated" and made.json()["participant_name"] == "rhea"
    other = next(n for n in http.get(f"/api/posts/{post}").json()["numbers"] if n["offset"] != offset)
    marked = CliRunner().invoke(app, ["--root", str(root), "curate", "unlocatable", post, "--offset", str(other["offset"]),
                                      "--note", "computed in the prose from two cells", "--as", "rhea"])
    assert marked.exit_code == 0, marked.output
    before = sequence(root)
    page = http.get(f"/api/posts/{post}").json()
    [curated] = [n for n in page["numbers"] if n["offset"] == offset]
    assert curated["scope"] == "curated" and curated["status"] == "verified"
    [pointer] = curated["pointers"]
    assert pointer["curated"] and pointer["curator_name"] == "rhea" and pointer["locator"] == locator
    assert pointer["route"].startswith(f"/artifact/{artifact}?locator=") and pointer["at"] == "key"
    unlocatable = next(n for n in page["numbers"] if n["offset"] == other["offset"])
    assert unlocatable["unlocatable"]["curator_name"] == "rhea" and unlocatable["scope"] == other["scope"]
    # Never the author's: not number-level, not in verified_share; the dashboard keeps the three apart.
    summary = page["number_summary"]
    assert summary["pointers"]["curated"] == 1 and summary["pointers"]["author"] == 0
    assert summary["pointers"]["unlocatable"] == 1 and summary["curated_verified"] == 1
    assert summary["verified_share"] == 0.0 and summary["number_level"] == 0
    board_numbers = http.get("/api/dashboard").json()["summary"]["board"]["numbers"]
    assert board_numbers["pointers"]["curated"] == 1 and board_numbers["pointers"]["author"] == 0
    assert board_numbers["verified_share"] == 0.0 and board_numbers["number_level_share"] == 0.0
    acts = http.get("/api/curation/pointers", params={"post": post}).json()
    assert [a["kind"] for a in acts["acts"]] == ["pointer_curated", "unlocatable"]
    assert acts["progress"]["curated"] == 1 and acts["progress"]["unlocatable"] == 1
    # The tour walks the curated number: two clicks from bytes, with the curator named.
    walked = http.get("/api/tours/pmp22-cohort").json()
    final = next(f for f in walked["finals"] if f["post"] == post)
    entry = next(n for n in final["numbers"] if n["offset"] == offset)
    assert entry["resolution"] == "curated" and entry["curated"]["curator_name"] == "rhea" and final["curators"] == ["rhea"]
    progress = http.get("/api/curation/progress", params={"tour": "pmp22-cohort"}).json()
    assert progress["milestone"]["met"] is False and progress["milestone"]["required_finals"] == 5
    # Surface parity (spec v3 section 1): the post's author sees both acts as attributed marks on its post.
    from daw.commons import agentview
    with Community(root) as board:
        author = board.one("SELECT author FROM post WHERE id=?", (post,))["author"]
        seen = agentview.acts(board, author, after=0, caller=board.agent(author))["acts"]
        shown = agentview.post_acts(board, post, caller=board.agent(author))
    for listed in (seen, shown):
        curations = [a for a in listed if a["kind"] in ("pointer_curated", "unlocatable")]
        assert [(a["kind"], a["participant_name"], a["target_id"]) for a in curations] == \
            [("pointer_curated", "rhea", post), ("unlocatable", "rhea", post)]
        assert curations[0]["pointers"] == [{"kind": "artifact", "id": artifact, "locator": locator}]
        assert curations[1]["note"] == "computed in the prose from two cells" and "never counted" in curations[1]["meaning"]
    assert sequence(root) == before  # reads never write
    # The receipt is written only when the milestone is met: no receipt claims curation that did not happen.
    output = tmp_path / "cohort-curation.json"
    refused = CliRunner().invoke(app, ["--root", str(root), "curate", "receipt", "--output", str(output)])
    assert refused.exit_code == 1 and not output.exists()
    # A fixture records curation acts, and nothing else, through its own tool.
    entry = record_curation(root, reason="test curation by rhea")
    assert entry["curation_acts"] == 2 and verify_fixture(root)["verified"] and not verify_fixture(root)["untracked"]
    with Community(root) as board:
        comment(board, "rhea", "post", post, "Which table is this?")
    with pytest.raises(DawError, match="fixture_curation_has_other_writes"):
        record_curation(root, reason="laundering a comment")


@pytest.mark.skipif(not CURATION_RECEIPT.is_file(), reason="no person has curated the tour finals yet (spec v3 G2)")
def test_committed_curation_receipt_reproduces_from_the_fixture(cohort):
    from daw.commons import curation, tour
    receipt = json.loads(CURATION_RECEIPT.read_text())
    with Archive(cohort) as view:
        value = curation.receipt(view, tour.get(view, receipt["tour"]["name"], resolved=False))
    assert value["finals"] == receipt["finals"] and value["milestone"] == receipt["milestone"]
    assert value["milestone"]["met"] and all(f["unresolved"] == 0 for f in value["finals"] if f.get("resolved"))
