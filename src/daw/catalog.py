"""One authoritative SQLite catalog and an immutable content-addressed store."""
import contextlib
import fcntl
import json
import os
import shutil
import sqlite3
import tempfile
import tomllib
import uuid
from pathlib import Path

from daw.models import Asset, Budgets
from daw.util import DawError, canonical, digest, file_hash, now, read_json, write_json

SCHEMA = """
CREATE TABLE IF NOT EXISTS resource (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, provider TEXT NOT NULL, native_id TEXT NOT NULL,
 body TEXT NOT NULL, created TEXT NOT NULL, UNIQUE(kind,provider,native_id));
CREATE TABLE IF NOT EXISTS blob (
 sha256 TEXT PRIMARY KEY, size INTEGER NOT NULL, path TEXT NOT NULL UNIQUE,
 classification TEXT NOT NULL, integrity TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshot (
 id TEXT PRIMARY KEY, resource_id TEXT REFERENCES resource(id), locator TEXT NOT NULL,
 retrieved TEXT NOT NULL, outcome TEXT NOT NULL, blob TEXT REFERENCES blob(sha256), body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS link (
 id TEXT PRIMARY KEY, subject TEXT NOT NULL REFERENCES resource(id),
 object TEXT NOT NULL REFERENCES resource(id), relationship TEXT NOT NULL,
 snapshot_id TEXT REFERENCES snapshot(id), locator TEXT NOT NULL, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS asset_revision (
 id TEXT PRIMARY KEY, resource_id TEXT NOT NULL REFERENCES resource(id),
 snapshot_id TEXT REFERENCES snapshot(id), blob TEXT REFERENCES blob(sha256),
 access TEXT NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS current_asset (
 resource_id TEXT PRIMARY KEY REFERENCES resource(id), revision TEXT NOT NULL REFERENCES asset_revision(id));
CREATE TABLE IF NOT EXISTS assertion (
 id TEXT PRIMARY KEY, subject TEXT NOT NULL REFERENCES resource(id), field TEXT NOT NULL,
 body TEXT NOT NULL, evidence_blob TEXT NOT NULL REFERENCES blob(sha256));
CREATE TABLE IF NOT EXISTS curation_revision (
 digest TEXT PRIMARY KEY, asset_revision TEXT NOT NULL REFERENCES asset_revision(id),
 selector TEXT NOT NULL, blob TEXT NOT NULL REFERENCES blob(sha256), supersedes TEXT,
 validation_blob TEXT NOT NULL REFERENCES blob(sha256), created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS current_curation (
 asset_revision TEXT NOT NULL REFERENCES asset_revision(id), selector TEXT NOT NULL,
 digest TEXT NOT NULL REFERENCES curation_revision(digest), PRIMARY KEY(asset_revision,selector));
CREATE TABLE IF NOT EXISTS inspection (
 id TEXT PRIMARY KEY, asset_revision TEXT NOT NULL REFERENCES asset_revision(id),
 status TEXT NOT NULL, blob TEXT NOT NULL REFERENCES blob(sha256), created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS run (
 id TEXT PRIMARY KEY, work_key TEXT NOT NULL, kind TEXT NOT NULL, state TEXT NOT NULL,
 input_blob TEXT NOT NULL REFERENCES blob(sha256), output_blob TEXT REFERENCES blob(sha256),
 created TEXT NOT NULL, finished TEXT, error TEXT, stale INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS run_dependency (
 run_id TEXT NOT NULL REFERENCES run(id), identity TEXT NOT NULL, PRIMARY KEY(run_id,identity));
CREATE TABLE IF NOT EXISTS capability (
 id TEXT PRIMARY KEY, asset_revision TEXT NOT NULL REFERENCES asset_revision(id), curation TEXT,
 name TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL, validator_run TEXT REFERENCES run(id));
CREATE INDEX IF NOT EXISTS asset_resource ON asset_revision(resource_id);
CREATE INDEX IF NOT EXISTS link_subject ON link(subject,relationship);
CREATE INDEX IF NOT EXISTS assertion_subject ON assertion(subject,field);
CREATE INDEX IF NOT EXISTS run_key ON run(work_key,state);
PRAGMA user_version=1;
"""

MIGRATION_2 = """
CREATE TABLE review_decision (
 id TEXT PRIMARY KEY, subject TEXT NOT NULL REFERENCES resource(id), field TEXT NOT NULL,
 selected_assertion TEXT NOT NULL REFERENCES assertion(id),
 body_blob TEXT NOT NULL REFERENCES blob(sha256), created TEXT NOT NULL);
CREATE TRIGGER immutable_review_update BEFORE UPDATE ON review_decision
 BEGIN SELECT RAISE(ABORT,'immutable history'); END;
CREATE TRIGGER immutable_review_delete BEFORE DELETE ON review_decision
 BEGIN SELECT RAISE(ABORT,'immutable history'); END;
PRAGMA user_version=2;
"""


class Workspace:
    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        if not (self.root / "catalog.sqlite").is_file():
            raise DawError("workspace_not_initialized", str(self.root))
        self.db = sqlite3.connect(self.root / "catalog.sqlite", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=30000")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        from daw.substrate_schema import MIGRATION, VERSION
        if version in {1, 2}:
            with self.writer():
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                migration = (MIGRATION_2 if version == 1 else "") + (MIGRATION if version < VERSION else "")
                self.db.executescript("BEGIN IMMEDIATE;\n" + migration + "\nCOMMIT;")
        elif version != VERSION:
            raise DawError("unsupported_catalog_version")
        for part in ("questions", "profiles"):
            (self.root / part).mkdir(exist_ok=True)
        config = tomllib.loads((self.root / "config.toml").read_text())
        self.budgets = Budgets.model_validate(config.get("budgets", {}))

    @classmethod
    def create(cls, root):
        root = Path(root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if (root / "catalog.sqlite").exists():
            for part in ("blobs/sha256", "staging", "proposals", "runs", "reports", "cache"):
                (root / part).mkdir(parents=True, exist_ok=True)
            return cls(root)
        for part in ("blobs/sha256", "staging", "proposals", "runs", "reports", "cache"):
            (root / part).mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(root / "catalog.sqlite") as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.executescript(SCHEMA)
            # History cannot be silently changed, even by an accidental UPDATE.
            for table in ("snapshot", "asset_revision", "assertion", "curation_revision", "inspection", "link", "capability"):
                for verb in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER immutable_{table}_{verb.lower()} BEFORE {verb} ON {table} "
                               "BEGIN SELECT RAISE(ABORT,'immutable history'); END")
        (root / "config.toml").write_text(
            '# Data stays local. Raw processing and downloaded code execution are disabled.\n'
            '# Zero means unlimited for asset_bytes, bundle_bytes and requests.\n'
            '[budgets]\nasset_bytes = 0\nbundle_bytes = 0\nrequests = 0\n'
            'reserve_bytes = 5368709120\nreserve_fraction = 0.1\n')
        return cls(root)

    def close(self):
        self.db.close()

    @contextlib.contextmanager
    def writer(self):
        with (self.root / ".writer.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as e:
                raise DawError("writer_busy", "another daw process owns this workspace") from e
            try:
                yield self
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def rows(self, sql, params=()):
        return [dict(r) for r in self.db.execute(sql, params)]

    def one(self, sql, params=()):
        row = self.db.execute(sql, params).fetchone()
        return dict(row) if row else None

    def check_disk(self, required=0):
        disk = shutil.disk_usage(self.root)
        reserve = max(self.budgets.reserve_bytes, int(disk.total * self.budgets.reserve_fraction))
        if disk.free - required < reserve:
            raise DawError("over_budget", "minimum free-disk reserve")

    def blob_path(self, sha: str) -> Path:
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise DawError("invalid_blob_hash")
        path = self.root / "blobs/sha256" / sha[:2] / sha
        if not path.is_file() or path.is_symlink():
            raise DawError("missing_blob", sha)
        return path

    def put_file(self, path, classification="full") -> str:
        path = Path(path)
        size = path.stat().st_size
        self.check_disk(size)
        sha = file_hash(path)
        destination = self.root / "blobs/sha256" / sha[:2] / sha
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            fd, temp = tempfile.mkstemp(dir=self.root / "staging")
            try:
                with os.fdopen(fd, "wb") as out, path.open("rb") as source:
                    shutil.copyfileobj(source, out)
                    out.flush()
                    os.fsync(out.fileno())
                if file_hash(Path(temp)) != sha:
                    raise DawError("source_changed_during_registration")
                os.chmod(temp, 0o444)
                os.replace(temp, destination)
                directory_fd = os.open(destination.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                if Path(temp).exists():
                    Path(temp).unlink()
        elif file_hash(destination) != sha:
            raise DawError("integrity_failed", "existing content-addressed blob was modified")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO blob VALUES(?,?,?,?,?)",
                            (sha, size, str(destination.relative_to(self.root)), classification, "verified"))
        return sha

    def put_bytes(self, data: bytes, classification="metadata"):
        fd, temp = tempfile.mkstemp(dir=self.root / "staging")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            return self.put_file(temp, classification)
        finally:
            Path(temp).unlink(missing_ok=True)

    def put_json(self, value, classification="metadata"):
        return self.put_bytes(canonical(value), classification)

    def resource(self, kind, provider, native_id, body=None):
        rid = f"{kind}_{digest([provider, native_id])[:24]}"
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO resource VALUES(?,?,?,?,?,?)",
                            (rid, kind, provider, native_id, canonical(body or {}).decode(), now()))
        return rid

    def snapshot(self, locator, outcome, body, blob=None, resource=None):
        sid = f"snap_{uuid.uuid4().hex}"
        with self.db:
            self.db.execute("INSERT INTO snapshot VALUES(?,?,?,?,?,?,?)",
                            (sid, resource, locator, now(), outcome, blob, canonical(body).decode()))
        return sid

    def link(self, subject, obj, relationship, snapshot=None, locator="", state="accepted"):
        lid = digest([subject, obj, relationship, snapshot, locator, state])
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO link VALUES(?,?,?,?,?,?,?)",
                            (lid, subject, obj, relationship, snapshot, locator, state))

    def register_asset(self, bundle, provider, asset: Asset, snapshot=None, blob=None, previous=None):
        rid = self.resource("asset", provider, asset.native_id)
        body = asset.model_dump()
        old = self.one("SELECT revision FROM current_asset WHERE resource_id=?", (rid,))
        if old and blob is None and asset.access == "listed" and (asset.checksum or provider == "archive"):
            prior = self.asset(old["revision"])
            # Only strong file identity permits reusing acquired bytes after metadata refresh.
            identity_fields = ("native_id", "name", "version", "size", "checksum", "checksum_scope", "selector", "license")
            # A bounded gzip inventory can omit expanded size. The exact parent
            # bytes and member selector already identify this representation;
            # losing a size estimate must not hide previously extracted bytes.
            if provider == "archive" and body["size"] is None and body["selector"].get("chain"):
                identity_fields = tuple(k for k in identity_fields if k != "size")
            unchanged = all(body.get(k) == prior["body"].get(k) for k in identity_fields)
            old_metadata = {k: v for k, v in prior["body"]["metadata"].items()
                            if k not in {"acquisition_reason", "source_metadata_snapshot", "listed_revision"}}
            if unchanged and old_metadata == body["metadata"] and prior["access"] == "available_full":
                self.link(bundle, rid, "contains", snapshot, asset.native_id)
                return old["revision"]
        aid = "asset_" + digest([rid, body, blob])[:32]
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO asset_revision VALUES(?,?,?,?,?,?,?)",
                            (aid, rid, snapshot, blob, asset.access, canonical(body).decode(), now()))
            self.db.execute("INSERT INTO current_asset VALUES(?,?) ON CONFLICT(resource_id) DO UPDATE SET revision=excluded.revision",
                            (rid, aid))
            if old and old["revision"] != aid:
                self.db.execute("UPDATE run SET stale=1 WHERE id IN (SELECT run_id FROM run_dependency WHERE identity=?)",
                                (old["revision"],))
            lid = digest([bundle, rid, "contains", snapshot, asset.native_id, "accepted"])
            self.db.execute("INSERT OR IGNORE INTO link VALUES(?,?,?,?,?,?,?)",
                            (lid, bundle, rid, "contains", snapshot, asset.native_id, "accepted"))
            if previous:
                parent = self.asset(previous)["resource_id"]
                locator = canonical(asset.selector).decode()
                lid = digest([rid, parent, "derived_from", snapshot, locator, "accepted"])
                self.db.execute("INSERT OR IGNORE INTO link VALUES(?,?,?,?,?,?,?)",
                                (lid, rid, parent, "derived_from", snapshot, locator, "accepted"))
        return aid

    def asset(self, aid):
        row = self.one("SELECT * FROM asset_revision WHERE id=?", (aid,))
        if not row:
            raise DawError("unknown_asset_revision", aid)
        row["body"] = json.loads(row["body"])
        return row

    def assets(self, scope=()):
        query = """SELECT a.* FROM asset_revision a JOIN current_asset c ON a.id=c.revision"""
        params = []
        if scope:
            marks = ",".join("?" for _ in scope)
            query += f" WHERE a.id IN ({marks}) OR a.resource_id IN ({marks}) OR a.resource_id IN (SELECT object FROM link WHERE subject IN ({marks}) AND relationship='contains')"
            params = list(scope) * 3
        rows = self.rows(query + " ORDER BY a.resource_id", params)
        for row in rows:
            row["body"] = json.loads(row["body"])
        return rows

    def bundle_for(self, asset):
        row = self.one("SELECT subject FROM link WHERE object=? AND relationship='contains' ORDER BY subject LIMIT 1",
                       (asset["resource_id"],))
        if not row:
            raise DawError("asset_has_no_bundle")
        return row["subject"]

    def local_asset(self, path, bundle_name="local"):
        path = Path(path).resolve()
        if self.budgets.asset_bytes and path.stat().st_size > self.budgets.asset_bytes:
            raise DawError("over_budget", "local file exceeds per-asset budget")
        bundle = self.resource("bundle", "local", bundle_name)
        sha = self.put_file(path)
        sid = self.snapshot(str(path), "available_full", {"source": "explicit_local_import"}, sha, bundle)
        aid = self.register_asset(bundle, "local", Asset(native_id=f"{bundle_name}:{path.name}",
                                  name=path.name, size=path.stat().st_size, access="available_full"), sid, sha)
        return {"bundle": bundle, "asset_revision": aid, "blob": sha}

    def start_run(self, kind, inputs):
        ib = self.put_json(inputs)
        key = digest({"kind": kind, "inputs": inputs})
        attempt = "run_" + uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO run(id,work_key,kind,state,input_blob,created) VALUES(?,?,?,?,?,?)",
                            (attempt, key, kind, "running", ib, now()))
        (self.root / "runs" / attempt).mkdir()
        return attempt, key

    def finish_run(self, attempt, output, error=None):
        ob = self.put_json(output)
        with self.db:
            self.db.execute("UPDATE run SET state=?,output_blob=?,finished=?,error=? WHERE id=? AND state='running'",
                            ("failed" if error else "succeeded", ob, now(), error, attempt))
        return ob

    def recover(self):
        interrupted = self.rows("SELECT id FROM run WHERE state='running'")
        with self.db:
            self.db.execute("UPDATE run SET state='interrupted',finished=?,error='process ended before acceptance' WHERE state='running'", (now(),))
        registered = []
        for path in (self.root / "blobs/sha256").glob("*/*"):
            if path.is_file() and not self.one("SELECT sha256 FROM blob WHERE sha256=?", (path.name,)):
                if file_hash(path) == path.name:
                    self.put_file(path, "recovered_orphan")
                    registered.append(path.name)
        return {"interrupted_runs": interrupted, "verified_orphans": registered,
                "staging_files": [str(p.relative_to(self.root)) for p in (self.root / "staging").rglob("*") if p.is_file()]}

    def backup(self, destination):
        dest = Path(destination).resolve()
        if dest.exists():
            raise DawError("destination_exists", str(dest))
        if dest == self.root or self.root in dest.parents:
            raise DawError("backup_must_be_outside_workspace")
        dest.mkdir(parents=True)
        with sqlite3.connect(dest / "catalog.sqlite") as target:
            self.db.backup(target)
        shutil.copy2(self.root / "config.toml", dest / "config.toml")
        with sqlite3.connect(dest / "catalog.sqlite") as snapshot:
            blobs = snapshot.execute("SELECT sha256,path,size FROM blob ORDER BY sha256").fetchall()
        manifest = []
        for sha, relative, size in blobs:
            source = self.blob_path(sha)
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if file_hash(target) != sha:
                raise DawError("backup_integrity_failed", sha)
            manifest.append({"sha256": sha, "path": relative, "size": size})
        work_files = []
        questions = self.root / "questions"
        if questions.is_symlink():
            raise DawError("unsafe_question_path")
        for source in sorted(questions.rglob("*")):
            if source.is_symlink():
                raise DawError("unsafe_backup_symlink", str(source.relative_to(self.root)))
            if not source.is_file():
                continue
            relative = source.relative_to(self.root)
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            expected = file_hash(source)
            shutil.copyfile(source, target)
            if file_hash(target) != expected:
                raise DawError("backup_source_changed", str(relative))
            work_files.append({"path": str(relative), "sha256": expected, "size": target.stat().st_size})
        write_json(dest / "backup.json", {"created": now(), "catalog_sha256": file_hash(dest / "catalog.sqlite"),
                                         "blobs": manifest, "work_files": work_files})
        return {"path": str(dest), "blobs": len(manifest), "work_files": len(work_files)}


def restore_check(backup):
    backup = Path(backup).resolve()
    manifest = read_json(backup / "backup.json")
    failures = []
    if file_hash(backup / "catalog.sqlite") != manifest["catalog_sha256"]:
        failures.append("catalog checksum")
    with tempfile.TemporaryDirectory(prefix="daw-restore-") as tmp:
        root = Path(tmp) / "restored"
        shutil.copytree(backup, root)
        for part in ("staging", "runs", "reports", "cache", "proposals"):
            (root / part).mkdir(exist_ok=True)
        ws = Workspace(root)
        try:
            if ws.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                failures.append("SQLite integrity_check")
            if ws.rows("PRAGMA foreign_key_check"):
                failures.append("foreign keys")
            for item in manifest["blobs"]:
                try:
                    path = ws.blob_path(item["sha256"])
                    if path.stat().st_size != item["size"] or file_hash(path) != item["sha256"]:
                        failures.append(item["sha256"])
                except DawError:
                    failures.append(item["sha256"])
            catalog_hashes = {r["sha256"] for r in ws.rows("SELECT sha256 FROM blob")}
            if catalog_hashes != {b["sha256"] for b in manifest["blobs"]}:
                failures.append("manifest/catalog mismatch")
            inventory = len(ws.assets())
            for item in manifest.get("work_files", []):
                path = ws.root / item["path"]
                if not path.resolve().is_relative_to(ws.root) or not path.is_file() or file_hash(path) != item["sha256"]:
                    failures.append(item["path"])
        finally:
            ws.close()
    return {"ok": not failures, "failures": failures, "verified_blobs": len(manifest["blobs"]),
            "restored_assets": inventory, "verified_work_files": len(manifest.get("work_files", [])),
            "test": "copied backup into independent temporary workspace"}
