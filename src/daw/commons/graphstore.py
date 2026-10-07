"""Persistent graph store (spec v2 V6): the evidence map's recorded operations on disk, keyed by event sequence.

The evidence map is built from segments of recorded operations (`daw.commons.evidence_map.record_segment`):
board agents, the library catalog, each workspace catalog, posts, notebook links, answered requests, board
events, claims, marks and frontier items. This module keeps those operations in a derived SQLite database,
`<commons>/cache/graph/graph.sqlite`, so the map replays stored operations instead of re-reading every store,
and one node (`/api/map/node/{id}`, `/api/artifacts/{id}`) is answered from the operations that touch it
(indexed by identity): constant work per node, whatever the size of the board.

Never authoritative. Deleting the directory loses nothing; `refresh(full=True)` rebuilds it from the archive,
and every answer equals the in-memory build (a test compares them on the demo and the cohort).

Freshness. Posts and events are immutable, so their segments grow by sequence (`covered` is the last post or
event sequence folded in). Workspace and library catalogs change without board events, so each catalog
segment records the catalog file's stat (size and mtime of catalog.sqlite and its WAL) and a content
fingerprint (row counts and latest timestamps); a stat change with an unchanged content fingerprint is not a
change. The small board tables (agents, answered requests, claims, marks, frontier items) carry aggregate
fingerprints.

Reads write no record (spec v2 C3, v3 B16: a disposable cache may be written). GET handlers open the store
read-only (rollback journal, `mode=ro`, so a reader creates no file). The map is served from the stored merged
graph (parsed once per store version and process, copied per request) with an incremental merge for the stale
tail (spec v3 B11): segments behind the archive or stale are computed in memory (the post and event deltas past
`covered`, or the whole segment for a changed catalog or board table, memoized per process by fingerprint), and
only the nodes and edges their operations touch (stored and new) are replayed again, in segment order. Nothing
replays every operation per request while a store exists.

The store is built at first serve in the background (`ensure_soon`, from `create_app(graph_store=True)`, which
`bio commons serve` and `host` use), and updated by write paths: the HTTP write layer schedules a refresh after
a successful write (`install`), the runtime refreshes after each delivery, `bio commons serve --graph-refresh N`
refreshes on an interval, and `bio commons graph refresh [--full]` is the operator command. A refresh holds a
`refresh.lock` beside the store, rewrites only the segments whose fingerprint changed, and a full rebuild writes
a new file that replaces the old one atomically.

Location. `<commons>/cache/graph/graph.sqlite` (ignored by git and by `fixture verify`). When that directory
cannot be written (a read-only commons) the store lives in a disposable per-commons directory outside it,
`$COLLOQUY_CACHE_DIR/graph/<sha256(root)[:16]>/` (default `~/.cache/colloquy`), so a read-only commons is still
served from a store and its bytes stay untouched. `/api/map/store` reports where, how old and how complete it is.
"""
import hashlib
import json
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path

from daw.util import DawError, digest, now

VERSION = 1
FILE = "graph.sqlite"
CATALOG_QUERIES = ("SELECT count(*), max(created) FROM artifact", "SELECT count(*) FROM artifact_input",
                   "SELECT count(*), max(created) FROM work_event", "SELECT count(*), max(updated) FROM question",
                   "SELECT count(*) FROM asset_revision", "SELECT count(*) FROM snapshot",
                   "SELECT count(*) FROM work_snapshot", "SELECT count(*) FROM question_artifact")
BOARD_QUERIES = {
    "board:agents": "SELECT id,name,kind,parent,trial,created FROM agent ORDER BY created,id",
    "board:requests": "SELECT count(*) AS n, max(updated) AS m, count(DISTINCT answer) AS a FROM request "
                      "WHERE answer IS NOT NULL",
    # Claim nodes carry verified pointer counts from recorded write-up verdicts (`writeup_check` events, V2).
    "board:claims": "SELECT count(*) AS n, max(created) AS m, count(withdrawn_by) AS w, total(length(status)) AS s, "
                    "(SELECT coalesce(max(seq),0) FROM event WHERE kind='writeup_check') AS v FROM claim",
    "board:marks": "SELECT count(*) AS n, max(created) AS m FROM mark",
    "board:frontier": "SELECT count(*) AS n, max(created) AS c, max(updated) AS u, total(length(status)) AS s, "
                      "count(promoted_to) AS p, total(length(text)) AS t FROM frontier_item",
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS segment (name TEXT PRIMARY KEY, fingerprint TEXT, stat TEXT, covered INTEGER,
  ops INTEGER NOT NULL, refreshed TEXT NOT NULL, seconds REAL);
CREATE TABLE IF NOT EXISTS op (segment TEXT NOT NULL, n INTEGER NOT NULL, kind TEXT NOT NULL, a TEXT, b TEXT,
  relation TEXT, guard TEXT, payload TEXT NOT NULL, PRIMARY KEY(segment, n));
CREATE INDEX IF NOT EXISTS op_a ON op(a);
CREATE INDEX IF NOT EXISTS op_b ON op(b, relation);
CREATE TABLE IF NOT EXISTS post_notebook (post TEXT PRIMARY KEY, seq INTEGER NOT NULL, author TEXT, question TEXT,
  snapshot TEXT, created TEXT, body_blob TEXT);
CREATE TABLE IF NOT EXISTS named (artifact TEXT NOT NULL, post TEXT NOT NULL, seq INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS named_artifact ON named(artifact, seq);
CREATE TABLE IF NOT EXISTS fetched (artifact TEXT NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY(artifact, seq));
CREATE INDEX IF NOT EXISTS op_guard ON op(guard);
-- The merged graph as a reader with nothing hidden sees it; hidden posts are applied at read time.
CREATE TABLE IF NOT EXISTS merged_node (id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS merged_edge (source TEXT NOT NULL, target TEXT NOT NULL, relation TEXT NOT NULL,
  body TEXT NOT NULL, PRIMARY KEY(source, target, relation));
"""
_MEMO: "OrderedDict[tuple, tuple]" = OrderedDict()
_MEMO_SIZE = 64
_MEMO_LOCK = threading.Lock()
_BASE: dict = {}  # store file -> (version key, parsed merged graph)


def _primary(root):
    return Path(root).expanduser().resolve() / "cache" / "graph" / FILE


def _fallback(root):
    """The disposable store of a commons whose own cache directory cannot be written (read-only)."""
    base = Path(os.environ.get("COLLOQUY_CACHE_DIR") or Path.home() / ".cache" / "colloquy").expanduser()
    key = hashlib.sha256(str(Path(root).expanduser().resolve()).encode()).hexdigest()[:16]
    return base.resolve() / "graph" / key / FILE


def _writable(directory):
    """Whether a directory exists writable or could be created (its nearest existing ancestor is writable)."""
    probe = Path(directory)
    while not probe.exists():
        if probe.parent == probe:
            return False
        probe = probe.parent
    return probe.is_dir() and os.access(probe, os.W_OK | os.X_OK)


def _target(root):
    """Where a refresh writes: the commons' own cache when it can be written, else the per-commons fallback."""
    primary = _primary(root)
    return primary if _writable(primary.parent) else _fallback(root)


def location(root):
    """Where readers find the store: the refresh target, or a store the read-only commons already carries while
    the fallback has not been built yet."""
    target, primary = _target(root), _primary(root)
    return primary if target != primary and not target.is_file() and primary.is_file() else target


# ---------------------------------------------------------------------------- fingerprints

def _stat(path):
    out = []
    for candidate in (path, Path(str(path) + "-wal")):
        try:
            st = os.stat(candidate)
            out.append([st.st_mtime_ns, st.st_size])
        except OSError:
            out.append(None)
    return out


def catalog_store(view, name):
    """The read-only catalog behind a library or workspace segment, or None when it does not open."""
    if name == "library":
        return view.library
    try:
        return view.workspace(name.split(":", 1)[1])
    except DawError:
        return None


def catalog_content(ws):
    values = []
    for sql in CATALOG_QUERIES:
        try:
            values.append(list(ws.db.execute(sql).fetchone()))
        except sqlite3.Error:
            values.append(None)
    return digest(values)


class Fingerprints:
    """Current fingerprints of the archive's segments, computed lazily; catalog content only on a stat change."""

    def __init__(self, view, stored=None):
        self.view, self.stored, self.cache, self.trials = view, stored or {}, {}, None

    def path(self, name):
        """catalog.sqlite behind a catalog segment, found without opening it (the same checks as Archive)."""
        if name == "library":
            return self.view.root / "library" / "catalog.sqlite"
        if self.trials is None:
            self.trials = {r["id"]: r["trial"] for r in self.view.rows("SELECT id,trial FROM agent WHERE trial IS NOT NULL")}
        trial = self.trials.get(name.split(":", 1)[1])
        if not trial:
            return None
        relative = Path(trial)
        path = self.view.root / relative / "workspace"
        if relative.is_absolute() or ".." in relative.parts or not path.resolve().is_relative_to(self.view.root / "agents"):
            return None
        return path / "catalog.sqlite"

    def catalog(self, name):
        if name in self.cache:
            return self.cache[name]
        path = self.path(name)
        if path is None or not path.is_file():
            value = (None, None)
        else:
            stat = _stat(path)
            row = self.stored.get(name)
            if row and row["stat"] == json.dumps(stat) and row["fingerprint"] is not None:
                value = (row["fingerprint"], stat)  # unchanged file: unchanged content, nothing opened
            else:
                ws = catalog_store(self.view, name)
                value = (catalog_content(ws) if ws is not None else None, stat)
        self.cache[name] = value
        return value

    def covered(self, name):
        if name not in self.cache:
            table = "post" if name == "board:posts" else "event"
            self.cache[name] = self.view.one(f"SELECT coalesce(max(seq),0) AS s FROM {table}")["s"]
        return self.cache[name]

    def board(self, name):
        if name not in self.cache:
            self.cache[name] = digest(self.view.rows(BOARD_QUERIES[name]))
        return self.cache[name]

    def notebooks(self, order):
        if "board:notebooks" not in self.cache:
            self.cache["board:notebooks"] = digest([
                [name, self.catalog(name)[0]] for name in order if name.startswith("workspace:")])
        return self.cache["board:notebooks"]

    def of(self, name, order):
        """(fingerprint, stat, covered) of one segment as the archive is now."""
        if name in ("board:posts", "board:events"):
            return None, None, self.covered(name)
        if name == "library" or name.startswith("workspace:"):
            fingerprint, stat = self.catalog(name)
            return fingerprint, stat, None
        if name == "board:notebooks":
            return self.notebooks(order), None, None
        return self.board(name), None, None


def catalog_fingerprints(view):
    """[[segment, content fingerprint]] for the library and every workspace catalog, in map order. With a graph
    store, an unchanged catalog file is not opened (its recorded fingerprint stands)."""
    from daw.commons.evidence_map import segment_order
    store = reader(view)
    prints = store.prints if store is not None else Fingerprints(view)
    order = store.order if store is not None else segment_order(view)
    return [[name, prints.catalog(name)[0]] for name in order if name == "library" or name.startswith("workspace:")]


# ---------------------------------------------------------------------------- reading (never writes)

def _connect_ro(path):
    db = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    return db


def _op(row):
    return (row["kind"], row["a"], row["b"], row["relation"], row["guard"], json.loads(row["payload"]))


def _memo(key, compute):
    with _MEMO_LOCK:
        if key in _MEMO:
            _MEMO.move_to_end(key)
            return _MEMO[key]
    value = compute()
    with _MEMO_LOCK:
        _MEMO[key] = value
        while len(_MEMO) > _MEMO_SIZE:
            _MEMO.popitem(last=False)
    return value


class Reader:
    """The graph store as of this archive: stored operations for current segments, in-memory ones for the rest."""

    def __init__(self, view, db):
        from daw.commons.evidence_map import segment_order
        self.view, self.db = view, db
        self.stored = {r["name"]: r for r in db.execute("SELECT * FROM segment")}
        self.order = segment_order(view)
        self.rank = {name: i for i, name in enumerate(self.order)}
        self.prints = Fingerprints(view, self.stored)
        self._state, self._memory, self._workspaces = {}, {}, None

    def close(self):
        self.db.close()

    # ------------------------------------------------------------ freshness
    def state(self, name):
        """'fresh', 'behind' (posts or events: stored plus a delta) or 'stale' (computed in memory)."""
        if name not in self._state:
            row = self.stored.get(name)
            fingerprint, _, covered = self.prints.of(name, self.order)
            if row is None:
                value = "stale"
            elif name == "board:notebooks":
                # Notebook links depend on the workspaces (fingerprint) and grow with posts (covered).
                posts = self.prints.covered("board:posts")
                value = ("stale" if fingerprint != row["fingerprint"] or posts < (row["covered"] or 0)
                         else "fresh" if posts == row["covered"] else "behind")
            elif covered is not None:
                value = "fresh" if covered == row["covered"] else "behind" if covered > (row["covered"] or 0) else "stale"
            else:
                value = "fresh" if fingerprint == row["fingerprint"] else "stale"
            self._state[name] = value
        return self._state[name]

    def status(self):
        return {name: self.state(name) for name in self.order}

    def _workspace_map(self):
        if self._workspaces is None:
            from daw.commons.evidence_map import open_workspaces
            self._workspaces = open_workspaces(self.view)
        return self._workspaces

    def _notebook_refs(self):
        state = self.state("board:posts")
        refs = [] if state == "stale" else [dict(r) for r in self.db.execute("SELECT * FROM post_notebook ORDER BY seq")]
        if state != "fresh":
            refs += self._delta("board:posts")[1]
        return refs

    def _delta(self, name):
        """(ops, extra) of a segment computed in memory: the whole segment, or only past `covered`."""
        if name in self._memory:
            return self._memory[name]
        from daw.commons.evidence_map import Recorder, record_segment, segment_notebooks
        state = self.state(name)
        after = (self.stored[name]["covered"] or 0) if state == "behind" else 0
        fingerprint, _, covered = self.prints.of(name, self.order)
        key = (str(self.view.root), name, fingerprint, covered, after)
        if name == "board:notebooks":
            def compute():
                graph = Recorder()
                refs = self._notebook_refs()
                if state == "behind":
                    refs = [r for r in refs if r["seq"] > (self.stored[name]["covered"] or 0)]
                segment_notebooks(self.view, graph, refs, self._workspace_map())
                return graph.ops, None
        else:
            def compute():
                return record_segment(self.view, name, workspaces=self._workspace_map(), after=after)
        value = _memo(key, compute) if name != "board:notebooks" else compute()
        self._memory[name] = value
        return value

    # ------------------------------------------------------------ operations
    def ops_of(self, name):
        state = self.state(name)
        ops = []
        if state in ("fresh", "behind"):
            ops = [_op(r) for r in self.db.execute("SELECT * FROM op WHERE segment=? ORDER BY n", (name,))]
        if state != "fresh":
            ops += self._delta(name)[0]
        return ops

    def all_ops(self):
        return [op for name in self.order for op in self.ops_of(name)]

    def _base(self):
        """The stored merged graph, parsed once per store version per process (callers get copies)."""
        meta = {r["key"]: r["value"] for r in self.db.execute("SELECT key,value FROM meta")}
        path = self.db.execute("PRAGMA database_list").fetchone()["file"]
        key = ("merged", path, meta.get("refreshed"), meta.get("sequence"), json.dumps(_stat(Path(path))))

        with _MEMO_LOCK:
            held = _BASE.get(path)
        if held and held[0] == key:
            return held[1]
        nodes = {r["id"]: json.loads(r["body"]) for r in self.db.execute("SELECT id,body FROM merged_node")}
        edges = {(r["source"], r["target"], r["relation"]): json.loads(r["body"])
                 for r in self.db.execute("SELECT source,target,relation,body FROM merged_edge")}
        with _MEMO_LOCK:
            _BASE[path] = (key, (nodes, edges))  # one version per store file: a refresh replaces it
        return nodes, edges

    def _key_ops(self, memory, states, *, node=None, edge=None):
        """Every operation for one node or edge in replay order: stored operations of segments that are not stale,
        then the in-memory operations (a stale segment's whole set, a behind segment's delta past `covered`)."""
        if node is not None:
            rows = self.db.execute("SELECT * FROM op WHERE a=? AND kind IN ('node','placeholder')", (node,)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM op WHERE a=? AND b=? AND relation=?", edge).fetchall()
        found = [(self.rank[r["segment"]], 0, r["n"], _op(r)) for r in rows
                 if r["segment"] in self.rank and states.get(r["segment"]) != "stale"]
        for name, (by_node, by_edge) in memory.items():
            for n, op in (by_node.get(node, ()) if node is not None else by_edge.get(edge, ())):
                found.append((self.rank[name], 1, n, op))
        found.sort(key=lambda item: item[:3])
        return [op for *_, op in found]

    def graph(self, vis):
        """The full graph for this caller: the stored merged graph with an incremental merge (spec v3 B11). The
        nodes and edges touched by a hidden post's guarded operations, by a stale segment's stored and recomputed
        operations, and by the deltas of segments behind the archive are replayed from their own operations in
        segment order; every other node and edge is the stored merged row."""
        from daw.commons.evidence_map import Graph, replay
        states = self.status()
        nodes_base, edges_base = self._base()
        graph = Graph()
        graph.nodes = {k: {**v, "stores": list(v.get("stores", []))} for k, v in nodes_base.items()}
        graph.edges = {k: {**v, "records": list(v.get("records", []))} for k, v in edges_base.items()}
        memory, nodes, edges = {}, set(), set()
        for name in self.order:
            if states[name] == "fresh":
                continue
            ops = self._delta(name)[0]
            by_node, by_edge = {}, {}
            for n, op in enumerate(ops):
                if op[0] == "edge":
                    by_edge.setdefault((op[1], op[2], op[3]), []).append((n, op))
                else:
                    by_node.setdefault(op[1], []).append((n, op))
            memory[name] = (by_node, by_edge)
            _keys(ops, nodes, edges)
            if states[name] == "stale" and name in self.stored:
                _keys(self.db.execute("SELECT kind,a,b,relation FROM op WHERE segment=?", (name,)), nodes, edges)
        for post in vis.records:
            nodes.add(post)
            _keys(self.db.execute("SELECT kind,a,b,relation FROM op WHERE guard=?", (post,)), nodes, edges)
            for by_node, by_edge in memory.values():
                _keys([op for ops in (*by_node.values(), *by_edge.values()) for _, op in ops if op[4] == post],
                      nodes, edges)
        for identity in nodes:
            graph.nodes.pop(identity, None)
            replay(self._key_ops(memory, states, node=identity), vis, graph)
        for key in edges:
            graph.edges.pop(key, None)
            replay(self._key_ops(memory, states, edge=key), vis, graph)
        return graph

    def touching(self, identity, *, relation=None, side=None, kind=None):
        """Operations whose subject (a) or target (b) is `identity`, in replay order: [(segment, op)]."""
        found = []
        clauses = []
        extra = (" AND relation=?" if relation else "") + (" AND kind=?" if kind else "")
        params = (identity,) + ((relation,) if relation else ()) + ((kind,) if kind else ())
        if side in (None, "a"):
            clauses.append(("SELECT * FROM op WHERE a=?" + extra, params))
        if side in (None, "b"):
            clauses.append(("SELECT * FROM op WHERE b=?" + extra, params))
        seen = set()
        for sql, params in clauses:
            for row in self.db.execute(sql, params):
                name = row["segment"]
                if (name, row["n"]) in seen or name not in self.rank or self.state(name) == "stale":
                    continue
                seen.add((name, row["n"]))
                found.append((self.rank[name], 0, row["n"], name, _op(row)))
        for name in self.order:
            if self.state(name) == "fresh":
                continue
            for n, op in enumerate(self._delta(name)[0]):
                if (relation is None or op[3] == relation) and (kind is None or op[0] == kind) and (
                        (side in (None, "a") and op[1] == identity) or (side in (None, "b") and op[2] == identity)):
                    found.append((self.rank[name], 1, n, name, op))
        found.sort(key=lambda item: item[:3])
        return [(name, op) for *_, name, op in found]

    def holders(self, identity):
        """Catalog segments holding a recorded node for `identity` (library first, then workspaces in map order)."""
        out = []
        for name, op in self.touching(identity, side="a", kind="node"):
            if op[0] == "node" and op[5].get("present", True) and op[5].get("store") == name and name not in out:
                out.append(name)
        return out

    def posts_naming(self, artifact):
        rows = [] if self.state("board:events") == "stale" else [
            r["post"] for r in self.db.execute("SELECT post FROM named WHERE artifact=? ORDER BY seq", (artifact,))]
        if self.state("board:events") != "fresh":
            rows += [post for a, post, _ in self._delta("board:events")[1][0] if a == artifact]
        return rows

    def fetch_events(self, artifact):
        seqs = [] if self.state("board:events") == "stale" else [
            r["seq"] for r in self.db.execute("SELECT seq FROM fetched WHERE artifact=? ORDER BY seq", (artifact,))]
        if self.state("board:events") != "fresh":
            seqs += sorted({seq for a, seq in self._delta("board:events")[1][1] if a == artifact})
        return seqs


def reader(view):
    """The graph store as this archive sees it, or None when there is no usable store (then callers build in
    memory). Cached on the archive for the request; opened read-only."""
    cached = view.extras.get("graphstore") if hasattr(view, "extras") else None
    if cached is not None:
        return cached or None
    path = location(view.root)
    value = False
    if path.is_file():
        db = None
        try:
            db = _connect_ro(path)
            version = db.execute("SELECT value FROM meta WHERE key='version'").fetchone()
            if version and version[0] == str(VERSION):
                value = Reader(view, db)
            else:
                db.close()
        except sqlite3.Error:
            if db is not None:
                db.close()
            value = False
    if hasattr(view, "extras"):
        view.extras["graphstore"] = value
    return value or None


def neighbourhood(view, identity, vis):
    """The map node for `identity` and every edge touching it, replayed from the store for this caller (the
    same node and edges the full map draws), or None without a store."""
    from daw.commons.evidence_map import RELATIONS, Graph, _label_withheld, replay
    store = reader(view)
    if store is None:
        return None
    touching = store.touching(identity)
    graph = replay([op for _, op in touching if op[0] != "node" and op[0] != "placeholder" or op[1] == identity],
                   vis, Graph())
    node = graph.nodes.get(identity)
    if node is None:
        return {"node": None, "edges": []}
    node["stores"].sort()
    edges = sorted((e for e in graph.edges.values() if identity in (e["source"], e["target"])),
                   key=lambda e: (e["source"], e["target"], e["relation"]))
    newer = sorted(e["source"] for e in edges if e["relation"] == "supersedes" and e["target"] == identity)
    if newer:
        node["superseded_by"] = newer
        node["label"] = f"{node['label']} (superseded)"
    for edge in edges:
        if edge["relation"] == "supersedes":
            continue
        if edge["target"] == identity:
            into = newer
        elif not str(edge["target"]).startswith("post_"):
            continue  # only posts are superseded
        else:
            ops = [op for _, op in store.touching(edge["target"], relation="supersedes", side="b")]
            into = sorted(e["source"] for e in replay(ops, vis, Graph()).edges.values())
        if into:
            edge["into_superseded"] = into
    _label_withheld(vis, graph)  # C5: a refused write-up is a placeholder here too (after superseded, as in build)
    return {"node": node, "edges": edges,
            "relations": {e["relation"]: RELATIONS[e["relation"]][1] for e in edges}}


# ---------------------------------------------------------------------------- writing (write paths only)

def _connect_rw(path):
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=DELETE")  # readers open mode=ro and must not create -wal/-shm files
    db.execute("PRAGMA busy_timeout=30000")
    db.executescript(SCHEMA)
    return db


def _keys(ops, nodes, edges):
    """Collect the node identities and edge keys a list of operations (tuples or op rows) contributes to."""
    for op in ops:
        kind, a, b, relation = (op[0], op[1], op[2], op[3]) if isinstance(op, tuple) else (
            op["kind"], op["a"], op["b"], op["relation"])
        if kind == "edge":
            edges.add((a, b, relation))
        else:
            nodes.add(a)


def _write_segment(db, name, ops, fingerprint, stat, covered, seconds, *, append=False, affected=None):
    start = 0
    if append:
        start = db.execute("SELECT coalesce(max(n)+1,0) FROM op WHERE segment=?", (name,)).fetchone()[0]
    else:
        if affected is not None:
            _keys(db.execute("SELECT kind,a,b,relation FROM op WHERE segment=?", (name,)), *affected)
        db.execute("DELETE FROM op WHERE segment=?", (name,))
    if affected is not None:
        _keys(ops, *affected)
    db.executemany("INSERT INTO op(segment,n,kind,a,b,relation,guard,payload) VALUES(?,?,?,?,?,?,?,?)",
                   [(name, start + i, kind, a, b, relation, guard, json.dumps(payload, separators=(",", ":"),
                                                                               ensure_ascii=False))
                    for i, (kind, a, b, relation, guard, payload) in enumerate(ops)])
    total = db.execute("SELECT count(*) FROM op WHERE segment=?", (name,)).fetchone()[0]
    db.execute("INSERT INTO segment(name,fingerprint,stat,covered,ops,refreshed,seconds) VALUES(?,?,?,?,?,?,?) "
               "ON CONFLICT(name) DO UPDATE SET fingerprint=excluded.fingerprint,stat=excluded.stat,"
               "covered=excluded.covered,ops=excluded.ops,refreshed=excluded.refreshed,seconds=excluded.seconds",
               (name, fingerprint, json.dumps(stat) if stat is not None else None, covered, total, now(),
                round(seconds, 4)))
    return total


def _ordered(rows, rank):
    return [_op(r) for r in sorted(rows, key=lambda r: (rank.get(r["segment"], len(rank)), r["n"]))]


def key_ops(db, rank, *, node=None, edge=None):
    """Every stored operation for one node identity or one edge key, in replay order."""
    if node is not None:
        rows = db.execute("SELECT * FROM op WHERE a=? AND kind IN ('node','placeholder')", (node,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM op WHERE a=? AND b=? AND relation=?", edge).fetchall()
    return _ordered(rows, rank)


def _merge_keys(db, rank, nodes, edges):
    """Recompute the merged rows (as a reader with nothing hidden sees them) for the given keys."""
    from daw.commons.evidence_map import Graph, replay
    from daw.commons.moderation import Visibility
    everyone = Visibility()
    for identity in nodes:
        graph = replay(key_ops(db, rank, node=identity), everyone, Graph())
        node = graph.nodes.get(identity)
        if node is None:
            db.execute("DELETE FROM merged_node WHERE id=?", (identity,))
        else:
            db.execute("INSERT OR REPLACE INTO merged_node(id,body) VALUES(?,?)", (identity, json.dumps(node)))
    for key in edges:
        graph = replay(key_ops(db, rank, edge=key), everyone, Graph())
        edge = graph.edges.get(key)
        if edge is None:
            db.execute("DELETE FROM merged_edge WHERE source=? AND target=? AND relation=?", key)
        else:
            db.execute("INSERT OR REPLACE INTO merged_edge(source,target,relation,body) VALUES(?,?,?,?)",
                       (*key, json.dumps(edge)))


def _merge_all(db, rank):
    from daw.commons.evidence_map import Graph, replay
    from daw.commons.moderation import Visibility
    db.execute("DELETE FROM merged_node")
    db.execute("DELETE FROM merged_edge")
    graph = replay(_ordered(db.execute("SELECT * FROM op").fetchall(), rank), Visibility(), Graph())
    db.executemany("INSERT INTO merged_node(id,body) VALUES(?,?)",
                   [(identity, json.dumps(node)) for identity, node in graph.nodes.items()])
    db.executemany("INSERT INTO merged_edge(source,target,relation,body) VALUES(?,?,?,?)",
                   [(*key, json.dumps(edge)) for key, edge in graph.edges.items()])
    return len(graph.nodes), len(graph.edges)


def _update(db, view, *, full):
    """Bring the store in `db` up to the archive; returns {segment: action}. Segment operations are rewritten
    only when their fingerprint changed (posts and events are appended past `covered`), and the merged graph
    is recomputed for exactly the nodes and edges those operations touch."""
    from daw.commons.evidence_map import Recorder, open_workspaces, record_segment, segment_notebooks, segment_order
    stored = {r["name"]: dict(r) for r in db.execute("SELECT * FROM segment")}
    prints = Fingerprints(view, {} if full else stored)
    order = segment_order(view)
    rank = {name: i for i, name in enumerate(order)}
    workspaces = open_workspaces(view)
    report = {}
    affected = None if full else (set(), set())
    db.execute("BEGIN IMMEDIATE")
    try:
        for name in set(stored) - set(order):
            if affected is not None:
                _keys(db.execute("SELECT kind,a,b,relation FROM op WHERE segment=?", (name,)), *affected)
            db.execute("DELETE FROM op WHERE segment=?", (name,))
            db.execute("DELETE FROM segment WHERE name=?", (name,))
            report[name] = {"action": "removed"}
        for name in order:
            began = time.perf_counter()
            fingerprint, stat, covered = prints.of(name, order)
            row = None if full else stored.get(name)
            if name in ("board:posts", "board:events"):
                after = row["covered"] if row and row["covered"] is not None and row["covered"] <= covered else 0
                if row and after == covered:
                    report[name] = {"action": "kept", "ops": row["ops"]}
                    continue
                if not after:
                    if name == "board:posts":
                        db.execute("DELETE FROM post_notebook")
                    else:
                        db.execute("DELETE FROM named")
                        db.execute("DELETE FROM fetched")
                ops, extra = record_segment(view, name, workspaces=workspaces, after=after)
                if name == "board:posts":
                    db.executemany("INSERT OR REPLACE INTO post_notebook(post,seq,author,question,snapshot,created,"
                                   "body_blob) VALUES(:post,:seq,:author,:question,:snapshot,:created,:body_blob)", extra)
                else:
                    named, fetched = extra
                    db.executemany("INSERT INTO named(artifact,post,seq) VALUES(?,?,?)", named)
                    db.executemany("INSERT OR IGNORE INTO fetched(artifact,seq) VALUES(?,?)", fetched)
                total = _write_segment(db, name, ops, None, None, covered, time.perf_counter() - began,
                                       append=bool(after), affected=affected)
                report[name] = {"action": "appended" if after else "built", "ops": total, "added": len(ops),
                                "seconds": round(time.perf_counter() - began, 4)}
                continue
            if name == "board:notebooks":
                posts = prints.covered("board:posts")
                after = row["covered"] if row and row["fingerprint"] == fingerprint and (row["covered"] or 0) <= posts else None
                if after == posts:
                    report[name] = {"action": "kept", "ops": row["ops"]}
                    continue
                refs = [dict(r) for r in db.execute("SELECT * FROM post_notebook WHERE seq>? ORDER BY seq", (after or 0,))]
                graph = Recorder()
                segment_notebooks(view, graph, refs, workspaces)
                total = _write_segment(db, name, graph.ops, fingerprint, None, posts, time.perf_counter() - began,
                                       append=after is not None, affected=affected)
                report[name] = {"action": "appended" if after is not None else "rebuilt" if row else "built",
                                "ops": total, "seconds": round(time.perf_counter() - began, 4)}
                continue
            if row and row["fingerprint"] == fingerprint:
                if stat is not None and row["stat"] != json.dumps(stat):
                    db.execute("UPDATE segment SET stat=? WHERE name=?", (json.dumps(stat), name))
                report[name] = {"action": "kept", "ops": row["ops"]}
                continue
            ops, _ = record_segment(view, name, workspaces=workspaces)
            total = _write_segment(db, name, ops, fingerprint, stat, None, time.perf_counter() - began,
                                   affected=affected)
            report[name] = {"action": "rebuilt" if row else "built", "ops": total,
                            "seconds": round(time.perf_counter() - began, 4)}
        began = time.perf_counter()
        if affected is None:
            nodes, edges = _merge_all(db, rank)
            report["merged"] = {"action": "built", "nodes": nodes, "edges": edges}
        elif affected[0] or affected[1]:
            _merge_keys(db, rank, *affected)
            report["merged"] = {"action": "updated", "nodes": len(affected[0]), "edges": len(affected[1])}
        else:
            report["merged"] = {"action": "kept"}
        report["merged"]["seconds"] = round(time.perf_counter() - began, 4)
        db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('version',?)", (str(VERSION),))
        db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('sequence',?)", (str(view.sequence()),))
        db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('refreshed',?)", (now(),))
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    return report


def refresh(root, *, full=False):
    """Bring the graph store up to the archive (only changed segments), or rebuild it from scratch (`full`, or
    when the file is missing or from another version). Called by write paths, at first serve and by operators,
    never inside a GET handler."""
    from daw.commons.archive import Archive
    from daw.community import exclusive
    root = Path(root).expanduser().resolve()
    path = _target(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    began = time.perf_counter()
    with exclusive(path.parent / "refresh.lock", blocking=True), Archive(root) as view:
        rebuild = full or not path.is_file()
        if not rebuild:
            try:
                with sqlite3.connect(path) as probe:
                    row = probe.execute("SELECT value FROM meta WHERE key='version'").fetchone()
                rebuild = not row or row[0] != str(VERSION)
            except sqlite3.Error:
                rebuild = True
        if rebuild:
            temp = path.with_name(f".{FILE}.{os.getpid()}.{threading.get_ident()}.tmp")
            temp.unlink(missing_ok=True)
            db = _connect_rw(temp)
            try:
                report = _update(db, view, full=True)
            finally:
                db.close()
            os.replace(temp, path)
        else:
            db = _connect_rw(path)
            try:
                report = _update(db, view, full=False)
            finally:
                db.close()
        sequence = view.sequence()
    return {"store": _shown(root, path), "rebuilt": rebuild, "sequence": sequence,
            "seconds": round(time.perf_counter() - began, 4), "segments": report}


def _shown(root, path):
    """The store path relative to the commons, or absolute when it lives outside (a read-only commons)."""
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def _age(stamp):
    try:
        return round((datetime.now(UTC) - datetime.fromisoformat(stamp)).total_seconds(), 1)
    except (TypeError, ValueError):
        return None


def describe(view):
    """Read-only description of the store for one archive (GET /api/map/store): where it is, its age (seconds since
    the last refresh, events behind the archive) and its coverage (segments and stored operations current)."""
    store = reader(view)
    building = _SCHEDULE.get(str(Path(view.root).resolve()), {}).get("running", False)
    if store is None:
        return {"present": False, "segments": {}, "current": False, "building": building,
                "note": "no graph store yet; map reads build in memory until the background build at first serve, a "
                        "write path or `bio commons graph refresh` creates it"}
    states = store.status()
    meta = {r["key"]: r["value"] for r in store.db.execute("SELECT key,value FROM meta")}
    ops = {r["name"]: r["ops"] for r in store.stored.values()}
    fresh_ops = sum(ops.get(name, 0) for name, state in states.items() if state == "fresh")
    stored_ops = sum(ops.get(name, 0) for name in states)
    sequence = int(meta.get("sequence", 0))
    counts = {state: sum(1 for v in states.values() if v == state) for state in ("fresh", "behind", "stale")}
    path = location(view.root)
    return {"present": True, "version": VERSION, "location": _shown(Path(view.root).resolve(), path),
            "inside_commons": path.is_relative_to(Path(view.root).resolve()),
            "sequence": sequence, "archive_sequence": view.sequence(), "refreshed": meta.get("refreshed"),
            "age": {"seconds": _age(meta.get("refreshed")), "events_behind": max(0, view.sequence() - sequence)},
            "coverage": {"segments": len(states), **counts,
                         "segment_share": round(counts["fresh"] / len(states), 4) if states else None,
                         "stored_ops": stored_ops,
                         "fresh_op_share": round(fresh_ops / stored_ops, 4) if stored_ops else None,
                         "merged_nodes": store.db.execute("SELECT count(*) FROM merged_node").fetchone()[0],
                         "merged_edges": store.db.execute("SELECT count(*) FROM merged_edge").fetchone()[0]},
            "segments": states, "counts": counts, "building": building,
            "current": all(v == "fresh" for v in states.values()),
            "note": "derived and never authoritative; segments behind the archive are computed in memory per read and "
                    "merged incrementally (only the nodes and edges they touch are replayed)"}


def status(root):
    """Which segments are current, behind (by sequence) or stale, without writing anything."""
    from daw.commons.archive import Archive
    root = Path(root).expanduser().resolve()
    with Archive(root) as view:
        store = reader(view)
        if store is None:
            return {"store": None, "note": "no graph store; reads build in memory until `bio commons graph refresh`"}
        states = store.status()
        meta = {r["key"]: r["value"] for r in store.db.execute("SELECT key,value FROM meta")}
        return {"store": _shown(root, location(root)), "meta": meta, "segments": states,
                "ops": {r["name"]: r["ops"] for r in store.stored.values()},
                "current": all(v == "fresh" for v in states.values())}


# ---------------------------------------------------------------------------- refresh triggers

_SCHEDULE: dict = {}
_SCHEDULE_LOCK = threading.Lock()


def refresh_soon(root):
    """Refresh in a background thread, coalescing bursts: one refresh runs per commons at a time, and a request
    arriving meanwhile runs one more afterwards. Errors leave the store behind (readers compute the rest)."""
    root = str(Path(root).expanduser().resolve())
    with _SCHEDULE_LOCK:
        state = _SCHEDULE.setdefault(root, {"running": False, "again": False})
        if state["running"]:
            state["again"] = True
            return False
        state["running"] = True

    def work():
        while True:
            try:
                refresh(root)
            except Exception:  # a derived cache: the next write, interval or operator refresh catches up
                pass
            with _SCHEDULE_LOCK:
                if not state["again"]:
                    state["running"] = False
                    return
                state["again"] = False
    threading.Thread(target=work, name="graph-refresh", daemon=True).start()
    return True


def ensure_soon(root):
    """At first serve: build or update the store in the background when it is absent, from another version or
    behind the archive (spec v3 B11). Never blocks a request; returns whether a refresh was scheduled."""
    from daw.commons.archive import Archive
    try:
        with Archive(root) as view:
            store = reader(view)
            current = store is not None and all(v == "fresh" for v in store.status().values())
    except Exception:  # an unreadable archive answers its own errors to readers; nothing to build
        return False
    return False if current else refresh_soon(root)


class BuildAtFirstServe:
    """ASGI middleware: the first HTTP request a commons app serves schedules `ensure_soon` (once per app)."""

    def __init__(self, app, root):
        self.app, self.root, self.started = app, root, False

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and not self.started:
            self.started = True
            threading.Thread(target=ensure_soon, args=(self.root,), name="graph-first-serve", daemon=True).start()
        return await self.app(scope, receive, send)


def wait(root, timeout=30.0):
    """Block until no background refresh is running for this commons (tests and the CLI)."""
    root = str(Path(root).expanduser().resolve())
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _SCHEDULE_LOCK:
            if not _SCHEDULE.get(root, {}).get("running"):
                return True
        time.sleep(0.02)
    return False


WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class RefreshAfterWrites:
    """ASGI middleware: after a successful write request under /api, schedule a graph refresh (the write path
    updates the projection; GET handlers never do)."""

    def __init__(self, app, root):
        self.app, self.root = app, root

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") not in WRITE_METHODS or "/api/" not in scope.get("path", ""):
            return await self.app(scope, receive, send)
        status = {}

        async def watch(message):
            if message.get("type") == "http.response.start":
                status["code"] = message.get("status")
            await send(message)
        await self.app(scope, receive, watch)
        if status.get("code") and status["code"] < 400:
            refresh_soon(self.root)


def install(app, root, *, at_first_serve=False):
    app.add_middleware(RefreshAfterWrites, root=root)
    if at_first_serve:
        app.add_middleware(BuildAtFirstServe, root=root)


def start_interval(root, seconds):
    """`bio commons serve --graph-refresh SECONDS`: refresh now and then every interval, in a daemon thread."""
    if not seconds or seconds <= 0:
        return None
    root = str(Path(root).expanduser().resolve())

    def loop():
        while True:
            try:
                refresh(root)
            except Exception:  # a derived cache: retried on the next interval
                pass
            time.sleep(seconds)
    thread = threading.Thread(target=loop, name="graph-refresh-interval", daemon=True)
    thread.start()
    return thread
