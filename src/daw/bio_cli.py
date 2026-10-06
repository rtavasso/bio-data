"""Agent-facing research substrate. Ordinary files and tools are the analysis interface."""
import contextlib
import json
import re
import os
import platform
import sqlite3
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from daw.adapters import Sources
from daw.artifacts import artifact_info, attach_artifact, check_output_role, find_derivation, provenance, register_artifact
from daw.catalog import Workspace, restore_check
from daw.commons.cli import app as commons_app
from daw.community_cli import app as community_app
from daw.gaps import report_gaps
from daw.indexer import create_job, import_graph, index_status, run_job, schedule_feed, tick
from daw.inspectors import extract_members, inspect_asset
from daw.models import Discovery
from daw.profiles import add_profile, profile_asset, profile_manifest, show_data, verify_object
from daw.search import add_embedding, document, search
from daw.substrate_models import ArtifactRegistration, Derivation, Embedding, IndexPlan, ObjectInput, Profile
from daw.transport import Transport
from daw.util import DawError, canonical, environment_identity, read_json
from daw.work import create_question, record_event, show_work, sync_work

app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="BIO — persistent public data, searchable contents, and reusable research work.")
data_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="Search and inspect data without a scientific acceptance gate.")
artifact_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="Find and reuse artifacts by their actual derivation.")
work_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="Question folders, notebooks, and prior research.")
index_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="Resumable progressive indexing and recurring feeds.")
object_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="Preserve exact source, code and reference bytes.")
app.add_typer(data_app, name="data")
app.add_typer(artifact_app, name="artifact")
app.add_typer(work_app, name="work")
app.add_typer(index_app, name="index")
app.add_typer(object_app, name="object")
app.add_typer(community_app, name="community")
app.add_typer(commons_app, name="commons")


def emit(value):
    typer.echo(canonical(value).decode())


@app.callback()
def root(ctx: typer.Context, workspace: Annotated[Path, typer.Option("--workspace", "-w", envvar="BIO_WORKSPACE")] = Path("workspace")):
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
    """Create or migrate a local workspace, preserving v1 evidence and history."""
    ws = Workspace.create(workspace)
    emit({"workspace": str(ws.root), "catalog_version": ws.db.execute("PRAGMA user_version").fetchone()[0],
          "object_store": str(ws.root / "blobs/sha256"), "next": "bio resolve, bio index run, or bio work new"})
    ws.close()


@app.command()
def doctor(ctx: typer.Context):
    """Check the actual catalog, search engine, and environment."""
    with session(ctx, False) as ws:
        emit({"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "catalog_version": ws.db.execute("PRAGMA user_version").fetchone()[0],
            "integrity": ws.db.execute("PRAGMA integrity_check").fetchone()[0],
            "journal_mode": ws.db.execute("PRAGMA journal_mode").fetchone()[0],
            "search": "SQLite FTS5; optional supplied model vectors", "model_required": False,
            "network_required_for_local_work": False, "budgets": ws.budgets.model_dump(),
            "workspace": str(ws.root), "writable": os.access(ws.root, os.W_OK)})


def local_search(ctx, text, family=None, feature=None, provider=None, format=None, limit=20, offset=0,
                 min_level=0, include_historical=False, vector=None, model=None):
    with session(ctx, False) as ws:
        emit(search(ws, text, family=family, feature=feature, provider=provider, format=format, limit=limit,
                    offset=offset, min_level=min_level, include_historical=include_historical,
                    vector=read_json(vector) if vector else None, model=model))


@app.command("search")
def search_command(ctx: typer.Context, text: str = "", family: str | None = None, feature: str | None = None,
                   provider: str | None = None, format: str | None = None, limit: int = 20, offset: int = 0,
                   min_level: int = 0, include_historical: bool = False, vector: Path | None = None, model: str | None = None,
                   vector_text: Annotated[str | None, typer.Option(help="Embed this text with the pinned local model "
                                                                    "(default hashing-ngram-v1) and rank by cosine")] = None):
    """Search local data and prior work; no internet, model, or scientific planner."""
    if vector_text is not None:
        from daw.embeddings import vector_search
        if vector or text:
            raise DawError("select_one_search_mode", "use TEXT, --vector or --vector-text")
        with session(ctx, False) as ws:
            emit(vector_search(ws, vector_text, model=model, family=family, provider=provider, format=format,
                               limit=limit, offset=offset, min_level=min_level, include_historical=include_historical))
        return
    local_search(ctx, text, family, feature, provider, format, limit, offset, min_level, include_historical, vector, model)


@data_app.command("search")
def data_search(ctx: typer.Context, text: str = "", feature: str | None = None, provider: str | None = None,
                format: str | None = None, limit: int = 20, offset: int = 0, min_level: int = 0):
    """Search source context, apparent affordances, and literal labels inside files."""
    local_search(ctx, text, "data", feature, provider, format, limit, offset, min_level)


@artifact_app.command("search")
def artifact_search(ctx: typer.Context, text: str = "", limit: int = 20, offset: int = 0):
    local_search(ctx, text, "artifact", limit=limit, offset=offset)


@work_app.command("search")
def work_search(ctx: typer.Context, text: str = "", limit: int = 20, offset: int = 0):
    local_search(ctx, text, "work", limit=limit, offset=offset)


@app.command()
def discover(ctx: typer.Context, text: str, provider: Annotated[str, typer.Option()], pages: int = 1, page_size: int = 25):
    """Explicit bounded public-provider search; add hits to the local research index."""
    with session(ctx) as ws:
        source = Sources(ws)
        try:
            result = source.discover(Discovery(provider=provider, query=text, max_pages=pages, page_size=page_size))
            for rid in result["resources"]:
                profile_manifest(ws, rid)
            emit({k: v for k, v in result.items() if k != "pages"})
        finally:
            source.http.close()


@app.command()
def resolve(ctx: typer.Context, reference: str, provider: str | None = None):
    """Enumerate a public reference and index its file manifests; no large downloads."""
    with session(ctx) as ws:
        source = Sources(ws)
        source.native_metadata_only = True
        try:
            result = source.add(reference, provider)
            profile_manifest(ws, result["bundle"])
            for aid in result["assets"]:
                profile_manifest(ws, aid)
            emit({**{k: v for k, v in result.items() if k not in {"metadata", "assets"}},
                  "assets": result["assets"][:100], "asset_count": len(result["assets"]),
                  "next": "bio data list --scope BUNDLE_ID, then bio fetch ASSET_ID"})
        finally:
            source.http.close()


@app.command()
def fetch(ctx: typer.Context, asset: str, allow_raw: bool = False, question: str | None = None):
    """Acquire one exact representation; raw downloading requires an explicit flag."""
    with session(ctx) as ws:
        http = Transport(ws)
        try:
            result = http.acquire(asset, allow_raw)
            profile_manifest(ws, result["asset_revision"])
            if question:
                record_event(ws, question, "acquisition", result)
            emit(result)
        finally:
            http.close()


@data_app.command("fulltext")
def data_fulltext(ctx: typer.Context, pmcid: str):
    """Fetch Europe PMC JATS full text; index paragraphs with stable locators (sec[2]/p[3]) and SHA-256."""
    with session(ctx) as ws:
        source = Sources(ws)
        try:
            emit(source.fulltext(pmcid))
        finally:
            source.http.close()


@data_app.command("supplementary")
def data_supplementary(ctx: typer.Context, pmcid: str, max_files: int = 10, max_bytes: int = 256 * 2**20,
                       max_asset_bytes: int = 64 * 2**20):
    """List an article's supplementary files, fetch tables within budgets and inspect them safely (receipted)."""
    with session(ctx) as ws:
        source = Sources(ws)
        source.native_metadata_only = True
        try:
            emit(source.supplementary(pmcid, max_files=max_files, max_bytes=max_bytes, max_asset_bytes=max_asset_bytes))
        finally:
            source.http.close()


@data_app.command("import")
def import_data(ctx: typer.Context, path: Path, dataset: str = "local"):
    """Preserve an explicitly selected local source without executing its contents."""
    with session(ctx) as ws:
        result = ws.local_asset(path, dataset)
        emit({**result, "profile": profile_manifest(ws, result["asset_revision"])})


@data_app.command("list")
def data_list(ctx: typer.Context, scope: str | None = None, limit: int = 20, offset: int = 0):
    with session(ctx, False) as ws:
        if not 1 <= limit <= 100 or offset < 0:
            raise DawError("invalid_search_bounds")
        assets = ws.assets([scope] if scope else [])
        emit({"total": len(assets), "offset": offset, "items": [{"asset_revision": a["id"], "name": a["body"]["name"],
              "access": a["access"], "blob": a["blob"], "bytes": a["body"]["size"]} for a in assets[offset:offset + limit]],
              "next_offset": offset + limit if offset + limit < len(assets) else None})


@app.command("inspect")
def inspect_command(ctx: typer.Context, asset: str, structure_only: bool = False):
    """Inspect immutable bytes and index structural facts/literal feature labels."""
    with session(ctx) as ws:
        emit(inspect_asset(ws, asset) if structure_only else profile_asset(ws, asset))


@data_app.command("extract")
def extract(ctx: typer.Context, asset: str, member: Annotated[list[str], typer.Option()]):
    """Extract only explicitly named archive members within safety/resource bounds."""
    with session(ctx) as ws:
        results = extract_members(ws, asset, member)
        for result in results:
            profile_manifest(ws, result["asset_revision"])
        emit({"members": results})


@data_app.command("show")
def data_show(ctx: typer.Context, subject: str):
    with session(ctx, False) as ws:
        emit(show_data(ws, subject))


@data_app.command("profile")
def data_profile(ctx: typer.Context, manifest: Annotated[Path, typer.Option()]):
    """Index an attributed descriptive profile; alternatives coexist without approval gates."""
    with session(ctx) as ws:
        emit(add_profile(ws, Profile.model_validate(read_json(manifest))))


@data_app.command("history")
def profile_history(ctx: typer.Context, subject: str):
    with session(ctx, False) as ws:
        emit({"subject": subject, "profiles": ws.rows("SELECT * FROM dataset_profile WHERE subject=? ORDER BY created,id", (subject,))})


@object_app.command("add")
def object_add(ctx: typer.Context, path: Path, classification: str = "source"):
    with session(ctx) as ws:
        if path.is_symlink() or not path.is_file() or (ws.budgets.asset_bytes and path.stat().st_size > ws.budgets.asset_bytes):
            raise DawError("invalid_or_over_budget_object")
        sha = ws.put_file(path, classification)
        emit({"blob": sha, "bytes": path.stat().st_size, "path": str(ws.blob_path(sha))})


@object_app.command("show")
def object_show(ctx: typer.Context, blob: str):
    with session(ctx, False) as ws:
        path = verify_object(ws, blob)
        emit({"blob": blob, "bytes": path.stat().st_size, "path": str(path)})


@app.command("register")
def register(ctx: typer.Context, path: Path, manifest: Path | None = None, question: str | None = None,
             title: str = "", summary: str = "",
             input: Annotated[list[str] | None, typer.Option("--input", help="Asset ID, artifact ID, or stored blob SHA256. Preserve local files with bio object add first.")] = None,
             code: Annotated[list[Path] | None, typer.Option(help="Local analysis script path; repeat for multiple scripts.")] = None, parameters: str = "{}",
             reference: Annotated[list[str] | None, typer.Option()] = None, environment: Path | None = None,
             output_role: str = "result"):
    """Register a computed output. Flags require --input and --code; prose can stay in LABBOOK.md."""
    with session(ctx) as ws:
        check_output_role(output_role)
        if manifest:
            if input or code or reference or environment or title or summary or parameters != "{}" or output_role != "result":
                raise DawError("registration_manifest_and_flags_are_exclusive")
            registration = ArtifactRegistration.model_validate(read_json(manifest))
        else:
            inputs = []
            for value in input or []:
                if value.startswith("asset_"):
                    inputs.append(ObjectInput(blob=ws.asset(value)["blob"], source_identity=value))
                elif value.startswith("artifact_"):
                    inputs.append(ObjectInput(blob=artifact_info(ws, value)["output_blob"], source_identity=value))
                else:
                    try:
                        ws.blob_path(value)
                    except DawError as e:
                        if e.reason != "invalid_blob_hash":
                            raise
                        raise DawError(e.reason, f"--input {value!r} must be an asset ID, artifact ID, or stored blob SHA256. "
                                       "For a local file, run bio object add PATH, then use its returned blob hash as --input.") from e
                    inputs.append(ObjectInput(blob=value))
            registration = ArtifactRegistration(title=title or path.name, summary=summary, output_role=output_role,
                derivation=Derivation(inputs=inputs, code=[ws.put_file(p, "code") for p in code or []],
                    parameters=json.loads(parameters), references=reference or [],
                    environment=read_json(environment) if environment else environment_identity()))
        emit(register_artifact(ws, path, registration, question=question))


@artifact_app.command("find")
def artifact_find(ctx: typer.Context, derivation: Annotated[Path, typer.Option()], output_role: str = "result"):
    with session(ctx, False) as ws:
        emit(find_derivation(ws, Derivation.model_validate(read_json(derivation)), output_role))


@artifact_app.command("show")
def artifact_show(ctx: typer.Context, artifact: str):
    with session(ctx, False) as ws:
        emit(artifact_info(ws, artifact))


@artifact_app.command("use")
def artifact_use(ctx: typer.Context, artifact: str, question: Annotated[str, typer.Option()], name: str | None = None,
                 reason: Annotated[str | None, typer.Option(help="How the bytes inform this analysis; marks the artifact reused. Without it the link is considered.")] = None):
    """Attach an artifact to a question. Retrieval alone is `considered`; `reused` needs --reason or a later --input."""
    with session(ctx) as ws:
        emit(attach_artifact(ws, question, artifact, "reused" if reason else "considered", name=name, reason=reason))


@work_app.command("new")
def work_new(ctx: typer.Context, title: str, prompt: Path | None = None):
    with session(ctx) as ws:
        emit(create_question(ws, title, prompt.read_text() if prompt else None))


@work_app.command("show")
def work_show(ctx: typer.Context, question: str, notebook: bool = False, events: int = 0):
    with session(ctx, False) as ws:
        emit(show_work(ws, question, notebook=notebook, events=events))


@work_app.command("sync")
def work_sync(ctx: typer.Context, question: str, summary: str | None = None, status: str | None = None):
    """Snapshot edited files and index the notebook for future questions."""
    with session(ctx) as ws:
        emit(sync_work(ws, question, summary=summary, status=status))


@work_app.command("event")
def work_event(ctx: typer.Context, question: str, kind: Annotated[str, typer.Option()], payload: Annotated[Path, typer.Option()]):
    with session(ctx) as ws:
        emit(record_event(ws, question, kind, read_json(payload)))


@work_app.command("gap")
def work_gap(ctx: typer.Context, question: str, desired_information: Annotated[str, typer.Option("--need")],
             why_current_tools_failed: Annotated[str, typer.Option("--failed")], source_or_format: str = "unspecified",
             likely_value: str | None = None, possible_indexing_solution: str | None = None, gap_key: str | None = None,
             evidence: Path | None = None):
    """Record an actual information-access failure; freeform details remain question-local."""
    payload = {"desired_information": desired_information, "why_current_tools_failed": why_current_tools_failed,
               "source_or_format": source_or_format}
    payload.update({k: v for k, v in {"likely_value": likely_value, "possible_indexing_solution": possible_indexing_solution,
                                    "gap_key": gap_key}.items() if v is not None})
    with session(ctx) as ws:
        if evidence is None and re.search(r"browser|web\.run|captcha", why_current_tools_failed, re.IGNORECASE):
            raise DawError("evidence_required", "a browser/web failure claim needs --evidence pointing at the saved response "
                           "or tool result; stock Hermes has no browser, so an unreceipted claim is unsupported")
        if evidence:
            payload["evidence_blob"] = ws.put_file(evidence, "work")
        emit(record_event(ws, question, "retrieval_gap", payload))


@work_app.command("gap-withdraw")
def work_gap_withdraw(ctx: typer.Context, question: str, event: str, reason: Annotated[str, typer.Option()]):
    """Withdraw an unsupported failure report without changing its original bytes."""
    with session(ctx) as ws:
        emit(record_event(ws, question, "retrieval_gap_withdrawal", {"event": event, "reason": reason}))


@work_app.command("gaps")
def work_gaps(ctx: typer.Context, question: str | None = None, since: str | None = None,
              source_or_format: str | None = None, limit: int = 20, max_events: int = 10000):
    """Aggregate recurring retrieval failures across questions, with source events and coverage."""
    with session(ctx, False) as ws:
        emit(report_gaps(ws, question=question, since=since, source=source_or_format, limit=limit, max_events=max_events))


@app.command("provenance")
def provenance_command(ctx: typer.Context, identity: str, depth: int = 3):
    with session(ctx, False) as ws:
        emit(provenance(ws, identity, depth=depth))


@index_app.command("run")
def index_run(ctx: typer.Context, plan: Path | None = None, job: str | None = None, level: int = 2,
              max_tasks: int | None = None, seconds: int | None = None, retry: bool = False):
    """Start or resume bounded indexing; an ordinary scheduler can invoke this repeatedly."""
    with session(ctx) as ws:
        if plan and job:
            raise DawError("select_plan_or_existing_job")
        if not job:
            request = IndexPlan.model_validate(read_json(plan)) if plan else IndexPlan(level=level)
            job = create_job(ws, request)["id"]
        emit(run_job(ws, job, max_tasks=max_tasks, seconds=seconds, retry=retry))


@index_app.command("status")
def index_status_command(ctx: typer.Context, job: str | None = None, limit: int = 30):
    with session(ctx, False) as ws:
        if not 1 <= limit <= 100:
            raise DawError("invalid_status_limit")
        emit(index_status(ws, job, limit=limit))


@index_app.command("import")
def index_import(ctx: typer.Context, path: Path, max_records: int = 1000):
    """Import/resume a bulk research graph JSONL file without crawling linked datasets."""
    with session(ctx) as ws:
        emit(import_graph(ws, path, max_records=max_records))


@index_app.command("schedule")
def index_schedule(ctx: typer.Context, plan: Annotated[Path, typer.Option()], every: int = 86400):
    with session(ctx) as ws:
        emit(schedule_feed(ws, IndexPlan.model_validate(read_json(plan)), every))


@index_app.command("tick")
def index_tick(ctx: typer.Context, max_feeds: int = 1):
    with session(ctx) as ws:
        emit(tick(ws, max_feeds=max_feeds))


@index_app.command("embedding")
def index_embedding(ctx: typer.Context, manifest: Annotated[Path, typer.Option()]):
    """Register a model-versioned vector computed with the agent's chosen tools."""
    with session(ctx) as ws:
        emit(add_embedding(ws, Embedding.model_validate(read_json(manifest))))


@index_app.command("embed")
def index_embed(ctx: typer.Context, model: Annotated[str | None, typer.Option(help="hashing-ngram-v1 (default) or "
                                                                            "sentence-transformers:<name>@<revision>")] = None,
                family: str | None = None, limit: int | None = None, allow_download: bool = False):
    """Embed index documents with a pinned local model; only documents whose fingerprint changed are re-embedded."""
    from daw.embeddings import embed_documents, load_model
    with session(ctx) as ws:
        loaded = load_model(model, allow_download=allow_download)
        emit({**embed_documents(ws, loaded, family=family, limit=limit), "model_card": loaded.card()})


@index_app.command("document")
def index_document_show(ctx: typer.Context, document_id: str):
    with session(ctx, False) as ws:
        emit(document(ws, document_id))


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
def recover(ctx: typer.Context):
    with session(ctx) as ws:
        from daw.work import rebuild_event_log
        result = ws.recover()
        with ws.db:
            tasks = ws.db.execute("UPDATE index_task SET state='pending' WHERE state='running' AND stage!='semantic'").rowcount
            ws.db.execute("UPDATE index_job SET state='pending' WHERE state='running'")
        journals = [rebuild_event_log(ws, q["id"]) for q in ws.rows("SELECT id FROM question")]
        emit({**result, "index_tasks_requeued": tasks, "question_journals": journals})


@app.command()
def demo(ctx: typer.Context):
    """Index hidden content, write a normal script, and reuse its artifact in a second question."""
    from daw.substrate_demo import demo as run_demo
    with session(ctx) as ws:
        emit(run_demo(ws))


def main():
    try:
        app()
    except DawError as e:
        emit({"error": e.reason, "detail": e.detail})
        raise SystemExit(1) from None
    except ValidationError as e:
        emit({"error": "invalid_contract", "details": e.errors(include_url=False, include_input=False)})
        raise SystemExit(1) from None
    except (OSError, ValueError) as e:
        emit({"error": type(e).__name__, "detail": str(e)})
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
