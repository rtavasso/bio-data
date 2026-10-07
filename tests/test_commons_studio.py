"""Studio (M6.1–M6.5, M8.4, Flow B step 5): write-up renderer, regeneration flags, reviews as marks,
replication confirmation and mismatch, digests, static export and read-only federation. Offline."""
import hashlib
import json
import shutil
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daw.artifacts import artifact_info
from daw.commons import checks, export, locators, studio, studio_demo, writeup
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
    # Spec v2 C5: heading numbers and letter-glued decimals count; spelled-out small integers and unicode
    # fractions are detected. Integers glued to letters stay identifier characters (PMP22, IL-6, chr1).
    source = (f"# 2.1 Results for PMP22\n\nBy Ada, 2026-01-05 10:30 UTC\n\n"
              f"1. IL-6, log2, GSE1234, chr1, H3K27me3, B_vs_A, the 3′ UTR, measured-zero and {P} carry no numbers.\n"
              f"2. Values 12%, 1e-5, 3.2×10^-4, 3.2×10⁻⁴, 3:1, 1/3, 1,000 and -0.5 are numbers.\n"
              "3. Glued values count: v1.2, FC1.54, x2 and chr10:49316968.\n"
              "4. Spelled: three donors, twenty-one wells, a dozen runs and half a dozen arms; no one and each one "
              "are not counts; two-sided tests are methods; seven-fold is a count.\n"
              "5. Fractions: ½, 1½ and 1⁄2.\n\n"
              "Dates outside a byline count: 2026-01-05.\n")
    found = numbers(source)
    assert [t for t, _ in found] == [
        "2.1", "12%", "1e-5", "3.2×10^-4", "3.2×10⁻⁴", "3:1", "1/3", "1,000", "-0.5", "1.2", "1.54", "2", "49316968",
        "three", "twenty-one", "a dozen", "half a dozen", "seven", "½", "1½", "1⁄2", "2026", "01", "05"]
    assert all(scope == "none" for _, scope in found)
    assert numbers("A 5mg dose on the 2nd day.") == [("5", "none"), ("2", "none")]  # digits before letters count
    values = {t: locators.parse_number(t)["value"] for t, _ in found if t not in ("2026", "01", "05")}
    assert values["twenty-one"] == 21 and values["half a dozen"] == 6 and values["1½"] == 1.5
    assert values["3.2×10⁻⁴"] == pytest.approx(3.2e-4) and values["1/3"] == pytest.approx(1 / 3)


def test_coverage_is_number_granular():
    # A pointer covers the numbers in its own link text, or the one number right before its bracket in the same
    # clause. Sentence-level coverage is gone: two numbers and one pointer leave the other number unpointed.
    source = (f"The contrast is [1.54]({C}). Means were 11.0 and 32.0 [{A}]. Approx. 5 samples e.g. in Fig. 2 "
              f"[{C}].\nThe value is 7. [{A}] Context only: [4 samples]({P}). Ratio 1.54, p = 0.003 [{C}]. "
              f"Fold 2 [{A}] [{C}]. Cell 1.54 [{A}#row=B_vs_A;col=log2_ratio] and key [0.5]({A}#key=stats.fit[0]).\n\n"
              f"| a | b |\n|---|---|\n| x | 3 |\n| y 8 [{C}] | 9 |\n\n![2 panels]({A})\n\n"
              f"```\nvalue 8 {A}\nother 6, {A}\n```\n")
    found = numbers(source)
    # An artifact pointer without a locator (a citation, a figure, an identifier in code) has scope text (v3 B6).
    assert found == [("1.54", "claim"), ("11.0", "none"), ("32.0", "text"), ("5", "none"), ("2", "claim"),
                     ("7", "text"), ("4", "none"), ("1.54", "none"), ("0.003", "claim"), ("2", "claim"),
                     ("1.54", "cell"), ("0.5", "cell"), ("3", "none"), ("8", "claim"), ("9", "none"),
                     ("2", "text"), ("8", "text"), ("6", "none")]
    blocks = writeup.parse(source)
    sentences = blocks[0]["sentences"]
    assert len(sentences) == 8 and sentences[3]["pointers"] == [A]  # a citation after the period belongs to it
    context = next(n for _, _, n in writeup.all_numbers(blocks) if n["text"] == "4")
    assert context["reason"].startswith("a post pointer gives context only")
    cell = next(n for _, _, n in writeup.all_numbers(blocks) if n["scope"] == "cell")
    assert cell["pointers"] == [{"id": A, "kind": "artifact", "locator": "row=B_vs_A;col=log2_ratio", "form": "citation"}]


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
    assert first["context"] == "The marker rose 3-fold." and first["context_start"] == 0
    # A refused write-up is never served: no blocks, no source, a placeholder (spec v2 C5).
    assert "blocks" not in refused and "source" not in refused and refused["placeholder"].startswith("This write-up")
    assert refused["verdict"]["source"] == "computed"  # not delivered as a writing task: checked at read time


def test_rendered_writeup_is_three_clicks_from_bytes_with_the_cited_subgraph(demo):
    root, ctx = demo
    claim = ctx["claims"]["current"]
    figure = ctx["observatory_map"]["figure"]
    measurement = ctx["artifacts"]["measurement"]
    body = (f"# Corrected contrast\n\nBy dana, 2026-01-05\n\nThe ratio is [1.54]({claim}). Means were "
            f"[11.0]({measurement}#row=A;col=mean) and [32.0]({measurement}#row=B;col=mean).\n\n"
            f"![Figure 1: synthetic figure]({figure})\n\nContext: [the correction]({ctx['claims']['correction']}).")
    with Community(root) as board:
        post = _writeup_post(board, ctx["agents"]["dana"], body)
    http = client(root)
    rendered = http.get(f"/api/studio/writeups/{post}").json()
    assert rendered["status"] == "rendered"
    # B14: the measurement's producing question published posts later superseded (the finding and the structured
    # summary); citing the corrections does not clear an artifact flag.
    flag = rendered["regeneration_required"]
    assert flag["claims"] == [] and flag["posts"] == []
    assert [(a["artifact"], set(a["superseded_posts"]), a["relisted_by"]) for a in flag["artifacts"]] == [
        (measurement, {ctx["posts"]["finding"], ctx["claims"]["summary"]}, [])]
    # Every number is pointed; the figure caption's "1" is pointed at a PNG, so it is unverified (shown, not refused).
    assert {k: rendered["stats"][k] for k in ("numbers", "pointed", "verified", "unverified", "unpointed", "units",
                                              "pointers")} == {"numbers": 4, "pointed": 4, "verified": 3,
                                                               "unverified": 1, "unpointed": 0, "units": 6, "pointers": 4}
    assert [(n["text"], n["scope"], n["status"]) for n in rendered["numbers"]] == [
        ("1.54", "claim", "verified"), ("11.0", "cell", "verified"), ("32.0", "cell", "verified"),
        ("1", "text", "unverified")]
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


# ---- Spec v2 C5, V1, V2: one checker for every rendering, value-in-record pointers ------------------------

def _writing(root, ctx, text, *, task_type="writing", target="dana"):
    """Commission a writing (or digest) task and deliver `text` through the runtime (scripted harness)."""
    with Community(root) as board, scripted_runtime(root) as (_, answers):
        request = commission(board, human(ctx), task_type, ctx["agents"][target], {"minutes": 10},
                             subject_kind="post", subject_id=ctx["claims"]["correction"], note="Spec v2 checker test.")
        done = deliver(board, answers, request, text)
        return done, events(board, "writeup_check")


def test_unpointed_number_is_a_placeholder_on_post_search_studio_and_export(demo, tmp_path):
    """C5: the verdict is recorded at delivery; a refused write-up completes its request but every surface serves a
    placeholder. A sentence with two numbers and one pointer refuses the second."""
    root, ctx = demo
    claim = ctx["claims"]["current"]
    text = f"Zebrafinch summary: the log2 ratio is [1.54]({claim}) across 4 samples."
    done, recorded = _writing(root, ctx, text)
    post = done["answer"]
    assert done["state"] == "completed" and post
    [check] = [r for r in recorded if r["post"] == post]
    assert check["status"] == "refused" and check["task_type"] == "writing" and check["request"] == done["id"]
    assert [(n["text"], n["status"], n["offset"]) for n in check["numbers"]] == [
        ("1.54", "verified", text.index("1.54")), ("4", "unpointed", text.index("4 samples"))]
    assert [(p["kind"], p["text"], p["line"]) for p in check["problems"]] == [("unpointed_number", "4", 1)]
    http = client(root)
    with Archive(root) as view:  # the verdict blob in the library is the full record
        body = checks.verdict_body(view, check)
    assert body["status"] == "refused" and body["post"] == post and body["body_blob"] == check["body_blob"]
    # /post/:id read model: placeholder, no content, no numbers; the verdict's locations are listed.
    shown = http.get(f"/api/posts/{post}").json()
    assert shown["content"] is None and shown["numbers"] == [] and shown["withheld"]["status"] == "refused"
    assert shown["withheld"]["title"] == checks.PLACEHOLDER_TITLE and shown["withheld"]["problems"][0]["text"] == "4"
    # Thread and listing cards, and search snippets, show the placeholder.
    tree = http.get(f"/api/threads/{post}").json()["tree"]

    def walk(node):
        yield node
        for child in node["children"] + node["corrections"]:
            yield from walk(child)
    node = next(n for n in walk(tree) if n["id"] == post)
    assert node["title"] == checks.PLACEHOLDER_TITLE and "Zebrafinch" not in json.dumps(tree)
    listing = http.get("/api/posts", params={"kind": "answer", "full": True}).json()
    assert "Zebrafinch" not in json.dumps(listing)
    found = http.get("/api/posts", params={"q": "Zebrafinch"}).json()
    hits = [h for item in found["items"] for h in item.get("hits", []) if h["post"] == post]
    assert hits and all("Zebrafinch" not in (h["snippet"] or "") for h in hits) and "withheld" in hits[0]["snippet"]
    assert "Zebrafinch" not in json.dumps(found["items"])
    # Studio: 422 with the recorded verdict and a placeholder; the source is not served.
    studio_view = http.get(f"/api/studio/writeups/{post}")
    assert studio_view.status_code == 422
    refused = studio_view.json()
    assert refused["verdict"]["source"] == "recorded" and "source" not in refused and "blocks" not in refused
    assert [p["text"] for p in refused["problems"] if p["kind"] == "unpointed_number"] == ["4"]
    overview = http.get("/api/studio").json()
    item = next(i for i in overview["groups"]["writeups"] if i["request"] == done["id"])
    assert item["outputs"][0]["status"] == "refused" and item["outputs"][0]["title"] == checks.PLACEHOLDER_TITLE
    assert item["answer"]["title"] == checks.PLACEHOLDER_TITLE and "Zebrafinch" not in json.dumps(overview)
    # The evidence map labels it with the placeholder and its node record has no excerpt.
    node = http.get(f"/api/map/node/{post}").json()["record"]
    assert node["title"] == checks.PLACEHOLDER_TITLE and node["excerpt"] is None
    mapped = next(n for n in http.get("/api/map", params={"limit": 10000}).json()["nodes"] if n["id"] == post)
    assert mapped["label"] == checks.PLACEHOLDER_TITLE and mapped["withheld"]
    # Digests that quote it see the placeholder.
    with Archive(root) as view:
        skeleton = studio.digest_skeleton(view, {}, None, None)
    quoted = next(p for p in skeleton["sections"]["posts"] if p["id"] == post)
    assert quoted["title"] == checks.PLACEHOLDER_TITLE and quoted["withheld"] and "Zebrafinch" not in skeleton["markdown"]
    # Export: the same verdict in the snapshot, a placeholder page.
    with Community(root) as board:
        export.export_snapshot(board, "operator", "board", output=tmp_path / "site")
    site = tmp_path / "site"
    page = (site / f"posts/{post}.html").read_text()
    assert checks.PLACEHOLDER_TITLE in page and "Zebrafinch" not in page and "across 4 samples" not in page
    listed = {e["path"] for e in json.loads((site / "snapshot.json").read_text())["files"]}
    assert f"checks/{post}.json" in listed
    exported = json.loads((site / f"checks/{post}.json").read_text())
    assert exported["status"] == "refused" and exported["verdict"]["source"] == "recorded"
    assert [p["text"] for p in exported["problems"]] == ["4"] and "context" not in exported["problems"][0]
    assert "Zebrafinch" not in "".join(p.read_text() for p in site.rglob("*.html"))


def test_two_numbers_and_one_bracket_refuse_the_number_the_bracket_does_not_follow(demo):
    """C5: the bracket covers the number immediately before it, in its clause; nothing else in the sentence."""
    root, ctx = demo
    claim = ctx["claims"]["current"]
    with Community(root) as board:
        post = _writeup_post(board, ctx["agents"]["dana"], f"In 4 samples the log2 ratio is 1.54 [{claim}].")
        second = _writeup_post(board, ctx["agents"]["dana"], f"The log2 ratio is 1.54 [{claim}] in 4 samples.")
        clause = _writeup_post(board, ctx["agents"]["dana"], f"The log2 ratio is 1.54, in 4 samples [{claim}].")
    with Archive(root) as view:
        for pid, refused in ((post, "4"), (second, "4"), (clause, "1.54")):
            result = writeup.render_writeup(view, pid, with_map=False)
            assert result["status"] == "refused"
            assert [p["text"] for p in result["problems"] if p["kind"] == "unpointed_number"] == [refused]


def test_writing_task_refuses_to_cite_a_claimless_post(demo):
    """V1: a writing task refuses to cite a post without ledger claims; a digest may cite posts as items."""
    root, ctx = demo
    claimless = ctx["posts"]["reply"]
    with Archive(root) as view:
        assert not view.rows("SELECT id FROM claim WHERE post=?", (claimless,))
    text = f"See [the normalization reply]({claimless}) and [the correction]({ctx['claims']['correction']})."
    done, recorded = _writing(root, ctx, text)
    [check] = [r for r in recorded if r["post"] == done["answer"]]
    assert check["status"] == "refused"
    assert [(p["kind"], p["pointer"]) for p in check["problems"]] == [("claimless_post_cited", claimless)]
    digest, recorded = _writing(root, ctx, f"This period: [{claimless}] replied to the finding.", task_type="digest")
    [check] = [r for r in recorded if r["post"] == digest["answer"]]
    assert check["status"] == "rendered" and check["task_type"] == "digest"


def test_writing_task_refuses_to_cite_a_completed_question_without_a_non_gap_frontier_item(demo):
    """v3 G1: like a claimless post, a post publishing a completed question whose only frontier items are retrieval
    gaps cannot be cited by a writing task; once its author records a non-gap item it can."""
    from daw.work import sync_work
    root, ctx = demo
    with Community(root) as board:
        alice = Researcher(board, board.agent(ctx["agents"]["alice"]), root / "demo-harness" / "inputs")
        question = alice.question("Bounded closure audit", "# Research notebook\n\n## Open questions\n")
        alice.gap(question, {"desired_information": "Matched donor table", "why_current_tools_failed": "not indexed",
                             "source_or_format": "supplement"}, "receipt: supplement not indexed\n")
        ws = alice.ws()
        try:
            with ws.writer():
                completed = sync_work(ws, question, status="completed")
        finally:
            ws.close()
        assert [w["code"] for w in completed["warnings"]] == ["completion_without_frontier"]
        claims = [{"text": "The bounded audit found no matched donor table.", "status": "descriptive", "scope": {},
                   "pointers": [{"kind": "artifact", "id": ctx["artifacts"]["contrast"]}]}]
        post = alice.publish("Bounded closure audit", "The audit is complete; the donor table is missing.",
                             question=question, claims=claims, request_key="g1-closure-post")["id"]
    text = f"See [the closure audit]({post})."
    done, recorded = _writing(root, ctx, text)
    [check] = [r for r in recorded if r["post"] == done["answer"]]
    assert check["status"] == "refused"
    assert [(p["kind"], p["pointer"]) for p in check["problems"]] == [("frontierless_question_cited", post)]
    digest, recorded = _writing(root, ctx, f"This period: [{post}] closed an audit.", task_type="digest")
    assert [r for r in recorded if r["post"] == digest["answer"]][0]["status"] == "rendered"
    # The author records the next computable step (the platform never does); the same citation now renders.
    with Community(root) as board:
        alice = Researcher(board, board.agent(ctx["agents"]["alice"]), root / "demo-harness" / "inputs")
        alice.publish("Next step for the closure audit", "Recorded the next step.", question=question,
                      frontier=[{"kind": "next_step", "text": "Re-run the contrast once the donor table is indexed."}],
                      request_key="g1-closure-next")
    done, recorded = _writing(root, ctx, text)
    assert [r for r in recorded if r["post"] == done["answer"]][0]["status"] == "rendered"


def test_cited_cell_value_that_differs_from_the_prose_is_unverified_and_the_artifact_opens_at_it(demo):
    """V2: the checker compares the cited cell with the prose at the declared or implied rounding."""
    root, ctx = demo
    contrast = ctx["artifacts"]["contrast"]
    cell = "row=B_vs_A;col=log2_ratio"
    text = (f"Reported [1.45]({contrast}#{cell}); measured [1.54]({contrast}#{cell}); rounded [1.5]({contrast}#{cell}) "
            f"and [1.5]({contrast}#{cell};round=1); declared [1.5]({contrast}#{cell};round=2); by column number "
            f"[1.54]({contrast}#row=%231;col=%232).")
    done, recorded = _writing(root, ctx, text)
    [check] = [r for r in recorded if r["post"] == done["answer"]]
    assert check["status"] == "rendered"  # unverified numbers are shown, not refused
    assert [n["status"] for n in check["numbers"]] == ["unverified", "verified", "verified", "verified", "unverified",
                                                       "verified"]
    assert all(n["scope"] == "cell" for n in check["numbers"])
    http = client(root)
    rendered = http.get(f"/api/studio/writeups/{done['answer']}").json()
    first = rendered["numbers"][0]
    assert first["pointers"][0]["result"] == "unverified"
    assert first["pointers"][0]["reason"] == "the cited cell holds 1.54, not this number"
    assert first["pointers"][0]["found"] == {"row": 1, "col": 2, "row_key": "B_vs_A", "column": "log2_ratio",
                                             "value": "1.54"}
    assert rendered["stats"]["verified"] == 4 and rendered["stats"]["unverified"] == 2
    # The post page marks them the same way and links each number to the artifact at its locator.
    numbers = http.get(f"/api/posts/{done['answer']}").json()["numbers"]
    assert [n["status"] for n in numbers] == [n["status"] for n in check["numbers"]]
    assert numbers[1]["pointers"][0]["route"] == f"/artifact/{contrast}?locator=row%3DB_vs_A%3Bcol%3Dlog2_ratio"
    # The artifact page opens at the locator: the table window with the cited cell.
    located = http.get(f"/api/artifacts/{contrast}/locate", params={"locator": cell}).json()
    assert located["kind"] == "cell" and located["header"] == ["contrast", "log2_ratio"]
    assert located["target"] == {"row": 1, "col": 2, "row_key": "B_vs_A", "column": "log2_ratio", "value": "1.54"}
    assert located["rows"] == [["B_vs_A", "1.54"]] and located["value"] == 1.54
    assert http.get(f"/api/artifacts/{contrast}/locate", params={"locator": "row=B_vs_A"}).status_code == 400


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


# ---- M6.3 replications (spec v2 C6: replication that executes, under an explicit carve-out) ----------

# A copied-bytes replication: the hook registers the original's output bytes under the same derivation
# without executing anything (what every v1 test and demo did). Modes: `copied` records no receipt;
# `forged_run` runs run_analysis.py (captured in the stream) on a different saved script that copies the
# bytes, so a receipt exists but its producer is not the derivation's code; `handwritten` stores a receipt
# written by hand that claims everything the gate checks (derivation code, inputs, output bytes) with no
# run_analysis.py call in the stream; `printed` adds a terminal call that merely echoes a matching
# analysis_executed line.
COPY_BYTES = '''import hashlib, json, os, pathlib, shlex, subprocess, sys
from daw.artifacts import artifact_info, register_artifact
from daw.catalog import Workspace
from daw.substrate_models import ArtifactRegistration, Derivation
from daw.work import create_question, record_event
trial = pathlib.Path(os.environ.get("HERMES_CWD") or os.getcwd())
mode = {mode!r}
CALLS = []
ws = Workspace(os.environ["BIO_WORKSPACE"])
with ws.writer():
    info = artifact_info(ws, {original!r})
    derivation = info["manifest"]["derivation"]
    question = create_question(ws, "Replicate")
    out = pathlib.Path(question["path"]) / "outputs" / "replicated.tsv"
    receipt = pathlib.Path(question["path"]) / "outputs" / "execution.json"
    if mode == "forged_run":
        script = pathlib.Path(question["path"]) / "scripts" / "copy.py"
        script.write_text("import shutil, sys\\nshutil.copyfile(sys.argv[1], sys.argv[2])\\n")
        argv = [sys.executable, str(trial / ".agents/skills/bio-research/scripts/run_analysis.py"),
                "--receipt", str(receipt), "--output", str(out), "--", sys.executable, str(script),
                str(ws.blob_path(info["output_blob"])), str(out)]
        done = subprocess.run(argv, check=True, capture_output=True, text=True)
        CALLS.append({{"command": shlex.join(argv), "exit_code": 0, "output": done.stdout}})
    else:
        out.write_bytes(ws.blob_path(info["output_blob"]).read_bytes())
    if mode in ("handwritten", "printed"):
        receipt.write_text(json.dumps({{
            "version": 1, "argv": ["python", "scripts/contrast.py"], "producer": str(question["path"]) + "/scripts/x.py",
            "code_sha256": derivation["code"][0], "started": "2026-01-01T00:00:00+00:00",
            "finished": "2026-01-01T00:00:01+00:00", "exit_code": 0, "code_unchanged": True,
            "inputs": [{{"path": "in", "sha256": item["blob"]}} for item in derivation["inputs"]],
            "inputs_unchanged": True, "complete": True,
            "outputs": [{{"path": str(out), "sha256": info["output_blob"], "written": True}}]}}))
    if mode == "printed":
        line = json.dumps({{"event": "analysis_executed", "receipt": str(receipt),
                           "sha256": hashlib.sha256(receipt.read_bytes()).hexdigest()}})
        CALLS.append({{"command": "echo " + shlex.quote(line), "exit_code": 0, "output": line + "\\n"}})
    if mode != "copied":
        record_event(ws, question["question"], "replication_execution",
                     {{"receipt_blob": ws.put_file(receipt, "work"), "receipt_path": "outputs/execution.json",
                       "original": {original!r}}})
    register_artifact(ws, out, ArtifactRegistration(title="Replication", summary="copied bytes",
        output_role=info["manifest"]["output_role"], derivation=Derivation(**derivation)),
        question=question["question"])
ws.close()
'''

def replication_system(board):
    row = board.one("SELECT id,kind FROM agent WHERE name='replication'")
    assert row and row["kind"] == "system"
    return row["id"]


@pytest.fixture
def sandboxed(demo, fake_engine):
    """The demo commons with a configured sandbox (a logging engine stand-in that runs the container's command
    on the host, `conftest.fake_engine`) and the operator's board service, so replications are dispatched as
    sandboxed. It checks the dispatch path and records, never container isolation."""
    from daw.commons.boardservice import BoardService
    root, ctx = demo
    # The scripted harness reads its answers and hooks from COLLOQUY_DEMO_ANSWERS, passed by name.
    (root / "sandbox.toml").write_text('engine = "docker"\nimage = "agent:1"\nenv = ["COLLOQUY_DEMO_ANSWERS"]\n')
    service = BoardService(root)
    service.refresh()
    yield root, ctx
    service.close()


@pytest.mark.parametrize("mode", ["copied", "forged_run", "handwritten", "printed"])
def test_copied_bytes_registration_without_receipt_is_no_execution_receipt(sandboxed, mode):
    """Spec v2 §5 C6, v3 B3: a same-derivation registration of copied bytes confirms nothing, even in a sandboxed
    dispatch and with a hand-written receipt that claims the derivation's code, inputs and output: only a
    run_analysis.py call captured in the delivery's stream, printing the cited receipt's path and sha256, counts."""
    from daw.commons.replication import NOT_CAPTURED
    root, ctx = sandboxed
    original = ctx["artifacts"]["contrast"]
    with Community(root) as board, scripted_runtime(root) as (_, answers):
        request = commission(board, human(ctx), "replication", ctx["agents"]["bob"], {"minutes": 10},
                             subject_kind="artifact", subject_id=original, note="Re-execute the contrast.")
        done = deliver(board, answers, request, "Replicated.", COPY_BYTES.format(original=original, mode=mode))
        assert json.loads((root / "runs" / done["active_run"] / "sandbox.json").read_text())["sandboxed"] is True
        [result] = events(board, "task_outcome")[-1]["criteria"]["replication"]
        assert result["outcome"] == "no_execution_receipt" and not result["identical"] and not result["different"]
        assert result["sandboxed"] is True
        [unreceipted] = result["unreceipted"]
        assert unreceipted["artifact"] == original  # byte-identical copy: the same artifact identity
        problems = [p for c in unreceipted["candidates"] for p in c["problems"]]
        assert problems == {"copied": ["no_replication_execution_recorded"],
                            "forged_run": ["producer_not_a_derivation_code_blob", "inputs_differ"],
                            "handwritten": [NOT_CAPTURED], "printed": [NOT_CAPTURED]}[mode]
        [check] = events(board, "replication_checked")
        assert check["results"][0]["outcome"] == "no_execution_receipt" and "post" not in check["results"][0]
        assert not board.rows("SELECT * FROM mark WHERE target_id=? AND kind='reproduced'", (original,))
        assert not board.rows("SELECT id FROM post WHERE request_key LIKE 'replication-%'")
        assert not [n for n in events(board, "notice_queued") if "Replication" in board.show(n["post"])["content"]["title"]]
    # An outcome recorded before the receipt gate (byte comparison only) is re-gated at check time.
    with Community(root) as board:
        legacy = {**result, "outcome": "byte_identical", "identical": [original], "receipts": {}}
        with board.writer(), board.db:
            board.event("task_outcome", {**events(board, "task_outcome")[-1], "criteria": {"replication": [legacy]}})
        assert studio.replication_check(board, request["id"])["results"][0]["outcome"] == "no_execution_receipt"
        assert not board.rows("SELECT * FROM mark WHERE target_id=? AND kind='reproduced'", (original,))
        if mode in ("handwritten", "printed"):
            # An outcome naming the hand-written receipt is re-checked against the run's stream at check time too.
            [candidate] = unreceipted["candidates"]
            forged = {**legacy, "receipts": {original: {k: candidate[k] for k in ("event", "receipt_blob")}}}
            with board.writer(), board.db:
                board.event("task_outcome", {**events(board, "task_outcome")[-1], "criteria": {"replication": [forged]}})
            assert studio.replication_check(board, request["id"])["results"][0]["outcome"] == "no_execution_receipt"
            assert not board.rows("SELECT * FROM mark WHERE target_id=? AND kind='reproduced'", (original,))


def test_replication_target_that_produced_the_original_is_refused(demo, monkeypatch):
    """Spec v2 §5 C6: commission, promotion, assignment and dispatch refuse the original's producer and forks
    that inherited its workspace."""
    from daw.commons import assignments, replication
    from daw.commons.participation import promote
    root, ctx = demo
    original = ctx["artifacts"]["contrast"]
    with Community(root) as board:
        assert replication.producers(board, [original]) == {ctx["agents"]["alice"]: [original],
                                                            ctx["fork"]: [original]}
        for target in (ctx["agents"]["alice"], ctx["fork"]):
            with pytest.raises(DawError, match="replication_target_produced_original"):
                commission(board, human(ctx), "replication", target, {"minutes": 10}, subject_kind="artifact",
                           subject_id=original, note="Re-execute the contrast.")
            with pytest.raises(DawError, match="replication_target_produced_original"):
                promote(board, human(ctx), "post", ctx["posts"]["finding"], "replication", target, {"minutes": 10})
            with pytest.raises(DawError, match="replication_target_produced_original"):
                assignments.assign(board, "operator", target, "Replicate", "Replicate.", task_type="replication",
                                   evidence={"subject_kind": "artifact", "subject_id": original})
        # Bob fetched the artifact but did not produce it; a review by the producer is still allowed.
        assert commission(board, human(ctx), "replication", ctx["agents"]["bob"], {"minutes": 10}, subject_kind="artifact",
                          subject_id=original, note="Re-execute the contrast.")["state"] == "pending"
        assert commission(board, human(ctx), "review", ctx["agents"]["alice"], {"minutes": 10}, subject_kind="artifact",
                          subject_id=original, note="Check it.")["state"] == "pending"
        # A request queued before the check existed is refused at dispatch, before any state changes.
        monkeypatch.setattr(replication, "refuse_producer", lambda *args: None)
        legacy = assignments.assign(board, "operator", ctx["fork"], "Replicate", "Replicate.", task_type="replication",
                                    evidence={"subject_kind": "artifact", "subject_id": original})
        monkeypatch.undo()
        with scripted_runtime(root) as (executable, _):
            with pytest.raises(DawError, match="replication_target_produced_original"):
                dispatch(board, legacy["id"], executable)
        assert board.one("SELECT state FROM request WHERE id=?", (legacy["id"],))["state"] == "pending"
        assert not board.rows("SELECT id FROM attempt WHERE request=?", (legacy["id"],))
    http = client(root, local_user="mira")
    refused = http.post("/api/commissions", headers=WRITE, json={
        "task_type": "replication", "target": ctx["fork"], "budget": {"minutes": 10}, "subject_kind": "artifact",
        "subject_id": original, "note": "Re-execute."})
    assert refused.status_code == 400 and refused.json()["error"] == "replication_target_produced_original"


def _receipt(root, agent, blob):
    with Archive(root) as view:
        ws = view.workspace(agent)
        return json.loads(ws.blob_path(blob).read_bytes())


@pytest.mark.parametrize("altered", [False, True])
def test_reexecution_through_the_helper_confirms_or_an_altered_script_mismatches(sandboxed, altered, monkeypatch):
    """Spec v2 C6: the scripted harness runs replicate.py in bob's checkout with ./bin/python; it hash-checks the
    saved script and inputs, executes the script through run_analysis.py and registers the output. In a sandboxed
    dispatch, the confirmation (or mismatch) is a platform record by the `replication` participant citing bob's
    receipt, its input hashes and the captured call (v3 B3)."""
    from daw.commons.demo import CODE
    root, ctx = sandboxed
    original, post = ctx["artifacts"]["contrast"], ctx["posts"]["finding"]
    with Community(root) as board, scripted_runtime(root) as (_, answers):
        if altered:
            # Alice's saved script rounds to one decimal while her registered output has two: re-execution differs.
            alice = Researcher(board, board.agent(ctx["agents"]["alice"]), root / "demo-harness" / "inputs")
            meas = board.library.one("SELECT output_blob FROM artifact WHERE id=?", (ctx["artifacts"]["measurement"],))
            bad = alice.register(ctx["questions"]["alice"], "contrast-r2.tsv", "contrast\tlog2_ratio\nB_vs_A\t1.54\n",
                                 title="Contrast (altered script)", summary="log2(B/A).", role="contrast-table-r2",
                                 parameters={"contrast": "B_vs_A"}, code=CODE["contrast.tsv"].replace(":.2f", ":.1f"),
                                 inputs=[{"blob": meas["output_blob"], "source_identity": ctx["artifacts"]["measurement"]}])
            original = bad["artifact"]
            post = alice.publish("Contrast from the altered script", f"log2(B/A) ({original}).", artifacts=[original],
                                 question=ctx["questions"]["alice"], request_key="studio-altered")["id"]
        blob = board.library.one("SELECT output_blob FROM artifact WHERE id=?", (original,))["output_blob"]
        request = commission(board, human(ctx), "replication", ctx["agents"]["bob"], {"minutes": 10},
                             subject_kind="artifact", subject_id=original, note="Re-execute the contrast.")
        done = deliver(board, answers, request, "No answer recorded.", studio_demo.replication_hook(post, original))
        run = done["active_run"]
        sandbox_receipt = json.loads((root / "runs" / run / "sandbox.json").read_text())
        assert sandbox_receipt["sandboxed"] is True and sandbox_receipt["replication_egress"] == "none"
        assert "This dispatch is that sandbox." in (root / "runs" / run / "prompt.txt").read_text()
        assert not events(board, "replication_unsandboxed")
        [result] = events(board, "task_outcome")[-1]["criteria"]["replication"]
        assert result["sandboxed"] is True
        replica = (result["identical"] + result["different"])[0]
        receipt = result["receipts"][replica]
        stored = _receipt(root, ctx["agents"]["bob"], receipt["receipt_blob"])
        derivation = artifact_info(board.library, original)["manifest"]["derivation"]
        code, inputs = derivation["code"], [i["blob"] for i in derivation["inputs"]]
        assert stored["code_sha256"] == receipt["code_sha256"] == code[0] and stored["exit_code"] == 0
        assert stored["complete"] and receipt["producer"].startswith("questions/") and "/scripts/" in receipt["producer"]
        # v3 B3: the receipt records the inputs the run read, and the call is in the delivery's captured stream.
        assert [i["sha256"] for i in stored["inputs"]] == receipt["inputs"] == inputs and stored["inputs_unchanged"]
        assert receipt["stream"]["helper"] == "replicate.py" and receipt["stream"]["line"]
        written = [o["sha256"] for o in stored["outputs"] if o["written"]]
        answer = board.show(done["answer"])["content"]["body"]
        assert receipt["receipt_blob"] in answer and "through run_analysis.py" in answer  # worded from the receipt
        system = replication_system(board)
        [check] = events(board, "replication_checked")
        [entry] = check["results"]
        if not altered:
            assert result["outcome"] == "byte_identical" and result["identical"] == [original] and written == [blob]
            mark = board.one("SELECT * FROM mark WHERE id=?", (entry["mark"],))
            assert (mark["participant"], mark["target_kind"], mark["target_id"], mark["kind"]) == (
                system, "artifact", original, "reproduced") and blob in mark["note"]
            assert {"kind": "receipt", "id": receipt["receipt_blob"]}.items() <= json.loads(mark["pointers"])[2].items()
            reply = board.show(entry["post"])
            assert reply["author"] == system and reply["parent"] == ctx["posts"]["finding"]
            assert reply["content"]["kind"] == "replication_confirmed"
            assert receipt["receipt_blob"] in reply["content"]["body"] and code[0] in reply["content"]["body"]
            assert inputs[0] in reply["content"]["body"]
            assert reply["content"]["evidence"]["replication"]["receipts"][0]["receipt_blob"] == receipt["receipt_blob"]
        else:
            assert result["outcome"] == "bytes_differ" and result["different"] == [replica] and written != [blob]
            replica_blob = written[0]
            assert board.library.blob_path(replica_blob).read_text() == "contrast\tlog2_ratio\nB_vs_A\t1.5\n"
            correction = board.show(entry["post"])
            assert correction["author"] == system and correction["parent"] == post
            assert correction["content"]["kind"] == "replication_mismatch"
            body = correction["content"]["body"]
            assert blob in body and replica_blob in body and receipt["receipt_blob"] in body
            assert replica in correction["content"]["evidence"]["artifacts"]  # published: bytes verifiable
            assert not board.rows("SELECT * FROM mark WHERE target_id=? AND kind='reproduced'", (original,))
            notice = events(board, "notice_queued")[-1]  # the runtime notice uses the same receipt gate
            assert notice["target"] == ctx["agents"]["alice"]
            assert receipt["receipt_blob"] in board.show(notice["post"])["content"]["body"]
        # The agent signs only what it wrote: its answer. Platform records carry the replication participant.
        assert [p["id"] for p in board.rows("SELECT id FROM post WHERE author=? AND created>=?",
                                            (ctx["agents"]["bob"], request["created"]))] == [done["answer"]]
    # Operator re-check (CLI) is idempotent: no new marks, posts or events.
    from typer.testing import CliRunner

    from daw.commons.cli import app
    monkeypatch.delenv("BIO_AGENT", raising=False)
    rechecked = CliRunner().invoke(app, ["--root", str(root), "replication", "check", request["id"]])
    assert rechecked.exit_code == 0, rechecked.output
    assert json.loads(rechecked.output)["results"][0]["post"] == entry["post"]
    with Community(root) as board:
        assert len(events(board, "replication_checked")) == 1
        with pytest.raises(DawError, match="not_a_replication_request"):
            studio.replication_check(board, ctx["requests"]["brief"])
        with pytest.raises(DawError, match="permission_denied"):
            studio.replication_check(board, request["id"], actor=human(ctx))


def test_unsandboxed_replication_is_a_local_rehearsal_never_a_confirmation(demo):
    """v3 B3: local single-user mode executes the derivation's code without a sandbox. The prompt says so, the
    byte comparison is kept as a rehearsal, and nothing is confirmed, marked or corrected."""
    root, ctx = demo
    original, post = ctx["artifacts"]["contrast"], ctx["posts"]["finding"]
    with Community(root) as board, scripted_runtime(root) as (_, answers):
        request = commission(board, human(ctx), "replication", ctx["agents"]["bob"], {"minutes": 10},
                             subject_kind="artifact", subject_id=original, note="Re-execute the contrast.")
        done = deliver(board, answers, request, "No answer recorded.", studio_demo.replication_hook(post, original))
        run = done["active_run"]
        assert "replication_unsandboxed" in (root / "runs" / run / "sandbox.json").read_text()
        assert events(board, "replication_unsandboxed")[-1]["request"] == request["id"]
        prompt = (root / "runs" / run / "prompt.txt").read_text()
        assert "NOT sandboxed" in prompt and "local rehearsal, never a confirmation" in prompt
        assert "This dispatch is that sandbox." not in prompt
        [result] = events(board, "task_outcome")[-1]["criteria"]["replication"]
        assert result["outcome"] == "local_rehearsal" and result["rehearsal"] == "byte_identical"
        assert result["identical"] == [original] and result["receipts"][original]["stream"]["helper"] == "replicate.py"
        assert result["sandboxed"] is False and not result["correction_required"]
        [entry] = events(board, "replication_checked")[-1]["results"]
        assert entry["outcome"] == "local_rehearsal" and "post" not in entry and "mark" not in entry
        assert not board.rows("SELECT * FROM mark WHERE target_id=? AND kind='reproduced'", (original,))
        assert not board.rows("SELECT id FROM post WHERE request_key LIKE 'replication-%'")


# The right code on the wrong inputs: the hook copies the derivation's own (hash-checked) code blob into a saved
# script, runs it through run_analysis.py on a different means table it declares with --input, and registers
# the output under the original derivation. Fixture code (the demo's own saved script), never downloaded code.
WRONG_INPUTS = '''import hashlib, os, pathlib, shlex, subprocess, sys
from daw.artifacts import artifact_info, register_artifact
from daw.catalog import Workspace
from daw.substrate_models import ArtifactRegistration, Derivation
from daw.work import create_question, record_event
trial = pathlib.Path(os.environ.get("HERMES_CWD") or os.getcwd())
CALLS = []
ws = Workspace(os.environ["BIO_WORKSPACE"])
with ws.writer():
    info = artifact_info(ws, {original!r})
    derivation = info["manifest"]["derivation"]
    question = pathlib.Path(create_question(ws, "Replicate")["path"])
    code = ws.blob_path(derivation["code"][0]).read_bytes()
    assert hashlib.sha256(code).hexdigest() == derivation["code"][0]
    (question / "scripts" / "contrast.py").write_bytes(code)
    wrong = question / "inputs" / "means.tsv"
    wrong.parent.mkdir(exist_ok=True)
    wrong.write_text("condition\\tmean\\nA\\t2.0\\nB\\t8.0\\n")
    out, receipt = question / "outputs" / "contrast.tsv", question / "outputs" / "execution.json"
    argv = [sys.executable, str(trial / ".agents/skills/bio-research/scripts/run_analysis.py"), "--receipt",
            "workspace/questions/" + question.name + "/outputs/execution.json", "--output", str(out), "--input",
            str(wrong), "--", sys.executable, str(question / "scripts" / "contrast.py"), str(wrong), str(out)]
    done = subprocess.run(argv, cwd=trial, check=True, capture_output=True, text=True)
    CALLS.append({{"command": shlex.join(argv), "exit_code": 0, "output": done.stdout}})
    record_event(ws, question.name, "replication_execution",
                 {{"receipt_blob": ws.put_file(receipt, "work"), "receipt_path": "outputs/execution.json",
                   "original": {original!r}}})
    register_artifact(ws, out, ArtifactRegistration(title="Replication", summary="the code on other inputs",
        output_role=info["manifest"]["output_role"], derivation=Derivation(**derivation)), question=question.name)
ws.close()
'''


def test_right_code_on_wrong_inputs_is_inputs_differ_and_never_a_correction(sandboxed):
    """v3 B3: run_analysis.py records the inputs a run read; a captured run of the derivation's own code on other
    inputs is `inputs_differ`, not a mismatch: no platform correction against the innocent original, no notice."""
    root, ctx = sandboxed
    original = ctx["artifacts"]["contrast"]
    with Community(root) as board, scripted_runtime(root) as (_, answers):
        notices = len(events(board, "notice_queued"))
        request = commission(board, human(ctx), "replication", ctx["agents"]["bob"], {"minutes": 10},
                             subject_kind="artifact", subject_id=original, note="Re-execute the contrast.")
        deliver(board, answers, request, "Replicated.", WRONG_INPUTS.format(original=original))
        [result] = events(board, "task_outcome")[-1]["criteria"]["replication"]
        assert result["outcome"] == "inputs_differ" and not result["identical"] and not result["different"]
        assert not result["correction_required"]
        [(replica, receipt)] = result["inputs_differ"].items()
        assert replica != original and receipt["stream"]["helper"] == "run_analysis.py"
        assert receipt["inputs"] != result["input_blobs"] and receipt["code_sha256"] == result["code_blobs"][0]
        [unreceipted] = result["unreceipted"]
        assert [p for c in unreceipted["candidates"] for p in c["problems"]] == ["inputs_differ"]
        [entry] = events(board, "replication_checked")[-1]["results"]
        assert entry["outcome"] == "inputs_differ" and "post" not in entry
        assert not board.rows("SELECT id FROM post WHERE request_key LIKE 'replication-%'")
        assert not [r for r in board.rows("SELECT id FROM post")
                    if board.show(r["id"])["content"].get("kind") in ("replication_mismatch", "replication_confirmed")]
        assert not board.rows("SELECT * FROM mark WHERE target_id=?", (original,))
        assert len(events(board, "notice_queued")) == notices  # no "different bytes" notice to the author


def test_replicate_helper_refuses_a_code_blob_that_fails_its_hash(demo):
    """The carve-out executes only hash-verified code: a tampered stored script stops the helper before any run."""
    import os
    import subprocess
    root, ctx = demo
    original = ctx["artifacts"]["contrast"]
    with Community(root) as board:
        bob = board.agent(ctx["agents"]["bob"])
        trial = board.trial(bob)
        code = artifact_info(board.library, original)["manifest"]["derivation"]["code"][0]
    env = {**os.environ, "BIO_WORKSPACE": str(trial / "workspace"), "BIO_COMMUNITY": str(root), "BIO_AGENT": bob["id"]}
    question = json.loads(subprocess.run(["./bin/bio", "work", "new", "Replicate"], cwd=trial, env=env, check=True,
                                         capture_output=True, text=True).stdout)["question"]
    stored = trial / "workspace" / "blobs" / "sha256" / code[:2] / code  # bob fetched it with the finding post
    stored.chmod(0o644)
    stored.write_text("import os\nos.system('echo executed > TAMPERED')\n")
    done = subprocess.run(["./bin/python", ".agents/skills/bio-research/scripts/replicate.py", original, "--question",
                           question], cwd=trial, env=env, capture_output=True, text=True)
    refused = json.loads(done.stdout.strip().splitlines()[-1])
    assert done.returncode == 2 and refused["event"] == "replication_refused" and "integrity_failed" in refused["detail"]
    assert not (trial / "TAMPERED").exists()
    assert not list((trial / "workspace" / "questions" / question / "outputs").glob("replication-*/execution.json"))


def test_demo_saved_scripts_reproduce_their_registered_outputs(demo, tmp_path):
    """The synthetic derivations carry real saved code (`demo.CODE`): run on its recorded input, each script
    writes exactly the bytes registered as its output (our own fixture code, run here as a check)."""
    import subprocess
    import sys
    root, ctx = demo
    with Community(root) as board:
        for name in ("measurement", "contrast", "normalized"):
            info = artifact_info(board.library, ctx["artifacts"][name])
            derivation = info["manifest"]["derivation"]
            script = tmp_path / f"{name}.py"
            script.write_bytes(board.library.blob_path(derivation["code"][0]).read_bytes())
            out = tmp_path / f"{name}.out"
            subprocess.run([sys.executable, str(script), str(board.library.blob_path(derivation["inputs"][0]["blob"])),
                            str(out)], check=True)
            assert hashlib.sha256(out.read_bytes()).hexdigest() == info["output_blob"], name


def test_demo_deliver_replicate_runs_the_helper_on_the_request_subject(demo, monkeypatch):
    """`bio commons demo-deliver --replicate`: the operator's scripted delivery of a replication request runs
    replicate.py in the agent's checkout, so the demo's saved script executes under a receipt."""
    from typer.testing import CliRunner

    from daw.commons.cli import app
    root, ctx = demo
    monkeypatch.delenv("BIO_AGENT", raising=False)
    with Community(root) as board:
        request = commission(board, human(ctx), "replication", ctx["agents"]["dana"], {"minutes": 10},
                             subject_kind="artifact", subject_id=ctx["artifacts"]["measurement"], note="Re-execute.")
        writing = commission(board, human(ctx), "writing", ctx["agents"]["dana"], {"minutes": 10},
                             subject_kind="post", subject_id=ctx["posts"]["finding"], note="Summarise.")
    answer = root / "answer.md"
    answer.write_text("placeholder")
    runner = CliRunner()
    refused = runner.invoke(app, ["--root", str(root), "demo-deliver", writing["id"], "--answer", str(answer),
                                  "--replicate"])
    assert refused.exit_code != 0 and refused.exception.reason == "not_a_replication_request"
    done = runner.invoke(app, ["--root", str(root), "demo-deliver", request["id"], "--answer", str(answer), "--replicate"])
    assert done.exit_code == 0, done.output
    with Community(root) as board:
        [result] = events(board, "task_outcome")[-1]["criteria"]["replication"]
        # Local single-user demo: unsandboxed, so a rehearsal (v3 B3); its byte comparison and receipt are kept.
        assert result["outcome"] == "local_rehearsal" and result["rehearsal"] == "byte_identical"
        assert result["identical"] == [ctx["artifacts"]["measurement"]]
        assert "post" not in events(board, "replication_checked")[-1]["results"][0]
        assert "through run_analysis.py" in board.show(json.loads(done.output)["answer"])["content"]["body"]


def test_replication_prompt_states_the_carve_out_without_contradiction(demo):
    from daw.community_runtime import UNTRUSTED, compose_prompt
    root, ctx = demo
    with Community(root) as board:
        request = commission(board, human(ctx), "replication", ctx["agents"]["bob"], {"minutes": 10},
                             subject_kind="artifact", subject_id=ctx["artifacts"]["contrast"], note="Re-execute.")
        agent, request = board.agent(ctx["agents"]["bob"]), board.one("SELECT * FROM request WHERE id=?", (request["id"],))
        post = board.show(request["post"])
        prompts = {flag: compose_prompt(board, request, agent, board.trial(agent), post, "a test", sandboxed=flag)
                   for flag in (True, False)}
        # Without a decision, the sentence follows sandbox.toml (absent here: unsandboxed).
        assert compose_prompt(board, request, agent, board.trial(agent), post, "a test") == prompts[False]
    for prompt in prompts.values():
        assert "only the code blobs named in the fetched derivation, after hash verification, through run_analysis.py" in prompt
        assert "egress off" in prompt and "replicate.py" in prompt and "remains forbidden" in prompt
        assert UNTRUSTED not in prompt and "permission to execute downloaded code" not in prompt
        assert "{sandbox}" not in prompt and "{platform}" not in prompt
    # v3 B3: the sandbox sentence is conditioned on the dispatch.
    assert "This dispatch is that sandbox." in prompts[True] and "NOT sandboxed" not in prompts[True]
    assert "posts the confirmation or mismatch" in prompts[True]
    assert "NOT sandboxed" in prompts[False] and "local rehearsal, never a confirmation" in prompts[False]
    assert "posts no confirmation or mismatch" in prompts[False]
    agents_md = (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text()
    assert "only the code blobs named in the fetched derivation" in agents_md
    assert "an unsandboxed replication is a local rehearsal, never a confirmation" in agents_md


def test_replication_dispatch_needs_a_sandbox_with_egress_off_on_a_multi_tenant_commons(demo):
    from daw.commons import sandbox
    root, ctx = demo
    sandbox.record_tenancy(root, "accounts")
    with pytest.raises(DawError, match="sandbox_required"):
        sandbox.policy(root, "operator says so", "replication")  # no override for executing fetched code
    assert sandbox.policy(root, "operator says so", "research")["override"] == "operator says so"
    (root / "sandbox.toml").write_text('engine = "docker"\nimage = "agent:1"\n')
    assert sandbox.policy(root, None, "replication")["replication_egress"] == "none"
    (root / "sandbox.toml").write_text('engine = "docker"\nimage = "agent:1"\nnetwork = "egress"\n'
                                       'proxy = "http://egress:3128"\nallow_hosts = ["example.org"]\n')
    decision = sandbox.policy(root, None, "replication")
    assert decision["replication_egress"] == "model_hosts_only" and "warning" not in decision

    class Adapter:
        def auth_files(self, env):
            return ()

        def hosts(self, config):
            return ("api.anthropic.com",)
    with Community(root) as board:
        trial = board.trial(board.agent(ctx["agents"]["bob"]))
    env = {"BIO_AGENT": ctx["agents"]["bob"], "BIO_COMMUNITY": str(root), "PATH": "/usr/bin"}
    _, _, receipt = sandbox.apply(decision, ["claude"], env, trial=trial, board_root=root, adapter=Adapter(),
                                  agent_config={}, run="run_1")
    assert receipt["egress_allowlist"] == ["api.anthropic.com"] and receipt["replication_egress"] == "model_hosts_only"
    _, _, research = sandbox.apply(sandbox.policy(root), ["claude"], env, trial=trial, board_root=root,
                                   adapter=Adapter(), agent_config={}, run="run_2")
    assert "example.org" in research["egress_allowlist"] and "replication_egress" not in research


def test_replication_producers_on_the_cohort_include_forks(cohort):
    """Real data: in the PMP22 cohort every library artifact's producers include the agents whose own workspace
    produced it, and forks created afterwards inherit that production; commissioning one is refused."""
    from daw.commons import replication
    with Community(cohort) as board:
        artifacts = [r["id"] for r in board.library.rows("SELECT id FROM artifact ORDER BY id")]
        found = replication.producers(board, artifacts)
        agents = {r["id"]: r for r in board.rows("SELECT id,parent,kind FROM agent")}
        produced = {a for ids in found.values() for a in ids}
        assert produced == set(artifacts)  # every published artifact (281) was produced by some participant here
        forks = [p for p in found if agents[p]["parent"]]
        assert forks and all(agents[agents[p]["parent"]]["kind"] == "agent" for p in forks)
        inherited = [p for p in forks if set(found[p]) & set(found.get(agents[p]["parent"], []))]
        assert inherited  # a fork holds its parent's production
        fork = inherited[0]
        artifact = sorted(set(found[fork]) & set(found[agents[fork]["parent"]]))[0]
        person = board.one("SELECT id FROM agent WHERE kind='human'")["id"]
        before = board.one("SELECT max(seq) AS n FROM event")["n"]
        for target in (fork, agents[fork]["parent"]):
            with pytest.raises(DawError, match="replication_target_produced_original"):
                commission(board, person, "replication", target, {"minutes": 10}, subject_kind="artifact",
                           subject_id=artifact, note="Re-execute.")
        assert board.one("SELECT max(seq) AS n FROM event")["n"] == before  # refused before any write


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
    with Archive(root) as view:  # nothing foreign entered the board's posts, claims or library
        # Spec v2 V7: an import registers the snapshot's ids in the federation index (a projection) and records
        # one `federation_indexed` event; no other event names the snapshot.
        kinds = {r["kind"] for r in view.rows("SELECT kind FROM event WHERE body LIKE ?", (f"%{made['snapshot']}%",))}
        assert kinds <= {"snapshot_exported", "federation_indexed"}
        assert view.one("SELECT count(*) AS n FROM federation_record WHERE snapshot=?", (made["snapshot"],))["n"] > 0
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
    # The stale report cites a withdrawn claim; the current write-up cites artifacts of the superseded summary that
    # the correction re-lists, which no longer clears the flag (B14).
    assert {f["post"] for f in overview["regeneration_flags"]} == {made["flagged"], made["writeup"]}
    assert [m["kind"] for m in groups["reviews"][0]["review"]["marks"]] == ["checked_source", "disputed", "checked_source"]
    # The local demo replication is unsandboxed: a rehearsal of identical bytes, never a confirmation (v3 B3).
    assert groups["replications"][0]["replication"]["followup"][0]["outcome"] == "local_rehearsal"
    assert groups["replications"][0]["replication"]["followup"][0]["rehearsal"] == "byte_identical"
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
    problems = json.loads(refused.output)["problems"]
    assert refused.exit_code == 1 and [(p["kind"], p.get("text")) for p in problems] == [
        ("claimless_post_cited", None), ("unpointed_number", "1.31"), ("unpointed_number", "15%")]
    assert json.loads(refused.output)["verdict"]["source"] == "recorded"  # stored at delivery by the runtime hook
    skeleton = runner.invoke(app, ["--root", str(root), "digest", "skeleton", "--markdown"])
    assert skeleton.exit_code == 0 and skeleton.output.startswith("# Digest skeleton")


def test_regeneration_flags_superseded_posts_and_artifacts_not_only_withdrawn_claims(demo):
    """v2 C8: a write-up that cites a superseded post (and none of its later versions), or an artifact that a
    superseded publication named, is flagged for regeneration; citing the replacement too clears the post flag.
    B14: a current publication re-listing the artifact does not clear the artifact flag; the flag names it."""
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
        assert [(a["artifact"], a["superseded_posts"], a["replacements"], a["relisted_by"]) for a in flag["artifacts"]] \
            == [(interim, [first["id"]], [second["id"]], [])]
        assert first["id"] in flag["commission"]["note"] and interim in flag["commission"]["note"]
        assert "cites superseded posts" in flag["note"]
        # Citing a later version clears the post flag. The contrast table was named by the demo's superseded finding
        # and summary; both corrections re-list it, and the flag stays, naming them (B14).
        flag = writeup.render_writeup(view, acknowledged["id"], with_map=False)["regeneration_required"]
        assert flag["claims"] == [] and flag["posts"] == []
        assert [(a["artifact"], set(a["superseded_posts"]), set(a["relisted_by"])) for a in flag["artifacts"]] == [
            (ctx["artifacts"]["contrast"], {ctx["posts"]["finding"], ctx["claims"]["summary"]},
             {ctx["posts"]["correction"], ctx["claims"]["correction"]})]
        assert "re-listed by" in flag["commission"]["note"] and ctx["claims"]["correction"] in flag["commission"]["note"]
    # Over HTTP the flag travels with the response; this write-up also cites a claimless post, which the checker
    # (v2 C5) refuses, and a refusal still carries the regeneration flag.
    response = client(root).get(f"/api/studio/writeups/{stale['id']}")
    assert response.status_code == 422 and response.json()["error"] == "writeup_refused"
    assert response.json()["regeneration_required"]["artifacts"][0]["artifact"] == interim
