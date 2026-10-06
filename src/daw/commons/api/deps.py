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
    """Read-write board for write endpoints. Call board functions only; they take the writer lock."""
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
