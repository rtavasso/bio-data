"""Studio (M6.1–M6.5, M8.4, Flow B step 5): write-up renderer, regeneration flags, reviews as marks,
replication confirmation and mismatch, digests, static export and read-only federation. Offline."""
import hashlib
import json
import shutil
import stat

import pytest
from fastapi.testclient import TestClient

from daw.commons import export, studio, studio_demo, writeup
from daw.commons.app import create_app
from daw.commons.archive import Archive
from daw.commons.claims import claim_id
from daw.commons.demo import Researcher, scripted_runtime
from daw.commons.moderation import hide
from daw.commons.participation import commission
from daw.community import Community
from daw.community_runtime import dispatch
from daw.util import DawError, canonical

WRITE = {"X-Colloquy-Request": "1"}
C = "claim_" + "a" * 32
A = "artifact_" + "b" * 64
P = "post_" + "c" * 32


def client(root, **options):
    return TestClient(create_app(root, static_dir=root / "missing", **options))


def events(board, kind):
    return [json.loads(r["body"]) for r in board.rows("SELECT body FROM event WHERE kind=? ORDER BY seq", (kind,))]


def deliver(board, answers, request, text, hook=None):
    post = board.one("SELECT post FROM request WHERE id=?", (request["id"],))["post"]
    (answers / f"{post}.md").write_text(text)
    if hook:
        (answers / f"{post}.hook.py").write_text(hook)
    return dispatch(board, request["id"], str(board.root / "demo-harness" / "hermes"))


def human(ctx):
    return ctx["participation"]["human"]


def numbers(source):
    return [(n["text"], n["scope"]) for _, unit in writeup.units(writeup.parse(source)) for n in unit["numbers"]]


# ---- M6.1 pointer syntax and the number check ----------------------------------------------------

def test_numeric_tokens_are_defined_precisely():
    source = (f"# 2.1 Results for PMP22\n\nBy Ada, 2026-01-05 10:30 UTC\n\n"
              f"1. IL-6, log2, v1.2, GSE1234, chr1, B_vs_A and {P} carry no numbers.\n"
              f"2. Values 12%, 1e-5, 3.2×10^-4, 3:1, 1/3, 1,000 and -0.5 are numbers.\n\n"
              "Dates outside a byline count: 2026-01-05.\n")
    found = numbers(source)
    assert [t for t, _ in found] == ["12%", "1e-5", "3.2×10^-4", "3:1", "1/3", "1,000", "-0.5", "2026", "01", "05"]
    assert all(scope == "none" for _, scope in found)
    assert numbers("A 5mg dose on the 2nd day.") == [("5", "none"), ("2", "none")]  # digits before letters count


def test_sentences_pointer_links_citations_and_units():
    source = (f"The contrast is [1.54]({C}). Means were 11.0 and 32.0 [{A}]. Approx. 5 samples e.g. in Fig. 2 "
              f"[{C}].\nThe value is 7. [{A}] Context only: 4 samples [see]({P}).\n\n"
              f"| a | b |\n|---|---|\n| x | 3 |\n| y [{C}] | 9 |\n\n![Figure 1: 2 panels]({A})\n\n"
              f"```\nvalue 8 {A}\nother 6\n```\n")
    found = numbers(source)
    assert found == [("1.54", "pointer"), ("11.0", "sentence"), ("32.0", "sentence"), ("5", "sentence"),
                     ("2", "sentence"), ("7", "sentence"), ("4", "none"), ("3", "none"), ("9", "sentence"),
                     ("1", "pointer"), ("2", "pointer"), ("8", "block"), ("6", "block")]
    blocks = writeup.parse(source)
    sentences = blocks[0]["sentences"]
    assert len(sentences) == 5 and sentences[3]["pointers"] == [A]  # a citation after the period belongs to it
    unit = next(u for _, u in writeup.units(blocks) for n in u["numbers"] if n["text"] == "4")
    assert unit["numbers"][0]["reason"] == "only post pointers (context) in this sentence"


def _writeup_post(board, author, body, *, parent=None):
    with board.writer(), board.library.writer():
        return board._post(author, "Write-up", body, parent=parent, kind="answer")


def test_renderer_refuses_unpointed_numbers_and_unresolved_pointers_with_locations(demo):
    root, ctx = demo
    contrast = ctx["artifacts"]["contrast"]
    run = "run_" + "d" * 32
    body = (f"The marker rose 3-fold.\n\nIt is [1.54]({C}) and see [{contrast}].\n\n![Figure 2]({P})\n\n"
            f"A run [link]({run}) and a malformed [x](claim_123).")
    with Community(root) as board:
        post = _writeup_post(board, ctx["agents"]["dana"], body)
    response = client(root).get(f"/api/studio/writeups/{post}")
    assert response.status_code == 422
    refused = response.json()
    assert refused["error"] == "writeup_refused" and refused["status"] == "refused"
    kinds = [(p["kind"], p.get("text") or p.get("pointer")) for p in refused["problems"]]
    assert kinds == [("unpointed_number", "3"), ("unresolved_pointer", C), ("figure_not_artifact", P),
                     ("unpointed_number", "2"), ("pointer_kind_not_allowed", run), ("unresolved_pointer", "claim_123")]
    first = refused["problems"][0]
    assert body[first["offset"]:first["offset"] + first["length"]] == "3" and first["line"] == 1
    assert first["context"] == "The marker rose 3-fold." and refused["source"] == body
    assert "blocks" not in refused  # a refused write-up is never served


def test_rendered_writeup_is_three_clicks_from_bytes_with_the_cited_subgraph(demo):
    root, ctx = demo
    claim = ctx["claims"]["current"]
    figure = ctx["observatory_map"]["figure"]
    body = (f"# Corrected contrast\n\nBy dana, 2026-01-05\n\nThe ratio is [1.54]({claim}). Means were 11.0 and 32.0 "
            f"[{ctx['artifacts']['measurement']}].\n\n![Figure 1: synthetic figure]({figure})\n\n"
            f"Context: [the correction]({ctx['claims']['correction']}).")
    with Community(root) as board:
        post = _writeup_post(board, ctx["agents"]["dana"], body)
    http = client(root)
    rendered = http.get(f"/api/studio/writeups/{post}").json()
    assert rendered["status"] == "rendered" and rendered["regeneration_required"] is None
    assert rendered["stats"] == {"numbers": 4, "pointed": 4, "units": 6, "pointers": 4}
    # Sentence -> claim pointer -> artifact -> verified bytes.
    sentence = next(s for b in rendered["blocks"] for s in b.get("sentences", []) if claim in s["pointers"])
    entry = rendered["pointers"][claim]
    assert entry["present"] and entry["status"] == "supported" and sentence["numbers"][0]["covered_by"] == [claim]
    artifact = next(p for p in entry["pointers"] if p["kind"] == "artifact")
    shown = http.get(artifact["route"].replace("/artifact/", "/api/artifacts/")).json()
    data = http.get(artifact["bytes_url"])
    assert data.status_code == 200 and data.headers["x-content-sha256"] == shown["output_blob"]
    assert hashlib.sha256(data.content).hexdigest() == shown["output_blob"]
    figure_entry = rendered["pointers"][figure]
    assert figure_entry["location"]["store"] == "workspace" and figure_entry["image_url"].startswith("/api/blobs/")
    assert http.get(figure_entry["image_url"]).headers["content-type"] == "image/png"
    # The embedded map holds the cited records and only relations the full map records.
    graph = rendered["evidence_map"]
    ids = {n["id"] for n in graph["nodes"]}
    assert {post, claim, figure, ctx["artifacts"]["measurement"], ctx["claims"]["correction"]} <= ids
    full = http.get("/api/map", params={"limit": 10000}).json()
    recorded = {(e["source"], e["target"], e["relation"]) for e in full["edges"]}
    assert graph["edges"] and all((e["source"], e["target"], e["relation"]) in recorded for e in graph["edges"])
    assert set(graph["positions"]) == ids


def test_regeneration_flag_after_a_supersede_and_the_studio_listing(demo):
    root, ctx = demo
    contrast = ctx["artifacts"]["contrast"]
    with Community(root) as board, scripted_runtime(root) as (_, answers):
        alice = Researcher(board, board.agent(ctx["agents"]["alice"]), root / "demo-harness" / "inputs")
        first = alice.publish("Contrast claims", f"Claims with pointers ({contrast}).", artifacts=[contrast],
                              claims=[{"text": "log2(B/A) = 1.54.", "status": "supported",
                                       "pointers": [{"kind": "artifact", "id": contrast}]}], request_key="studio-c1")
        cited = claim_id(first["id"], 0)
        request = commission(board, human(ctx), "writing", ctx["agents"]["dana"], {"minutes": 10},
                             subject_kind="post", subject_id=first["id"], note="Summarise the contrast claims.")
        done = deliver(board, answers, request, f"The contrast is log2(B/A) = [1.54]({cited}).")
        writeup_post = done["answer"]
        with Archive(root) as view:
            assert writeup.render_writeup(view, writeup_post)["regeneration_required"] is None
        second = alice.publish("Contrast claims, corrected", f"Corrected ({contrast}).", artifacts=[contrast],
                               claims=[{"text": "log2(B/A) = 1.55.", "status": "supported",
                                        "pointers": [{"kind": "artifact", "id": contrast}]}],
                               supersedes=first["id"], parent=first["id"], request_key="studio-c2")
    response = client(root).get(f"/api/studio/writeups/{writeup_post}")
    assert response.status_code == 200
    flagged = response.json()
    assert flagged["flagged"] and flagged["blocks"]
    [withdrawn] = flagged["regeneration_required"]["claims"]
    assert withdrawn["claim"] == cited and withdrawn["withdrawn_by"] == second["id"]
    assert withdrawn["same_ordinal"] == claim_id(second["id"], 0)
    assert [c["text"] for c in withdrawn["replacement_claims"]] == ["log2(B/A) = 1.55."]
    prefill = flagged["regeneration_required"]["commission"]
    assert prefill["task_type"] == "writing" and prefill["subject_id"] == writeup_post and cited in prefill["note"]
    overview = client(root).get("/api/studio").json()
    item = next(i for i in overview["groups"]["writeups"] if i["request"] == request["id"])
    assert item["state"] == "completed" and item["outputs"][0]["flagged"]
    assert [f["post"] for f in overview["regeneration_flags"]] == [writeup_post]
    with Community(root) as board:  # a person commissions the regeneration with the prefilled scope
        again = commission(board, human(ctx), prefill["task_type"], ctx["agents"]["dana"], {"minutes": 10},
                           subject_kind=prefill["subject_kind"], subject_id=prefill["subject_id"], note=prefill["note"])
    assert again["task_type"] == "writing" and again["state"] == "pending"


# ---- M6.2 reviews as marks ----------------------------------------------------------------------

def test_agent_review_becomes_idempotent_marks_by_the_reviewer(demo):
    root, ctx = demo
    correction, contrast = ctx["posts"]["correction"], ctx["artifacts"]["contrast"]
    block = {"review": {"target": correction, "verdicts": [
        {"criterion": "claims_traceable_to_pointers", "verdict": "supported", "pointers": [contrast], "note": "row B_vs_A"},
        {"criterion": "methods_reproducible_from_receipts", "verdict": "not_supported",
         "pointers": [f"{contrast}#row B_vs_A"], "note": "placeholder script"},
        {"criterion": "limitations_stated", "verdict": "partially_supported", "pointers": [], "note": "no pointer"},
        {"criterion": "scope_matches_evidence", "verdict": "not_assessable", "pointers": [], "note": "n=4"}]}}
    with Community(root) as board, scripted_runtime(root) as (_, answers):
        request = commission(board, human(ctx), "review", ctx["agents"]["bob"], {"minutes": 10},
                             subject_kind="post", subject_id=correction, note="Check the correction.")
        done = deliver(board, answers, request, "Review.\n```review\n" + json.dumps(block) + "\n```")
        marks = board.rows("SELECT * FROM mark WHERE participant=? ORDER BY created", (ctx["agents"]["bob"],))
        assert [(m["target_id"], m["kind"]) for m in marks] == [(correction, "checked_source"), (correction, "disputed")]
        assert marks[1]["note"].startswith("Review criterion methods_reproducible_from_receipts: not_supported.")
        assert json.loads(marks[1]["pointers"]) == [{"kind": "locator", "id": contrast, "locator": "row B_vs_A"}]
        followup = json.loads((root / board.one("SELECT path FROM attempt WHERE request=?", (request["id"],))["path"]
                               / "studio-followup.json").read_text())
        assert {s["criterion"] for s in followup["review"]["skipped"]} == {"limitations_stated", "scope_matches_evidence"}
        before = len(events(board, "mark_recorded"))
        again = studio.record_review_marks(board, done["answer"], actor="operator")
        assert [m["created_now"] for m in again["marks"]] == [False, False] and len(events(board, "mark_recorded")) == before
    listed = client(root).get("/api/marks", params={"target_kind": "post", "target_id": correction}).json()
    assert {m["participant_name"] for m in listed["items"]} >= {"bob"}


def test_person_submits_a_structured_review_from_the_ui(demo):
    root, ctx = demo
    http = client(root, local_user="rhea")
    claim = ctx["claims"]["current"]
    verdict = {"criterion": "value matches the table", "verdict": "reproduced", "note": "Recomputed from the means.",
               "pointers": [{"kind": "artifact", "id": ctx["artifacts"]["measurement"]}]}
    response = http.post("/api/studio/reviews", headers=WRITE, json={
        "target_kind": "claim", "target_id": claim, "summary": "Checked.",
        "verdicts": [verdict, {"criterion": "scope", "verdict": "not_assessable", "note": "", "pointers": []}]})
    assert response.status_code == 200, response.text
    made = response.json()
    assert [m["kind"] for m in made["marks"]] == ["reproduced"] and made["marks"][0]["target_id"] == claim
    with Community(root) as board:
        shown = board.show(made["post"])
        assert shown["content"]["kind"] == "review" and shown["parent"] == ctx["claims"]["correction"]
        value, _ = __import__("daw.commons.tasks", fromlist=["review_block"]).review_block(shown["content"]["body"])
        assert value["review"]["target"] == claim
        assert board.agent(made["marks"][0]["participant"])["name"] == "rhea"
    unpointed = http.post("/api/studio/reviews", headers=WRITE, json={
        "target_kind": "claim", "target_id": claim, "verdicts": [{**verdict, "pointers": []}]})
    assert unpointed.status_code == 400 and unpointed.json()["error"] == "review_pointer_required"
    assert http.post("/api/studio/reviews", json={"target_kind": "claim", "target_id": claim,
                                                  "verdicts": [verdict]}).status_code == 403  # CSRF header required


# ---- M6.3 replications ---------------------------------------------------------------------------

REPLICATE = '''import os
from daw.artifacts import artifact_info, register_artifact
from daw.catalog import Workspace
from daw.substrate_models import ArtifactRegistration, Derivation
from daw.work import create_question
ws = Workspace(os.environ["BIO_WORKSPACE"])
with ws.writer():
    manifest = artifact_info(ws, {original!r})["manifest"]
    question = create_question(ws, "Replicate")["question"]
    open("replicated.tsv", "w").write({content!r})
    register_artifact(ws, "replicated.tsv", ArtifactRegistration(title="Replication", summary="re-executed",
        output_role=manifest["output_role"], derivation=Derivation(**manifest["derivation"])), question=question)
ws.close()
'''


@pytest.mark.parametrize("identical", [True, False])
def test_replication_confirms_bytes_or_posts_a_mismatch_correction(demo, identical, monkeypatch):
    """Milestone 3 offline: a person commissions a replication of one derivation to another agent; the scripted
    harness re-registers the same derivation in that agent's workspace; bytes are confirmed or corrected."""
    root, ctx = demo
    original = ctx["artifacts"]["contrast"]
    with Community(root) as board, scripted_runtime(root) as (_, answers):
        blob = board.library.one("SELECT output_blob FROM artifact WHERE id=?", (original,))["output_blob"]
        content = board.library.blob_path(blob).read_text() if identical else "contrast\tlog2_ratio\nB_vs_A\t1.60\n"
        request = commission(board, human(ctx), "replication", ctx["agents"]["bob"], {"minutes": 10},
                             subject_kind="artifact", subject_id=original, note="Re-execute the contrast.")
        deliver(board, answers, request, "Re-executed.", REPLICATE.format(original=original, content=content))
        [check] = events(board, "replication_checked")
        [result] = check["results"]
        if identical:
            assert result["outcome"] == "byte_identical"
            mark = board.one("SELECT * FROM mark WHERE id=?", (result["mark"],))
            assert (mark["participant"], mark["target_kind"], mark["target_id"], mark["kind"]) == (
                ctx["agents"]["bob"], "artifact", original, "reproduced") and blob in mark["note"]
            reply = board.show(result["post"])
            assert reply["author"] == ctx["agents"]["bob"] and reply["parent"] == ctx["posts"]["finding"]
            assert reply["content"]["kind"] == "replication_confirmed"
        else:
            assert result["outcome"] == "bytes_differ"
            correction = board.show(result["post"])
            replica = correction["content"]["evidence"]["replication"]["different"][0]
            assert correction["author"] == ctx["agents"]["bob"] and correction["parent"] == ctx["posts"]["finding"]
            assert correction["content"]["kind"] == "replication_mismatch"
            assert blob in correction["content"]["body"] and replica["output_sha256"] in correction["content"]["body"]
            assert replica["artifact"] in correction["content"]["evidence"]["artifacts"]  # published: bytes verifiable
            assert board.library.one("SELECT id FROM artifact WHERE id=?", (replica["artifact"],))
            assert not board.rows("SELECT * FROM mark WHERE participant=?", (ctx["agents"]["bob"],))
    # Operator re-check (CLI) is idempotent: no new marks, posts or events.
    from typer.testing import CliRunner

    from daw.commons.cli import app
    monkeypatch.delenv("BIO_AGENT", raising=False)
    result = CliRunner().invoke(app, ["--root", str(root), "replication", "check", request["id"]])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["results"][0]["post"] == check["results"][0]["post"]
    with Community(root) as board:
        assert len(events(board, "replication_checked")) == 1
        with pytest.raises(DawError, match="not_a_replication_request"):
            studio.replication_check(board, ctx["requests"]["brief"])
        with pytest.raises(DawError, match="permission_denied"):
            studio.replication_check(board, request["id"], actor=human(ctx))


# ---- M6.4 digests ----------------------------------------------------------------------------------

def test_digest_skeleton_is_deterministic_and_scoped(demo):
    root, ctx = demo
    with Archive(root) as view:
        whole = studio.digest_skeleton(view, {}, None, None)
        assert whole == studio.digest_skeleton(view, {}, None, None)
        assert ctx["posts"]["correction"] in {p["id"] for p in whole["sections"]["corrections"]}
        assert ctx["claims"]["withdrawn"] in {c["id"] for c in whole["sections"]["withdrawn_claims"]}
        assert f"[{ctx['posts']['correction']}]" in whole["markdown"]
        scoped = studio.digest_skeleton(view, {"questions": [ctx["questions"]["dana"]]}, None, None)
        assert {p["id"] for p in scoped["sections"]["posts"]} == {ctx["posts"]["gap"]}
        assert {i["question"] for i in scoped["sections"]["open_items"]} <= {ctx["questions"]["dana"]}
        empty = studio.digest_skeleton(view, {}, "2099-01-01T00:00:00+00:00", None)
        assert empty["counts"]["posts"] == 0 and "- none in this period" in empty["markdown"]
        with pytest.raises(DawError, match="invalid_digest_scope"):
            studio.digest_skeleton(view, {"topics": ["x"]}, None, None)
    query = client(root).get("/api/studio/digest-skeleton", params={"query": "normalization"}).json()
    assert ctx["posts"]["reply"] in {p["id"] for p in query["sections"]["posts"]}


def test_standing_digest_tick_creates_requests_attributed_to_the_person(demo):
    root, ctx = demo
    person = human(ctx)
    http = client(root, local_user="mira")
    made = http.post("/api/studio/digests", headers=WRITE, json={
        "target": "dana", "scope": {"questions": [ctx["questions"]["alice"]]}, "cadence": "weekly",
        "budget": {"minutes": 15}, "start": "2026-01-01T00:00:00+00:00"})
    assert made.status_code == 200, made.text
    schedule = made.json()
    assert schedule["person"] == person and schedule["interval_days"] == 7
    with Community(root) as board:
        assert studio.digest_tick(board, at="2025-12-31T00:00:00+00:00")["ticked"] == []  # not due yet
        with pytest.raises(DawError, match="permission_denied"):
            studio.digest_tick(board, person)
        [ticked] = studio.digest_tick(board, at="2026-01-02T00:00:00+00:00")["ticked"]
        request = board.one("SELECT * FROM request WHERE id=?", (ticked["request"],))
        post = board.show(request["post"])
        assert post["author"] == person and request["task_type"] == "digest" and request["target"] == ctx["agents"]["dana"]
        digest = post["content"]["evidence"]["digest"]
        assert digest["schedule"] == schedule["id"] and digest["since"] == "2025-12-25T00:00:00+00:00"
        assert digest["until"] == "2026-01-02T00:00:00+00:00" and "# Digest skeleton" in post["content"]["body"]
        assert board.library.one("SELECT sha256 FROM blob WHERE sha256=?", (digest["skeleton_blob"],))
        assert studio.digest_tick(board, at="2026-01-03T00:00:00+00:00")["ticked"] == []
        [second] = studio.digest_tick(board, at="2026-01-09T00:00:00+00:00")["ticked"]
        assert second["since"] == "2026-01-02T00:00:00+00:00"
        studio.cancel_digest(board, person, schedule["id"])
        assert studio.digest_tick(board, at="2026-02-01T00:00:00+00:00")["ticked"] == []
        with pytest.raises(DawError, match="invalid_digest_cadence"):
            studio.schedule_digest(board, person, "dana", {}, "hourly", {"minutes": 5})
    once = http.post("/api/studio/digests/commission", headers=WRITE, json={
        "target": "dana", "scope": {"query": "contrast"}, "budget": {"minutes": 5}})
    assert once.status_code == 200 and once.json()["task_type"] == "digest"


# ---- M6.5 + M8.4 export and federation ----------------------------------------------------------------

def _hostile_post(root, ctx):
    with Community(root) as board:
        with board.writer(), board.library.writer():
            return board._post(human(ctx), "<script>alert(1)</script>",
                               "<img src=x onerror=alert(1)> [click](javascript:alert(1)) <b>bold</b>",
                               parent=ctx["posts"]["finding"])


def test_export_is_deterministic_static_escaped_and_public_only(demo, tmp_path):
    root, ctx = demo
    hostile = _hostile_post(root, ctx)
    with Community(root) as board:
        hide(board, "operator", ctx["posts"]["reply"], "synthetic moderation test")
        first = export.export_snapshot(board, "operator", "board", output=tmp_path / "one")
        second = export.export_snapshot(board, human(ctx), "board", output=tmp_path / "two")
        assert first["snapshot"] == second["snapshot"]  # same archive state, even after the export events
        with pytest.raises(DawError, match="permission_denied"):
            export.export_snapshot(board, ctx["agents"]["alice"], "board", output=tmp_path / "three")
        with pytest.raises(DawError, match="export_output_not_empty"):
            export.export_snapshot(board, "operator", "board", output=tmp_path / "one")
    one, two = tmp_path / "one", tmp_path / "two"
    manifest = json.loads((one / "snapshot.json").read_text())
    assert hashlib.sha256((one / "snapshot.json").read_bytes()).hexdigest() == first["snapshot"]
    assert (one / "snapshot.id").read_text().strip() == first["snapshot"]
    for entry in manifest["files"]:
        data = (one / entry["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"] and data == (two / entry["path"]).read_bytes()
    paths = {e["path"] for e in manifest["files"]}
    assert {"index.html", "map.html", "map.json", "style.css", f"posts/{ctx['posts']['correction']}.html",
            f"artifacts/{ctx['artifacts']['contrast']}.html", f"artifacts/{ctx['artifacts']['contrast']}/alice-contrast.tsv",
            f"artifacts/{ctx['artifacts']['contrast']}/manifest.json"} <= paths
    assert any(p.startswith("notebooks/") and p.endswith("LABBOOK.md") for p in paths)
    pages = [(one / p).read_text() for p in paths if p.endswith(".html")]
    assert all("<script" not in page.lower() and 'href="javascript:' not in page and "<img src=x" not in page
               for page in pages)
    hostile_page = (one / f"posts/{hostile}.html").read_text()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in hostile_page and "&lt;b&gt;bold&lt;/b&gt;" in hostile_page
    hidden_page = (one / f"posts/{ctx['posts']['reply']}.html").read_text()
    assert "synthetic moderation test" in hidden_page and "1.31" not in hidden_page
    assert "Normalization shrinks" not in "".join(pages) + (one / "map.json").read_text()
    # Private workspace records never leave: only library artifacts, no server paths, map edges from board/library.
    figure = ctx["observatory_map"]["figure"]
    assert not any(figure in p for p in paths)
    assert str(root) not in "".join(pages) + (one / "map.json").read_text()
    graph = json.loads((one / "map.json").read_text())
    assert graph["edges"] and all(r["store"] in ("board", "library") for e in graph["edges"] for r in e["records"])
    assert "<svg" in (one / "map.html").read_text()


def test_thread_and_question_exports_and_api_export(demo, tmp_path):
    root, ctx = demo
    with Community(root) as board:
        thread = export.export_snapshot(board, "operator", "thread", ctx["posts"]["correction"], tmp_path / "thread")
        question = export.export_snapshot(board, "operator", "question",
                                          f"alice/{ctx['questions']['alice']}", tmp_path / "question")
    listed = {e["path"] for e in json.loads((tmp_path / "thread" / "snapshot.json").read_text())["files"]}
    assert f"posts/{ctx['posts']['finding']}.html" in listed and f"posts/{ctx['posts']['gap']}.html" not in listed
    assert thread["scope"] == {"kind": "thread", "root": ctx["posts"]["finding"]}
    assert question["scope"]["question"] == ctx["questions"]["alice"] and question["counts"]["notebooks"] >= 1
    http = client(root, local_user="rhea")
    made = http.post("/api/exports", headers=WRITE, json={"scope": "thread", "id": ctx["posts"]["correction"]})
    assert made.status_code == 200, made.text
    assert made.json()["snapshot"] == thread["snapshot"] and made.json()["location"] == f"exports/{thread['snapshot']}"
    assert (root / "exports" / thread["snapshot"] / "snapshot.json").is_file()
    assert http.post("/api/exports", headers=WRITE, json={"scope": "thread", "id": "post_nope"}).status_code == 404
    recorded = http.get("/api/exports").json()["exports"]
    assert recorded[0]["snapshot"] == thread["snapshot"] and recorded[0]["actor"]


def test_federation_import_verifies_hashes_and_serves_foreign_files_read_only(demo, tmp_path):
    root, ctx = demo
    with Community(root) as board:
        made = export.export_snapshot(board, "operator", "thread", ctx["posts"]["finding"], tmp_path / "snap")
    source = tmp_path / "snap"
    # Tampering is rejected: a changed byte, an extra file, a link, a changed manifest, a wrong expected ID.
    for name, damage, reason in [
            ("byte", lambda d: (d / "style.css").write_text("body{}"), "snapshot_hash_mismatch"),
            ("extra", lambda d: (d / "extra.html").write_text("x"), "snapshot_unlisted_file"),
            ("link", lambda d: (d / "evil").symlink_to("/etc/passwd"), "snapshot_link_rejected"),
            ("manifest", lambda d: (d / "snapshot.json").write_text(
                (d / "snapshot.json").read_text().replace('"posts":', '"posts" :')), "invalid_snapshot_manifest"),
            ("missing", lambda d: (d / "index.html").unlink(), "snapshot_file_missing")]:
        copy = tmp_path / f"tampered-{name}"
        shutil.copytree(source, copy, symlinks=True)
        damage(copy)
        with pytest.raises(DawError, match=reason):
            export.import_snapshot(root, copy)
    with pytest.raises(DawError, match="snapshot_id_mismatch"):
        export.import_snapshot(root, source, expect="0" * 64)
    assert not (root / "federation" / made["snapshot"]).exists()
    from typer.testing import CliRunner

    from daw.commons.cli import app
    result = CliRunner().invoke(app, ["--root", str(root), "federation", "import", str(source), "--expect", made["snapshot"]])
    assert result.exit_code == 0, result.output
    imported = json.loads(result.output)
    assert imported["snapshot"] == made["snapshot"] and imported["foreign"] and not imported["already_imported"]
    stored = root / "federation" / made["snapshot"]
    assert not (stored / "index.html").stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    assert export.import_snapshot(root, source)["already_imported"]
    http = client(root)
    listing = http.get("/api/federation").json()
    assert [s["snapshot"] for s in listing["snapshots"]] == [made["snapshot"]] and listing["foreign"]
    info = http.get(f"/api/federation/{made['snapshot']}", params={"verify": True}).json()
    assert info["verified"] and info["content_is_untrusted_data"]
    page = http.get(f"/api/federation/{made['snapshot']}/files/index.html")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/plain")
    assert page.headers["x-colloquy-foreign-snapshot"] == made["snapshot"] and page.headers["x-content-type-options"] == "nosniff"
    assert http.get(f"/api/federation/{made['snapshot']}/files/../board.sqlite").status_code == 404
    assert http.get(f"/api/federation/{made['snapshot']}/files/nope.html").status_code == 404
    with Archive(root) as view:  # nothing foreign entered the board
        assert not view.rows("SELECT * FROM event WHERE body LIKE ?", (f"%{made['snapshot']}%",)) or all(
            r["kind"] == "snapshot_exported" for r in view.rows("SELECT kind FROM event WHERE body LIKE ?",
                                                                 (f"%{made['snapshot']}%",)))
    assert canonical(json.loads((stored / "snapshot.json").read_text())) == (stored / "snapshot.json").read_bytes()


# ---- Screens' data and CLI ---------------------------------------------------------------------------------

def test_studio_demo_overview_groups_outputs_by_type(demo):
    root, ctx = demo
    made = studio_demo.apply(root)
    assert studio_demo.apply(root) == made  # applied once
    overview = client(root).get("/api/studio").json()
    groups = overview["groups"]
    assert {k: len(v) for k, v in groups.items()} == {"writeups": 3, "reviews": 1, "replications": 1, "digests": 1}
    statuses = {o["post"]: o["status"] for i in groups["writeups"] for o in i["outputs"]}
    assert statuses == {made["writeup"]: "rendered", made["flagged"]: "rendered", made["refused"]: "refused"}
    assert [f["post"] for f in overview["regeneration_flags"]] == [made["flagged"]]
    assert [m["kind"] for m in groups["reviews"][0]["review"]["marks"]] == ["checked_source", "disputed", "checked_source"]
    assert groups["replications"][0]["replication"]["followup"][0]["outcome"] == "byte_identical"
    assert groups["digests"][0]["digest"]["schedule"] == made["digest_schedule"]
    assert overview["digest_schedules"][0]["person_name"] == "mira"
    assert all(g["completed"] == len(groups[name]) for name, g in overview["states"].items())


def test_writeup_check_cli_exit_codes(demo, monkeypatch):
    from typer.testing import CliRunner

    from daw.commons.cli import app
    root, ctx = demo
    made = studio_demo.apply(root)
    runner = CliRunner()
    ok = runner.invoke(app, ["--root", str(root), "writeup", "check", made["writeup"]])
    assert ok.exit_code == 0 and json.loads(ok.output)["status"] == "rendered"
    refused = runner.invoke(app, ["--root", str(root), "writeup", "check", made["refused"]])
    assert refused.exit_code == 1 and [p["text"] for p in json.loads(refused.output)["problems"]] == ["1.31", "15%"]
    skeleton = runner.invoke(app, ["--root", str(root), "digest", "skeleton", "--markdown"])
    assert skeleton.exit_code == 0 and skeleton.output.startswith("# Digest skeleton")


def test_regeneration_flags_superseded_posts_and_artifacts_not_only_withdrawn_claims(demo):
    """v2 C8: a write-up that cites a superseded post (and none of its later versions), or an artifact that only
    superseded publications name, is flagged for regeneration; citing the replacement too clears the post flag."""
    root, ctx = demo
    with Community(root) as board:
        alice = Researcher(board, board.agent(ctx["agents"]["alice"]), root / "demo-harness" / "inputs")
        measurement = ctx["artifacts"]["measurement"]
        interim = alice.register(ctx["questions"]["alice"], "interim.tsv", "condition\tvalue\nA\t1\n",
                                 title="Interim table", summary="An interim table.", role="interim-table",
                                 inputs=[{"blob": board.library.one("SELECT output_blob FROM artifact WHERE id=?",
                                                                    (measurement,))["output_blob"],
                                          "source_identity": measurement}], parameters={"stage": "interim"})["artifact"]
        first = alice.publish("Interim note", f"Interim values ({interim}).", artifacts=[interim],
                              request_key="studio-interim-1")
        second = alice.publish("Interim note, corrected", "The interim table was mislabelled; see the correction.",
                               supersedes=first["id"], parent=first["id"], request_key="studio-interim-2")
        stale = board.publish(ctx["agents"]["dana"], "Summary",
                              f"See [the interim note]({first['id']}) and [the interim table]({interim}).")
        acknowledged = board.publish(ctx["agents"]["dana"], "Summary, with the correction",
                                     f"See [the interim note]({first['id']}), corrected in [the correction]"
                                     f"({second['id']}), and [the contrast table]({ctx['artifacts']['contrast']}).")
    with Archive(root) as view:
        flag = writeup.render_writeup(view, stale["id"], with_map=False)["regeneration_required"]
        assert flag["claims"] == []
        assert [(p["post"], p["superseded_by"]) for p in flag["posts"]] == [(first["id"], second["id"])]
        assert [(a["artifact"], a["superseded_posts"], a["replacements"]) for a in flag["artifacts"]] == \
            [(interim, [first["id"]], [second["id"]])]
        assert first["id"] in flag["commission"]["note"] and interim in flag["commission"]["note"]
        assert "cites superseded posts" in flag["note"]
        # Citing a later version clears the post flag; an artifact a current publication still names is not flagged
        # (the contrast table is named by the demo's current correction).
        assert writeup.render_writeup(view, acknowledged["id"], with_map=False)["regeneration_required"] is None
    flagged = client(root).get(f"/api/studio/writeups/{stale['id']}").json()
    assert flagged["flagged"] and flagged["regeneration_required"]["artifacts"][0]["artifact"] == interim
