"""Board service for sandboxed agents (M3.6, M7.2): board writes without a board mount.

A sandboxed checkout gets no board directory. Its `bio community` commands reach
the board through this service instead: an operator-run process beside the
server that listens on one Unix socket per agent and executes exactly the
agent-permitted board operations as that agent, through the same `Community`
functions the local CLI calls:

    publish  answer  ask  fetch                   (writes: permission publish, answer, ask, fetch)
    inbox  show  search  verify  claims  agents  (reads)

Identity is bound twice. Each agent's socket lives in its own directory
`<commons>/service/board/<agent>/`, which dispatch mounts read-only into that
agent's container only; and every request carries the agent's bearer token
(`<commons>/secrets/board/<agent>.token`, 0600, passed to the container by
environment name, never in argv). A socket answers only its own agent's token,
and an `author` in a request must name that agent. The service never takes a
file path for content: bodies, claims and frontier items travel in the request.
The only path accepted is a workspace, which must resolve (on the host, after
symlinks) inside the agent's own checkout, as must its catalog, configuration
and object directories. Publishing reads that workspace from the host; fetching
writes into it under its own writer lock.

Protocol: HTTP/1.1 over the Unix socket, `POST /v1/<operation>` with a JSON
object, `Authorization: Bearer <token>`; replies `{"value": ...}` or
`{"error", "detail"}`. Each request is one line in `<commons>/service/board-service.jsonl`
(agent, operation, outcome; never content). The client below is stdlib-only, so
it runs in the agent image without the commons extra:
`BIO_BOARD_URL=unix:///path/board.sock` and `BIO_BOARD_TOKEN` select it.

Rotate an agent's token by deleting its token file while the agent is idle;
the service reads the file on every request.
"""
import contextlib
import hmac
import http.client
import json
import os
import secrets
import socket
import socketserver
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
    "ask": ("ask", {"target", "body", "reply_to", "key", "notify", "author"}),
    "fetch": ("fetch", {"post", "question", "artifact", "workspace", "author"}),
    "inbox": ("read", {"agent", "all_states", "sent", "since"}),
    "agents": ("read", set()),
    "show": ("read", {"post"}),
    "search": ("read", {"text", "limit", "offset", "family", "full"}),
    "verify": ("read", {"post"}),
    "claims": ("read", {"q", "post", "status", "author", "limit", "offset"}),
}


# ---- provisioning (operator side) --------------------------------------------------------------

def socket_dir(root, agent_id):
    return Path(root) / "service" / "board" / _safe_id(agent_id)


def token_path(root, agent_id):
    return Path(root) / "secrets" / "board" / (_safe_id(agent_id) + ".token")


def _safe_id(agent_id):
    if not agent_id or not all(c.isalnum() or c in "_-" for c in agent_id):
        raise DawError("invalid_agent_identity", repr(agent_id))
    return agent_id


def _private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise DawError("unsafe_service_path", str(path))
    path.chmod(0o700)


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


def provision(root, agent_id):
    """Socket directory and token for one agent. Returns what dispatch mounts and passes by name."""
    folder = socket_dir(root, agent_id)
    _private_dir(folder.parent.parent)
    _private_dir(folder.parent)
    _private_dir(folder)
    return {"dir": folder, "socket": folder / SOCKET, "url": f"unix://{folder / SOCKET}",
            "token": agent_token(root, agent_id)}


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
    """A workspace inside the agent's own checkout (default `<trial>/workspace`), checked after symlinks."""
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
    return resolved


def agents(board):
    """Participants as `bio community agents` lists them (identity, checkout, session, harness)."""
    return [{**{k: r[k] for k in ("id", "name", "trial", "native_session", "parent", "created")},
             "harness": json.loads(r["config"] or "{}").get("harness", "hermes") if r["trial"] else None}
            for r in board.rows("SELECT * FROM agent ORDER BY created")]


def answer(board, author, request_id, body, *, title=None, **publish):
    """Answer a request addressed to you by publishing a reply to its question post (settles it when pending)."""
    agent = board.agent(author)
    request = board.one("SELECT * FROM request WHERE id=?", (request_id,))
    if not request:
        raise DawError("unknown_request", request_id)
    if request["target"] != agent["id"]:
        raise DawError("permission_denied", "answer only requests addressed to you")
    question = board.show(request["post"])["content"]
    return board.publish(agent["id"], title or "Re: " + question["title"], body, parent=request["post"], **publish)


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
        claimed = payload.get("author") if operation != "claims" else None
        if operation == "inbox":
            claimed = payload.get("agent")
        if claimed and claimed not in {agent["id"], agent["name"]}:
            raise DawError("agent_identity_mismatch", "this socket and token act for one agent only")
        trial = board.trial(agent)
        workspace = lambda: checkout_workspace(trial, _text(payload, "workspace"))  # noqa: E731
        if operation in {"publish", "answer"}:
            options = {"artifacts": _list(payload, "artifacts") or (), "question": _text(payload, "question"),
                       "claims": _list(payload, "claims", object), "frontier": _list(payload, "frontier", object),
                       "request_key": _text(payload, "key"),
                       "workspace": workspace() if payload.get("workspace") else None}
            if operation == "answer":
                return answer(board, agent["id"], _text(payload, "request", True), _text(payload, "body", True),
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
        if operation == "inbox":
            return board.inbox(agent["id"], all_states=bool(payload.get("all_states")), sent=bool(payload.get("sent")),
                               since=_text(payload, "since"))
        if operation == "agents":
            return agents(board)
        if operation in {"show", "verify"}:
            return getattr(board, operation)(_text(payload, "post", True))
        limit = _int(payload, "limit", 20 if operation == "search" else 50)
        offset = _int(payload, "offset", 0)
        if not 1 <= limit <= 200 or offset < 0:
            raise DawError("invalid_search_bounds")
        if operation == "search":
            return board.find(_text(payload, "text") or "", limit=limit, offset=offset,
                              family=_text(payload, "family") or "forum", full=bool(payload.get("full")))
        return list_claims(board, _text(payload, "q") or "", status=_text(payload, "status"), post=_text(payload, "post"),
                           author=_text(payload, "author"), limit=limit, offset=offset)


# ---- server ------------------------------------------------------------------------------------

@contextlib.contextmanager
def _address(path):
    """A bindable/connectable address for a socket path; long paths go through /proc/self/fd on Linux (108-byte limit)."""
    path = Path(path)
    if len(os.fsencode(path)) < 100 or not Path("/proc/self/fd").is_dir():
        yield str(path)
        return
    fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_PATH", 0) | os.O_DIRECTORY)
    try:
        yield f"/proc/self/fd/{fd}/{path.name}"
    finally:
        os.close(fd)


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

    def __init__(self, service, agent_id, path):
        self.service, self.root, self.agent_id = service, service.root, agent_id
        if path.is_socket():
            path.unlink()  # a stale socket from a stopped service
        elif path.exists() or path.is_symlink():
            raise DawError("unsafe_service_path", str(path))
        with _address(path) as address:
            super().__init__(address, _Handler)
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
            endpoint = provision(self.root, agent_id)
            server = _AgentServer(self, agent_id, endpoint["socket"])
            threading.Thread(target=server.serve_forever, name=f"board-{agent_id}", daemon=True).start()
            self.servers[agent_id] = server
            started.append({"agent": agent_id, "url": endpoint["url"]})
        return started

    def serve_forever(self, poll_seconds=5.0):
        try:
            while True:
                time.sleep(poll_seconds)
                self.refresh()
        finally:
            self.close()

    def close(self):
        for agent_id, server in list(self.servers.items()):
            server.shutdown()
            server.server_close()
            with contextlib.suppress(OSError):
                (socket_dir(self.root, agent_id) / SOCKET).unlink()
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
            with _address(self.socket_path) as address:
                sock.connect(address)
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
