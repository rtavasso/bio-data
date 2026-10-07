"""Board service for sandboxed agents (M3.6, M7.2): board writes without a board mount.

A sandboxed checkout gets no board directory. Its `bio community` commands reach
the board through this service instead: an operator-run process beside the
server that listens on one Unix socket per agent and executes exactly the
agent-permitted board operations as that agent, through the same `Community`
functions the local CLI calls:

    publish  answer  reply  ask  fetch            (writes: permission publish, answer, reply, ask, fetch)
    inbox  show  search  verify  claims  agents  overview  frontier  experiments  (reads)

Identity is bound twice. Each agent's socket lives in its own short directory
`$TMPDIR/colloquy/<sha256(root)[:12]>/<index>/` (see "provisioning" below; the
old location `<commons>/service/board/<agent>/board.sock` is a symlink to it),
which dispatch mounts read-only into that agent's container only; and every
request carries the agent's bearer token
(`<commons>/secrets/board/<agent>.token`, 0600, passed to the container by
environment name, never in argv). A socket answers only its own agent's token,
and an `author` in a request must name that agent. The service never takes a
file path for content: bodies, claims and frontier items travel in the request.
The only path accepted is a workspace, which must resolve (on the host, after
symlinks) to the agent's checkout workspace `<checkout>/workspace` (no other
workspace, even inside the checkout), and its catalog, configuration and object
directories must resolve inside the checkout. Publishing reads that workspace from the host; fetching
writes into it under its own writer lock.

Protocol: HTTP/1.1 over the Unix socket, `POST /v1/<operation>` with a JSON
object, `Authorization: Bearer <token>`; replies `{"value": ...}` or
`{"error", "detail"}`. Each request is one line in `<commons>/service/board-service.jsonl`
(agent, operation, outcome; never content). The client below is stdlib-only, so
it runs in the agent image without the commons extra:
`BIO_BOARD_URL=unix:///path/<index>.sock` and `BIO_BOARD_TOKEN` select it.

Rotate an agent's token by deleting its token file while the agent is idle;
the service reads the file on every request.
"""
import contextlib
import hashlib
import hmac
import http.client
import json
import os
import secrets
import socket
import socketserver
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from daw.util import DawError, canonical, now

URL_ENV, TOKEN_ENV = "BIO_BOARD_URL", "BIO_BOARD_TOKEN"
SOCKET = "board.sock"
MAX_BODY = 32 * 2**20
# Operation -> permission (daw.commons.permissions) and accepted request fields.
OPERATIONS = {
    "publish": ("publish", {"title", "body", "artifacts", "question", "channel", "reply_to", "supersedes", "key",
                            "claims", "frontier", "workspace", "author"}),
    "answer": ("answer", {"request", "title", "body", "artifacts", "question", "key", "claims", "frontier",
                          "workspace", "author"}),
    "reply": ("reply", {"post", "title", "body", "artifacts", "question", "key", "claims", "frontier", "workspace",
                        "author"}),
    "ask": ("ask", {"target", "body", "reply_to", "key", "notify", "author"}),
    "fetch": ("fetch", {"post", "question", "artifact", "workspace", "author"}),
    "inbox": ("read", {"agent", "all_states", "sent", "since", "acts", "after"}),
    "overview": ("read", {"after"}),
    "frontier": ("read", {"kind", "status", "question", "mine"}),
    "experiments": ("read", set()),
    "agents": ("read", set()),
    "show": ("read", {"post"}),
    "search": ("read", {"text", "limit", "offset", "family", "full"}),
    "verify": ("read", {"post"}),
    "claims": ("read", {"q", "post", "status", "author", "limit", "offset"}),
}


# ---- provisioning (operator side) --------------------------------------------------------------
#
# Socket paths are bounded by sun_path (104 bytes on macOS/BSD, 108 on Linux, NUL included), and a
# commons under a long directory would exceed it. Sockets therefore live under a short per-commons
# directory, `$TMPDIR/colloquy/<sha256(root)[:12]>/<index>/<index>.sock` (or `$BIO_BOARD_SOCKET_DIR`
# in place of `$TMPDIR/colloquy`), where <index> is a small stable per-agent number recorded in
# `<commons>/service/board/sockets.json`. Each agent keeps its own directory so a container mounts
# only its own socket, and the mount survives a service restart. The old location
# `<commons>/service/board/<agent>/board.sock` is a symlink to the short socket.

SOCKET_ROOT_ENV = "BIO_BOARD_SOCKET_DIR"
STATE = "sockets.json"


def socket_limit(platform=None):
    """sun_path size in bytes, NUL terminator included: 108 on Linux, 104 on macOS and the BSDs."""
    return 108 if (platform or sys.platform).startswith("linux") else 104


def check_socket_path(path, platform=None):
    """Refuse a socket path the platform cannot bind (resolved, so /var -> /private/var on macOS counts)."""
    path = Path(path)
    parent = path.parent.resolve() if path.parent.exists() else path.parent
    resolved = parent / path.name
    size, limit = len(os.fsencode(resolved)), socket_limit(platform)
    if size + 1 > limit:
        raise DawError("socket_path_too_long",
                       f"{resolved} is {size} bytes; Unix socket paths are limited to {limit - 1} bytes here. "
                       f"Set {SOCKET_ROOT_ENV} to a shorter directory.")
    return resolved


def socket_root(env=None):
    """The short directory holding every commons' board sockets on this host."""
    env = os.environ if env is None else env
    if env.get(SOCKET_ROOT_ENV):
        return Path(env[SOCKET_ROOT_ENV]).expanduser()
    return Path(env.get("TMPDIR") or tempfile.gettempdir()) / "colloquy"


def commons_socket_dir(root, env=None):
    digest = hashlib.sha256(str(Path(root).expanduser().resolve()).encode()).hexdigest()[:12]
    return socket_root(env) / digest


def legacy_dir(root, agent_id):
    """The pre-v2 per-agent directory under the commons; it now holds a symlink to the short socket."""
    return Path(root) / "service" / "board" / _safe_id(agent_id)


def token_path(root, agent_id):
    return Path(root) / "secrets" / "board" / (_safe_id(agent_id) + ".token")


def _safe_id(agent_id):
    if not agent_id or not all(c.isalnum() or c in "_-" for c in agent_id):
        raise DawError("invalid_agent_identity", repr(agent_id))
    return agent_id


def _private_dir(path, *, owned=False, group=None):
    """A service directory: 0700, or 0750 with `group` (per-agent uids share a group, spec v2 V9)."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise DawError("unsafe_service_path", str(path))
    if owned:
        info = path.stat()
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise DawError("unsafe_service_path", f"{path} belongs to another user; set {SOCKET_ROOT_ENV}")
    if group is not None:
        _group(path, group)
        path.chmod(0o750)
    else:
        path.chmod(0o700)


def _group(path, group):
    if path.stat().st_gid != group:
        try:
            os.chown(path, -1, group)
        except PermissionError as e:
            raise DawError("socket_group_unavailable", f"cannot give {path} to group {group}: the board service's "
                           "user must belong to the sandbox's agent_gid") from e


@contextlib.contextmanager
def _state_lock(root):
    import fcntl
    folder = Path(root) / "service" / "board"
    _private_dir(folder.parent)
    _private_dir(folder)
    with (folder / ".sockets.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield folder / STATE
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def socket_state(root):
    """Recorded agent indexes and bound socket paths (`service/board/sockets.json`); read-only."""
    path = Path(root) / "service" / "board" / STATE
    if not path.is_file():
        return {"format": 1, "agents": {}}
    return json.loads(path.read_text())


def provision_socket(root, agent_id, *, bind=False, group=None):
    """The agent's stable index and socket path, recorded in the service state.

    The board service (`bind=True`) is authoritative: it records the path it binds, computed from its
    own environment. Dispatch reuses the recorded path, so both sides agree even when the service runs
    with a different TMPDIR (for example in its own container); only before any service ran does dispatch
    compute it. Paths over the platform limit are refused with `socket_path_too_long`."""
    _safe_id(agent_id)
    root = Path(root)
    with _state_lock(root) as path:
        state = json.loads(path.read_text()) if path.is_file() else {"format": 1, "agents": {}}
        entry = state["agents"].get(agent_id)
        if entry is None:
            entry = {"index": 1 + max((e["index"] for e in state["agents"].values()), default=0)}
        index = entry["index"]
        recorded = entry.get("socket")
        if bind or not recorded:
            socket_path = commons_socket_dir(root) / str(index) / f"{index}.sock"
        else:
            socket_path = Path(recorded)
        check_socket_path(socket_path)
        _private_dir(socket_path.parent.parent.parent, owned=True)
        _private_dir(socket_path.parent.parent)
        _private_dir(socket_path.parent, group=group)
        socket_path = check_socket_path(socket_path)
        changed = entry.get("socket") != str(socket_path)
        entry.update(socket=str(socket_path), **({"recorded": now()} if changed else {}))
        state["agents"][agent_id] = entry
        if changed or not path.is_file():
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(state, indent=1, sort_keys=True))
            os.replace(temporary, path)
    link = _legacy_link(root, agent_id, socket_path)
    return {"index": index, "socket": socket_path, "link": link}


def _legacy_link(root, agent_id, target):
    """`service/board/<agent>/board.sock` -> the short socket (the location older receipts name)."""
    folder = legacy_dir(root, agent_id)
    _private_dir(folder)
    link = folder / SOCKET
    if link.is_symlink():
        if Path(os.readlink(link)) == target:
            return link
        link.unlink()
    elif link.is_socket():
        link.unlink()  # a socket bound there by a pre-v2 service
    elif link.exists():
        raise DawError("unsafe_service_path", str(link))
    link.symlink_to(target)
    return link


def agent_token(root, agent_id):
    """The agent's board-service token, created once (0600) and shared by dispatch and the service."""
    path = token_path(root, agent_id)
    _private_dir(path.parent.parent)
    _private_dir(path.parent)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w") as stream:
            stream.write("board_" + secrets.token_urlsafe(32))
    return read_token(root, agent_id)


def read_token(root, agent_id):
    """The current token, or "" when none is provisioned (the service then refuses every request)."""
    path = token_path(root, agent_id)
    if not path.is_file():
        return ""
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise DawError("unsafe_board_token", f"{path} must be a regular file readable only by its owner")
    return path.read_text().strip()


def provision(root, agent_id, *, bind=False, group=None):
    """Socket directory and token for one agent. Returns what dispatch mounts and passes by name:
    {dir, socket, url, token, index, link} where `link` is the old in-commons location (a symlink).
    With `group` (per-agent container uids, spec v2 V9) the socket directory is 0750 and the socket 0660 for it."""
    placed = provision_socket(root, agent_id, bind=bind, group=group)
    socket_path = placed["socket"]
    return {"dir": socket_path.parent, "socket": socket_path, "url": f"unix://{socket_path}",
            "token": agent_token(root, agent_id), "index": placed["index"], "link": placed["link"]}


# ---- operations (run on the host as the bound agent) -------------------------------------------

def _text(payload, key, required=False):
    value = payload.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise DawError("invalid_board_request", f"{key} must be a {'non-empty ' if required else ''}string")
    return value


def _list(payload, key, item=str):
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, item) for v in value):
        raise DawError("invalid_board_request", f"{key} must be a list")
    return value


def _int(payload, key, default):
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise DawError("invalid_board_request", f"{key} must be an integer")
    return value


def checkout_workspace(trial, value):
    """The agent's checkout workspace, `<trial>/workspace`, checked after symlinks. Another workspace, even one
    inside the checkout (`bio init sub/ws`), is refused (v3 B5): the board reads and writes only the workspace
    the runtime gave the agent."""
    trial = Path(trial).resolve()
    path = Path(value) if value else trial / "workspace"
    if not path.is_absolute():
        raise DawError("workspace_outside_checkout", "use an absolute path inside your checkout")
    resolved = path.resolve()
    if not resolved.is_relative_to(trial):
        raise DawError("workspace_outside_checkout", str(path))
    store = resolved / "blobs" / "sha256"
    entries = [*(resolved.iterdir() if resolved.is_dir() else ()), resolved / "blobs", store,
               *(store.iterdir() if store.is_dir() else ())]
    for entry in entries:
        if (entry.exists() or entry.is_symlink()) and not entry.resolve().is_relative_to(trial):
            raise DawError("workspace_outside_checkout", f"{entry.name} links outside the checkout")
    if resolved != (trial / "workspace").resolve():
        raise DawError("workspace_not_checkout_workspace", f"{path}: use {trial / 'workspace'}")
    return resolved


def local_agents(board):
    """`bio community agents` on the host (direct board access): identity, checkout, session, harness."""
    return [{**{k: r[k] for k in ("id", "name", "trial", "native_session", "parent", "created")},
             "harness": json.loads(r["config"] or "{}").get("harness", "hermes") if r["trial"] else None}
            for r in board.rows("SELECT * FROM agent ORDER BY created")]


def agents(board):
    """The service's `agents` operation: public participant fields only (`participants.describe`, plus
    `harness: null` for non-agents so rows share one shape), never another agent's host checkout path,
    native session id, configuration or tool hashes (spec v2 C14)."""
    from daw.commons.participants import describe
    return [{"harness": None, **describe(r)} for r in board.rows("SELECT * FROM agent ORDER BY created,id")]


def answer(board, author, request_id, body, *, title=None, **publish):
    """Answer a request addressed to you by publishing a reply to its question post (settles it when pending)."""
    agent = board.agent(author)
    request = board.one("SELECT * FROM request WHERE id=?", (request_id,))
    if not request:
        raise DawError("unknown_request", request_id)
    if request["target"] != agent["id"]:
        raise DawError("permission_denied", "answer only requests addressed to you")
    question = board.read(request["post"], agent["id"])
    # A hidden question's title is withheld from its answerer too; the reply still threads under it by id.
    subject = question["content"]["title"] if "content" in question else "request " + request_id
    return board.publish(agent["id"], title or "Re: " + subject, body, parent=request["post"], **publish)


def execute(root, agent_id, operation, payload):
    """Run one permitted operation as `agent_id` through the Community functions."""
    from daw.commons.claims import list_claims
    from daw.commons.permissions import require
    from daw.community import Community
    if operation not in OPERATIONS:
        raise DawError("unknown_board_operation", operation)
    action, accepted = OPERATIONS[operation]
    if not isinstance(payload, dict) or set(payload) - accepted:
        raise DawError("invalid_board_request", f"{operation} accepts {', '.join(sorted(accepted))}")
    with Community(root) as board:
        agent = board.agent(agent_id)
        if agent["kind"] != "agent":
            raise DawError("permission_denied", "the board service acts only for agents")
        require(board, agent, action)
        # The identity a request names (claims' `author` is a search filter, not an identity).
        claimed = {"inbox": payload.get("agent"), "claims": None}.get(operation, payload.get("author"))
        if claimed and claimed not in {agent["id"], agent["name"]}:
            raise DawError("agent_identity_mismatch", "this socket and token act for one agent only")
        trial = board.trial(agent)

        def workspace():
            return checkout_workspace(trial, _text(payload, "workspace"))
        if operation in {"publish", "answer", "reply"}:
            options = {"artifacts": _list(payload, "artifacts") or (), "question": _text(payload, "question"),
                       "claims": _list(payload, "claims", object), "frontier": _list(payload, "frontier", object),
                       "request_key": _text(payload, "key"),
                       "workspace": workspace() if payload.get("workspace") else None}
            if operation == "answer":
                return answer(board, agent["id"], _text(payload, "request", True), _text(payload, "body", True),
                              title=_text(payload, "title"), **options)
            if operation == "reply":
                from daw.commons.dialogue import reply
                return reply(board, agent["id"], _text(payload, "post", True), _text(payload, "body", True),
                             title=_text(payload, "title"), **options)
            return board.publish(agent["id"], _text(payload, "title", True), _text(payload, "body", True),
                                 channel=_text(payload, "channel") or "research", parent=_text(payload, "reply_to"),
                                 supersedes=_text(payload, "supersedes"), **options)
        if operation == "ask":
            return board.ask(_text(payload, "target", True), agent["id"], _text(payload, "body", True),
                             parent=_text(payload, "reply_to"), request_key=_text(payload, "key"),
                             notify=bool(payload.get("notify")))
        if operation == "fetch":
            return board.fetch(_text(payload, "post", True), workspace(), _text(payload, "question", True),
                               artifact=_text(payload, "artifact"), author=agent["id"])
        if operation in {"overview", "frontier", "experiments"} or (operation == "inbox" and payload.get("acts")):
            from daw.commons import agentview
            if operation == "frontier":
                return agentview.frontier_list(board, kind=_text(payload, "kind"), status=_text(payload, "status"),
                                               question=_text(payload, "question"),
                                               author=agent["id"] if payload.get("mine") else None)
            if operation == "experiments":
                return agentview.experiments(board)
            after = payload.get("after")
            if after is not None and (type(after) is not int or after < 0):
                raise DawError("invalid_cursor", "after is a board event sequence (an integer >= 0)")
            if operation == "overview":
                return agentview.overview(board, agent, after=after, caller=agent)
            return agentview.acts(board, agent, after=after or 0, caller=agent)
        if operation == "inbox":
            return board.inbox(agent["id"], all_states=bool(payload.get("all_states")), sent=bool(payload.get("sent")),
                               since=_text(payload, "since"))
        if operation == "agents":
            return agents(board)
        if operation == "show":
            return board.read(_text(payload, "post", True), agent["id"])
        if operation == "verify":
            return board.verify(_text(payload, "post", True), agent["id"])
        limit = _int(payload, "limit", 20 if operation == "search" else 50)
        offset = _int(payload, "offset", 0)
        if not 1 <= limit <= 200 or offset < 0:
            raise DawError("invalid_search_bounds")
        if operation == "search":
            return board.find(_text(payload, "text") or "", limit=limit, offset=offset,
                              family=_text(payload, "family") or "forum", full=bool(payload.get("full")),
                              reader=agent["id"])
        return list_claims(board, _text(payload, "q") or "", status=_text(payload, "status"), post=_text(payload, "post"),
                           author=_text(payload, "author"), limit=limit, offset=offset)


# ---- server ------------------------------------------------------------------------------------

def _address(path):
    """A connectable address: the path itself, or its symlink target when only that fits sun_path.

    No /proc or abstract-socket tricks: the service binds short paths, and a long legacy URL (the
    in-commons symlink) is followed to the short socket it names."""
    path = Path(path)
    try:
        return str(check_socket_path(path))
    except DawError:
        if not path.is_symlink():
            raise
    return str(check_socket_path(path.resolve()))


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "colloquy-board/1"

    def log_message(self, *args):  # requests are logged as JSON lines by the service, without content
        pass

    def _reply(self, status, value):
        data = canonical(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._reply(405, {"error": "method_not_allowed", "detail": "POST /v1/<operation>"})

    def do_POST(self):
        server = self.server
        operation = self.path[len("/v1/"):] if self.path.startswith("/v1/") else ""
        try:
            scheme, _, token = self.headers.get("Authorization", "").partition(" ")
            expected = read_token(server.root, server.agent_id)
            if scheme.lower() != "bearer" or not expected or not hmac.compare_digest(token.strip().encode(), expected.encode()):
                raise DawError("authentication_required", "this socket's agent token is required")
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                raise DawError("invalid_board_request", f"a JSON body of at most {MAX_BODY} bytes is required")
            try:
                payload = json.loads(self.rfile.read(length))
            except ValueError as e:
                raise DawError("invalid_board_request", "body is not JSON") from e
            value = execute(server.root, server.agent_id, operation, payload)
        except DawError as error:
            from daw.commons.app import status_for
            status = 404 if error.reason == "unknown_board_operation" else status_for(error)
            server.service.log(server.agent_id, operation, error.reason)
            self.close_connection = True
            return self._reply(status, {"error": error.reason, "detail": error.detail})
        except Exception as error:  # noqa: BLE001 - a malformed request must not stop the service
            server.service.log(server.agent_id, operation, "internal_error")
            self.close_connection = True
            return self._reply(500, {"error": "internal_error", "detail": type(error).__name__})
        server.service.log(server.agent_id, operation, "ok")
        self._reply(200, {"value": value})


class _AgentServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, service, agent_id, path, group=None):
        self.service, self.root, self.agent_id = service, service.root, agent_id
        if path.is_socket():
            path.unlink()  # a stale socket from a stopped service
        elif path.exists() or path.is_symlink():
            raise DawError("unsafe_service_path", str(path))
        super().__init__(str(check_socket_path(path)), _Handler)
        if group is not None:
            _group(path, group)
            path.chmod(0o660)  # the agent's own uid reaches it through the shared group; the token still binds it
        else:
            path.chmod(0o600)


class BoardService:
    """One socket per agent with a checkout; `refresh` picks up agents added after start."""

    def __init__(self, root, agents=(), log=None):
        from daw.community import Community
        self.root = Path(root).expanduser().resolve()
        with Community(self.root) as board:
            self.only = {board.agent(a)["id"] for a in agents}
        self.log_path = Path(log) if log else self.root / "service" / "board-service.jsonl"
        self.servers, self._lock = {}, threading.Lock()
        # Refuse at startup, not at the first agent: the longest index this commons could need must fit.
        check_socket_path(commons_socket_dir(self.root) / "999999" / "999999.sock")
        # Per-agent container uids reach their sockets through the sandbox's shared group (spec v2 V9).
        from daw.commons import sandbox
        self.group = sandbox.socket_group(sandbox.load(self.root))

    def log(self, agent, operation, outcome):
        line = canonical({"time": now(), "agent": agent, "operation": operation, "outcome": outcome}).decode()
        with self._lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as stream:
                stream.write(line + "\n")

    def refresh(self):
        from daw.community import Community
        with Community(self.root) as board:
            ids = [r["id"] for r in board.rows("SELECT id FROM agent WHERE kind='agent' AND trial IS NOT NULL "
                                               "ORDER BY created,id")]
        started = []
        for agent_id in ids:
            if agent_id in self.servers or (self.only and agent_id not in self.only):
                continue
            endpoint = provision(self.root, agent_id, bind=True, group=self.group)
            server = _AgentServer(self, agent_id, endpoint["socket"], self.group)
            server.socket_path = endpoint["socket"]
            threading.Thread(target=server.serve_forever, name=f"board-{agent_id}", daemon=True).start()
            self.servers[agent_id] = server
            started.append({"agent": agent_id, "index": endpoint["index"], "url": endpoint["url"],
                            "link": str(endpoint["link"])})
        return started

    def serve_forever(self, poll_seconds=5.0):
        try:
            while True:
                time.sleep(poll_seconds)
                self.refresh()
        finally:
            self.close()

    def close(self):
        for server in list(self.servers.values()):
            server.shutdown()
            server.server_close()
            with contextlib.suppress(OSError):
                server.socket_path.unlink()

        self.servers.clear()


# ---- client (inside the sandbox; stdlib only) --------------------------------------------------

class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(_address(self.socket_path))
        except OSError:
            sock.close()
            raise
        self.sock = sock


class BoardClient:
    def __init__(self, url, token, timeout=900):
        if not url.startswith("unix://") or not Path(url[len("unix://"):]).is_absolute():
            raise DawError("invalid_board_url", "use unix:///absolute/path/board.sock")
        if not token:
            raise DawError("board_token_missing", f"{TOKEN_ENV} is not set")
        self.path, self.token, self.timeout = Path(url[len("unix://"):]), token, timeout

    @classmethod
    def from_env(cls, env=None):
        """The board client when `BIO_BOARD_URL` is set (sandboxed checkout), else None (direct board access)."""
        env = os.environ if env is None else env
        url = env.get(URL_ENV)
        return cls(url, env.get(TOKEN_ENV, "")) if url else None

    def call(self, operation, payload):
        payload = {k: v for k, v in payload.items() if v is not None}
        body = canonical(payload)
        connection = _UnixConnection(self.path, self.timeout)
        try:
            connection.request("POST", "/v1/" + operation, body=body,
                               headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
            response = connection.getresponse()
            data = response.read()
        except OSError as e:
            raise DawError("board_service_unavailable", f"{self.path}: {e.strerror or e}") from e
        finally:
            connection.close()
        try:
            reply = json.loads(data)
        except ValueError as e:
            raise DawError("board_service_invalid_response", str(response.status)) from e
        if response.status != 200:
            raise DawError(reply.get("error", "board_service_error"), reply.get("detail", ""))
        return reply["value"]
