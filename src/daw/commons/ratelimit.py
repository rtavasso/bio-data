"""Bounded attempt counters for login (M7, M2.8).

POST /api/session counts failed token presentations per client address and per
presented token (by hash). After `attempts` failures within `window_seconds`
either key is refused with `rate_limited` (429) until its oldest failure leaves
the window. Successful logins are not counted and never reset a counter, so a
valid token cannot launder guesses made with others.

The served app counts on the board (`BoardAttemptLimiter`, table `login_failure`):
the counters are operational state, not records, but they survive restarts and
hold across worker processes. Failures are written under the board writer lock;
keys are stored as sha256 digests, never as raw addresses or tokens; rows older
than the window are pruned on each write. Storage is bounded twice: each key keeps
at most `attempts` rows, and at most `max_keys` keys are kept (the least recently
failed are evicted). `AttemptLimiter` is the same interface in process memory.
Limits come from `<commons>/commons.toml`:

    [login]
    attempts = 10
    window_seconds = 300

A multi-tenant host may override them per tenant (`daw.commons.tenants`).
"""
import hashlib
import threading
import time
import tomllib
from collections import OrderedDict, deque
from pathlib import Path

from daw.util import DawError

LOGIN_DEFAULTS = {"attempts": 10, "window_seconds": 300}
MAX_KEYS = 10_000


def login_limits(root, overrides=None):
    """`[login]` limits of a commons (defaults when absent), then any per-tenant overrides."""
    configured = {}
    path = Path(root) / "commons.toml"
    if path.is_file():
        try:
            configured = tomllib.loads(path.read_text()).get("login", {})
        except tomllib.TOMLDecodeError as e:
            raise DawError("invalid_commons_config", str(e)) from e
    merged = {**LOGIN_DEFAULTS, **configured, **(overrides or {})}
    unknown = set(merged) - set(LOGIN_DEFAULTS)
    if unknown:
        raise DawError("invalid_commons_config", f"unknown login limits {', '.join(sorted(unknown))}")
    for key, value in merged.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise DawError("invalid_commons_config", f"login {key} must be a positive integer")
    return merged


def token_key(token):
    return "token:" + hashlib.sha256(str(token).encode()).hexdigest()[:32]


class AttemptLimiter:
    """Sliding-window failure counter over a bounded set of keys; safe across request threads."""

    def __init__(self, attempts, window_seconds, *, max_keys=MAX_KEYS, clock=time.monotonic):
        self.attempts, self.window, self.max_keys, self.clock = attempts, window_seconds, max_keys, clock
        self._failures: "OrderedDict[str, deque]" = OrderedDict()
        self._lock = threading.Lock()

    def retry_after(self, *keys):
        """Seconds until every key may try again (0 when none is limited)."""
        now = self.clock()
        wait = 0.0
        with self._lock:
            for key in keys:
                times = self._failures.get(key)
                if times and len(times) >= self.attempts:
                    wait = max(wait, self.window - (now - times[0]))
        return max(0.0, wait)

    def failed(self, *keys):
        now = self.clock()
        with self._lock:
            for key in keys:
                times = self._failures.pop(key, None) or deque(maxlen=self.attempts)
                while times and now - times[0] >= self.window:
                    times.popleft()
                times.append(now)
                self._failures[key] = times
            while len(self._failures) > self.max_keys:
                self._failures.popitem(last=False)

    def __len__(self):
        return len(self._failures)


def _stored(key):
    return hashlib.sha256(str(key).encode()).hexdigest()


class BoardAttemptLimiter:
    """`AttemptLimiter`'s interface with counters on the board (`login_failure`), so they survive restarts.

    Reads open the board read-only; `failed` writes under the board writer lock. Time is wall-clock
    seconds (a monotonic clock does not survive a restart)."""

    def __init__(self, root, attempts, window_seconds, *, max_keys=MAX_KEYS, clock=time.time):
        self.root = Path(root)
        self.attempts, self.window, self.max_keys, self.clock = attempts, window_seconds, max_keys, clock

    def _read(self):
        import sqlite3
        return sqlite3.connect(f"file:{self.root / 'board.sqlite'}?mode=ro", uri=True, timeout=30)

    def retry_after(self, *keys):
        """Seconds until every key may try again (0 when none is limited)."""
        now = self.clock()
        wait = 0.0
        db = self._read()
        try:
            for key in keys:
                rows = [r[0] for r in db.execute("SELECT at FROM login_failure WHERE key=? AND at>? ORDER BY at DESC "
                                                 "LIMIT ?", (_stored(key), now - self.window, self.attempts))]
                if len(rows) >= self.attempts:
                    wait = max(wait, self.window - (now - min(rows)))
        finally:
            db.close()
        return max(0.0, wait)

    def failed(self, *keys):
        from daw.community import Community
        now = self.clock()
        with Community(self.root) as board, board.writer(), board.db:
            board.db.execute("DELETE FROM login_failure WHERE at<=?", (now - self.window,))
            for key in keys:
                stored = _stored(key)
                board.db.execute("INSERT INTO login_failure(key,at) VALUES(?,?)", (stored, now))
                board.db.execute("DELETE FROM login_failure WHERE key=? AND rowid NOT IN (SELECT rowid FROM login_failure "
                                 "WHERE key=? ORDER BY at DESC,rowid DESC LIMIT ?)", (stored, stored, self.attempts))
            board.db.execute("DELETE FROM login_failure WHERE key NOT IN (SELECT key FROM login_failure GROUP BY key "
                             "ORDER BY max(at) DESC LIMIT ?)", (self.max_keys,))

    def __len__(self):
        db = self._read()
        try:
            return db.execute("SELECT count(DISTINCT key) FROM login_failure WHERE at>?",
                              (self.clock() - self.window,)).fetchone()[0]
        finally:
            db.close()
