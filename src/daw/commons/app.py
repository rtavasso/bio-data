"""HTTP surface for the commons (M8): read-only views plus write paths through board functions.

`create_app` mounts every router listed in ROUTER_MODULES. Each module exposes a
FastAPI `router`; feature modules add their module path to the list. Reads use
`deps.archive` (mode=ro SQLite). Writes use `deps.board` and must call board
functions under the board writer lock with the caller's participant identity.
"""
import importlib
import os
from dataclasses import dataclass
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
]

STATUS = {"authentication_required": 401, "permission_denied": 403, "participant_suspended": 403,
          "rate_limited": 429, "live_opt_in_required": 409, "writer_busy": 409, "agent_busy": 409}


@dataclass
class Settings:
    root: Path
    mode: str = "local"           # local: single user, no login; accounts: cookies/tokens (M7)
    local_user: str = "local"
    static_dir: Path | None = None


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


def create_app(root, *, mode="local", local_user="local", static_dir=None):
    from fastapi import FastAPI, Request
    from fastapi.responses import FileResponse, JSONResponse

    from daw.commons import auth
    from daw.community import Community

    if mode not in {"local", "accounts"}:
        raise DawError("invalid_commons_mode", "local or accounts")
    settings = Settings(Path(root).expanduser().resolve(), mode, local_user, static_dir or default_static_dir())
    # Opening the board read-write once applies the additive schema; views then use mode=ro.
    with Community(settings.root) as board:
        auth.prepare(board, settings)
    app = FastAPI(title="Colloquy", description="Research commons API: immutable records, attributed writes.",
                  version="1")
    app.state.settings = settings

    @app.exception_handler(DawError)
    async def daw_error(request: Request, error: DawError):
        return JSONResponse({"error": error.reason, "detail": error.detail}, status_code=status_for(error))

    for name in ROUTER_MODULES:
        app.include_router(importlib.import_module(name).router)

    static = settings.static_dir
    if static and (static / "index.html").is_file():
        static = static.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        async def frontend(path: str):
            if path.startswith("api/"):
                return JSONResponse({"error": "unknown_endpoint", "detail": path}, status_code=404)
            candidate = (static / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(static):
                return FileResponse(candidate)
            return FileResponse(static / "index.html")
    return app
