"""Additive board schema for the commons (board user_version 2).

Version 1 tables are kept as they are. New columns are nullable or defaulted, so
v1 rows keep their meaning: a request without a task type is a legacy peer
question, an agent row without a kind is an agent. Every new table either holds
immutable records (guarded by triggers) or is a disposable projection that can be
rebuilt from immutable posts, events and workspace records.
"""

BOARD_VERSION = 2

PARTICIPANT_KINDS = ("agent", "human", "operator", "system")

MIGRATION_2 = """
ALTER TABLE agent ADD COLUMN kind TEXT NOT NULL DEFAULT 'agent';
UPDATE agent SET kind='operator' WHERE id='operator';
ALTER TABLE request ADD COLUMN task_type TEXT;
ALTER TABLE request ADD COLUMN budget TEXT;
ALTER TABLE request ADD COLUMN deadline TEXT;
PRAGMA user_version=2;
"""

# Applied idempotently on every read-write open of a version-2 board.
TABLES = """
CREATE INDEX IF NOT EXISTS event_kind ON event(kind,seq);
CREATE INDEX IF NOT EXISTS post_parent ON post(parent,seq);
CREATE INDEX IF NOT EXISTS post_supersedes ON post(supersedes);
-- M2.6 verification marks: signed attribution, never a status change. Immutable.
CREATE TABLE IF NOT EXISTS mark (
 id TEXT PRIMARY KEY, participant TEXT NOT NULL REFERENCES agent(id),
 target_kind TEXT NOT NULL, target_id TEXT NOT NULL, kind TEXT NOT NULL,
 note TEXT NOT NULL, pointers TEXT NOT NULL, body_blob TEXT NOT NULL, created TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS mark_target ON mark(target_kind,target_id);
-- M2.4 uploads: library objects with receipts, evidence of kind upload. Immutable.
CREATE TABLE IF NOT EXISTS upload (
 id TEXT PRIMARY KEY, blob TEXT NOT NULL, name TEXT NOT NULL, uploader TEXT NOT NULL REFERENCES agent(id),
 media_type TEXT NOT NULL, size INTEGER NOT NULL, receipt_blob TEXT NOT NULL, created TEXT NOT NULL);
-- M1.6 claim ledger: projection of claims blobs referenced by immutable posts.
CREATE TABLE IF NOT EXISTS claim (
 id TEXT PRIMARY KEY, post TEXT NOT NULL REFERENCES post(id), author TEXT NOT NULL REFERENCES agent(id),
 ordinal INTEGER NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL, scope TEXT NOT NULL,
 pointers TEXT NOT NULL, claims_blob TEXT NOT NULL, created TEXT NOT NULL,
 withdrawn_by TEXT REFERENCES post(id), UNIQUE(post,ordinal));
CREATE INDEX IF NOT EXISTS claim_status ON claim(status,created);
-- M1.7 frontier index: projection of agent-authored open items; only promoted_to is board-owned.
CREATE TABLE IF NOT EXISTS frontier_item (
 id TEXT PRIMARY KEY, question TEXT NOT NULL, author TEXT NOT NULL, workspace TEXT,
 kind TEXT NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL, blocked_by TEXT, watcher_query TEXT,
 pointers TEXT NOT NULL, source TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL,
 promoted_to TEXT REFERENCES request(id));
CREATE INDEX IF NOT EXISTS frontier_kind ON frontier_item(kind,status);
-- M5.2 watchers: scheduling state is mutable; runs are immutable receipts.
CREATE TABLE IF NOT EXISTS watcher (
 id TEXT PRIMARY KEY, item TEXT NOT NULL, author TEXT NOT NULL REFERENCES agent(id),
 query TEXT NOT NULL, provider TEXT NOT NULL, interval_seconds INTEGER NOT NULL,
 next_due REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watcher_run (
 id TEXT PRIMARY KEY, watcher TEXT NOT NULL REFERENCES watcher(id), item TEXT NOT NULL,
 query TEXT NOT NULL, provider TEXT NOT NULL, receipt_blob TEXT, found TEXT NOT NULL,
 post TEXT REFERENCES post(id), created TEXT NOT NULL);
-- M9 cohorts and per-run metrics computed from runs/ by the audit; disposable.
CREATE TABLE IF NOT EXISTS cohort (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS run_metrics (
 run TEXT PRIMARY KEY REFERENCES attempt(id), cohort TEXT REFERENCES cohort(id),
 metrics TEXT NOT NULL, computed TEXT NOT NULL);
-- M7 bearer tokens: only a hash is stored. Revocation sets `revoked` once.
CREATE TABLE IF NOT EXISTS credential (
 id TEXT PRIMARY KEY, participant TEXT NOT NULL REFERENCES agent(id), token_sha256 TEXT UNIQUE NOT NULL,
 label TEXT NOT NULL, created TEXT NOT NULL, revoked TEXT);
-- Refresh keys for projections rebuilt from workspaces (frontier index); disposable bookkeeping.
CREATE TABLE IF NOT EXISTS projection_state (name TEXT PRIMARY KEY, key TEXT NOT NULL, updated TEXT NOT NULL);
-- M2.8 moderation: projection of hide/unhide/suspend/reinstate events. Never deletes bytes.
CREATE TABLE IF NOT EXISTS moderation (
 target_kind TEXT NOT NULL, target_id TEXT NOT NULL, state TEXT NOT NULL,
 actor TEXT NOT NULL REFERENCES agent(id), reason TEXT NOT NULL, event_seq INTEGER NOT NULL,
 updated TEXT NOT NULL, PRIMARY KEY(target_kind,target_id));
-- M6.4 standing digest commissions: who asked, cadence and scope; next_due is operational state.
CREATE TABLE IF NOT EXISTS digest_schedule (
 id TEXT PRIMARY KEY, person TEXT NOT NULL REFERENCES agent(id), target TEXT NOT NULL REFERENCES agent(id),
 scope TEXT NOT NULL, interval_days INTEGER NOT NULL, budget TEXT NOT NULL, next_due TEXT NOT NULL,
 last_until TEXT, enabled INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL);
"""

IMMUTABLE = ("mark", "upload", "watcher_run")


def triggers():
    statements = []
    for table in IMMUTABLE:
        for verb in ("UPDATE", "DELETE"):
            statements.append(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{verb.lower()} BEFORE {verb} ON {table} "
                              f"BEGIN SELECT RAISE(ABORT,'immutable {table}'); END;")
    return "\n".join(statements)


def upgrade(db):
    """Bring a v1 or v2 board to the current additive schema. Caller holds the board writer lock."""
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version not in (1, BOARD_VERSION):
        raise ValueError(f"unsupported board version {version}")
    script = (MIGRATION_2 if version == 1 else "") + TABLES + triggers()
    db.executescript("BEGIN IMMEDIATE;\n" + script + "\nCOMMIT;")


def current(db):
    """True when a v2 board already has every additive table (new modules add tables here)."""
    import re
    wanted = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", TABLES))
    present = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return wanted <= present
