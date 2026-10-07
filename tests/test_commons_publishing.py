"""Publishing and federation that resolve (spec v2 V7), the real-data pilot's code and data parts (V3) and the
live multi-harness tooling (V8).

Shares, counts and the reading path are measured on the committed PMP22 cohort fixture (C0); invariants,
writes and the verifier's tamper cases run on the synthetic demo."""
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from daw.commons import (checks, directory, export, federation, harnesscheck, hygiene, locators, metrics, pilotkit,
                         preprint, preprint_verify, publicdemo, studio_demo, tour, views, writeup)
from daw.commons.app import create_app
from daw.commons.archive import Archive
from daw.commons.cli import app
from daw.commons.demo import scripted_runtime
from daw.commons.participation import commission
from daw.community import Community
from daw.community_runtime import dispatch
from daw.util import DawError, canonical

ROOT = Path(__file__).resolve().parents[1]
TOUR = ROOT / "docs" / "colloquy" / "tours" / "pmp22-cohort.json"
WRITE = {"X-Colloquy-Request": "1"}


def client(root):
    return TestClient(create_app(root, static_dir=root / "missing"))


def sequence(root):
    return sqlite3.connect(root / "board.sqlite").execute("SELECT max(seq) FROM event").fetchone()[0]


def events(root, kind):
    with Archive(root) as view:
        return [json.loads(r["body"]) for r in view.rows("SELECT body FROM event WHERE kind=? ORDER BY seq", (kind,))]


def deliver_writing(root, ctx, text, *, target="dana"):
    with Community(root) as board, scripted_runtime(root) as (_, answers):
        person = (ctx.get("participation") or {}).get("human", "operator")
        subject = (ctx.get("claims") or {}).get("correction") or ctx["posts"]["finding"]
        request = commission(board, person, "writing", ctx["agents"][target], {"minutes": 10},
                             subject_kind="post", subject_id=subject, note="publishing test")
        post = board.one("SELECT post FROM request WHERE id=?", (request["id"],))["post"]
        (answers / f"{post}.md").write_text(text)
        return dispatch(board, request["id"], str(root / "demo-harness" / "hermes"))


def studio(root):
    """The Studio demo records plus Dana's figure published to the library (a preprint needs public bytes)."""
    made = studio_demo.apply(root)
    ctx = json.loads((root / "demo-harness" / "context.json").read_text())
    figure = ctx["observatory_map"]["figure"]
    with Community(root) as board:
        dana = board.agent("dana")
        board.publish(dana["id"], "Search hits figure", "The synthetic search-hit figure, published for the preprint "
                      "tests. Synthetic demo record.", artifacts=[figure], workspace=board.trial(dana) / "workspace",
                      request_key="publishing-figure")
    return made, ctx


def run_verifier(folder, *args):
    return subprocess.run([sys.executable, "-I", str(folder / "verify.py"), str(folder), *args], capture_output=True,
                          text=True, cwd=folder.parent)


def rehash(folder):
    """Rewrite snapshot.json after a deliberate edit, so only the value re-check can catch the edit."""
    manifest = json.loads((folder / "snapshot.json").read_bytes())
    for entry in manifest["files"]:
        data = (folder / entry["path"]).read_bytes()
        entry.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
    data = canonical(manifest)
    (folder / "snapshot.json").write_bytes(data)
    (folder / "snapshot.id").write_text(hashlib.sha256(data).hexdigest() + "\n")


# ---- the standalone verifier mirrors the checker (parity) -------------------------------------------------

PROSE = ["1.54", "1.5", "2", "−0.5", "+0.394", "12%", "3.2×10^-4", "1e-5", "17,949", "±0.2", "½", "three", "3:1",
         "49316968", "0.0151", "1,000", "−3.039", "15.172", "0.5603"]
VALUES = [1.5432, 1.535, 1.545, -0.5, 0.393787, 0.1204, 12.04, 3.24e-4, 1.4e-5, 17949, -0.2, 0.5, 3, 3.0, 49316968,
          0.0151, 1000.4, -3.0393, 15.171999, 0.56026, 2.0, 0.0]


def test_verifier_number_rules_equal_the_checkers():
    for prose in PROSE:
        assert preprint_verify.parse_number(prose) == locators.parse_number(prose), prose
        for value in VALUES:
            for decimals in (None, 0, 2, 4):
                assert preprint_verify.matches(preprint_verify.parse_number(prose), value, decimals) == \
                    locators.matches(locators.parse_number(prose), value, decimals), (prose, value, decimals)
    for text in ("row=B_vs_A;col=log2_ratio", "row=B%20vs%20A;col=%232;round=2", "key=stats.fit[0].value", "line=3"):
        assert preprint_verify.parse_locator(text) == locators.parse_locator(text)
    for bad in ("row=B_vs_A", "line=0", "round=13", "key=a..b", "colour=x"):
        with pytest.raises(preprint_verify.Problem):
            preprint_verify.parse_locator(bad)
    for cell in ("NA", " 1.54 ", 2, "-0.17624552522424877", "3.48E-12", True, None, "12%"):
        assert preprint_verify.parse_cell(cell) == locators.parse_cell(cell)


@pytest.mark.parametrize("name,data,locator,prose", [
    ("t.tsv", b"## c\ncontrast\tlog2_ratio\nB_vs_A\t1.54\nC_vs_A\tNA\n", "row=B_vs_A;col=log2_ratio", "1.54"),
    ("t.tsv", b"contrast\tlog2_ratio\nB_vs_A\t1.54\n", "row=B_vs_A;col=log2_ratio", "1.55"),
    ("t.tsv", b"contrast\tlog2_ratio\nB_vs_A\t1.54\n", "row=#1;col=#2", "1.5"),
    ("t.tsv", b"contrast\tlog2_ratio\nB_vs_A\tNA\n", "row=B_vs_A;col=log2_ratio", "1.5"),
    ("t.csv", b"a,b\nx,0.003\n", "row=x;col=b", "0.003"),
    ("t.csv", b"a,b\nx,0.003\n", "row=y;col=b", "0.003"),
    ("s.json", b'{"stats": {"fit": [{"value": 0.512}]}}', "key=stats.fit[0].value", "0.51"),
    ("s.json", b'{"stats": {"fit": [{"value": 0.512}]}}', "key=stats.fit[1].value", "0.51"),
    ("s.json", b'{"stats": {"fit": [{"value": 0.512}]}}', "key=stats", "0.51"),
    ("log.txt", b"first 1\nsecond 32.0 here\n", "line=2", "32.0"),
    ("log.txt", b"first 1\nsecond 32.0 here\n", "line=1", "32.0"),
    ("log.txt", b"first 1\nsecond 32.0 here\n", None, "32"),
    ("log.txt", b"first 1\nsecond 32.0 here\n", None, "33"),
    ("log.txt", b"a 32.0\nb 32.0\n", None, "32"),  # v3 B6: twice, so no text match verifies
    ("img.png", b"\x89PNG\r\n\x1a\n\x00\xff", None, "1"),
])
def test_verifier_reads_cited_values_like_the_checker(name, data, locator, prose):
    aid = "artifact_" + "a" * 64
    checker = locators.verify_artifact(None, aid, locator, locators.parse_number(prose), {aid: (data, name, None)})
    mine = preprint_verify.verify_bytes(data, name, locator, preprint_verify.parse_number(prose))
    assert mine["result"] == checker["result"], (checker, mine)
    if checker["result"] == "verified" and "found" in checker:
        assert str(mine["found"].get("value")) == str(checker["found"].get("value"))


# ---- V7 preprint export -----------------------------------------------------------------------------------

def test_preprint_export_is_verified_offline_by_its_own_verifier(demo, tmp_path):
    root, _ = demo
    made, ctx = studio(root)
    post = made["writeup"]
    before = sequence(root)
    with Community(root) as board:
        result = preprint.export_preprint(board, ctx["participation"]["human"], post, tmp_path / "preprint")
    out = Path(result["output"])
    assert sequence(root) == before + 1 and events(root, "preprint_exported")[-1]["snapshot"] == result["snapshot"]
    assert result["snapshot"] == hashlib.sha256((out / "snapshot.json").read_bytes()).hexdigest()
    listed = {e["path"] for e in json.loads((out / "snapshot.json").read_bytes())["files"]}
    assert {"index.html", "claims.html", "verification.html", "preprint.json", "verify.py", "records.json",
            f"source/{post}.md", f"records/{post}.json", f"checks/{post}.json"} <= listed
    assert (out / "verify.py").read_bytes() == Path(preprint_verify.__file__).read_bytes()
    data = json.loads((out / "preprint.json").read_bytes())
    # The write-up's numbers: a claim pointer and two cells, each with its recorded result.
    statuses = {n["text"]: n["status"] for n in data["numbers"]}
    assert statuses["1.54"] == statuses["11.0"] == statuses["32.0"] == "verified"
    cells = [p for n in data["numbers"] for p in n["pointers"] if p.get("locator")]
    assert {p["locator"] for p in cells} == {"row=A;col=mean", "row=B;col=mean"}
    assert ctx["claims"]["current"] in data["claims"] and ctx["artifacts"]["measurement"] in data["artifacts"]
    # The cited claim's own artifact pointers travel too ("its cited claims, artifacts").
    claim_artifacts = [p["id"] for p in data["claims"][ctx["claims"]["current"]]["pointers"] if p["kind"] == "artifact"]
    assert set(claim_artifacts) <= set(data["artifacts"])
    # Each figure links to its artifact bytes and embeds them; the pages carry no scripts.
    figure = ctx["observatory_map"]["figure"]
    index = (out / "index.html").read_text()
    png = data["artifacts"][figure]["path"]
    assert f'<a href="{png}"><img src="{png}"' in index
    for page in ("index.html", "claims.html", "verification.html"):
        text = (out / page).read_text()
        assert "<script" not in text.lower() and "script-src" not in text and "default-src 'none'" in text
    assert 'class="num num-verified"' in index
    # The verifier: every hash, the record chain and every number, from the folder alone (stdlib only, -I).
    checked = run_verifier(out, "--expect", result["snapshot"])
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "OK" in checked.stdout and "verified" in checked.stdout
    report = json.loads(run_verifier(out, "--json").stdout)
    assert report["ok"] and report["numbers"] == len(data["numbers"]) and report["statuses"]["verified"] >= 3
    assert run_verifier(out, "--expect", "0" * 64).returncode == 1


def test_verifier_recomputes_values_rather_than_trusting_hashes(demo, tmp_path):
    root, _ = demo
    made, ctx = studio(root)
    with Community(root) as board:
        result = preprint.export_preprint(board, ctx["participation"]["human"], made["writeup"], tmp_path / "p")
    good = Path(result["output"])
    # 1. A changed byte without a re-hashed manifest: the file hash fails.
    one = tmp_path / "one"
    shutil.copytree(good, one)
    data = json.loads((one / "preprint.json").read_bytes())
    measurement = data["artifacts"][ctx["artifacts"]["measurement"]]["path"]
    (one / measurement).write_bytes((one / measurement).read_bytes().replace(b"32.0", b"33.0"))
    failed = run_verifier(one)
    assert failed.returncode == 1 and "hash or size mismatch" in failed.stdout
    # 2. The same change with snapshot.json re-hashed: the artifact no longer hashes to its recorded output sha256.
    rehash(one)
    failed = run_verifier(one)
    assert failed.returncode == 1 and "bytes do not hash to the artifact's output sha256" in failed.stdout
    # 3. A recorded status changed in preprint.json (and re-hashed): the recomputation disagrees.
    two = tmp_path / "two"
    shutil.copytree(good, two)
    data = json.loads((two / "preprint.json").read_bytes())
    number = next(n for n in data["numbers"] if n["text"] == "32.0")
    number["status"] = "unverified"
    (two / "preprint.json").write_bytes(canonical(data))
    rehash(two)
    failed = run_verifier(two)
    assert failed.returncode == 1 and "recorded unverified, recomputed verified" in failed.stdout
    # 4. A post record that is not the board's bytes (re-hashed): body_blob no longer matches.
    three = tmp_path / "three"
    shutil.copytree(good, three)
    record = three / data["record"]
    record.write_bytes(record.read_bytes().replace(b"corrected", b"revised!!"))
    rehash(three)
    failed = run_verifier(three)
    assert failed.returncode == 1 and "body_blob" in failed.stdout
    # An unlisted file is refused, as on import.
    four = tmp_path / "four"
    shutil.copytree(good, four)
    (four / "extra.py").write_text("print('never run')\n")
    assert "unlisted file: extra.py" in run_verifier(four).stdout


def test_preprint_refuses_what_a_reader_could_not_verify(demo):
    root, _ = demo
    made = studio_demo.apply(root)
    ctx = json.loads((root / "demo-harness" / "context.json").read_text())
    person = ctx["participation"]["human"]
    with Community(root) as board:
        # Dana's figure is only in her workspace: its bytes would not be in the preprint.
        with pytest.raises(DawError, match="preprint_unverifiable") as error:
            preprint.export_preprint(board, person, made["writeup"])
        assert "only in a participant workspace" in error.value.detail
        with pytest.raises(DawError, match="preprint_refused"):
            preprint.export_preprint(board, person, made["refused"])
        from daw.commons.moderation import moderate
        moderate(board, "operator", "hide", made["flagged"], "test")
        with pytest.raises(DawError, match="hidden_by_moderation"):
            preprint.export_preprint(board, person, made["flagged"])
        with pytest.raises(DawError, match="permission_denied"):
            preprint.export_preprint(board, ctx["agents"]["alice"], made["writeup"])


def test_preprint_http_route_needs_the_write_discipline(demo):
    root, _ = demo
    made, _ = studio(root)
    api = client(root)
    assert api.post("/api/preprints", json={"post": made["writeup"]}).status_code == 403
    created = api.post("/api/preprints", json={"post": made["writeup"]}, headers=WRITE)
    assert created.status_code == 200, created.text
    body = created.json()
    assert (root / body["location"] / "verify.py").is_file()
    listed = api.get("/api/preprints").json()["preprints"]
    assert listed[0]["snapshot"] == body["snapshot"] and listed[0]["post"] == made["writeup"]


# ---- V7 federation that resolves --------------------------------------------------------------------------

def export_thread(root, post, out):
    with Archive(root) as view:
        site, manifest = export.build_site(view, "thread", post)
    return export.write_site(site, manifest, out)


def test_imported_snapshot_claims_and_artifacts_resolve_to_bytes_across_commons(demo, demo_only, tmp_path):
    lab_a, ctx_a = demo
    snapshot = export_thread(lab_a, ctx_a["claims"]["correction"], tmp_path / "snap")
    records = json.loads((tmp_path / "snap" / "records.json").read_bytes())
    claim = next(c for c in records["claims"] if "1.54" in c["text"])
    contrast = ctx_a["artifacts"]["contrast"]
    assert any(a["id"] == contrast and a["output"]["path"] for a in records["artifacts"])
    # Lab B: a separate commons with only the core records.
    lab_b, ctx_b = demo_only()
    with Community(lab_b) as board:
        imported = federation.import_and_index(board, tmp_path / "snap", expect=snapshot)
    assert imported["index"]["claims"] >= 1 and imported["index"]["artifacts"] >= 2 and imported["index"]["changed"]
    with Community(lab_b) as board:  # idempotent: unchanged rows write nothing
        assert federation.index_snapshot(board, snapshot)["changed"] is False
    assert len(events(lab_b, "federation_indexed")) == 1
    foreign_claim = f"snapshot:{snapshot}/{claim['id']}"
    foreign_cell = f"snapshot:{snapshot}/{contrast}#row=B_vs_A;col=log2_ratio"
    text = (f"# Cross-commons note\n\nLab A's corrected contrast is [1.54]({foreign_claim}); its table holds "
            f"[1.54]({foreign_cell}) as well, and [1.60]({foreign_cell}) is not what it holds.\n")
    done = deliver_writing(lab_b, ctx_b, text)
    with Archive(lab_b) as view:
        value, _, pointers = writeup.verdict(view, done["answer"])
    assert value["status"] == "rendered", value["problems"]
    by_text = {}
    for n in value["numbers"]:
        by_text.setdefault(n["text"], []).append(n)
    assert [n["status"] for n in by_text["1.54"]] == ["verified", "verified"]
    assert by_text["1.60"][0]["status"] == "unverified"
    assert by_text["1.60"][0]["pointers"][0]["reason"].startswith("the cited cell holds 1.54")
    entry = pointers[f"snapshot:{snapshot}/{contrast}"]
    assert entry["foreign"] and entry["snapshot"] == snapshot and entry["bytes_url"].startswith(f"/api/federation/{snapshot}/files/")
    # The citation carries the snapshot id; the post page shows the pointer as foreign, the checker verified it.
    api = client(lab_b)
    before = sequence(lab_b)
    page = api.get(f"/api/posts/{done['answer']}").json()
    foreign = [p for n in page["numbers"] for p in n["pointers"] if p.get("foreign")]
    assert foreign and all(p["route"].startswith(f"/directory/{snapshot}") for p in foreign)
    assert api.get(api.get(f"/api/directory/{snapshot}").json()["records"]["artifacts"][0]["bytes_url"]).status_code == 200
    shown = api.get(f"/api/directory/{snapshot}").json()
    assert claim["id"] in {c["id"] for c in shown["records"]["claims"]}
    assert shown["citations"]["citing_posts"] == 1
    cited = api.get("/api/snapshot-citations").json()["snapshots"]
    assert cited[0]["snapshot"] == snapshot and cited[0]["imported"] and all(c["resolves"] for c in cited[0]["citations"])
    assert api.get("/api/directory").json()["imported"] == [snapshot]
    assert sequence(lab_b) == before  # reads never write
    # An unknown snapshot does not resolve: refused, never guessed.
    unknown = "f" * 64
    refused = deliver_writing(lab_b, ctx_b, f"A value [1.54](snapshot:{unknown}/{claim['id']}).\n")
    with Archive(lab_b) as view:
        value, _, _ = writeup.verdict(view, refused["answer"])
    assert value["status"] == "refused" and value["problems"][0]["kind"] == "unresolved_pointer"
    assert "import the snapshot first" in value["problems"][0]["reason"]


def test_federation_index_is_rebuilt_from_imported_directories_and_drops_tampered_ones(demo, tmp_path):
    root, ctx = demo
    snapshot = export_thread(root, ctx["claims"]["correction"], tmp_path / "snap")
    with Community(root) as board:
        federation.import_and_index(board, tmp_path / "snap", expect=snapshot)
        rows = board.rows("SELECT * FROM federation_record ORDER BY record")
        board.db.execute("DELETE FROM federation_record")
        board.db.execute("DELETE FROM projection_state WHERE name LIKE 'federation:%'")
        board.db.commit()
        rebuilt = federation.reindex(board)
        assert rebuilt["indexed"][0]["changed"] and not rebuilt["refused"]
        assert [dict(r) | {"indexed": None} for r in board.rows("SELECT * FROM federation_record ORDER BY record")] == \
            [dict(r) | {"indexed": None} for r in rows]
        # A stored copy that no longer verifies is not indexed (and loses its rows).
        stored = root / "federation" / snapshot / "records.json"
        stored.chmod(stat.S_IWUSR | stat.S_IRUSR)
        stored.write_bytes(stored.read_bytes().replace(b"1.54", b"9.99"))
        dropped = federation.reindex(board)
        assert dropped["refused"][0]["snapshot"] == snapshot and dropped["removed"] == [snapshot]
        assert board.one("SELECT count(*) AS n FROM federation_record")["n"] == 0


def test_snapshots_exported_before_records_json_index_their_artifacts(demo, tmp_path):
    root, ctx = demo
    folder = tmp_path / "old"
    snapshot = export_thread(root, ctx["claims"]["correction"], folder)
    # Drop records.json as an older export would not have it, and re-hash the manifest.
    manifest = json.loads((folder / "snapshot.json").read_bytes())
    manifest["files"] = [f for f in manifest["files"] if f["path"] != "records.json"]
    (folder / "records.json").unlink()
    data = canonical(manifest)
    (folder / "snapshot.json").write_bytes(data)
    (folder / "snapshot.id").write_text(hashlib.sha256(data).hexdigest())
    snapshot = hashlib.sha256(data).hexdigest()
    with Community(root) as board:
        index = federation.import_and_index(board, folder, expect=snapshot)["index"]
    assert index["claims"] == 0 and index["artifacts"] >= 2


def test_serving_a_board_that_imported_nothing_creates_no_federation_table(cohort):
    with Archive(cohort) as view:
        assert federation.indexed(view) == {} and federation.lookup(view, "a" * 64, "claim_" + "b" * 32) is None
    tables = {r[0] for r in sqlite3.connect(cohort / "board.sqlite").execute("SELECT name FROM sqlite_master")}
    assert "federation_record" not in tables


# ---- V7 public commons directory --------------------------------------------------------------------------

class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(folder):
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(folder)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_directory_publish_list_and_fetch_over_paths_and_http(demo, demo_only, tmp_path):
    root, ctx = demo
    snapshot = export_thread(root, ctx["claims"]["correction"], tmp_path / "snap")
    site = tmp_path / "site"
    published = directory.publish(tmp_path / "snap", site, lab="Lab A", title="Corrected contrast thread",
                                  publisher="mira")
    assert not published["already_listed"] and (site / "snapshots" / snapshot / "snapshot.json").is_file()
    assert directory.publish(tmp_path / "snap", site / "directory.json", lab="Lab A")["already_listed"]
    receipt = json.loads((site / "receipts" / f"{snapshot}.publish.json").read_text())
    assert receipt["executed"] is False and receipt["snapshot"] == snapshot
    listing = directory.listing(str(site))
    assert [e["snapshot"] for e in listing["entries"]] == [snapshot] and listing["entries"][0]["location"] == f"snapshots/{snapshot}/"
    # Fetch over a local path into another commons: verified, imported read-only and indexed.
    lab_b, _ = demo_only()
    with Community(lab_b) as board:
        fetched = directory.fetch(board, str(site / "directory.json"), snapshot)
    assert fetched["receipt"]["executed"] is False and fetched["receipt"]["index"]["artifacts"] >= 2
    assert (lab_b / "federation" / f"{snapshot}.fetch.json").is_file()
    # Over http(s): the directory and every file are downloaded and checked byte for byte.
    server = serve(site)
    url = f"http://127.0.0.1:{server.server_port}/directory.json"
    try:
        assert directory.listing(url)["entries"][0]["snapshot"] == snapshot
        lab_c = tmp_path / "lab-c"
        shutil.copytree(lab_b, lab_c, symlinks=True)
        shutil.rmtree(lab_c / "federation")
        with Community(lab_c) as board:
            board.db.execute("DELETE FROM federation_record")
            board.db.execute("DELETE FROM projection_state WHERE name LIKE 'federation:%'")
            board.db.commit()
            over_http = directory.fetch(board, url, snapshot)
        assert over_http["receipt"]["location"].startswith("http://127.0.0.1")
        with Archive(lab_c) as view:
            known = directory.known(view)
        assert known["imported"] == [snapshot] and known["sources"][0]["source"] == url
        assert known["sources"][0]["entries"][0]["imported"]
        # A served file that does not match its listed hash: nothing is imported.
        lab_d = tmp_path / "lab-d"
        shutil.copytree(lab_c, lab_d, symlinks=True)
        for path in (lab_d / "federation").rglob("*"):
            path.chmod(stat.S_IRWXU)
        shutil.rmtree(lab_d / "federation")
        served = next(p for p in (site / "snapshots" / snapshot / "artifacts").rglob("*.tsv"))
        original = served.read_bytes()
        served.write_bytes(original[:-2] + b"9\n")  # same size, other bytes
        with Community(lab_d) as board, pytest.raises(DawError, match="snapshot_hash_mismatch"):
            directory.fetch(board, url, snapshot)
        served.write_bytes(original + b"more\n")  # longer than listed: the download is capped
        with Community(lab_d) as board, pytest.raises(DawError, match="download_too_large"):
            directory.fetch(board, url, snapshot)
        assert not (lab_d / "federation" / snapshot).exists()
        assert not list((lab_d / "federation").glob(".fetch-*"))
    finally:
        server.shutdown()
    # Locations that leave the directory or use another scheme are refused when the directory is read.
    bad = {"format": directory.FORMAT, "entries": [{"snapshot": snapshot, "location": "../elsewhere/"}]}
    (tmp_path / "bad.json").write_bytes(canonical(bad))
    with pytest.raises(DawError, match="invalid_directory"):
        directory.listing(str(tmp_path / "bad.json"))
    bad["entries"][0]["location"] = "ftp://host/x/"
    (tmp_path / "bad.json").write_bytes(canonical(bad))
    with pytest.raises(DawError, match="invalid_directory"):
        directory.listing(str(tmp_path / "bad.json"))


def test_directory_cli_publishes_lists_and_fetches(demo, tmp_path):
    root, ctx = demo
    snapshot = export_thread(root, ctx["claims"]["correction"], tmp_path / "snap")
    runner = CliRunner()
    out = runner.invoke(app, ["directory", "publish", str(tmp_path / "snap"), "--directory", str(tmp_path / "site"),
                              "--lab", "Lab A"])
    assert out.exit_code == 0, out.output
    listed = runner.invoke(app, ["directory", "list", str(tmp_path / "site")])
    assert json.loads(listed.output)["entries"][0]["snapshot"] == snapshot
    fetched = runner.invoke(app, ["--root", str(root), "directory", "fetch", str(tmp_path / "site"), snapshot])
    assert fetched.exit_code == 0, fetched.output
    citations = runner.invoke(app, ["--root", str(root), "federation", "citations"])
    assert json.loads(citations.output)["snapshots"] == []
    records = json.loads(runner.invoke(app, ["--root", str(root), "federation", "records", snapshot]).output)
    assert records["artifacts"]


# ---- V3 the cohort as the first public demo commons, and the reading path ------------------------------------

def test_the_cohort_board_exports_as_a_citable_snapshot_and_resolves_in_another_commons(cohort, demo_only, tmp_path):
    """Milestone E on real data, offline: the cohort board exports (bytes absent from the redacted fixture are
    listed with present: false, never invented), imports into another commons, and a write-up there cites a
    cohort artifact cell by snapshot id; the checker verifies the value from the snapshot's bytes."""
    with Archive(cohort) as view:
        site, manifest = export.build_site(view, "board")
    snapshot = export.write_site(site, manifest, tmp_path / "cohort-snapshot")
    assert manifest["counts"]["posts"] == 269 and manifest["counts"]["artifacts"] == 281
    records = json.loads((tmp_path / "cohort-snapshot" / "records.json").read_bytes())
    absent = [a for a in records["artifacts"] if a["output"].get("present") is False]
    assert len(records["artifacts"]) == 281 and absent and all(not a["output"].get("path") for a in absent)
    lab, ctx = demo_only()
    with Community(lab) as board:
        index = federation.import_and_index(board, tmp_path / "cohort-snapshot", expect=snapshot)["index"]
    assert index["artifacts"] == 281
    step = json.loads(TOUR.read_text())["steps"][0]  # the paired Pmp22 effect, key=primary[0].effect_log2
    pointer = f"snapshot:{snapshot}/{step['artifact']}#{step['locator']}"
    done = deliver_writing(lab, ctx, f"The cohort's paired Pmp22 effect is [−3.039]({pointer}) (log2).\n")
    with Archive(lab) as view:
        value, _, _ = writeup.verdict(view, done["answer"])
    assert value["status"] == "rendered", value["problems"]
    number = next(n for n in value["numbers"] if n["text"] == "−3.039")
    assert number["status"] == "verified" and number["scope"] == "cell"
    with Archive(lab) as view:
        cited = federation.citations(view)["snapshots"]
    assert cited[0]["snapshot"] == snapshot and cited[0]["citations"][0]["resolves"]


def test_every_number_offset_shows_its_text_on_the_cohort(cohort):
    """Regression (found building the tour): numbers on indented continuation lines were reported two code points
    early (412 of 3443 cohort numbers). Offsets now point at the number on every post."""
    with Archive(cohort) as view:
        index = views.thread_index(view)
        total = 0
        for pid, row in index["posts"].items():
            body = row["content"].get("body") or ""
            for n in checks.post_numbers(view, pid, body, row["content"].get("evidence")):
                assert body[n["offset"]:n["offset"] + n["length"]].strip() == n["text"], (pid, n)
                total += 1
    assert total > 3000


def test_tour_reaches_bytes_from_a_number_in_two_clicks_on_cohort_finals(cohort):
    """Milestone B: a visitor reaches bytes from a number in two clicks on at least five cohort finals."""
    before = sequence(cohort)
    data = tour.load(TOUR)
    with Archive(cohort) as view:
        resolved = tour.resolve(view, data)
        finals = checks.finals(view)
    assert resolved["applies"] and resolved["summary"]["broken"] == 0, [s["problems"] for s in resolved["steps"]]
    ok = [s for s in resolved["steps"] if s["ok"]]
    assert len({s["final"] for s in ok}) >= 5 and resolved["summary"]["finals_reaching_bytes_in_two_clicks"] >= 5
    api = client(cohort)
    for step in ok:
        assert step["final"] in finals and step["checks"]["artifact_named_by_post"]
        # The authors pointed no number at a cell: the checker reports these as the post's evidence (C11).
        assert step["number"]["checker_status"] == "post_scoped"
        # Click 1: the number opens the artifact page at the locator; the page reads the cited value from the bytes.
        route = step["clicks"][0]["to"]
        assert route.startswith(f"/artifact/{step['artifact']}?locator=")
        located = api.get(f"/api/artifacts/{step['artifact']}/locate", params={"locator": step["locator"]}).json()
        assert located["present"] and not located.get("error")
        value = located["target"]["value"]
        assert locators.matches(locators.parse_number(step["number"]["text"]), locators.parse_cell(value)), (step, value)
        # Click 2: the raw bytes, which hash to the artifact's recorded output.
        artifact = api.get(f"/api/artifacts/{step['artifact']}").json()
        raw = api.get(step["clicks"][1]["to"])
        assert raw.status_code == 200 and hashlib.sha256(raw.content).hexdigest() == artifact["output_blob"]
        assert step["clicks_to_bytes"] == 2
    listed = api.get("/api/tours").json()["tours"]
    assert any(t["name"] == "pmp22-cohort" and t["applies"] and t["summary"]["ok"] == len(ok) for t in listed)
    served = api.get("/api/tours/pmp22-cohort").json()
    assert served["summary"]["ok"] == len(ok) and served["steps"][0]["number"]["excerpt"]["text"]
    assert sequence(cohort) == before  # reads never write


def test_a_wrong_curated_pointer_is_served_broken_never_verified(cohort, tmp_path):
    data = json.loads(TOUR.read_text())
    data["name"] = "broken-copy"
    data["steps"][0]["locator"] = "key=primary[0].ci95_low"       # a real key, another value
    data["steps"][1]["number"]["offset"] += 3                      # the body does not show the number there
    data["steps"][2]["artifact"] = "artifact_" + "0" * 64          # not named by the post, not catalogued
    with Archive(cohort) as view:
        resolved = tour.resolve(view, tour.validate(data))
    first, second, third = resolved["steps"][:3]
    assert not first["ok"] and "not at the locator" in first["problems"][0]
    assert not second["ok"] and any("does not show" in p for p in second["problems"])
    assert not third["ok"] and any("not among the evidence" in p for p in third["problems"])
    assert resolved["summary"]["broken"] == 3
    with pytest.raises(DawError, match="invalid_tour"):
        tour.validate({**data, "curator": {}})


def test_tour_curation_aid_finds_candidate_locators_on_the_cohort(cohort):
    step = json.loads(TOUR.read_text())["steps"][7]
    with Archive(cohort) as view:
        found = tour.candidates(view, step["final"], step["number"]["offset"])
    hits = {c["artifact"]: c.get("locators") for c in found["candidates"]}
    assert step["locator"] in hits[step["artifact"]]


def test_tour_does_not_apply_to_another_commons(demo):
    root, _ = demo
    with Archive(root) as view:
        listed = tour.listing(view)["tours"]
    assert listed and all(not t["applies"] for t in listed if t["name"] == "pmp22-cohort")


def test_public_demo_commons_from_the_cohort_fixture(tmp_path):
    source = ROOT / "fixtures" / "pmp22-cohort"
    if not (source / "FIXTURE.json").is_file():
        pytest.skip("real-data fixture not checked out")
    out = tmp_path / "public"
    built = publicdemo.build(out)
    assert built["tour"]["finals_reaching_bytes_in_two_clicks"] >= 5 and built["board_sequence"] == json.loads((ROOT / "fixtures" / "pmp22-cohort" / "FIXTURE.json").read_text())["board_sequence"]
    assert (out / "tours" / "pmp22-cohort.json").read_bytes() == TOUR.read_bytes()
    public = json.loads((out / "PUBLIC.json").read_text())
    assert public["real_data"] and public["redaction"]["capped_blob_bytes"] == 65536
    api = client(out)
    health = api.get("/api/health").json()
    assert health["public_demo"]["fixture"] == "pmp22-cohort-2026-10" and health["demo"] is False
    tours = api.get("/api/tours").json()["tours"]
    assert [t["source"] for t in tours if t["name"] == "pmp22-cohort"] == ["commons"]
    # C2 is in force on the public commons: hiding a post makes it a stub on the tour as everywhere else.
    step = json.loads(TOUR.read_text())["steps"][0]
    with Community(out) as board:
        from daw.commons.moderation import moderate
        moderate(board, "operator", "hide", step["final"], "public demo moderation check")
    hidden = api.get("/api/tours/pmp22-cohort").json()["steps"][0]
    assert not hidden["ok"] and hidden["post"] == {"id": step["final"], "hidden": True} and "number" not in hidden
    # The fixture itself is untouched, and the output must be new.
    from daw.commons.fixture import verify_fixture
    assert verify_fixture(source)["verified"]
    with pytest.raises(DawError, match="public_demo_output_not_empty"):
        publicdemo.build(out)
    broken = json.loads(TOUR.read_text())
    broken["steps"][0]["locator"] = "key=primary[0].ci95_low"
    (tmp_path / "broken.json").write_text(json.dumps(broken))
    with pytest.raises(DawError, match="tour_steps_broken"):
        publicdemo.build(tmp_path / "public-2", tour=tmp_path / "broken.json")
    assert not (tmp_path / "public-2").exists()


def test_public_cohort_commons_reads_publicly_and_visitors_comment_and_mark_after_signing_in(tmp_path):
    """Spec v3 V15: the cohort fixture served as a public commons (accounts mode, read policy public): the first
    screen is the board, GETs write no record, anonymous callers read but cannot write, and a visitor who signs in
    with a display name can comment and mark, and nothing else."""
    source = ROOT / "fixtures" / "pmp22-cohort"
    if not (source / "FIXTURE.json").is_file():
        pytest.skip("real-data fixture not checked out")
    out = tmp_path / "public"
    built = publicdemo.build(out)
    assert built["read_policy"] == "public" and built["visitor_signin"] is True and built["first_screen"] == "/"
    assert "--mode accounts" in built["next"]
    public = json.loads((out / "PUBLIC.json").read_text())
    assert public["read_policy"] == "public" and public["first_screen"] == "/"
    static = tmp_path / "web"
    static.mkdir()
    (static / "index.html").write_text('<html><head><meta name="colloquy-base" content="/" /></head>'
                                       '<body><div id="root"></div></body></html>')
    api = TestClient(create_app(out, mode="accounts", static_dir=static))
    assert api.get("/api/access").json()["read"] == "public" and api.get("/api/access").json()["visitor_signin"]
    health = api.get("/api/health").json()
    assert health["read_policy"] == "public" and health["public_demo"]["first_screen"] == "/" and health["visitor_signin"]
    # The first screen: `/` serves the app, whose route `/` is the board (web App.test.tsx), not a prompt.
    assert api.get("/").status_code == 200 and "colloquy-base" in api.get("/").text
    step = json.loads(TOUR.read_text())["steps"][0]
    before = sequence(out)
    files = {p: p.stat().st_mtime_ns for p in (out / "board.sqlite", out / "library" / "catalog.sqlite")}
    for path in ("/api/posts?limit=5", f"/api/posts/{step['final']}", "/api/tours/pmp22-cohort", "/api/dashboard",
                 "/api/runs?limit=5", "/api/frontier", f"/api/curation/pointers?post={step['final']}",
                 "/api/curation/progress?tour=pmp22-cohort"):
        assert api.get(path).status_code == 200, path
    assert sequence(out) == before and {p: p.stat().st_mtime_ns for p in files} == files  # GETs write no record
    # Anonymous visitors read but never write.
    write = {"X-Colloquy-Request": "1"}
    note = {"target_kind": "post", "target_id": step["final"], "body": "Which table holds this number?"}
    assert api.post("/api/comments", json=note, headers=write).status_code == 401
    assert api.post("/api/visitors", json={"display_name": "A reviewer"}).status_code == 403  # the write header
    signed = api.post("/api/visitors", json={"display_name": "A reviewer", "affiliation": "Funder"}, headers=write)
    assert signed.status_code == 200, signed.text
    visitor = signed.json()
    assert visitor["visitor"] and visitor["token"].startswith("colloquy_") and visitor["kind"] == "human"
    me = api.get("/api/me").json()  # the session cookie is set
    assert me["visitor"] is True and set(me["permissions"]) == {"read", "comment", "mark", "token", "profile", "inbox"}
    commented = api.post("/api/comments", json=note, headers=write)
    assert commented.status_code == 200, commented.text
    marked = api.post("/api/marks", headers=write, json={"target_kind": "post", "target_id": step["final"],
                                                         "kind": "checked_source", "note": "Opened the summary JSON."})
    assert marked.status_code == 200, marked.text
    # ... and nothing else: no top-level posts, curation, promotions or commissions.
    refused = [api.post("/api/posts", json={"title": "x", "body": "y"}, headers=write),
               api.post("/api/curation/pointers", headers=write, json={"post": step["final"], "offset": 0, "note": "x",
                                                                         "unlocatable": True}),
               api.post("/api/commissions", headers=write, json={"task_type": "review", "target": "operator",
                                                                 "budget": {"minutes": 5}, "note": "x"})]
    assert [r.status_code for r in refused] == [403, 403, 403], [r.text for r in refused]
    with Archive(out) as view:
        kinds = [r["kind"] for r in view.rows("SELECT kind FROM event WHERE seq>? ORDER BY seq", (before,))]
    assert "visitor_signed_in" in kinds and "mark_recorded" in kinds
    from daw.commons.fixture import verify_fixture
    assert verify_fixture(source)["verified"]  # the committed fixture itself is untouched


# ---- V3 pilot tooling: presets, invitations and the participation report -------------------------------------

def test_round_two_preset_queues_three_questions_per_agent_with_assignment_keys(demo):
    root, ctx = demo
    from daw.community_runtime import add_agent
    with Community(root) as board:
        add_agent(board, "cody", harness="codex")
    runner = CliRunner()
    out = runner.invoke(app, ["--root", str(root), "cohort-run", "round-two-test", "--preset", "round-two",
                              "--agent", "alice", "--agent", "cody"])
    assert out.exit_code == 0, out.output
    value = json.loads(out.output)
    assert "warning" not in value and sorted(len(v) for v in value["queued"].values()) == [3, 3]
    with Archive(root) as view:
        bodies = [views.content(view, view.one("SELECT body_blob FROM post WHERE id=?", (r["post"],))["body_blob"])["body"]
                  for r in view.rows("SELECT post FROM request WHERE task_type='research' AND state='pending'")]
    keys = sorted(line for body in bodies for line in body.splitlines() if line.startswith("Assignment key:"))
    assert keys == sorted([f"Assignment key: round-two-{n}" for n in (1, 2, 3)] * 2)
    single = runner.invoke(app, ["--root", str(root), "cohort-run", "round-two-one", "--preset", "round-two",
                                 "--agent", "bob"])
    assert "meant for 2 harnesses" in json.loads(single.output)["warning"]
    preset, items = pilotkit.load_preset("round-two")
    assert len(items) == 3 and preset["harnesses"] == 2
    with pytest.raises(DawError, match="unknown_preset"):
        pilotkit.load_preset("nope")


def test_invitation_creates_a_person_with_a_token_and_the_report_traces_their_promotion(demo, tmp_path):
    root, ctx = demo
    with Community(root) as board:
        invited = pilotkit.invite(board, "operator", "rhea", display_name="Rhea", affiliation="External lab",
                                  minutes=120, url="https://commons.example", output=tmp_path / "rhea.md")
    letter = tmp_path / "rhea.md"
    assert stat.S_IMODE(letter.stat().st_mode) == 0o600
    token = next(line.strip() for line in letter.read_text().splitlines() if line.strip().startswith("colloquy_"))
    assert "https://commons.example/login" in letter.read_text()
    recorded = events(root, "participant_invited")[-1]
    assert recorded["participant"] == invited["participant"] and token not in json.dumps(events(root, "participant_invited"))
    # The person logs in with the token and promotes a post into a research request for an agent.
    api = client(root)
    accounts = TestClient(create_app(root, mode="accounts", static_dir=root / "missing"))
    me = accounts.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["name"] == "rhea"
    from daw.commons.participation import promote
    with Community(root) as board:
        request = promote(board, invited["participant"], "post", ctx["posts"]["finding"], "research", "alice",
                          {"minutes": 30}, note="Does the contrast hold in a second dataset?")
    with Community(root) as board, scripted_runtime(root) as (harness, answers):
        post = board.one("SELECT post FROM request WHERE id=?", (request["id"],))["post"]
        (answers / f"{post}.md").write_text("Checked: no second dataset found yet. Synthetic demo record.")
        dispatch(board, request["id"], harness)
    with Archive(root) as view:
        report = pilotkit.report(view)
    person = next(p for p in report["participants"] if p["name"] == "rhea")
    assert person["promotions"] == 1 and person["invited"] and person["requests_an_agent_worked_on"] == 1
    worked = person["requests"][0]["runs"][0]
    assert worked["agent"] == ctx["agents"]["alice"] and worked["state"] == "completed"
    assert worked["next_delivery_after_request"] and person["changed_an_agents_next_delivery"] == 1
    assert api.get("/api/pilot/report").json()["participants"][0]["name"] == "rhea"
    with Community(root) as board, pytest.raises(DawError, match="permission_denied"):
        pilotkit.invite(board, invited["participant"], "someone")


# ---- V8 live-receipt harness checks, compaction hygiene, three harnesses ------------------------------------

@pytest.mark.parametrize("harness", ["codex", "claude", "hermes"])
def test_harness_check_runs_two_turns_with_resume_offline(harness, tmp_path):
    receipt = harnesscheck.run(harness, tmp_path / "commons", scripted=True)
    assert receipt["verdict"] == "pass", receipt["failures"]
    assert receipt["live"] is False and receipt["scripted_stand_in"] and receipt["harness"] == harness
    first, second = receipt["turns"]
    assert first["state"] == second["state"] == "completed" and second["resume_argument"]
    assert receipt["resume"]["same_session"] and first["session"] == second["session"]
    assert first["tokens"] and first["answer_contains_phrase"] and second["answer_contains_phrase"]
    assert first["hygiene"]["assignment_markers"] >= 2  # the request post id and the assignment key phrase
    text = json.dumps(receipt)
    assert str(tmp_path) not in text and "COLLOQUY-CHECK-" not in text  # no paths, no phrase (only its hash)
    with pytest.raises(DawError, match="output_required"):
        harnesscheck.write(receipt)
    with pytest.raises(DawError, match="scripted_receipt_refused"):
        harnesscheck.write(receipt, harnesscheck.RECEIPTS / f"harness-check-{harness}.json")
    written = harnesscheck.write(receipt, tmp_path / "receipt.json")
    assert json.loads(Path(written).read_text())["verdict"] == "pass"


def test_live_harness_check_requires_opt_in_and_an_installed_harness(tmp_path, monkeypatch):
    monkeypatch.delenv("DAW_LIVE", raising=False)
    with pytest.raises(DawError, match="live_opt_in_required"):
        harnesscheck.run("codex", tmp_path / "a")
    monkeypatch.setenv("DAW_LIVE", "1")
    with pytest.raises(DawError, match="harness_not_installed"):
        harnesscheck.run("codex", tmp_path / "b", executable=str(tmp_path / "no-such-codex"))
    out = CliRunner().invoke(app, ["harness-check", "--harness", "claude", "--scripted"])
    assert out.exit_code != 0 and "output_required" in str(out.exception)
    good = CliRunner().invoke(app, ["harness-check", "--harness", "claude", "--scripted", "--workdir",
                                    str(tmp_path / "c"), "--output", str(tmp_path / "c.json")])
    assert good.exit_code == 0, good.output
    assert json.loads(good.output)["verdict"] == "pass" and json.loads(good.output)["live"] is False


def test_compaction_hygiene_detects_summaries_that_lost_the_assignment(tmp_path):
    run = tmp_path / "run"
    (run / "agent-state").mkdir(parents=True)
    post = "post_" + "1" * 32
    (run / "prompt.txt").write_text(f"Request post: {post}. Parent discussion: none.\nAssignment key: round-two-2\n")
    (run / "execution.json").write_text(json.dumps({"started": "2026-10-01T10:00:00+00:00",
                                                     "finished": "2026-10-01T11:00:00+00:00"}))
    db = sqlite3.connect(run / "agent-state" / "state.db")
    db.execute("CREATE TABLE messages(session TEXT, content TEXT, timestamp REAL)")
    from datetime import datetime
    inside = datetime.fromisoformat("2026-10-01T10:01:00+00:00").timestamp()
    base = inside - 10 * 86400  # another delivery, outside this run's window
    db.executemany("INSERT INTO messages VALUES('s',?,?)", [
        (f"[CONTEXT COMPACTION] Working on {post}: contrast registered.", inside),
        ("[CONTEXT COMPACTION] Continue the analysis of the dataset.", inside + 60),
        ("[CONTEXT COMPACTION] deterministic fallback: last 20 messages kept. Assignment key: round-two-2", inside + 120),
        ("[CONTEXT COMPACTION] From another delivery.", base),
        ("ordinary message", inside)])
    db.commit()
    db.close()
    with (run / "events.jsonl").open("w") as stream:
        for n, tokens in enumerate((1000, 1000, 5000)):  # the second line repeats the first message id
            stream.write(json.dumps({"type": "assistant", "message": {"id": f"m{min(n, 1)}", "usage": {
                "input_tokens": tokens, "cache_read_input_tokens": 200, "cache_creation_input_tokens": 0}}}) + "\n")
    value = hygiene.run_hygiene(run, "claude")
    assert value["compaction_summaries"] == 3 and value["compaction_fallbacks"] == 1
    assert value["summaries_missing_assignment"] == 1 and value["assignment_markers"] == 2
    assert value["context_per_call"] == {"unit": "call", "records": 2, "mean_input_tokens": 1200.0, "max_input_tokens": 1200}
    # Unavailable stays None: no session database, no prompt markers, no reported usage.
    bare = tmp_path / "bare"
    bare.mkdir()
    assert hygiene.run_hygiene(bare) == {"compaction_summaries": None, "compaction_fallbacks": None,
                                         "summaries_missing_assignment": None, "assignment_markers": 0,
                                         "context_per_call": None}
    totals = hygiene.aggregate([value, hygiene.run_hygiene(bare)])
    assert totals["runs_with_session_database"] == 1 and totals["summaries_missing_assignment"] == 1
    assert totals["context_unit"] == "call" and totals["context_max_input_tokens"] == 1200


def test_cohort_hygiene_is_unavailable_where_session_databases_were_dropped(cohort):
    with Archive(cohort) as view:
        board = metrics.dashboard(view)
    summary = board["summary"]["compaction_hygiene"]
    assert summary["runs"] == 97 and summary["runs_with_session_database"] == 0
    assert summary["compaction_summaries"] is None and summary["summaries_missing_assignment"] is None
    assert summary["context_runs"] > 0 and summary["context_unit"] == "turn"  # Hermes result tokens per turn
    harnesses = {g["key"]: g["compaction_hygiene"] for g in board["panels"]["harness"]}
    assert "hermes" in harnesses


def test_three_harness_cohorts_compare_side_by_side_with_separate_cells(demo):
    """Hermes, Codex and Claude (scripted stand-ins) on the same assignments: one cohort per harness, separate
    yield, calibration, correction and cost cells, and compaction hygiene per harness."""
    root, ctx = demo
    from daw.community_runtime import add_agent
    with Community(root) as board:
        for name, harness in (("hera", "hermes"), ("cody", "codex"), ("clio", "claude")):
            add_agent(board, name, harness=harness)
    runner = CliRunner()
    assignments = []
    for n in (1, 2):
        path = root / f"assignment-{n}.md"
        path.write_text(f"# Three-harness check {n}\n\nSummarise the synthetic demo contrast. Assignment key: three-{n}\n")
        assignments += ["--assignment", str(path)]
    queued = json.loads(runner.invoke(app, ["--root", str(root), "cohort-run", "three", *assignments,
                                            "--agent", "hera", "--agent", "cody", "--agent", "clio"]).output)["queued"]
    with Community(root) as board, scripted_runtime(root) as (harness, answers):
        for requests in queued.values():
            for request in requests.values():
                post = board.one("SELECT post FROM request WHERE id=?", (request,))["post"]
                (answers / f"{post}.md").write_text("Summary: synthetic contrast. Synthetic demo record.")
                dispatch(board, request, harness)
    collected = json.loads(runner.invoke(app, ["--root", str(root), "cohort-collect", "three"]).output)
    assert len(collected) == 3
    with Archive(root) as view:
        compared = metrics.compare(view, list(collected.values()))
        board = metrics.dashboard(view)
    assert compared["criteria"] == ["yield", "calibration", "corrections", "cost"]
    assert sorted(h for c in compared["cohorts"] for h in c["harnesses"]) == ["claude", "codex", "hermes"]
    assert compared["shared_assignments"] == 2
    for row in compared["assignments"]:
        cells = row["cells"]
        assert len(cells) == 3 and all(cells[c] and set(cells[c]) >= {"yield", "calibration", "corrections", "cost"}
                                       for c in cells)
    harnesses = {g["key"]: g for g in board["panels"]["harness"]}
    assert {"claude", "codex", "hermes"} <= set(harnesses)
    # The stand-in streams turn totals only (a live Claude stream reports usage per message: unit "call").
    assert harnesses["claude"]["compaction_hygiene"]["context_unit"] == "turn"
    assert harnesses["codex"]["compaction_hygiene"]["context_unit"] == "turn"


def test_publishing_reads_are_listed_and_never_write(demo):
    root, _ = demo
    api = client(root)
    before = sequence(root)
    for path in ("/api/tours", "/api/directory", "/api/federation-index", "/api/snapshot-citations", "/api/preprints",
                 "/api/pilot/report"):
        assert api.get(path).status_code == 200, path
    assert api.get("/api/tours/no-such-tour").status_code == 404
    assert api.get(f"/api/directory/{'a' * 64}").status_code == 404
    assert sequence(root) == before
    assert os.environ.get("BIO_AGENT") is None
