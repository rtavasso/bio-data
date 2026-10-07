"""Discovery area: pinned local embeddings (M1.8), commons search, and watchers (M5.2, Flow C).

All offline against the synthetic demo commons. Watcher ticks use an injected
httpx.MockTransport serving a recorded Europe PMC search response.
"""
import json
import re
import sqlite3
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from daw.catalog import Workspace
from daw.commons.app import create_app
from daw.commons.archive import Archive
from daw.commons.embeddings import embed_commons, search_commons
from daw.commons.participants import add_participant
from daw.commons.watchers import WEEK, add_watcher, disable_watcher, list_watchers, runs, tick
from daw.community import Community
from daw.embeddings import HASHING, embed_documents, load_model, vector_search
from daw.util import DawError, digest
from daw.work import create_question, sync_work


WRITE = {"X-Colloquy-Request": "1"}


def client(root, user="rhea"):
    return TestClient(create_app(root, local_user=user, static_dir=root / "missing"))


# ---- M1.8 embeddings ---------------------------------------------------------------------------------

def test_hashing_model_is_pinned_deterministic_and_unit_length():
    model = load_model()
    assert model.id.startswith(HASHING + ":dim=512,") and "max_chars=20000" in model.id
    assert load_model(model.id) is model and load_model(HASHING) is model
    a, b = model.embed("Schwann cell myelination", "", "PMP22 dosage"), model.embed("Schwann cell myelination", "", "PMP22 dosage")
    assert a == b and len(a) == 512 and abs(sum(x * x for x in a) - 1) < 1e-9
    with pytest.raises(DawError, match="unknown_embedding_model"):
        load_model("hashing-ngram-v1:dim=256")
    with pytest.raises(DawError, match="unpinned_embedding_model"):
        load_model("sentence-transformers:all-MiniLM-L6-v2")
    with pytest.raises(DawError, match="empty_embedding_text"):
        model.embed("", "", "a ? !")


def test_embed_job_reembeds_only_changed_documents(ws):
    with ws.writer():
        question = create_question(ws, "Myelin thickness after Pmp22 duplication")["question"]
        first = embed_documents(ws)
        assert first["embedded"] == first["documents"] >= 1 and first["without_current_vector"] == 0
        assert embed_documents(ws)["embedded"] == 0
        (ws.root / "questions" / question / "LABBOOK.md").write_text("# Notebook\n\nNew finding about remyelination.\n")
        sync_work(ws, question)
        changed = embed_documents(ws)
        assert changed["embedded"] == 1 and changed["embedded_documents"] == ["work:" + question]
    result = vector_search(ws, "remyelinating", family="work")
    assert result["items"][0]["subject"] == question and result["coverage"]["without_current_vector"] == 0


def tokens(text):
    return set(re.findall(r"\w+", text.casefold()))


def test_milestone4_vector_search_finds_own_related_notebook_for_held_out_query(demo):
    """DoD: a held-out query sharing no token with any notebook title still finds the related notebook.

    What this shows, honestly: hashing-ngram-v1 matches shared spelling (normalisation ~ normalization,
    robustness ~ robust, contrasts ~ contrast). It does not capture meaning: a synonym-only query
    ('gene silencing' for knockdown) gets near-zero similarity, asserted below.
    """
    root, ctx = demo
    held_out = "normalisation robustness of contrasts"
    with Archive(root) as view:
        titles = [r["title"] for r in view.workspace(ctx["agents"]["bob"]).rows("SELECT title FROM question")]
        titles += [r["title"] for name in ("alice", "dana")
                   for r in view.workspace(ctx["agents"][name]).rows("SELECT title FROM question")]
        assert all(not tokens(held_out) & tokens(title) for title in titles)
        exact = search_commons(view, held_out, family="work", scope="workspaces")
        assert exact["total"] == 0
    response = client(root).get("/api/search", params={"q": held_out, "vector": "true", "scope": "workspaces",
                                                       "family": "work"})
    assert response.status_code == 200
    result = response.json()
    top = result["items"][0]
    assert top["subject"] == ctx["questions"]["bob"] and top["source"]["participant"] == ctx["agents"]["bob"]
    assert top["score"] > 2 * result["items"][1]["score"]
    assert all(s.get("coverage", {}).get("without_current_vector") == 0 for s in result["sources"])
    synonym = client(root).get("/api/search", params={"q": "gene silencing", "vector": "true", "scope": "workspaces",
                                                      "family": "work"}).json()
    assert synonym["items"][0]["score"] < 0.1
    assert any("not synonyms" in x for x in synonym["limitations"])


def test_search_api_exact_is_primary_and_labels_catalogs(demo):
    root, ctx = demo
    api = client(root)
    exact = api.get("/api/search", params={"q": "contrast"}).json()
    assert exact["vector"] is False and exact["sources"] == [{"scope": "library", "total": exact["total"]}]
    assert {i["family"] for i in exact["items"]} <= {"forum", "artifact"} and exact["items"]
    assert all(i["source"] == {"scope": "library"} and i["content_is_untrusted_data"] for i in exact["items"])
    merged = api.get("/api/search", params={"q": "contrast", "scope": "workspaces", "family": "work"}).json()
    assert {i["source"]["scope"] for i in merged["items"]} == {"workspace"}
    names = {s.get("name") for s in merged["sources"]}
    assert {"alice", "bob", "dana"} <= names
    assert api.get("/api/search", params={"q": "x", "scope": "everywhere"}).status_code == 400
    assert api.get("/api/search", params={"q": "x", "family": "nope"}).status_code == 404  # unknown_search_family
    assert api.get("/api/search", params={"q": "", "vector": "true"}).status_code == 400


def test_commons_embed_skips_busy_workspace_and_is_incremental(demo):
    root, ctx = demo
    with Community(root) as board:
        bob = Workspace(board.trial(board.agent(ctx["agents"]["bob"])) / "workspace")
        try:
            with bob.writer():
                result = embed_commons(board)
        finally:
            bob.close()
        by_name = {s.get("name", s["scope"]): s for s in result["sources"]}
        assert by_name["bob"]["error"] == "writer_busy"
        assert by_name["library"]["embedded"] == 0 and by_name["alice"]["embedded"] == 0


# ---- M5.2 watchers -----------------------------------------------------------------------------------

def epmc(results):
    payload = {"hitCount": len(results), "resultList": {"result": results}}
    seen = []

    def handler(request):
        seen.append(str(request.url))
        assert request.url.path.endswith("/europepmc/webservices/rest/search")
        return httpx.Response(200, json=payload)
    return httpx.MockTransport(handler), seen


def frontier_item(board, author, *, status="open", kind="gap", text="Per-sample counts after Nae1 knockdown"):
    """An agent-authored item recorded in the author's own workspace and indexed by a rebuild (the projection
    holds no row a record does not support, v2 C3); "promoted" goes through a person's promotion event."""
    from daw.commons import frontier, participation
    agent = board.agent(author)
    ws = Workspace(board.trial(agent) / "workspace")
    try:
        with ws.writer():
            question = ws.one("SELECT id FROM question ORDER BY created,id LIMIT 1")["id"]
            event = frontier.record_item(ws, question, kind=kind, text=text, key="test-" + digest([text])[:12])
    finally:
        ws.close()
    frontier.rebuild_frontier(board)
    identity = frontier.item_id(agent["id"], event["id"])
    if status == "promoted":
        participation.promote(board, "operator", "frontier_item", identity, "research", agent["id"], {"minutes": 5})
    return identity


def mine(result, watcher):
    """This watcher's run in a tick (the demo's own watcher may be due at the same time)."""
    return next(r for r in result["ran"] if r["watcher"] == watcher["id"])


def test_weekly_watcher_posts_receipted_candidate_for_recorded_gap(demo):
    """Milestone 4 DoD offline: a weekly watcher posts a receipted candidate for a recorded gap."""
    root, ctx = demo
    with Community(root) as board:
        scratch = Workspace.create(root / "watchers" / "workspace")
        (scratch.root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0\n")
        scratch.close()
        rhea = add_participant(board, "rhea", "human")
        dana = ctx["agents"]["dana"]
        item = frontier_item(board, dana)
        watcher = add_watcher(board, rhea["id"], item, {"query": "Nae1 knockdown Schwann", "filters": {"source": "MED"}},
                              "europepmc")
        assert watcher["interval_seconds"] == WEEK and watcher["runs"] == 0
        assert json.loads(board.one("SELECT watcher_query FROM frontier_item WHERE id=?", (item,))["watcher_query"])["watcher"] == watcher["id"]
        hits = [{"id": "111", "source": "MED", "title": "Nae1 knockdown in Schwann cells", "pmcid": "PMC111"},
                {"id": "PPR9", "source": "PPR", "title": "A preprint outside the filter"}]
        transport, seen = epmc(hits)
        start = time.time()
        result = tick(board, now=start, transport=transport)
        run = mine(result, watcher)
        assert run["new"] == ["111"] and run["found"] == 1 and len(seen) == 1
        row = board.one("SELECT * FROM watcher_run WHERE id=?", (run["run"],))
        receipt = json.loads(board.library.blob_path(row["receipt_blob"]).read_text())
        assert receipt["excluded_by_filters"] == 1 and receipt["retrieval_only"]
        response = board.library.blob_path(receipt["pages"][0]["response_blob"]).read_text()
        assert "Nae1 knockdown in Schwann cells" in response
        notice = board.show(row["post"])
        assert notice["content"]["kind"] == "notice" and notice["content"]["title"] == f"New evidence may fit {item}"
        assert row["receipt_blob"] in notice["content"]["body"] and notice["content"]["evidence"]["target"] == dana
        assert board.agent(notice["author"])["kind"] == "system" and board.agent(notice["author"])["name"] == "watcher"
        request = board.one("SELECT * FROM request WHERE post=?", (row["post"],))
        assert request["target"] == dana and request["task_type"] == "notice" and request["state"] == "pending"
        assert board.one("SELECT status FROM frontier_item WHERE id=?", (item,))["status"] == "candidate_evidence"
        # Not due again until a week later; then the same hit is not new and nothing is posted.
        assert tick(board, now=start + 60, transport=transport)["ran"] == []
        later = mine(tick(board, now=start + WEEK, transport=transport), watcher)
        assert later["new"] == [] and later["notice"] is None
        transport, _ = epmc(hits + [{"id": "222", "source": "MED", "title": "Second study"}])
        third = mine(tick(board, now=start + 2 * WEEK, transport=transport), watcher)
        assert third["new"] == ["222"] and third["notice"]["post"] != row["post"]
        history = runs(board, watcher["id"])
        assert [len(r["found"]) for r in history] == [2, 1, 1]
        kinds = [(r["kind"], json.loads(r["body"])["watcher"]) for r in board.rows(
            "SELECT kind,body FROM event WHERE kind LIKE 'watcher_%' ORDER BY seq")]
        assert [k for k, w in kinds if w == watcher["id"]] == ["watcher_added", "watcher_ran", "watcher_ran", "watcher_ran"]
        with pytest.raises(sqlite3.IntegrityError):
            with board.db:
                board.db.execute("UPDATE watcher_run SET found='[]' WHERE id=?", (run["run"],))
        # The agent workspace was never written: discovery catalog writes stay in the scratch workspace.
        dana_ws = Workspace(board.trial(board.agent(dana)) / "workspace")
        try:
            assert not dana_ws.rows("SELECT id FROM run WHERE kind='discover'")
        finally:
            dana_ws.close()


def test_watcher_permissions_status_rules_and_disable(demo):
    root, ctx = demo
    with Community(root) as board:
        scratch = Workspace.create(root / "watchers" / "workspace")
        (scratch.root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0\n")
        scratch.close()
        promoted = frontier_item(board, ctx["agents"]["alice"], status="promoted", text="Test donor structure")
        with pytest.raises(DawError, match="permission_denied"):
            add_watcher(board, ctx["agents"]["alice"], promoted, "donor", "europepmc")
        with pytest.raises(DawError, match="unknown_frontier_item"):
            add_watcher(board, "operator", "frontier_missing", "x", "europepmc")
        with pytest.raises(DawError, match="unsupported_provider"):
            add_watcher(board, "operator", promoted, "x", "google")
        with pytest.raises(DawError, match="invalid_watcher_interval"):
            add_watcher(board, "operator", promoted, "x", "europepmc", interval_seconds=60)
        watcher = add_watcher(board, "operator", promoted, "donor structure", "europepmc", interval_seconds=3600)
        transport, _ = epmc([{"id": "333", "source": "MED", "title": "Donors"}])
        result = tick(board, now=time.time() + 1, transport=transport)
        assert [r["watcher"] for r in result["ran"]] == [watcher["id"]]  # the demo watcher is not due for a week
        # A promoted item keeps its state: the watcher never overrides or closes a person's decision.
        assert board.one("SELECT status FROM frontier_item WHERE id=?", (promoted,))["status"] == "promoted"
        rhea = add_participant(board, "rhea", "human")
        with pytest.raises(DawError, match="permission_denied"):
            disable_watcher(board, rhea["id"], watcher["id"])
        assert disable_watcher(board, "operator", watcher["id"])["enabled"] is False
        later = tick(board, now=time.time() + 10 * WEEK, transport=transport)["ran"]
        assert [r["watcher"] for r in later] == [ctx["discovery"]["watcher"]]
        with pytest.raises(DawError, match="permission_denied"):
            tick(board, actor=ctx["agents"]["bob"])


def test_demo_watcher_status_and_api(demo):
    root, ctx = demo
    discovery = ctx["discovery"]
    api = client(root)
    listed = api.get("/api/watchers", params={"item": discovery["frontier_item"]}).json()
    assert [w["id"] for w in listed["items"]] == [discovery["watcher"]]
    assert listed["items"][0]["last_run"]["found"] == 1 and "europepmc" in listed["providers"]
    history = api.get(f"/api/watchers/{discovery['watcher']}/runs").json()["items"]
    assert history[0]["receipt"]["kind"] == "watcher_receipt" and history[0]["post"] == discovery["notices"][0]
    with Archive(root) as view:
        item = view.one("SELECT * FROM frontier_item WHERE id=?", (discovery["frontier_item"],))
        assert item["status"] == "candidate_evidence" and item["author"] == ctx["agents"]["dana"]
        assert ctx["gap_event"] in item["source"]
    body = {"item": discovery["frontier_item"], "query": "marker knockdown RNA-seq", "provider": "europepmc",
            "interval_seconds": WEEK}
    # Watcher writes follow the Actor discipline: the CSRF header is required in local and cookie mode (v2 C3).
    assert api.post("/api/watchers", json=body).status_code == 403
    created = api.post("/api/watchers", headers=WRITE, json=body)
    assert created.status_code == 200 and created.json()["author"] != "operator"
    assert api.post("/api/watchers", headers=WRITE,
                    json={"item": "nope", "query": "x", "provider": "europepmc"}).status_code == 404
    assert api.post(f"/api/watchers/{created.json()['id']}/disable").status_code == 403
    assert api.post(f"/api/watchers/{created.json()['id']}/disable", headers=WRITE).json()["enabled"] is False
    assert api.get("/api/watchers/watcher_nope/runs").status_code == 404
    with Archive(root) as view:
        assert len(list_watchers(view, discovery["frontier_item"])) == 2


def test_cli_embed_vector_text_and_watch_commands(demo):
    from typer.testing import CliRunner

    from daw.bio_cli import app
    root, ctx = demo
    runner = CliRunner()
    with Community(root) as board:
        bob_ws = board.trial(board.agent(ctx["agents"]["bob"])) / "workspace"
    embedded = runner.invoke(app, ["-w", str(bob_ws), "index", "embed"])
    assert embedded.exit_code == 0, embedded.output
    assert json.loads(embedded.output)["embedded"] == 0  # the demo already embedded every catalog
    found = runner.invoke(app, ["-w", str(bob_ws), "search", "--vector-text", "normalisation robustness", "--family", "work"])
    assert json.loads(found.output)["items"][0]["subject"] == ctx["questions"]["bob"]
    listed = runner.invoke(app, ["commons", "--root", str(root), "watch", "list", "--runs"])
    rows = json.loads(listed.output)["items"]
    assert rows[0]["id"] == ctx["discovery"]["watcher"] and len(rows[0]["run_history"]) == 1
    added = runner.invoke(app, ["commons", "--root", str(root), "watch", "add", ctx["discovery"]["frontier_item"],
                                "--query", "marker knockdown", "--provider", "europepmc", "--filter", "source=MED"])
    assert json.loads(added.output)["query"]["filters"] == {"source": "MED"}
    disabled = runner.invoke(app, ["commons", "--root", str(root), "watch", "disable", json.loads(added.output)["id"]])
    assert json.loads(disabled.output)["enabled"] is False
    assert runner.invoke(app, ["commons", "--root", str(root), "embed", "--no-workspaces"]).exit_code == 0
