"""Allowlisting HTTP(S) egress proxy for sandboxed agent checkouts (M3.6, spec v2 C7).

Containers reach the network only through this proxy: `CONNECT host:port` for
TLS and absolute-form `GET http://host/...` for plain HTTP. A destination is
allowed when its host is an allowlisted name or a subdomain of one, its port
is allowed, and (unless explicitly permitted) none of its resolved addresses is
private, loopback, link-local or reserved. The proxy connects to the address it
checked, so a second DNS answer cannot redirect the connection. Every decision
is appended to a JSONL log. TLS is never intercepted.

Token-scoped policies. The allowlist is not frozen when the proxy starts. Each
dispatch computes its own list (the agent's harness provider hosts, the source
adapter hosts and the operator's extras) and writes it as a policy file into a
platform-owned directory, `<commons>/service/egress/policies/<sha256(token)>.json`
(0600; the commons root is never mounted into an agent container). The container
receives the proxy URL with that token as its password, by environment name only
(`HTTPS_PROXY=http://<run>:<token>@egress:3128`). The proxy reads the policy for
the presented `Proxy-Authorization` on every connection, so an agent added after
the proxy started is served, an expired or revoked token is refused (407), and one
agent's token never opens another agent's hosts. The credential is stripped from
plain-HTTP requests before they go upstream and never appears in the log.
"""
import asyncio
import base64
import hashlib
import ipaddress
import json
import os
import secrets
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from daw.util import DawError, now

# Hosts of the bio source adapters (daw.adapters, daw.geo) and the data portals agents use.
SOURCE_HOSTS = ("ncbi.nlm.nih.gov", "ebi.ac.uk", "encodeproject.org", "gtexportal.org", "cellxgene.cziscience.com",
                "zenodo.org", "figshare.com", "pmc-oa-opendata.s3.amazonaws.com", "chip-atlas.org", "chip-atlas.dbcls.jp",
                "ensembl.org", "uniprot.org", "humancellatlas.org", "proteinatlas.org")
HEAD_LIMIT = 65536
# Without a run time limit a policy still expires; an interrupted dispatch cannot leave a token valid forever.
DEFAULT_POLICY_SECONDS = 7 * 24 * 3600
POLICY_SLACK_SECONDS = 3600


class Policy:
    def __init__(self, hosts=SOURCE_HOSTS, ports=(443, 80), *, allow_private=False, resolver=None):
        self.hosts = tuple(sorted({h.lower().strip(".") for h in hosts if h}))
        self.ports = tuple(ports)
        self.allow_private = allow_private
        self.resolver = resolver or (lambda host, port: [i[4][0] for i in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)])

    def named(self, host):
        host = host.lower().strip(".")
        return any(host == h or host.endswith("." + h) for h in self.hosts)

    def check(self, host, port):
        """(allowed, reason, address to connect to)."""
        if not host or not self.named(host):
            return False, "host_not_allowlisted", None
        if port not in self.ports:
            return False, "port_not_allowed", None
        try:
            addresses = self.resolver(host, port)
        except OSError:
            return False, "resolution_failed", None
        if not addresses:
            return False, "resolution_failed", None
        if not self.allow_private:
            for address in addresses:
                ip = ipaddress.ip_address(address.split("%")[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                    return False, "resolves_to_private_address", None
        return True, "allowed", addresses[0]

    def with_hosts(self, hosts):
        return Policy(hosts, self.ports, allow_private=self.allow_private, resolver=self.resolver)


# ---- token-scoped policies (written at dispatch, read per connection) ---------------------------

def policy_dir(root):
    return Path(root) / "service" / "egress" / "policies"


def _policy_id(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue(root, hosts, *, run, agent, seconds=0):
    """Write one dispatch's policy; returns (token, record). The token is returned once and never stored."""
    folder = policy_dir(root)
    for part in (folder.parent.parent, folder.parent, folder):
        part.mkdir(exist_ok=True, mode=0o700)
        if part.is_symlink():
            raise DawError("unsafe_service_path", str(part))
    token = "egress_" + secrets.token_urlsafe(32)
    lifetime = (seconds + POLICY_SLACK_SECONDS) if seconds else DEFAULT_POLICY_SECONDS
    expires = (datetime.now(UTC) + timedelta(seconds=lifetime)).isoformat()
    record = {"format": 1, "policy": _policy_id(token), "run": run, "agent": agent,
              "hosts": sorted({h.lower().strip(".") for h in hosts if h}), "issued": now(), "expires": expires}
    path = folder / (record["policy"] + ".json")
    temporary = folder / (record["policy"] + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(record, stream, sort_keys=True)
    os.replace(temporary, path)
    return token, record


def revoke(root, policy):
    """Delete a dispatch's policy (end of the run); returns whether a file was removed."""
    if not policy or not all(c in "0123456789abcdef" for c in policy):
        return False
    path = policy_dir(root) / (policy + ".json")
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def proxy_url(base, run, token):
    """The configured proxy URL with the dispatch credential as userinfo (passed to the container by name)."""
    parts = urlsplit(base)
    if not parts.hostname:
        raise DawError("invalid_sandbox_config", "proxy must be an absolute URL such as http://egress:3128")
    netloc = f"{run}:{token}@{parts.hostname}" + (f":{parts.port}" if parts.port else "")
    return parts._replace(netloc=netloc).geturl()


class PolicyStore:
    """Policies read from the platform-owned directory on every connection (never cached)."""

    def __init__(self, directory, base=None):
        self.directory = Path(directory)
        self.base = base or Policy(())

    def resolve(self, authorization):
        """(Policy or None, reason, record) for a `Proxy-Authorization` header value."""
        scheme, _, value = (authorization or "").partition(" ")
        if scheme.lower() != "basic" or not value.strip():
            return None, "proxy_credential_required", None
        try:
            _, _, token = base64.b64decode(value.strip(), validate=True).decode().partition(":")
        except (ValueError, UnicodeDecodeError):
            return None, "proxy_credential_invalid", None
        if not token:
            return None, "proxy_credential_invalid", None
        path = self.directory / (_policy_id(token) + ".json")
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            return None, "proxy_credential_invalid", None
        try:
            expired = datetime.fromisoformat(record["expires"]) <= datetime.now(UTC)
        except (KeyError, TypeError, ValueError):
            expired = True
        if expired:
            return None, "proxy_credential_expired", record
        return self.base.with_hosts(record.get("hosts", ())), "ok", record


def parse_head(head):
    """(method, host, port, upstream head or None for CONNECT). Proxy credentials never go upstream."""
    lines = head.split(b"\r\n")
    method, target, version = lines[0].decode("latin-1").split(" ", 2)
    if method == "CONNECT":
        host, _, port = target.rpartition(":")
        return method, host.strip("[]"), int(port), None
    url = urlsplit(target)
    if url.scheme != "http" or not url.hostname:
        raise ValueError("absolute http URL required")
    path = (url.path or "/") + (f"?{url.query}" if url.query else "")
    kept = [line for line in lines[1:] if not line.lower().startswith(b"proxy-authorization:")]
    upstream = b"\r\n".join([f"{method} {path} {version}".encode("latin-1"), *kept])
    return method, url.hostname, url.port or 80, upstream


def header(head, name):
    """One request header's value (latin-1), or None."""
    prefix = name.lower().encode() + b":"
    for line in head.split(b"\r\n")[1:]:
        if line.lower().startswith(prefix):
            return line[len(prefix):].strip().decode("latin-1")
    return None


async def _pipe(reader, writer, counter, key):
    try:
        while data := await reader.read(65536):
            counter[key] += len(data)
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


def _log(path, record):
    if path:
        with Path(path).open("a") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


async def _refuse(writer, status, reason, extra=b""):
    writer.write(f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\nConnection: close\r\n".encode() + extra
                 + f"\r\negress denied: {reason}\n".encode())
    await writer.drain()
    writer.close()


async def handle(reader, writer, policy, log=None):
    record = {"observed": now(), "client": str(writer.get_extra_info("peername"))}
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 30)
        if len(head) > HEAD_LIMIT:
            raise ValueError("request head too large")
        method, host, port, upstream_head = parse_head(head)
    except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError) as e:
        _log(log, {**record, "allowed": False, "reason": "bad_request", "detail": str(e)[:200]})
        writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
        await writer.drain()
        writer.close()
        return
    record.update(method=method, host=host, port=port)
    if isinstance(policy, PolicyStore):
        scoped, reason, issued = policy.resolve(header(head, "Proxy-Authorization"))
        if issued:
            record.update(policy=issued.get("policy", "")[:16], run=issued.get("run"), agent=issued.get("agent"))
        if scoped is None:
            _log(log, {**record, "allowed": False, "reason": reason})
            await _refuse(writer, "407 Proxy Authentication Required", reason,
                          b'Proxy-Authenticate: Basic realm="colloquy-egress"\r\n')
            return
        policy = scoped
    allowed, reason, address = await asyncio.get_running_loop().run_in_executor(None, policy.check, host, port)
    record.update(allowed=allowed, reason=reason)
    if not allowed:
        _log(log, record)
        await _refuse(writer, "403 Forbidden", reason)
        return
    try:
        up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(address, port), 30)
    except (OSError, asyncio.TimeoutError):
        _log(log, {**record, "allowed": True, "reason": "upstream_unreachable"})
        writer.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
        await writer.drain()
        writer.close()
        return
    if upstream_head is None:
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
    else:
        up_writer.write(upstream_head)
    counter = {"bytes_up": 0, "bytes_down": 0}
    await asyncio.gather(_pipe(reader, up_writer, counter, "bytes_up"), _pipe(up_reader, writer, counter, "bytes_down"))
    _log(log, {**record, **counter, "closed": now()})


async def start(policy, host="127.0.0.1", port=3128, log=None):
    """`policy` is a static `Policy` (every client gets it) or a `PolicyStore` (per-dispatch credentials)."""
    return await asyncio.start_server(lambda r, w: handle(r, w, policy, log), host, port, limit=HEAD_LIMIT)


def serve(policy, host="0.0.0.0", port=3128, log=None):
    async def main():
        server = await start(policy, host, port, log)
        async with server:
            await server.serve_forever()
    asyncio.run(main())
