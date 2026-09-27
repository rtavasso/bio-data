"""Bounded byte-preserving HTTP acquisition. No implicit remote execution or resume."""
import email.utils
import hashlib
import ipaddress
import os
import random
import socket
import time
import uuid
import zlib
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from daw.models import Asset
from daw.util import DawError, now, safe_url


def validate_url(url, *, resolve=True):
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise DawError("unsafe_url", "only public HTTP(S) destinations without embedded credentials")
    if parsed.port not in (None, 80, 443):
        raise DawError("unsafe_url", "nonstandard port")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise DawError("unsafe_url", "private host")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = []
        if resolve:
            addresses = [ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(host, parsed.port or 443)]
    if any(not ip.is_global for ip in addresses):
        raise DawError("unsafe_url", "non-public address")
    return url


def sniff(path, expected=None):
    with Path(path).open("rb") as f:
        prefix = f.read(4096).lstrip()
    low = prefix.lower()
    if expected not in ("html", None) and (low.startswith((b"<!doctype html", b"<html")) or b"<title>access denied" in low):
        raise DawError("restricted", "HTML response instead of expected data")
    signatures = {"xlsx": b"PK", "zip": b"PK", "h5ad": b"\x89HDF\r\n\x1a\n", "cool": b"\x89HDF\r\n\x1a\n",
                  "mcool": b"\x89HDF\r\n\x1a\n", "gz": b"\x1f\x8b", "pdf": b"%PDF"}
    if expected in signatures and not prefix.startswith(signatures[expected]):
        raise DawError("integrity_failed", f"unexpected signature for {expected}")
    if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise DawError("unsupported_route", "Git LFS pointer, not data")


class Transport:
    def __init__(self, workspace, *, http_transport=None, sleep=time.sleep):
        self.ws = workspace
        self.client = httpx.Client(transport=http_transport, timeout=workspace.budgets.timeout_seconds,
                                   follow_redirects=False, trust_env=False,
                                   headers={"User-Agent": "DataArchaeologyWorkbench/0.1 (public research)",
                                            "Accept-Encoding": "identity"})
        self.mock = isinstance(http_transport, httpx.MockTransport)
        self.sleep = sleep
        self.requests = 0
        self.transferred = 0
        self.last_request = {}

    def close(self):
        self.client.close()

    def fetch(self, url, *, expected=None, checksum=None, checksum_scope="file", limit=None, resource=None):
        limit = min(limit or self.ws.budgets.asset_bytes, self.ws.budgets.asset_bytes)
        original_url = url
        histories = []
        for retry in range(self.ws.budgets.retries):
            path = self.ws.root / "staging" / f"http-{uuid.uuid4().hex}.partial"
            headers, status, response_blob = {}, None, None
            count, outcome, error = 0, "transient_failure", None
            retry_delay = None
            try:
                for redirect in range(6):
                    validate_url(url, resolve=not self.mock)
                    if self.requests >= self.ws.budgets.requests:
                        raise DawError("over_budget", "request budget exhausted")
                    self.ws.check_disk()
                    origin = urlsplit(url).netloc
                    delay = max(0, 0.2 - (time.monotonic() - self.last_request.get(origin, 0)))
                    if delay:
                        self.sleep(delay)
                    self.requests += 1
                    self.last_request[origin] = time.monotonic()
                    with self.client.stream("GET", url) as response:
                        status = response.status_code
                        headers = {k: v for k, v in response.headers.items() if k.lower() in
                                   {"etag", "last-modified", "content-length", "content-type", "content-encoding",
                                    "content-range", "retry-after"}}
                        if status in {301, 302, 303, 307, 308}:
                            target = urljoin(url, response.headers.get("location", ""))
                            validate_url(target, resolve=not self.mock)
                            histories.append({"url": safe_url(url), "status": status, "location": safe_url(target)})
                            url = target
                            if redirect == 5:
                                raise DawError("unsupported_route", "redirect limit")
                            continue
                        if status in {429, 500, 502, 503, 504}:
                            retry_delay = self._retry_delay(headers.get("retry-after"), retry)
                        # Small failure payloads are evidence too, but never a full successful asset.
                        response_limit = min(limit, 2**20) if status != 200 else limit
                        length = headers.get("content-length")
                        if length and int(length) > response_limit:
                            raise DawError("over_budget", "declared response size exceeds budget")
                        with path.open("wb") as f:
                            # MockTransport may already have consumed its synthetic response.
                            chunks = [response.content] if response.is_stream_consumed else response.iter_raw()
                            for chunk in chunks:
                                count += len(chunk)
                                self.transferred += len(chunk)
                                if count > response_limit or self.transferred > self.ws.budgets.bundle_bytes:
                                    raise DawError("over_budget", "actual transferred bytes exceed budget")
                                self.ws.check_disk(len(chunk))
                                f.write(chunk)
                            f.flush()
                            os.fsync(f.fileno())
                        response_blob = self.ws.put_file(path, "metadata" if status != 200 else "full")
                        if status != 200:
                            reason = {401: "restricted", 403: "restricted", 404: "not_found", 410: "removed_upstream"}.get(status)
                            raise DawError(reason or ("transient_failure" if retry_delay is not None else "unsupported_route"), f"HTTP {status}")
                        if length and count != int(length):
                            raise DawError("integrity_failed", "Content-Length mismatch")
                        encoded_blob = response_blob
                        encoding = headers.get("content-encoding", "identity").lower()
                        if encoding != "identity":
                            if encoding not in {"gzip", "deflate"}:
                                raise DawError("unsupported_route", f"unhandled transport encoding: {encoding}")
                            self._decode(path, encoding, limit)
                        if checksum:
                            if checksum_scope not in {"file", "http_representation"}:
                                raise DawError("integrity_failed", "unknown provider checksum representation")
                            algorithm, expected_hash = checksum.split(":", 1)
                            if algorithm not in {"md5", "sha256", "sha1"}:
                                raise DawError("integrity_failed", "unsupported checksum algorithm")
                            hash_path = self.ws.blob_path(encoded_blob) if checksum_scope == "http_representation" else path
                            h = hashlib.new(algorithm)
                            with hash_path.open("rb") as inp:
                                for block in iter(lambda: inp.read(2**20), b""):
                                    h.update(block)
                            if h.hexdigest().lower() != expected_hash.lower():
                                raise DawError("integrity_failed", "provider checksum mismatch")
                        sniff(path, expected)
                        file_blob = self.ws.put_file(path)
                        outcome = "available_full"
                        sid = self.ws.snapshot(safe_url(original_url), outcome,
                            {"url": safe_url(url), "status": status, "headers": headers, "redirects": histories,
                             "transferred_bytes": count, "file_blob": file_blob, "http_representation_blob": encoded_blob,
                             "transport_encoding": encoding, "checksum": checksum, "checksum_scope": checksum_scope,
                             "identity_strength": "local_sha256", "attempt": retry + 1,
                             "retrieved_utc": now(), "resume": "disabled; every retry starts fresh"},
                            encoded_blob, resource)
                        return {"outcome": outcome, "blob": file_blob, "snapshot": sid, "bytes": count}
                raise DawError("unsupported_route", "redirect loop")
            except (httpx.HTTPError, OSError) as e:
                # Exception strings can contain credentials or signed URLs.
                error = type(e).__name__
                outcome = "transient_failure"
            except (DawError, ValueError, zlib.error) as e:
                outcome = e.reason if isinstance(e, DawError) else "integrity_failed"
                error = e.detail if isinstance(e, DawError) else type(e).__name__
            finally:
                path.unlink(missing_ok=True)
            sid = self.ws.snapshot(safe_url(original_url), outcome,
                                   {"status": status, "headers": headers, "redirects": histories,
                                    "transferred_bytes": count, "error": error, "attempt": retry + 1},
                                   response_blob, resource)
            if outcome != "transient_failure" or retry + 1 == self.ws.budgets.retries or (retry_delay is not None and retry_delay > 30):
                return {"outcome": outcome, "blob": None, "snapshot": sid, "reason": error, "bytes": count,
                        "retry_after_seconds": retry_delay}
            self.sleep(retry_delay if retry_delay is not None else min(4, 2**retry + random.random()))
        raise AssertionError("unreachable")

    def _retry_delay(self, header, retry):
        if header:
            try:
                seconds = float(header)
            except ValueError:
                try:
                    seconds = email.utils.parsedate_to_datetime(header).timestamp() - time.time()
                except (TypeError, ValueError):
                    seconds = 2**retry
            return max(0, seconds)
        return min(4, 2**retry + random.random())

    def _decode(self, path, encoding, limit):
        decoded = path.with_suffix(".decoded")
        dec = zlib.decompressobj(31 if encoding == "gzip" else zlib.MAX_WBITS)
        count = 0
        try:
            with path.open("rb") as src, decoded.open("wb") as dst:
                for chunk in iter(lambda: src.read(2**16), b""):
                    result = dec.decompress(chunk, limit - count + 1)
                    count += len(result)
                    if count > limit or dec.unconsumed_tail:
                        raise DawError("over_budget", "decoded transport representation")
                    dst.write(result)
                if not dec.eof:
                    raise DawError("integrity_failed", "truncated encoded response")
                dst.flush()
                os.fsync(dst.fileno())
            os.replace(decoded, path)
        finally:
            decoded.unlink(missing_ok=True)

    def acquire(self, aid, allow_raw=False):
        current = self.ws.asset(aid)
        asset = Asset.model_validate(current["body"])
        if current["blob"] and current["access"] == "available_full":
            return {"asset_revision": aid, "outcome": "available_full", "blob": current["blob"], "reused": True}
        blocked = None
        if asset.raw and not allow_raw:
            blocked = "raw acquisition requires an explicit processing-plan allowance"
        elif not asset.url:
            blocked = "no downloadable public locator"
        if blocked:
            result = {"outcome": "unsupported_route", "reason": blocked, "snapshot": current["snapshot_id"], "blob": None}
        elif asset.size is not None and asset.size > self.ws.budgets.asset_bytes:
            result = {"outcome": "over_budget", "reason": "source-declared size exceeds per-asset budget",
                      "snapshot": current["snapshot_id"], "blob": None}
        else:
            result = self.fetch(asset.url, expected=asset.name.rsplit(".", 1)[-1].lower(),
                                checksum=asset.checksum, checksum_scope=asset.checksum_scope,
                                resource=current["resource_id"])
        asset.access = result["outcome"]
        asset.metadata = {**asset.metadata, "acquisition_reason": result.get("reason"),
                          "source_metadata_snapshot": asset.metadata.get("source_metadata_snapshot") or current["snapshot_id"],
                          "listed_revision": asset.metadata.get("listed_revision") or aid}
        revision = self.ws.register_asset(self.ws.bundle_for(current),
            self.ws.one("SELECT provider FROM resource WHERE id=?", (current["resource_id"],))["provider"],
            asset, result["snapshot"], result.get("blob"))
        return {**result, "asset_revision": revision, "previous_revision": aid}
