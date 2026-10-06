"""Caller identity for HTTP requests (M7).

Local single-user mode skips login: every request acts as one human participant
(created on first start). Account mode is completed by the accounts module.
Agents never reach the HTTP write API: they use the bio CLI in their checkout.
"""
from daw.commons.participants import add_participant
from daw.util import DawError


def prepare(board, settings):
    if settings.mode == "local":
        row = board.one("SELECT id,kind FROM agent WHERE name=?", (settings.local_user,))
        if row is None:
            add_participant(board, settings.local_user, "human", profile={"display_name": settings.local_user})
        elif row["kind"] not in {"human", "operator"}:
            raise DawError("local_user_must_be_human", settings.local_user)


def authenticate(request, archive):
    """Return the calling participant row, or raise authentication_required."""
    settings = request.app.state.settings
    if settings.mode == "local":
        return archive.participant(settings.local_user)
    raise DawError("authentication_required")
