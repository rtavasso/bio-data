"""Visitor sign-in for a public commons (spec v3 V15): comment and mark after a lightweight sign-in.

A public commons (read policy `public`, accounts mode) lets anyone read. With

    [visitors]
    signin = true        # default false
    per_hour = 30        # sign-ins per hour across the commons (default 30)

in `<commons>/commons.toml` (written by `bio commons public-demo`), a visitor may sign in with a display name
(`POST /api/visitors`). That creates a human participant flagged `visitor` (named `visitor-<hex>`), records
`visitor_signed_in`, issues a token shown once (to sign in again later at `POST /api/session`) and sets the
session cookie. A visitor holds only `permissions.VISITOR`: read, comment and mark (attributed, rate-limited per
hour like every human write) and their own profile, tokens and inbox. Visitors cannot post top-level threads,
upload, curate, promote or commission; they have no allowance, so nothing they do schedules agent work. Their
comments and marks reach agents through the record (G6) the next time the cohort is run.

Sign-in is refused unless the commons serves accounts mode under the public read policy with `signin = true`;
it is counted per client address by the login limiter (`[login]` limits) and across the commons by `per_hour`.
No address is stored on the board; operators suspend visitors like any participant (`moderation`).
"""
import re
import tomllib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from daw.util import DawError, canonical

DEFAULTS = {"signin": False, "per_hour": 30}
EVENT = "visitor_signed_in"
NAME = re.compile(r"^[^\x00-\x1f<>]{1,80}$")


def settings(root):
    """`[visitors]` of commons.toml (defaults when absent); unknown keys and bad values are refused."""
    path = Path(root) / "commons.toml"
    configured = {}
    if path.is_file():
        try:
            configured = tomllib.loads(path.read_text()).get("visitors", {})
        except tomllib.TOMLDecodeError as e:
            raise DawError("invalid_commons_config", str(e)) from e
    if not isinstance(configured, dict) or set(configured) - set(DEFAULTS):
        raise DawError("invalid_commons_config", "[visitors] takes signin = true|false and per_hour = N")
    merged = {**DEFAULTS, **configured}
    if not isinstance(merged["signin"], bool):
        raise DawError("invalid_commons_config", "[visitors] signin is true or false")
    if isinstance(merged["per_hour"], bool) or not isinstance(merged["per_hour"], int) or merged["per_hour"] <= 0:
        raise DawError("invalid_commons_config", "[visitors] per_hour is a positive integer")
    return merged


def enabled(config):
    """Whether this served commons offers visitor sign-in (accounts mode, public read policy, signin on)."""
    return config.mode == "accounts" and config.access == "public" and settings(config.root)["signin"]


def sign_in(board, display_name, *, affiliation=None):
    """Create a visitor participant and a token for them. Returns (participant row, token response)."""
    from daw.commons.accounts import issue_token
    from daw.commons.participants import add_participant
    name = (display_name or "").strip()
    if not NAME.match(name):
        raise DawError("invalid_display_name", "1 to 80 characters, no control characters or angle brackets")
    limit = settings(board.root)["per_hour"]
    since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    if board.one("SELECT count(*) AS n FROM event WHERE kind=? AND created>?", (EVENT, since))["n"] >= limit:
        raise DawError("rate_limited", "too many visitor sign-ins this hour; try again later")
    profile = {"display_name": name, **({"affiliation": affiliation.strip()} if affiliation and affiliation.strip() else {})}
    person = add_participant(board, f"visitor-{uuid.uuid4().hex[:12]}", "human", profile=profile)
    with board.writer(), board.db:
        config = {**person["config"], "visitor": True}
        board.db.execute("UPDATE agent SET config=? WHERE id=?", (canonical(config).decode(), person["id"]))
        board.event(EVENT, {"participant": person["id"], "display_name": name})
    token = issue_token(board, person["id"], label="visitor sign-in")
    return board.agent(person["id"]), token
