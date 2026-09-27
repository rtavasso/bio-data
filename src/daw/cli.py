"""Stable JSON command surface. Progress and errors never contaminate result stdout."""
import contextlib
import importlib.util
import json
import os
import platform
import shutil
import sqlite3
import sys
import time
from importlib.metadata import distributions
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from daw import __version__
from daw.adapters import Sources
from daw.catalog import Workspace, restore_check
from daw.curation import accept, add_assertion, packet, register_reference, validate_curation
from daw.inspectors import extract_members, inspect_asset
from daw.models import AssertionInput, Curation, Discovery, Plan, Query
from daw.query import coverage_audit, plan_query, query, render_report
from daw.transport import Transport
from daw.util import DawError, canonical, file_hash, now, read_json, write_json

app = typer.Typer(no_args_is_help=True, help="Data Archaeology Workbench — local measurement recovery with provenance.")
bundle_app = typer.Typer(no_args_is_help=True)
curate_app = typer.Typer(no_args_is_help=True)
audit_app = typer.Typer(no_args_is_help=True)
reference_app = typer.Typer(no_args_is_help=True)
app.add_typer(bundle_app, name="bundle")
app.add_typer(curate_app, name="curate")
app.add_typer(audit_app, name="audit")
app.add_typer(reference_app, name="reference")


def emit(value):
    sys.stdout.buffer.write(canonical(value) + b"\n") if hasattr(sys.stdout, "buffer") else typer.echo(canonical(value).decode())


@app.callback()
def root(ctx: typer.Context, workspace: Annotated[Path, typer.Option("--workspace", "-w", envvar="DAW_WORKSPACE")] = Path("workspace")):
    ctx.obj = workspace


@contextlib.contextmanager
def session(ctx, write=True):
    ws = Workspace(ctx.obj)
    try:
        with ws.writer() if write else contextlib.nullcontext():
            yield ws
    finally:
        ws.close()


@app.command()
def init(workspace: Path):
    """Create a private local workspace; initialization is idempotent."""
    ws = Workspace.create(workspace)
    emit({"workspace": str(ws.root), "catalog_version": ws.db.execute("PRAGMA user_version").fetchone()[0], "journal_mode": ws.db.execute("PRAGMA journal_mode").fetchone()[0]})
    ws.close()


@app.command()
def doctor(ctx: typer.Context):
    """Inspect actual environment, disk, catalog and optional reader availability."""
    with session(ctx, False) as ws:
        disk = shutil.disk_usage(ws.root)
        readers = {name: importlib.util.find_spec(name) is not None for name in
                   ["openpyxl", "pyarrow", "pyBigWig", "bioframe", "anndata", "cooler", "peppy", "duckdb"]}
        remote = None
        if readers["pyBigWig"]:
            import pyBigWig
            remote = bool(pyBigWig.remote)
        emit({"version": __version__, "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
              "journal_mode": ws.db.execute("PRAGMA journal_mode").fetchone()[0], "workspace": str(ws.root),
              "writable": os.access(ws.root, os.W_OK), "free_disk_bytes": disk.free, "readers": readers,
              "pybigwig_remote_compilation": remote, "remote_range_queries_enabled": False,
              "parser_hard_memory_limit": sys.platform.startswith("linux"), "budgets": ws.budgets.model_dump(),
              "references": ws.rows("SELECT id,native_id FROM resource WHERE kind='reference' AND provider='curated'"),
              "catalog_integrity": ws.db.execute("PRAGMA integrity_check").fetchone()[0]})


@app.command()
def discover(ctx: typer.Context, request: Annotated[Path, typer.Option()]):
    """Run bounded read-only discovery and preserve pagination receipts."""
    with session(ctx) as ws:
        source = Sources(ws)
        try:
            emit(source.discover(Discovery.model_validate(read_json(request))))
        finally:
            source.http.close()


@bundle_app.command("add")
def bundle_add(ctx: typer.Context, reference: Annotated[str, typer.Option()], provider: str | None = None):
    """Resolve a public reference without downloading large assets."""
    with session(ctx) as ws:
        source = Sources(ws)
        try:
            emit(source.add(reference, provider))
        finally:
            source.http.close()


@bundle_app.command("import")
def bundle_import(ctx: typer.Context, path: Path, name: str = "local"):
    """Register an explicitly selected local file, preserving its original bytes."""
    with session(ctx) as ws:
        emit(ws.local_asset(path, name))


@bundle_app.command("inventory")
def bundle_inventory(ctx: typer.Context, bundle_id: str):
    with session(ctx, False) as ws:
        emit(coverage_audit(ws, bundle_id))


def execute_plan(ws, plan):
    run, _ = ws.start_run("processing", {"plan": plan.model_dump()})
    outcomes = []
    http = Transport(ws)
    try:
        for aid in plan.assets:
            try:
                if plan.action == "acquire":
                    result = http.acquire(aid, plan.allow_raw_download)
                elif plan.action == "inspect":
                    result = inspect_asset(ws, aid)
                else:
                    result = {"asset_revision": aid, "members": extract_members(ws, aid, plan.members)}
                outcomes.append(result)
            except (DawError, OSError, ValueError) as e:
                outcomes.append({"asset_revision": aid, "outcome": "blocked", "reason": str(e)})
        failed = any(r.get("outcome") not in (None, "available_full") or r.get("status") in
                     {"not_inspected", "unsupported_format", "malformed", "unsafe_to_inspect", "partially_inspected"} for r in outcomes)
        result = {"run": run, "outcome": "partial" if failed else "complete", "items": outcomes,
                  "transferred_bytes": http.transferred, "requests": http.requests}
        ws.finish_run(run, result)
        return result
    except Exception as e:
        ws.finish_run(run, {"items": outcomes}, type(e).__name__)
        raise
    finally:
        http.close()


@bundle_app.command("inspect")
def bundle_inspect(ctx: typer.Context, bundle_id: str, plan: Path | None = None):
    with session(ctx) as ws:
        request = Plan.model_validate(read_json(plan)) if plan else Plan(action="inspect", assets=[a["id"] for a in ws.assets([bundle_id])])
        if request.action != "inspect" or not set(request.assets) <= {a["id"] for a in ws.assets([bundle_id])}:
            raise DawError("inspection_plan_outside_bundle")
        emit(execute_plan(ws, request))


@bundle_app.command("jats-links")
def jats_links(ctx: typer.Context, asset_revision: str):
    with session(ctx) as ws:
        source = Sources(ws)
        try:
            emit(source.jats_links(asset_revision))
        finally:
            source.http.close()


@app.command("run")
def processing_run(ctx: typer.Context, plan: Annotated[Path, typer.Option()]):
    """Execute an explicit acquisition, inspection or selected-member extraction plan."""
    with session(ctx) as ws:
        emit(execute_plan(ws, Plan.model_validate(read_json(plan))))


@curate_app.command("packet")
def curate_packet(ctx: typer.Context, bundle_id: str, output: Annotated[Path, typer.Option()]):
    with session(ctx, False) as ws:
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "packet.json", packet(ws, bundle_id))
        emit({"packet": str(output / "packet.json")})


@curate_app.command("assert")
def curate_assert(ctx: typer.Context, assertion: Annotated[Path, typer.Option()]):
    with session(ctx) as ws:
        emit({"assertion": add_assertion(ws, AssertionInput.model_validate(read_json(assertion)))})


@curate_app.command("validate")
def curate_validate(ctx: typer.Context, proposal: Annotated[Path, typer.Option()]):
    with session(ctx, False) as ws:
        emit(validate_curation(ws, Curation.model_validate(read_json(proposal))))


@curate_app.command("accept")
def curate_accept(ctx: typer.Context, proposal: Annotated[Path, typer.Option()]):
    with session(ctx) as ws:
        emit(accept(ws, Curation.model_validate(read_json(proposal))))


@curate_app.command("review")
def curate_review(ctx: typer.Context, decision: Annotated[Path, typer.Option()]):
    """Record a named operator's evidence-backed resolution of conflicting assertions."""
    from daw.curation import review_conflict
    with session(ctx) as ws:
        emit(review_conflict(ws, read_json(decision)))


@reference_app.command("add")
def reference_add(ctx: typer.Context, manifest: Annotated[Path, typer.Option()]):
    with session(ctx) as ws:
        emit(register_reference(ws, read_json(manifest)))


@reference_app.command("domain")
def reference_domain(ctx: typer.Context, manifest: Annotated[Path, typer.Option()]):
    """Register a versioned regulatory-domain definition separately from gene identity."""
    from daw.models import Evidence, Region
    from daw.curation import evidence_value
    with session(ctx) as ws:
        data = read_json(manifest)
        if not {"name", "region", "method", "uncertainty", "evidence"} <= data.keys():
            raise DawError("domain_prerequisites_missing")
        region = Region.model_validate(data["region"])
        ws.blob_path(region.reference)
        for item in data["evidence"]:
            evidence_value(ws, Evidence.model_validate(item))
        sha = ws.put_json(data)
        rid = ws.resource("domain", "curated", sha, {"blob": sha})
        emit({"domain": sha, "resource": rid})


@app.command("query")
def query_command(ctx: typer.Context, request: Annotated[Path, typer.Option()], plan_only: bool = False):
    """Freeze candidates and return measurements with every candidate's disposition."""
    with session(ctx, not plan_only) as ws:
        parsed = Query.model_validate(read_json(request))
        emit(plan_query(ws, parsed) if plan_only else query(ws, parsed))


@app.command()
def report(ctx: typer.Context, query_run_id: str):
    with session(ctx) as ws:
        emit(render_report(ws, query_run_id))


@app.command("export-igv")
def export_igv_command(ctx: typer.Context, request: Annotated[Path, typer.Option()], destination: Annotated[Path, typer.Option()]):
    """Copy eligible native tracks into a portable IGV Desktop session with provenance."""
    from daw.exports import export_igv
    with session(ctx, False) as ws:
        emit(export_igv(ws, Query.model_validate(read_json(request)), destination))


@audit_app.command("coverage")
def audit_coverage(ctx: typer.Context, scope: str | None = None):
    with session(ctx, False) as ws:
        emit(coverage_audit(ws, scope))


@audit_app.command("licenses")
def audit_licenses(ctx: typer.Context):
    with session(ctx, False) as ws:
        packages = []
        for dist in sorted(distributions(), key=lambda x: x.metadata["Name"].lower()):
            license_value = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "unknown"
            packages.append({"name": dist.metadata["Name"], "version": dist.version, "declared_license": license_value,
                             "bundled_libraries_review": "distribution metadata only; not a legal determination"})
        emit({"packages": packages, "assets": [{"asset_revision": a["id"], "name": a["body"]["name"],
                                                "license": a["body"].get("license", "unknown")} for a in ws.assets()]})


@app.command()
def refresh(ctx: typer.Context, scope: Annotated[str, typer.Option()], metadata_only: bool = True):
    if not metadata_only:
        raise DawError("explicit_acquisition_plan_required")
    with session(ctx) as ws:
        row = ws.one("SELECT * FROM resource WHERE id=? AND kind='bundle'", (scope,))
        if not row:
            raise DawError("unknown_bundle")
        source = Sources(ws)
        try:
            emit(source.add(row["native_id"], row["provider"]))
        finally:
            source.http.close()


@app.command()
def retry(ctx: typer.Context, attempt_id: str):
    with session(ctx) as ws:
        row = ws.one("SELECT * FROM run WHERE id=?", (attempt_id,))
        if not row:
            raise DawError("unknown_attempt")
        inputs = read_json(ws.blob_path(row["input_blob"]))
        if row["kind"] == "query":
            emit(query(ws, Query.model_validate(inputs["request"])))
        elif row["kind"] == "processing":
            emit(execute_plan(ws, Plan.model_validate(inputs["plan"])))
        elif row["kind"] in {"resolve", "discover"}:
            source = Sources(ws)
            try:
                emit(source.add(inputs["reference"], inputs["provider"]) if row["kind"] == "resolve"
                     else source.discover(Discovery.model_validate(inputs["request"])))
            finally:
                source.http.close()
        else:
            raise DawError("retry_requires_new_proposal")


@app.command()
def recover(ctx: typer.Context):
    with session(ctx) as ws:
        emit(ws.recover())


@app.command()
def backup(ctx: typer.Context, destination: Path):
    with session(ctx) as ws:
        emit(ws.backup(destination))


@app.command("restore-check")
def restore_check_command(backup: Path):
    result = restore_check(backup)
    emit(result)
    if not result["ok"]:
        raise typer.Exit(1)


@app.command()
def gc(ctx: typer.Context, dry_run: Annotated[bool, typer.Option("--dry-run/--execute")] = True):
    """Dry-run-first collection of unregistered orphan blobs older than seven days."""
    with session(ctx) as ws:
        candidates = []
        for path in (ws.root / "blobs/sha256").glob("*/*"):
            if path.is_file() and not path.is_symlink() and time.time() - path.stat().st_mtime > 7 * 86400:
                if not ws.one("SELECT sha256 FROM blob WHERE sha256=?", (path.name,)):
                    candidates.append({"path": str(path.relative_to(ws.root)), "sha256": file_hash(path)})
        receipt = ws.root / "proposals" / "gc-preview.json"
        if dry_run:
            write_json(receipt, {"created": now(), "candidates": candidates})
        else:
            if not receipt.exists() or read_json(receipt)["candidates"] != candidates:
                raise DawError("gc_preview_required", "run --dry-run and review the exact candidate list first")
            for candidate in candidates:
                (ws.root / candidate["path"]).unlink()
        emit({"dry_run": dry_run, "candidates": candidates, "accepted_evidence_deleted": False})


@app.command()
def demo(ctx: typer.Context):
    """Build a deterministic, adversarial synthetic example and query its hidden sheet."""
    from daw.demo import build_demo
    with session(ctx) as ws:
        emit(build_demo(ws))


def main():
    try:
        app()
    except DawError as e:
        emit({"error": e.reason, "detail": e.detail})
        raise SystemExit(1) from None
    except ValidationError as e:
        emit({"error": "invalid_contract", "details": e.errors(include_url=False, include_input=False)})
        raise SystemExit(1) from None
    except (FileNotFoundError, json.JSONDecodeError) as e:
        emit({"error": type(e).__name__, "detail": str(e)})
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
