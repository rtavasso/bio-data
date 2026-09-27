import gzip
import hashlib
import json

import httpx
import pytest

from daw.transport import Transport, validate_url
from daw.models import Asset
from daw.util import DawError, safe_url


def transport(ws, handler):
    return Transport(ws, http_transport=httpx.MockTransport(handler), sleep=lambda _: None)


def test_bytes_and_provider_checksum(ws):
    content = b"gene\tvalue\nNA\t0\n"
    http = transport(ws, lambda r: httpx.Response(200, content=content))
    result = http.fetch("https://example.org/table.tsv", expected="tsv", checksum="md5:" + hashlib.md5(content).hexdigest())
    assert result["outcome"] == "available_full"
    assert ws.blob_path(result["blob"]).read_bytes() == content
    http.close()


@pytest.mark.parametrize("status,outcome", [(403, "restricted"), (404, "not_found"), (410, "removed_upstream")])
def test_denied_and_disappeared_never_become_empty_data(ws, status, outcome):
    http = transport(ws, lambda r: httpx.Response(status, content=b"denied"))
    result = http.fetch("https://example.org/file.h5ad", expected="h5ad")
    assert result["outcome"] == outcome and result["blob"] is None
    assert len(ws.rows("SELECT * FROM snapshot")) == 1


@pytest.mark.parametrize("content,expected,outcome", [(b"<html>Access denied</html>", "h5ad", "restricted"),
    (b"not hdf5", "h5ad", "integrity_failed"), (b"version https://git-lfs.github.com/spec/v1\n", "txt", "unsupported_route")])
def test_challenge_and_pointer_not_success(ws, content, expected, outcome):
    result = transport(ws, lambda r: httpx.Response(200, content=content)).fetch("https://example.org/file", expected=expected)
    assert result["outcome"] == outcome and result["blob"] is None


def test_checksum_mismatch_preserves_receipt(ws):
    result = transport(ws, lambda r: httpx.Response(200, content=b"wrong")).fetch("https://example.org/a", checksum="md5:" + "0" * 32)
    assert result["outcome"] == "integrity_failed"
    snapshot = ws.one("SELECT * FROM snapshot WHERE id=?", (result["snapshot"],))
    assert snapshot["blob"] is not None and result["blob"] is None


def test_actual_stream_budget(ws):
    result = transport(ws, lambda r: httpx.Response(200, content=b"x" * 100)).fetch("https://example.org/a", limit=50)
    assert result["outcome"] == "over_budget"
    assert not list((ws.root / "staging").glob("*.partial"))


def test_retries_restart_not_append(ws):
    calls = []
    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, headers={"retry-after": "0"}, content=b"try later")
        return httpx.Response(200, headers={"etag": '"new"'}, content=b"complete")
    result = transport(ws, respond).fetch("https://example.org/a")
    assert result["outcome"] == "available_full"
    assert ws.blob_path(result["blob"]).read_bytes() == b"complete"
    assert all("range" not in request.headers for request in calls)
    assert len(ws.rows("SELECT * FROM snapshot")) == 2


def test_redirect_private_blocked(ws):
    result = transport(ws, lambda r: httpx.Response(302, headers={"location": "http://127.0.0.1/secrets"})).fetch("https://example.org/a")
    assert result["outcome"] == "unsafe_url"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://localhost/x", "http://169.254.169.254/x",
                                  "http://[::1]/x", "https://user:pass@example.org/", "http://192.168.1.1/x"])
def test_private_destinations_rejected(url):
    with pytest.raises(DawError):
        validate_url(url, resolve=False)


def test_secret_redaction():
    assert "secret" not in safe_url("https://u:secret@example.org/x?token=secret&file=12")
    assert "file=12" in safe_url("https://example.org/x?token=secret&file=12")


class RawBytes(httpx.SyncByteStream):
    def __init__(self, value):
        self.value = value

    def __iter__(self):
        yield self.value


def test_transport_encoding_separate_identities(ws):
    decoded = b"gene\tvalue\nPMP22\t1\n"
    encoded = gzip.compress(decoded)
    def response(r):
        return httpx.Response(200, headers={"content-encoding": "gzip"}, stream=RawBytes(encoded))
    result = transport(ws, response).fetch("https://example.org/a.tsv", expected="tsv", checksum="md5:" + hashlib.md5(decoded).hexdigest())
    assert result["outcome"] == "available_full"
    snapshot = ws.one("SELECT * FROM snapshot WHERE id=?", (result["snapshot"],))
    body = json.loads(snapshot["body"])
    assert body["file_blob"] != body["http_representation_blob"]
    assert ws.blob_path(result["blob"]).read_bytes() == decoded


def test_source_declared_budget_checked_without_request(ws):
    bundle = ws.resource("bundle", "test", "large")
    aid = ws.register_asset(bundle, "test", Asset(native_id="large", name="matrix.mtx.gz", url="https://example.org/large",
        size=ws.budgets.asset_bytes + 1), None)
    http = transport(ws, lambda r: pytest.fail("oversized listing must not issue a request"))
    result = http.acquire(aid)
    assert result["outcome"] == "over_budget"
    assert ws.asset(result["asset_revision"])["access"] == "over_budget"


def test_retry_after_larger_than_wait_budget_defers(ws):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"retry-after": "3600"}, content=b"later")
    result = transport(ws, handler).fetch("https://example.org/limited")
    assert len(calls) == 1 and result["outcome"] == "transient_failure"
    assert "3600" in ws.one("SELECT body FROM snapshot WHERE id=?", (result["snapshot"],))["body"]
