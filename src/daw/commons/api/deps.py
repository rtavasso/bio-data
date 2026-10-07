"""Shared FastAPI dependencies: read-only archive, board writer access, caller identity.

Use the Annotated aliases at the bottom in endpoint signatures: `def view(view: View, who: Caller)`.
"""
from typing import Annotated, Any

from fastapi import Depends, Request

from daw.commons.archive import Archive


def settings(request: Request):
    return request.app.state.settings


def archive(request: Request):
    """Read-only view for one request (mode=ro SQLite; no writer locks)."""
    value = Archive(request.app.state.settings.root)
    try:
        yield value
    finally:
        value.close()


def board(request: Request):
    """Read-write board opened by the dependency machinery. Do not use it in endpoints: FastAPI may resolve a
    dependency and run the endpoint in different threads, and SQLite connections are thread-bound. HTTP writes
    depend on `daw.commons.api.write.Actor` and open the board with `write.call` (a test enforces this)."""
    from daw.community import Community
    value = Community(request.app.state.settings.root)
    try:
        yield value
    finally:
        value.close()


def caller(request: Request, view: Annotated[Archive, Depends(archive)]):
    from daw.commons import auth
    return auth.authenticate(request, view)


View = Annotated[Archive, Depends(archive)]
Board = Annotated[Any, Depends(board)]
Caller = Annotated[dict, Depends(caller)]
Config = Annotated[Any, Depends(settings)]
