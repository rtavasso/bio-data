import hashlib
import sqlite3

import pytest
from hypothesis import given, settings, strategies as st

from daw.catalog import Workspace, restore_check
from daw.models import Asset, Budgets
from daw.util import DawError, canonical, digest, file_hash


def test_distinct_remote_and_biological_identity_same_bytes(ws, tmp_path):
    path = tmp_path / "table.tsv"
    path.write_text("gene\tx\nPMP22\t1\n")
    a, b = ws.local_asset(path, "study1"), ws.local_asset(path, "study2")
    assert a["blob"] == b["blob"]
    assert a["asset_revision"] != b["asset_revision"]
    assert ws.resource("donor", "study1", "donor_1") != ws.resource("donor", "study2", "donor_1")
    again = ws.local_asset(path, "study1")
    assert again == a
    assert len(ws.assets()) == 2
    assert len(ws.rows("SELECT * FROM snapshot")) == 3


def test_history_immutable_and_consistent_backup(ws, tmp_path):
    source = tmp_path / "file.tsv"
    source.write_text("feature\tvalue\nNA\t0\n")
    result = ws.local_asset(source)
    with pytest.raises(sqlite3.IntegrityError, match="immutable history"):
        with ws.db:
            ws.db.execute("UPDATE asset_revision SET access='not_found' WHERE id=?", (result["asset_revision"],))
    destination = tmp_path / "backup"
    ws.backup(destination)
    receipt = restore_check(destination)
    assert receipt["ok"] and receipt["restored_assets"] == 1
    assert receipt["verified_blobs"] >= 1


def test_interrupted_attempt_and_orphan_recovery(ws):
    attempt, _ = ws.start_run("test", {"input": "a"})
    content = b"unregistered but complete"
    sha = hashlib.sha256(content).hexdigest()
    path = ws.root / "blobs/sha256" / sha[:2] / sha
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(content)
    result = ws.recover()
    assert result["verified_orphans"] == [sha]
    assert ws.one("SELECT state FROM run WHERE id=?", (attempt,))["state"] == "interrupted"
    assert file_hash(ws.blob_path(sha)) == sha


def test_retry_attempts_distinct_work_key_stable(ws):
    a, keya = ws.start_run("extract", {"curation": "a", "blob": "x"})
    b, keyb = ws.start_run("extract", {"blob": "x", "curation": "a"})
    _, keyc = ws.start_run("extract", {"blob": "x", "curation": "b"})
    assert a != b and keya == keyb and keya != keyc


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_work_keys_rejected(number):
    with pytest.raises(ValueError):
        canonical({"value": number})


@settings(deadline=None)  # wall-clock deadlines flake under a loaded full suite; the property is unchanged
@given(st.dictionaries(st.text(max_size=15), st.integers(), max_size=8))
def test_canonical_key_order_property(value):
    assert digest(value) == digest(dict(reversed(list(value.items()))))


def test_invalid_hash_cannot_access_foreign_path(ws):
    with pytest.raises(DawError, match="invalid_blob_hash"):
        ws.blob_path("../../secrets")


def test_changed_asset_marks_dependencies_stale(ws):
    bundle = ws.resource("bundle", "test", "1")
    old = ws.register_asset(bundle, "test", Asset(native_id="x", name="x.tsv", checksum="md5:aaa"))
    run, _ = ws.start_run("test", {"input": old})
    with ws.db:
        ws.db.execute("INSERT INTO run_dependency VALUES(?,?)", (run, old))
    new = ws.register_asset(bundle, "test", Asset(native_id="x", name="x.tsv", checksum="md5:bbb"))
    assert old != new
    assert ws.one("SELECT stale FROM run WHERE id=?", (run,))["stale"] == 1
    assert len(ws.rows("SELECT * FROM asset_revision")) == 2


def test_writer_serialization(ws):
    other = Workspace(ws.root)
    try:
        with ws.writer(), pytest.raises(DawError, match="writer_busy"), other.writer():
            pass
    finally:
        other.close()


def test_unlimited_acquisition_keeps_production_disk_reserve(ws, monkeypatch):
    from types import SimpleNamespace

    ws.budgets = Budgets()
    disk = SimpleNamespace(total=100 * 2**30, free=9 * 2**30)
    monkeypatch.setattr("daw.catalog.shutil.disk_usage", lambda _: disk)
    with pytest.raises(DawError, match="minimum free-disk reserve"):
        ws.put_bytes(b"source")
    disk.free = 11 * 2**30
    blob = ws.put_bytes(b"source")
    assert ws.blob_path(blob).read_bytes() == b"source"


def test_existing_workspace_finite_limits_survive_reopening(tmp_path):
    root = tmp_path / "legacy"
    Workspace.create(root).close()
    (root / "config.toml").write_text("[budgets]\nasset_bytes=50\nbundle_bytes=100\nrequests=3\nreserve_bytes=0\nreserve_fraction=0.0\n")
    ws = Workspace.create(root)
    try:
        assert (ws.budgets.asset_bytes, ws.budgets.bundle_bytes, ws.budgets.requests) == (50, 100, 3)
        source = tmp_path / "larger.tsv"
        source.write_bytes(b"x" * 51)
        with pytest.raises(DawError, match="over_budget"):
            ws.local_asset(source)
    finally:
        ws.close()
