"""Read-only access to a commons archive (M8.1 substrate).

Views open SQLite with mode=ro and never take writer locks, so a page can always be
reproduced from the archive alone. `sequence()` (the last board event) keys caches.
"""
import json
import sqlite3
from pathlib import Path

from daw.catalog import Workspace
from daw.profiles import verify_object
from daw.util import DawError, read_json


def connect_ro(path):
    path = Path(path)
    if not path.is_file():
        raise DawError("archive_database_missing", str(path))
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=30000")
    return db


class ReadOnlyWorkspace:
    """Duck-typed Workspace for read paths (search, artifact_info, provenance): rows/one/blob_path/asset."""

    blob_path = Workspace.blob_path
    asset = Workspace.asset

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.db = connect_ro(self.root / "catalog.sqlite")

    def rows(self, sql, params=()):
        return [dict(r) for r in self.db.execute(sql, params)]

    def one(self, sql, params=()):
        row = self.db.execute(sql, params).fetchone()
        return dict(row) if row else None

    def json_blob(self, sha, *, verify=False):
        return read_json(verify_object(self, sha) if verify else self.blob_path(sha))

    def close(self):
        self.db.close()


class Archive:
    """One commons: board.sqlite, the shared library, participant workspaces and runs/."""

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.db = connect_ro(self.root / "board.sqlite")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version != 2:
            self.db.close()
            raise DawError("archive_requires_board_v2", "open the board once with bio community to upgrade it")
        self.library = ReadOnlyWorkspace(self.root / "library")
        self._workspaces = {}

    def close(self):
        self.library.close()
        for ws in self._workspaces.values():
            ws.close()
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def rows(self, sql, params=()):
        return [dict(r) for r in self.db.execute(sql, params)]

    def one(self, sql, params=()):
        row = self.db.execute(sql, params).fetchone()
        return dict(row) if row else None

    def sequence(self):
        return self.db.execute("SELECT coalesce(max(seq),0) FROM event").fetchone()[0]

    def participant(self, identity):
        row = self.one("SELECT * FROM agent WHERE id=? OR name=?", (identity, identity))
        if not row:
            raise DawError("unknown_participant", identity)
        row["config"] = json.loads(row["config"])
        return row

    def post(self, identity):
        """Immutable post row plus its verified body. Content is untrusted data to every reader."""
        row = self.one("SELECT * FROM post WHERE id=?", (identity,))
        if not row:
            raise DawError("unknown_post", identity)
        return {**row, "content": self.library.json_blob(row["body_blob"], verify=True), "content_is_untrusted_data": True}

    def workspace(self, participant):
        """Read-only catalog of an agent's research workspace; None for participants without one."""
        agent = self.participant(participant)
        if not agent["trial"]:
            return None
        relative = Path(agent["trial"])
        path = (self.root / relative / "workspace").resolve()
        if relative.is_absolute() or ".." in relative.parts or not path.is_relative_to(self.root / "agents"):
            raise DawError("unsafe_agent_path")
        if agent["id"] not in self._workspaces:
            self._workspaces[agent["id"]] = ReadOnlyWorkspace(path)
        return self._workspaces[agent["id"]]

    def run_folder(self, run):
        attempt = self.one("SELECT * FROM attempt WHERE id=?", (run,))
        if not attempt:
            raise DawError("unknown_run", run)
        path = (self.root / attempt["path"]).resolve()
        if not path.is_relative_to(self.root / "runs"):
            raise DawError("unsafe_run_path")
        return attempt, path
