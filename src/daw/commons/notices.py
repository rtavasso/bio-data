"""Platform notices: posts by a system participant addressed to one participant.

Watchers ("new evidence may fit gap X"), correction propagation ("a post you
fetched was superseded") and stall reports use this. A notice is an ordinary
immutable post of kind "notice" plus a request with task_type "notice", so it
appears in the addressee's inbox. The delivery service never launches a model
turn for a notice: reading it is the addressee's decision. Content is
untrusted like any post.
"""
import uuid

from daw.commons.participants import ensure_system
from daw.commons.tasks import NOTICE
from daw.util import now


def notify(board, system_name, target, title, body, *, parent=None, evidence=None, key=None):
    """Idempotent with `key`. Caller must not hold the board or library writer lock."""
    system = ensure_system(board, system_name)
    addressee = board.agent(target)
    with board.writer(), board.library.writer():
        post = board._post(system["id"], title, body, parent=parent, kind="notice", request_key=key,
                           evidence={**(evidence or {}), "target": addressee["id"]})
        existing = board.one("SELECT * FROM request WHERE post=?", (post,))
        if existing:
            return existing
        identity = "request_" + uuid.uuid4().hex
        with board.db:
            board.db.execute("INSERT INTO request(id,post,target,state,active_run,answer,created,updated,task_type) "
                             "VALUES(?,?,?,'pending',NULL,NULL,?,?,?)", (identity, post, addressee["id"], now(), now(), NOTICE))
            board.event("notice_queued", {"request": identity, "post": post, "target": addressee["id"],
                                          "system": system["id"]})
    return board.one("SELECT * FROM request WHERE id=?", (identity,))
