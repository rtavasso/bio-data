import hashlib
import json
import os
import platform
import re
from datetime import UTC, datetime
from importlib.metadata import distributions
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class DawError(Exception):
    def __init__(self, reason: str, detail: str = ""):
        self.reason, self.detail = reason, detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def now() -> str:
    return datetime.now(UTC).isoformat()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path, algorithm="sha256") -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(2**20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda x: (_ for _ in ()).throw(
        ValueError(f"nonfinite JSON constant: {x}")))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(canonical(value) + b"\n")
        f.flush()
        os.fsync(f.fileno())


SENSITIVE = re.compile(r"token|signature|credential|password|secret|api[_-]?key|authorization", re.I)


def safe_url(url: str) -> str:
    p = urlsplit(url)
    host = p.hostname or ""
    if p.port:
        host += f":{p.port}"
    query = urlencode([(k, "REDACTED" if SENSITIVE.search(k) else v)
                       for k, v in parse_qsl(p.query, keep_blank_values=True)])
    return urlunsplit((p.scheme, host, p.path, query, ""))


def environment_identity():
    root = Path(__file__).resolve().parents[2]
    package = Path(__file__).resolve().parent
    source = {str(p.relative_to(package)): file_hash(p) for p in sorted(package.rglob("*.py"))}
    return {"python": platform.python_version(), "platform": platform.platform(),
            "packages": sorted((d.metadata["Name"], d.version) for d in distributions()),
            "source": digest(source), "lock": file_hash(root / "uv.lock") if (root / "uv.lock").exists() else None}
