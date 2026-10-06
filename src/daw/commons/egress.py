"""Allowlisting HTTP(S) egress proxy for sandboxed agent checkouts (M3.6).

Containers reach the network only through this proxy: `CONNECT host:port` for
TLS and absolute-form `GET http://host/...` for plain HTTP. A destination is
allowed when its host is an allowlisted name or a subdomain of one, its port
is allowed, and (unless explicitly permitted) none of its resolved addresses is
private, loopback, link-local or reserved. The proxy connects to the address it
checked, so a second DNS answer cannot redirect the connection. Every decision
is appended to a JSONL log. TLS is never intercepted.
"""
import asyncio
import ipaddress
import json
import socket
from pathlib import Path
from urllib.parse import urlsplit

from daw.util import now

# Hosts of the bio source adapters (daw.adapters, daw.geo) and the data portals agents use.
SOURCE_HOSTS = ("ncbi.nlm.nih.gov", "ebi.ac.uk", "encodeproject.org", "gtexportal.org", "cellxgene.cziscience.com",
                "zenodo.org", "figshare.com", "pmc-oa-opendata.s3.amazonaws.com", "chip-atlas.org", "chip-atlas.dbcls.jp",
                "ensembl.org", "uniprot.org", "humancellatlas.org", "proteinatlas.org")
HEAD_LIMIT = 65536


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


def parse_head(head):
    """(method, host, port, upstream head or None for CONNECT)."""
    lines = head.split(b"\r\n")
    method, target, version = lines[0].decode("latin-1").split(" ", 2)
    if method == "CONNECT":
        host, _, port = target.rpartition(":")
        return method, host.strip("[]"), int(port), None
    url = urlsplit(target)
    if url.scheme != "http" or not url.hostname:
        raise ValueError("absolute http URL required")
    path = (url.path or "/") + (f"?{url.query}" if url.query else "")
    upstream = b"\r\n".join([f"{method} {path} {version}".encode("latin-1"), *lines[1:]])
    return method, url.hostname, url.port or 80, upstream


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
    allowed, reason, address = await asyncio.get_running_loop().run_in_executor(None, policy.check, host, port)
    record.update(allowed=allowed, reason=reason)
    if not allowed:
        _log(log, record)
        writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n"
                     + f"egress denied: {reason}\n".encode())
        await writer.drain()
        writer.close()
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
    return await asyncio.start_server(lambda r, w: handle(r, w, policy, log), host, port, limit=HEAD_LIMIT)


def serve(policy, host="0.0.0.0", port=3128, log=None):
    async def main():
        server = await start(policy, host, port, log)
        async with server:
            await server.serve_forever()
    asyncio.run(main())
