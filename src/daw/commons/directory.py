"""A public commons directory (spec v2 V7): where labs publish snapshots and other commons find and fetch them.

**Format.** A directory is one canonical JSON file, `directory.json` (`colloquy.directory/1`), usually served
as a static file next to the snapshots it lists:

```
{"format": "colloquy.directory/1", "name": "...", "entries": [
  {"snapshot": "<64 hex>", "title": "...", "lab": "...", "scope": {...}, "counts": {...},
   "location": "snapshots/<id>/" | "https://host/path/<id>/", "files": N, "bytes": N, "published": "<iso time>",
   "publisher": "...", "note": "..."}]}
```

A `location` is a path relative to the directory file (no `..`, no absolute paths) or an absolute http(s)
URL; it names a snapshot folder (its `snapshot.json` and listed files). The snapshot ID is the sha256 of
`snapshot.json`, so an entry cannot lie about what it lists: every fetch re-hashes.

**Publish** (`bio commons directory publish SNAPSHOT_DIR --directory DIR/directory.json`) verifies the
snapshot (canonical manifest, every listed hash and size, no unlisted files or links), copies it to
`DIR/snapshots/<id>/` unless `--location` names where it is already hosted, adds the entry (idempotent per
snapshot id) and writes a receipt `DIR/receipts/<id>.publish.json`. Publishing writes files only; hosting
the folder (any static web server or a shared drive) is the lab's choice.

**List** reads a directory from a local path, a `file://` URL or an http(s) URL and validates it.

**Fetch** (`bio commons --root COMMONS directory fetch DIRECTORY SNAPSHOT_ID`) resolves the entry's location
against the directory, downloads `snapshot.json` (its hash must equal the requested ID) and then every listed
file into a staging folder, checking each size and sha256 as it arrives (size-capped, http(s) only, no
redirects to other schemes), imports it read-only (`export.import_snapshot`, which re-verifies everything),
indexes its records (`federation.index_snapshot`), keeps a copy of the directory under
`<commons>/directory/sources/` and writes a receipt `<commons>/federation/<id>.fetch.json`. Nothing fetched
is executed, imported as code, or written into this board's posts, claims or library.
"""
import hashlib
import json
import re
import shutil
import urllib.parse
import urllib.request
import uuid
from pathlib import Path, PurePosixPath

from daw.util import DawError, canonical, now

FORMAT = "colloquy.directory/1"
FILE = "directory.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_DIRECTORY_BYTES = 8 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024 * 1024
TIMEOUT = 60


# ---------------------------------------------------------------------------- reading and validating

def _is_url(text):
    return isinstance(text, str) and re.match(r"^(https?|file)://", text, re.I) is not None


def _safe_relative(location):
    pure = PurePosixPath(location)
    return (not pure.is_absolute() and "\\" not in location and location.strip() and ":" not in location
            and not location.startswith("~")
            and all(part not in ("", ".", "..") for part in pure.parts))


def validate(data):
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("entries"), list):
        raise DawError("invalid_directory", f"a {FORMAT} file with an entries list")
    seen = set()
    for entry in data["entries"]:
        if not isinstance(entry, dict) or not HEX64.match(str(entry.get("snapshot"))):
            raise DawError("invalid_directory", f"bad entry {str(entry)[:200]}")
        if entry["snapshot"] in seen:
            raise DawError("invalid_directory", f"snapshot {entry['snapshot']} listed twice")
        seen.add(entry["snapshot"])
        location = entry.get("location")
        if not isinstance(location, str) or not (re.match(r"^https?://", location, re.I) or _safe_relative(location)):
            raise DawError("invalid_directory", f"{entry['snapshot']}: location must be a relative path or an http(s) URL")
    return data


def _read_url(url, limit):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        if path.stat().st_size > limit:
            raise DawError("directory_too_large", url)
        return path.read_bytes()
    if parsed.scheme not in ("http", "https"):
        raise DawError("unsupported_location", url)
    request = urllib.request.Request(url, headers={"User-Agent": "colloquy-directory/1", "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 (scheme checked above)
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme not in ("http", "https"):
            raise DawError("unsupported_location", response.geturl())
        data = response.read(limit + 1)
    if len(data) > limit:
        raise DawError("download_too_large", url)
    return data


def read(source):
    """(directory, base) from a local path (file or folder holding directory.json) or a URL."""
    if _is_url(source):
        data = _read_url(source, MAX_DIRECTORY_BYTES)
        base = source
    else:
        path = Path(source).expanduser()
        if path.is_dir():
            path = path / FILE
        if not path.is_file():
            raise DawError("directory_missing", str(source))
        data = path.read_bytes()
        if len(data) > MAX_DIRECTORY_BYTES:
            raise DawError("directory_too_large", str(source))
        base = str(path.resolve())
    try:
        directory = json.loads(data)
    except ValueError as error:
        raise DawError("invalid_directory", str(error)) from error
    return validate(directory), base, data


def resolve_location(base, location):
    """An entry's snapshot folder as a local Path or an http(s) URL ending in '/'."""
    if re.match(r"^https?://", location, re.I):
        return location if location.endswith("/") else location + "/"
    if _is_url(base):
        joined = urllib.parse.urljoin(base, location)
        if urllib.parse.urlparse(joined).scheme == "file":
            return Path(urllib.request.url2pathname(urllib.parse.urlparse(joined).path))
        return joined if joined.endswith("/") else joined + "/"
    return (Path(base).parent / location).resolve()


def listing(source):
    directory, base, data = read(source)
    return {"source": source, "sha256": hashlib.sha256(data).hexdigest(), "name": directory.get("name"),
            "entries": directory["entries"], "foreign": True, "content_is_untrusted_data": True}


# ---------------------------------------------------------------------------- publishing (writes files only)

def publish(snapshot_dir, directory_file, *, lab, title=None, location=None, publisher=None, note=None, name=None):
    """Verify a snapshot folder and list it in a directory file (created when missing). Idempotent per ID."""
    from daw.commons import export
    snapshot_dir = Path(snapshot_dir).expanduser().resolve()
    snapshot, manifest = export.read_manifest(snapshot_dir)
    export.verify_directory(snapshot_dir, manifest)
    directory_file = Path(directory_file).expanduser()
    if directory_file.is_dir() or directory_file.suffix != ".json":
        directory_file = directory_file / FILE
    folder = directory_file.parent.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if directory_file.is_file():
        directory, _, _ = read(directory_file)
    else:
        directory = {"format": FORMAT, "name": name or lab, "entries": []}
    existing = next((e for e in directory["entries"] if e["snapshot"] == snapshot), None)
    if existing:
        return {"snapshot": snapshot, "directory": str(directory_file), "already_listed": True, "entry": existing}
    if location is None:
        target = folder / "snapshots" / snapshot
        if not target.exists():
            staging = folder / "snapshots" / f".publish-{uuid.uuid4().hex}"
            staging.mkdir(parents=True)
            try:
                for entry in [{"path": export.MANIFEST}] + manifest["files"]:
                    destination = staging / entry["path"]
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(snapshot_dir / entry["path"], destination)
                (staging / "snapshot.id").write_text(snapshot + "\n")
                if export.read_manifest(staging)[0] != snapshot:
                    raise DawError("snapshot_source_changed", export.MANIFEST)
                export.verify_directory(staging, manifest)
                staging.rename(target)
            except BaseException:
                shutil.rmtree(staging, ignore_errors=True)
                raise
        location = f"snapshots/{snapshot}/"
    elif not (re.match(r"^https?://", location, re.I) or _safe_relative(location)):
        raise DawError("invalid_location", "a relative path under the directory or an http(s) URL")
    entry = {"snapshot": snapshot, "title": title or (manifest.get("scope") or {}).get("kind"), "lab": lab,
             "scope": manifest.get("scope"), "counts": manifest.get("counts"), "location": location,
             "files": len(manifest["files"]) + 1, "bytes": sum(f["bytes"] for f in manifest["files"]),
             "published": now(), "publisher": publisher, "note": note}
    entry = {k: v for k, v in entry.items() if v is not None}
    directory["entries"].append(entry)
    staging = directory_file.with_name(f".{directory_file.name}.{uuid.uuid4().hex}")
    staging.write_bytes(canonical(directory))
    staging.replace(directory_file)
    receipts = folder / "receipts"
    receipts.mkdir(exist_ok=True)
    receipt = {"format": "colloquy.directory-receipt/1", "action": "publish", "snapshot": snapshot,
               "directory": directory_file.name, "location": location, "files": entry["files"], "bytes": entry["bytes"],
               "published": entry["published"], "verified": "every listed sha256 and size matched; no unlisted files or links",
               "executed": False}
    (receipts / f"{snapshot}.publish.json").write_bytes(canonical(receipt))
    return {"snapshot": snapshot, "directory": str(directory_file), "already_listed": False, "entry": entry,
            "receipt": str(receipts / f"{snapshot}.publish.json")}


# ---------------------------------------------------------------------------- fetching (into a commons)

def _download_snapshot(url, snapshot, entry, staging):
    """Download a snapshot folder over http(s) into `staging`, verifying each file as it arrives."""
    from daw.commons import export
    manifest_bytes = _read_url(url + export.MANIFEST, MAX_DIRECTORY_BYTES)
    if hashlib.sha256(manifest_bytes).hexdigest() != snapshot:
        raise DawError("snapshot_id_mismatch", f"{url}{export.MANIFEST} does not hash to {snapshot}")
    manifest = json.loads(manifest_bytes)
    if canonical(manifest) != manifest_bytes or manifest.get("format") != export.FORMAT:
        raise DawError("invalid_snapshot_manifest", "snapshot.json must be canonical colloquy.snapshot/1")
    total = 0
    (staging / export.MANIFEST).write_bytes(manifest_bytes)
    for item in manifest["files"]:
        if not isinstance(item, dict) or not export._safe_listed(item.get("path")) \
                or not HEX64.match(str(item.get("sha256"))) or not isinstance(item.get("bytes"), int):
            raise DawError("invalid_snapshot_manifest", f"bad file entry {str(item)[:200]}")
        total += item["bytes"]
        if total > MAX_SNAPSHOT_BYTES:
            raise DawError("download_too_large", f"{snapshot} lists more than {MAX_SNAPSHOT_BYTES} bytes")
        data = _read_url(url + urllib.parse.quote(item["path"]), item["bytes"])
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise DawError("snapshot_hash_mismatch", item["path"])
        target = staging / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return total


def fetch(board, source, snapshot):
    """Fetch one listed snapshot into this commons (read-only import + federation index), with a receipt."""
    from daw.commons import federation
    if not HEX64.match(snapshot or ""):
        raise DawError("unknown_snapshot", str(snapshot)[:80])
    directory, base, data = read(source)
    entry = next((e for e in directory["entries"] if e["snapshot"] == snapshot), None)
    if not entry:
        raise DawError("snapshot_not_listed", snapshot)
    location = resolve_location(base, entry["location"])
    root = Path(board.root)
    origin = {"directory": source, "directory_sha256": hashlib.sha256(data).hexdigest(), "location": str(location)}
    staging = None
    try:
        if isinstance(location, Path):
            folder = location
        else:
            staging = root / "federation" / f".fetch-{uuid.uuid4().hex}"
            staging.mkdir(parents=True)
            _download_snapshot(location, snapshot, entry, staging)
            folder = staging
        result = federation.import_and_index(board, folder, expect=snapshot, origin=origin)
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    saved = root / "directory" / "sources"
    saved.mkdir(parents=True, exist_ok=True)
    (saved / f"{origin['directory_sha256']}.json").write_bytes(data)
    (saved / f"{origin['directory_sha256']}.source.json").write_bytes(canonical({"source": source, "saved": now()}))
    receipt = {"format": "colloquy.directory-receipt/1", "action": "fetch", "snapshot": snapshot, **origin,
               "fetched": now(), "files": result.get("files") if isinstance(result.get("files"), int) else len(result.get("files") or []),
               "already_imported": result.get("already_imported"), "index": result.get("index"),
               "verified": "snapshot.json hashes to the requested ID; every listed sha256 and size matched",
               "executed": False}
    (root / "federation" / f"{snapshot}.fetch.json").write_bytes(canonical(receipt))
    return {"snapshot": snapshot, "entry": entry, "receipt": receipt}


# ---------------------------------------------------------------------------- what this commons knows (reads)

def known(view):
    """The commons' own directory (`<commons>/directory/directory.json`) and the directories it fetched from,
    each entry marked imported/indexed. Reads files only."""
    from daw.commons import export, federation
    root = Path(view.root)
    imported = {s["snapshot"]: s for s in export.list_snapshots(root)}
    index = federation.indexed(view)

    def mark(entries):
        return [{**e, "imported": e["snapshot"] in imported, "indexed": index.get(e["snapshot"])} for e in entries]

    own = None
    path = root / "directory" / FILE
    if path.is_file():
        try:
            directory, _, data = read(path)
            own = {"name": directory.get("name"), "entries": mark(directory["entries"]),
                   "sha256": hashlib.sha256(data).hexdigest()}
        except DawError as error:
            own = {"error": f"{error.reason}: {error.detail}"}
    sources = []
    folder = root / "directory" / "sources"
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        if path.name.endswith(".source.json"):
            continue
        meta = path.with_name(path.stem + ".source.json")
        try:
            directory, _, _ = read(path)
            info = json.loads(meta.read_text()) if meta.is_file() else {}
            sources.append({"source": info.get("source"), "saved": info.get("saved"), "sha256": path.stem,
                            "name": directory.get("name"), "entries": mark(directory["entries"])})
        except (DawError, ValueError):
            continue
    receipts = {}
    for path in sorted((root / "federation").glob("*.fetch.json")) if (root / "federation").is_dir() else []:
        try:
            receipts[path.name[:64]] = json.loads(path.read_text())
        except ValueError:
            continue
    return {"own": own, "sources": sources, "imported": sorted(imported), "index": index, "fetch_receipts": receipts,
            "foreign": True, "content_is_untrusted_data": True,
            "note": "Directories list snapshots by sha256; fetching re-verifies every byte. Nothing fetched is executed."}
