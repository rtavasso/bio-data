"""Real-data fixtures (C0): a redacted, committable copy of a commons for development and tests.

A fixture keeps what agents and people wrote (board, posts, claims, marks, notebooks, scripts,
small derived outputs, artifact manifests, receipts, redacted tool streams) and drops what was
downloaded (source, full-text, reference and metadata blobs that no record names, question
inputs and sources, model-facing session databases). Blob rows stay in the catalogs so every
identity still resolves; a missing file reads as `present: false`, never as a different value.

Nothing here is synthetic. `FIXTURE.json` says so and records every file's sha256, the rules
applied and what was excluded, so a reviewer can tell a fixture from a live commons and a
builder can verify a checkout. The demo-only operator commands refuse fixtures as they refuse
any other real commons.
"""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from daw.util import DawError, file_hash, now, write_json

FORMAT = "colloquy-fixture/1"
KEEP_CLASSES = {"work", "code", "execution-receipt", "prediction", "agent-curated"}
CAPPED_CLASSES = {"derived", "interpretation"}  # metadata only when a record names it
DROP_CLASSES = {"source", "full", "research-input", "reference"}
DERIVED_CAP = 65536
QUESTION_FILE_CAP = 65536
INPUT_VALUE_CAP = 4096
QUESTION_SKIP_DIRS = {"inputs", "sources", "cache", "staging", "raw"}
QUESTION_SUFFIXES = {".md", ".json", ".tsv", ".csv", ".txt", ".py", ".r", ".sh", ".yaml", ".yml", ".toml", ".jsonl"}
SOURCE_LIKE = ("PMC", "PMID", "GSE", "GSM", "ENCSR", "PXD", "E-MTAB", "E-MEXP")
RUN_FILES = ("execution.json", "state-receipt.json", "heartbeat.json", "final.md", "prompt.txt", "task-outcome.json",
             "budget.json", "sandbox.json", "stall.json",
             # V6 delivery records: clocks, compaction ids/hashes (no summary text), the receipt index.
             "clock.jsonl", "compactions.jsonl", "receipts.json")
DROP_BOARD_TABLES = ("credential",)
# Working directories of every workspace (the library and each agent's). Git does not carry empty directories, so
# an empty one holds an empty KEEP file: a checkout is complete and serving it creates no directory (B2).
WORKING_DIRS = ("blobs/sha256", "staging", "proposals", "runs", "reports", "questions", "profiles")
KEEP = ".fixture-keep"
STREAM_KEEP_INPUT_KEYS = {"command", "path", "name", "names", "pattern", "query", "limit", "offset", "role_filter",
                          "detail", "start_line", "end_line", "offset_line", "timeout", "session_id", "cwd"}


def _redact_text(value):
    data = value.encode("utf-8", errors="replace")
    return f"[redacted {len(data)} bytes sha256:{hashlib.sha256(data).hexdigest()}]"


def redact_stream_line(line):
    """One events.jsonl line. Tool outputs become a length plus hash (exit codes survive, so metrics
    and timelines still work); oversized tool inputs are hashed; the agent's own text stays."""
    raw = line.rstrip("\n")
    if not raw.lstrip().startswith("{"):
        return raw  # plain-text runtime status such as the compaction marker
    try:
        event = json.loads(raw)
    except ValueError:
        return _redact_text(raw)
    kind = event.get("type")
    if kind == "tool_result":
        output = event.get("output")
        text = output if isinstance(output, str) else json.dumps(output)
        replacement = {"output": _redact_text(text)}
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict) and type(parsed.get("exit_code")) is int:
            replacement["exit_code"] = parsed["exit_code"]
        event["output"] = json.dumps(replacement)
    elif kind == "tool_use" and isinstance(event.get("input"), dict):
        cleaned = {}
        for key, value in event["input"].items():
            if isinstance(value, str) and (key not in STREAM_KEEP_INPUT_KEYS and len(value) > INPUT_VALUE_CAP):
                cleaned[key] = _redact_text(value)
            else:
                cleaned[key] = value
        event["input"] = cleaned
    return json.dumps(event, ensure_ascii=False)


def _copy_sqlite(source, target, *, drop_tables=(), clear_tables=()):
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    with sqlite3.connect(target) as db:
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in drop_tables:
            if name in names:
                db.execute(f"DELETE FROM {name}")
        for name in clear_tables:
            if name in names:
                db.execute(f"DELETE FROM {name}")
    with sqlite3.connect(target) as db:
        db.execute("VACUUM")


def _referenced_blobs(catalog):
    """Blobs any record names: post bodies live on the board, manifests, snapshots and events in catalogs."""
    with sqlite3.connect(f"file:{catalog}?mode=ro", uri=True) as db:
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        wanted = set()
        # Dataset profiles describe downloaded bytes and are rebuilt from them; they stay out with their sources.
        for table, column in (("artifact", "manifest_blob"), ("work_snapshot", "body_blob"), ("work_event", "body_blob"),
                              ("review_decision", "body_blob")):
            if table in names:
                wanted.update(r[0] for r in db.execute(f"SELECT {column} FROM {table}") if r[0])
        if "work_snapshot" in names:
            for (body,) in db.execute("SELECT body_blob FROM work_snapshot"):
                wanted.add(body)
        rows = db.execute("SELECT sha256,size,classification FROM blob").fetchall()
    return wanted, rows


def _blob_file(root, sha):
    return Path(root) / "blobs" / "sha256" / sha[:2] / sha


def _copy_blobs(source_ws, target_ws, extra_wanted, manifest, label):
    wanted, rows = _referenced_blobs(Path(source_ws) / "catalog.sqlite")
    wanted |= set(extra_wanted)
    copied = dropped = 0
    for sha, size, classification in rows:
        keep = (sha in wanted or classification in KEEP_CLASSES
                or (classification in CAPPED_CLASSES and size <= DERIVED_CAP))
        if classification in DROP_CLASSES and sha not in wanted:
            keep = False
        src = _blob_file(source_ws, sha)
        if not keep or not src.is_file():
            dropped += 1
            continue
        dst = _blob_file(target_ws, sha)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        manifest["files"][str(dst.relative_to(manifest["_root"]))] = file_hash(dst)
        copied += 1
    manifest["counts"][label + "_blobs_copied"] = manifest["counts"].get(label + "_blobs_copied", 0) + copied
    manifest["counts"][label + "_blobs_dropped"] = manifest["counts"].get(label + "_blobs_dropped", 0) + dropped


def _copy_question_folder(src, dst, manifest):
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if any(part in QUESTION_SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() not in QUESTION_SUFFIXES or path.stat().st_size > QUESTION_FILE_CAP:
            continue
        if any(token in path.name for token in SOURCE_LIKE) and rel.parts[0] == "outputs":
            continue  # extracted source text and downloaded tables saved under outputs/
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        manifest["files"][str(target.relative_to(manifest["_root"]))] = file_hash(target)


def build_fixture(source_root, out, *, name=None):
    source = Path(source_root).expanduser().resolve()
    out = Path(out).expanduser().resolve()
    if not (source / "board.sqlite").is_file():
        raise DawError("community_not_initialized", str(source))
    if out.exists() and any(out.iterdir()):
        raise DawError("fixture_target_not_empty", str(out))
    if (source / "DEMO.json").is_file():
        raise DawError("fixture_of_demo", "a synthetic demo is not real data; build fixtures from a real commons")
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"format": FORMAT, "real_data": True, "synthetic": False, "name": name or source.name,
                "built": now(), "source_basename": source.name, "_root": out, "files": {}, "counts": {},
                "rules": {"blob_classes_kept": sorted(KEEP_CLASSES), "blob_classes_dropped_unless_referenced": sorted(DROP_CLASSES),
                          "capped_blob_classes": sorted(CAPPED_CLASSES), "capped_blob_bytes": DERIVED_CAP, "question_file_cap_bytes": QUESTION_FILE_CAP,
                          "question_dirs_skipped": sorted(QUESTION_SKIP_DIRS), "stream_tool_outputs": "replaced by length and sha256; exit codes kept",
                          "stream_input_values_over_bytes": INPUT_VALUE_CAP, "catalog_tables_cleared": ["feature_term"], "profiles": "dataset_profile bodies not copied",
                          "board_tables_cleared": list(DROP_BOARD_TABLES), "run_files_excluded": ["agent-state/", "transcript.md", "stderr.log"],
                          "top_level_excluded": ["service", "secrets", "cache", "exports", "federation", "watchers"]}}
    with sqlite3.connect(f"file:{source / 'board.sqlite'}?mode=ro", uri=True) as db:
        manifest["board_sequence"] = db.execute("SELECT coalesce(max(seq),0) FROM event").fetchone()[0]
        agents = db.execute("SELECT id,name,trial FROM agent WHERE trial IS NOT NULL").fetchall()
        attempts = db.execute("SELECT id,path FROM attempt").fetchall()
        post_blobs = {r[0] for r in db.execute("SELECT body_blob FROM post")}
    _copy_sqlite(source / "board.sqlite", out / "board.sqlite", clear_tables=DROP_BOARD_TABLES)
    # Library: catalog, config, and the blobs records name or agents wrote.
    _copy_sqlite(source / "library/catalog.sqlite", out / "library/catalog.sqlite", clear_tables=("feature_term",))
    if (source / "library/config.toml").is_file():
        shutil.copyfile(source / "library/config.toml", out / "library/config.toml")
        manifest["files"]["library/config.toml"] = file_hash(out / "library/config.toml")
    for part in ("blobs/sha256", "staging", "proposals", "runs", "reports", "cache"):
        (out / "library" / part).mkdir(parents=True, exist_ok=True)
    _copy_blobs(source / "library", out / "library", post_blobs, manifest, "library")
    # Agent workspaces: catalog without the content index, written files, small outputs.
    manifest["counts"]["agents"] = 0
    for _agent_id, _agent_name, trial in agents:
        src_ws = source / trial / "workspace"
        if not (src_ws / "catalog.sqlite").is_file():
            continue
        dst_ws = out / trial / "workspace"
        _copy_sqlite(src_ws / "catalog.sqlite", dst_ws / "catalog.sqlite", clear_tables=("feature_term",))
        manifest["files"][str((dst_ws / "catalog.sqlite").relative_to(out))] = file_hash(dst_ws / "catalog.sqlite")
        for part in ("blobs/sha256", "staging", "proposals", "runs", "reports", "cache"):
            (dst_ws / part).mkdir(parents=True, exist_ok=True)
        if (src_ws / "config.toml").is_file():
            shutil.copyfile(src_ws / "config.toml", dst_ws / "config.toml")
            manifest["files"][str((dst_ws / "config.toml").relative_to(out))] = file_hash(dst_ws / "config.toml")
        _copy_blobs(src_ws, dst_ws, (), manifest, "workspace")
        questions = src_ws / "questions"
        if questions.is_dir() and not questions.is_symlink():
            for folder in sorted(p for p in questions.iterdir() if p.is_dir() and not p.is_symlink()):
                _copy_question_folder(folder, dst_ws / "questions" / folder.name, manifest)
        manifest["counts"]["agents"] += 1
    # Runs: receipts, prompts, finals and redacted streams; no session databases or rendered transcripts.
    manifest["counts"]["runs"] = 0
    for _run_id, rel in attempts:
        src_run = (source / rel).resolve()
        if not src_run.is_relative_to(source / "runs") or not src_run.is_dir():
            continue
        dst_run = out / rel
        dst_run.mkdir(parents=True, exist_ok=True)
        for name in RUN_FILES:
            if (src_run / name).is_file():
                shutil.copyfile(src_run / name, dst_run / name)
                manifest["files"][str((dst_run / name).relative_to(out))] = file_hash(dst_run / name)
        receipts = src_run / "receipts"  # V6: content-addressed copies of indexed run_analysis.py receipts
        if receipts.is_dir() and not receipts.is_symlink():
            for path in sorted(receipts.glob("*.json")):
                if path.is_file() and not path.is_symlink() and path.stat().st_size <= QUESTION_FILE_CAP:
                    (dst_run / "receipts").mkdir(exist_ok=True)
                    shutil.copyfile(path, dst_run / "receipts" / path.name)
                    manifest["files"][str((dst_run / "receipts" / path.name).relative_to(out))] = file_hash(path)
        stream = src_run / "events.jsonl"
        if stream.is_file():
            with stream.open(encoding="utf-8", errors="replace") as src_lines, (dst_run / "events.jsonl").open("w", encoding="utf-8") as dst_lines:
                for line in src_lines:
                    dst_lines.write(redact_stream_line(line) + "\n")
            manifest["files"][str((dst_run / "events.jsonl").relative_to(out))] = file_hash(dst_run / "events.jsonl")
        manifest["counts"]["runs"] += 1
    # Open once so a version-1 board is upgraded and the projections exist before hashing; a served
    # fixture then verifies unchanged until someone writes to it.
    manifest["settle"] = _settle(out)
    manifest["files"] = {str(p.relative_to(out)): file_hash(p) for p in sorted(out.rglob("*"))
                         if p.is_file() and p.name != "FIXTURE.json" and not _operational(p.relative_to(out))
                         and not _kept(out, p.relative_to(out))}
    manifest["counts"]["files"] = len(manifest["files"])
    manifest["counts"]["bytes"] = sum((out / p).stat().st_size for p in manifest["files"])
    del manifest["_root"]
    write_json(out / "FIXTURE.json", manifest)
    return {k: v for k, v in manifest.items() if k != "files"} | {"fixture": str(out)}


def _settle(root):
    """Schema upgrade, projection rebuilds and the local reader participant, through the same code a
    served commons runs, so serving the fixture in local mode writes nothing. Outcomes are recorded."""
    from daw.community import Community
    outcomes = {}
    with Community(root) as board:
        for module, function in (("daw.commons.moderation", "rebuild"), ("daw.commons.claims", "rebuild_claims"),
                                 ("daw.commons.frontier", "rebuild_frontier")):
            rebuild = getattr(__import__(module, fromlist=[function]), function)
            try:
                result = rebuild(board)
                outcomes[module.rsplit(".", 1)[-1]] = {k: v for k, v in (result or {}).items() if k != "orphaned"} if isinstance(result, dict) else "ok"
            except DawError as error:
                outcomes[module.rsplit(".", 1)[-1]] = {"error": error.reason, "detail": str(error.detail)[:200]}
        from daw.commons.participants import add_participant
        if not board.one("SELECT id FROM agent WHERE name='local'"):
            add_participant(board, "local", "human", profile={"display_name": "local"})
            outcomes["local_participant"] = "created"
    for leftover in Path(root).rglob("*.lock"):
        leftover.unlink(missing_ok=True)
    shutil.rmtree(Path(root) / "cache", ignore_errors=True)
    keep_working_dirs(root)
    return outcomes


def keep_working_dirs(root):
    """Create every workspace's working directories and leave a KEEP file in each empty one, so a checkout
    carries them. Returns the placeholders written."""
    root = Path(root)
    written = []
    for catalog in sorted(root.rglob("catalog.sqlite")):
        workspace = catalog.parent
        if workspace != root / "library" and workspace.name != "workspace":
            continue
        for part in WORKING_DIRS:
            folder = workspace / part
            folder.mkdir(parents=True, exist_ok=True)
            if not any(folder.iterdir()):
                (folder / KEEP).touch()
                written.append(str((folder / KEEP).relative_to(root)))
    return written


def resettle_fixture(root, *, reason):
    """Bring a committed fixture to the current schema and projections in place, then re-record its hashes.

    Schema additions (new tables, indexes, triggers) and projection rebuilds would otherwise be applied by the
    first read-write open of a served copy, so serving would change board.sqlite and `verify` would fail (C0).
    Only verified fixtures are resettled; the settle step is the same one `build` runs, so no record a
    participant wrote changes. The previous board sequence, the settle outcomes and the reason are kept."""
    from daw.community import Community
    root = Path(root).expanduser().resolve()
    before = verify_fixture(root)
    if not before["verified"] or before["untracked"]:
        raise DawError("fixture_not_verified", "resettle only an unchanged fixture; rebuild it from its source otherwise")
    manifest = json.loads((root / "FIXTURE.json").read_text())
    outcomes = _settle(root)
    with Community(root) as board:
        sequence = board.one("SELECT coalesce(max(seq),0) AS n FROM event")["n"]
    files = {str(p.relative_to(root)): file_hash(p) for p in sorted(root.rglob("*"))
             if p.is_file() and p.name != "FIXTURE.json" and not _operational(p.relative_to(root))
             and not _kept(root, p.relative_to(root))}
    changed = sorted(rel for rel, digest in files.items() if manifest["files"].get(rel) != digest)
    # Settling may add content-addressed library blobs (projection documents); nothing else may appear.
    added = sorted(set(files) - set(manifest["files"]))
    unexpected = [rel for rel in added if not rel.startswith("library/blobs/sha256/")]
    if unexpected:
        raise DawError("fixture_resettle_added_files", ", ".join(unexpected))
    entry = {"at": now(), "reason": reason, "board_sequence_before": manifest["board_sequence"],
             "board_sequence": sequence, "settle": outcomes, "changed": [rel for rel in changed if rel not in added],
             "added_library_blobs": len(added)}
    manifest.update(files=files, board_sequence=sequence, resettled=[*manifest.get("resettled", []), entry])
    manifest["counts"]["files"] = len(files)
    manifest["counts"]["bytes"] = sum((root / p).stat().st_size for p in files)
    write_json(root / "FIXTURE.json", manifest)
    return entry


CURATION_EVENTS = ("pointer_curated", "participant_created", "participant_profile_updated")


def record_curation(root, *, reason):
    """Re-record a fixture's hashes after people curated pointers on it in place (spec v3 G2).

    A curator runs `bio commons --root <fixture> curate pointer|unlocatable ... --as PERSON` (after
    `add-participant PERSON` when the person is new). That changes `board.sqlite`, adds library blobs (the
    marks' bodies) and their rows in `library/catalog.sqlite`, so `verify` fails until the hashes are recorded
    again. Only those changes are accepted, and
    only when every board event past the recorded sequence is a curation act or a curator's participant record;
    anything else (a post, a hide, a claim) refuses, so this never launders other writes into a fixture."""
    from daw.community import Community
    root = Path(root).expanduser().resolve()
    manifest = json.loads((root / "FIXTURE.json").read_text())
    checked = verify_fixture(root)
    if checked["missing"]:
        raise DawError("fixture_not_verified", f"missing {len(checked['missing'])} files")
    with Community(root) as board:
        events = board.rows("SELECT seq,kind FROM event WHERE seq>? ORDER BY seq", (manifest["board_sequence"],))
        sequence = board.one("SELECT coalesce(max(seq),0) AS n FROM event")["n"]
    other = sorted({e["kind"] for e in events if e["kind"] not in CURATION_EVENTS})
    if other:
        raise DawError("fixture_curation_has_other_writes", ", ".join(other))
    acts = sum(1 for e in events if e["kind"] == "pointer_curated")
    if not acts:
        raise DawError("fixture_curation_empty", "no curation act past the recorded board sequence")
    changed = [rel for rel in checked["changed"] if rel not in ("board.sqlite", "library/catalog.sqlite")]
    unexpected = changed + [rel for rel in checked["untracked"] if not rel.startswith("library/blobs/sha256/")]
    if unexpected:
        raise DawError("fixture_curation_changed_files", ", ".join(unexpected[:20]))
    for leftover in root.rglob("*.lock"):
        leftover.unlink(missing_ok=True)
    files = {str(p.relative_to(root)): file_hash(p) for p in sorted(root.rglob("*"))
             if p.is_file() and p.name != "FIXTURE.json" and not _operational(p.relative_to(root))
             and not _kept(root, p.relative_to(root))}
    entry = {"at": now(), "reason": reason, "kind": "curation", "board_sequence_before": manifest["board_sequence"],
             "board_sequence": sequence, "curation_acts": acts, "added_library_blobs": len(checked["untracked"])}
    manifest.update(files=files, board_sequence=sequence, resettled=[*manifest.get("resettled", []), entry])
    manifest["counts"]["files"] = len(files)
    manifest["counts"]["bytes"] = sum((root / p).stat().st_size for p in files)
    write_json(root / "FIXTURE.json", manifest)
    return entry


def _operational(rel):
    """Lock files and caches that opening a commons creates; never fixture content."""
    return (rel.suffix == ".lock" or any(part in {"cache", "staging"} for part in rel.parts)
            or rel.name.endswith(("-shm", "-wal")) or str(rel) == "tenancy.json")


def _kept(root, rel):
    """An empty working directory's placeholder: structure, not content (a KEEP file with bytes is content)."""
    return (rel.name == KEEP and rel.parent.name in {Path(part).name for part in WORKING_DIRS}
            and (root / rel).stat().st_size == 0)


def _empty_dirs(root):
    """Empty directories that are neither tracked (holding a file or a KEEP placeholder) nor operational (caches).
    A checkout drops them and serving recreates them, so one means the fixture is incomplete or was written to."""
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_dir() and not p.is_symlink()
                  and not any(p.iterdir()) and "cache" not in p.relative_to(root).parts)


def verify_fixture(root):
    root = Path(root).expanduser().resolve()
    manifest = json.loads((root / "FIXTURE.json").read_text())
    if manifest.get("format") != FORMAT:
        raise DawError("unknown_fixture_format", str(manifest.get("format")))
    changed, missing = [], []
    for rel, digest in manifest["files"].items():
        path = root / rel
        if not path.is_file():
            missing.append(rel)
        elif file_hash(path) != digest:
            changed.append(rel)
    extra = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()
                   and str(p.relative_to(root)) not in manifest["files"] and p.name != "FIXTURE.json"
                   and not _operational(p.relative_to(root)) and not _kept(root, p.relative_to(root)))
    return {"fixture": str(root), "name": manifest["name"], "board_sequence": manifest["board_sequence"],
            "files": len(manifest["files"]), "changed": changed, "missing": missing, "untracked": extra,
            "empty_dirs": _empty_dirs(root), "verified": not changed and not missing}
