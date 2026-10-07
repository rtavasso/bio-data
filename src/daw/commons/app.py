"""HTTP surface for the commons (M8): read-only views plus write paths through board functions.

`create_app` mounts every router listed in ROUTER_MODULES. Each module exposes a
FastAPI `router`; feature modules add their module path to the list. Reads use
`deps.archive` (mode=ro SQLite). Writes use `deps.board` and must call board
functions under the board writer lock with the caller's participant identity.

`base` is the URL path the app is served under ("/" for `bio commons serve`,
"/c/<tenant>/" under `bio commons host`). The web app is built with relative
asset URLs; the server rewrites index.html for its base and injects
`<meta name="colloquy-base">`, from which the client derives its router basename
and API prefix. Session cookies are scoped to the base path.
"""
import html
import importlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from daw.util import DawError

ROUTER_MODULES = [
    "daw.commons.api.meta",
    "daw.commons.api.read",
    "daw.commons.api.events",
    "daw.commons.api.accounts",
    "daw.commons.api.write",
    "daw.commons.api.frontier",
    "daw.commons.api.dashboard",
    "daw.commons.api.observatory",
    "daw.commons.api.search",
    "daw.commons.api.watchers",
    "daw.commons.api.studio",
    "daw.commons.api.checker",
]

STATUS = {"authentication_required": 401, "permission_denied": 403, "participant_suspended": 403,
          "rate_limited": 429, "live_opt_in_required": 409, "writer_busy": 409, "agent_busy": 409,
          "hidden_by_moderation": 403}


BASE = re.compile(r"/(?:(?!\.\.?/)[A-Za-z0-9._~-]+/)*")
BASE_META = '<meta name="colloquy-base" content="/" />'


@dataclass
class Settings:
    root: Path
    mode: str = "local"           # local: single user, no login; accounts: cookies/tokens (M7)
    local_user: str = "local"
    static_dir: Path | None = None
    base: str = "/"               # URL path prefix, always starting and ending with "/"
    login: dict = field(default_factory=dict)   # {attempts, window_seconds} (daw.commons.ratelimit)


def status_for(error: DawError):
    if error.reason in STATUS:
        return STATUS[error.reason]
    if error.reason.startswith("unknown_") or error.reason.endswith("_missing"):
        return 404
    return 400


def default_static_dir():
    configured = os.environ.get("COLLOQUY_WEB_DIST")
    if configured:
        return Path(configured)
    built = Path(__file__).resolve().parents[3] / "web" / "dist"
    return built if (built / "index.html").is_file() else None


def render_index(text, base):
    """index.html for a base path: relative asset URLs made absolute under it, and the base announced in a meta tag."""
    meta = f'<meta name="colloquy-base" content="{html.escape(base, quote=True)}" />'
    text = text.replace('="./', f'="{base}')
    return text.replace(BASE_META, meta) if BASE_META in text else text.replace("</head>", f"  {meta}\n  </head>", 1)


def create_app(root, *, mode="local", local_user="local", static_dir=None, base="/", login=None):
    """One commons' API and web app. `login` overrides its `[login]` attempt limits (multi-tenant host)."""
    from fastapi import FastAPI, Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

    from daw.commons import auth
    from daw.commons.ratelimit import AttemptLimiter, login_limits
    from daw.community import Community

    if mode not in {"local", "accounts"}:
        raise DawError("invalid_commons_mode", "local or accounts")
    if not BASE.fullmatch(base):
        raise DawError("invalid_base_path", "a path such as / or /c/lab/ (letters, digits, '.', '_', '~', '-')")
    root = Path(root).expanduser().resolve()
    settings = Settings(root, mode, local_user, static_dir or default_static_dir(), base, login_limits(root, login))
    # Opening the board read-write once applies the additive schema; views then use mode=ro.
    with Community(settings.root) as board:
        auth.prepare(board, settings)
    app = FastAPI(title="Colloquy", description="Research commons API: immutable records, attributed writes.",
                  version="1")
    app.state.settings = settings
    app.state.login_limiter = AttemptLimiter(settings.login["attempts"], settings.login["window_seconds"])

    @app.exception_handler(DawError)
    async def daw_error(request: Request, error: DawError):
        return JSONResponse({"error": error.reason, "detail": error.detail}, status_code=status_for(error))

    for name in ROUTER_MODULES:
        app.include_router(importlib.import_module(name).router)
    # V6: a successful write schedules a graph store refresh; GET handlers never write it.
    from daw.commons import graphstore
    graphstore.install(app, settings.root)

    static = settings.static_dir
    if static and (static / "index.html").is_file():
        static = static.resolve()
        index = render_index((static / "index.html").read_text(), settings.base)

        @app.get("/{path:path}", include_in_schema=False)
        async def frontend(path: str):
            if path.startswith("api/"):
                return JSONResponse({"error": "unknown_endpoint", "detail": path}, status_code=404)
            candidate = (static / path).resolve()
            if path and path != "index.html" and candidate.is_file() and candidate.is_relative_to(static):
                return FileResponse(candidate)
            return HTMLResponse(index, headers={"Cache-Control": "no-cache"})
    return app
