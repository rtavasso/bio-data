"""`bio commons export|federation|replication|review|digest|writeup`: Studio and federation commands (M6, M8.4).

Each command calls the same function as the HTTP API with an explicit acting participant; agents act
through `bio community` in their own checkout instead.
"""
import json
from pathlib import Path
from typing import Annotated

import typer

from daw.util import DawError, canonical

federation_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None,
                             help="Read-only federation: import and inspect exported snapshots of other commons.")
replication_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None,
                              help="Replication tasks: confirm identical bytes or record a mismatch correction.")
review_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="Review tasks: structured verdicts as marks.")
digest_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None,
                         help="Digests summarise existing records; `tick` (operator cron) creates standing digests' "
                              "requests. Not scientific scheduling.")
writeup_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="Write-up renderer checks (M6.1).")
As = Annotated[str, typer.Option("--as", help="Acting participant (name or id)")]


def emit(value):
    typer.echo(canonical(value).decode())


def acting(value):
    import os
    if os.environ.get("BIO_AGENT"):
        raise DawError("agents_use_community_cli", "agents publish, ask and answer with bio community")
    return value


def _board(ctx):
    from daw.community import Community
    return Community(ctx.obj)


def _budget(minutes, tokens, download_bytes):
    return {k: v for k, v in {"minutes": minutes, "tokens": tokens, "download_bytes": download_bytes}.items() if v is not None}


def _scope(query, question, post):
    return {k: v for k, v in {"query": query, "questions": question or [], "posts": post or []}.items() if v}


def demo_command(directory: Path):
    """Add Studio demo records (write-ups, review, replication, digest) to a commons built by `bio commons demo`."""
    from daw.commons.studio_demo import apply
    emit({"commons": str(directory.resolve()), "studio": apply(directory)})


def export_command(ctx: typer.Context, output: Annotated[Path | None, typer.Option(help="Empty or new directory; "
                                                                                   "default <commons>/exports/<id>")] = None,
                   board: Annotated[bool, typer.Option("--board", help="Export the whole board")] = False,
                   thread: Annotated[str | None, typer.Option(help="Export the thread containing POST")] = None,
                   question: Annotated[str | None, typer.Option(help="Export AGENT/QID")] = None, as_: As = "operator"):
    """Export a question, thread or the board as a static, content-addressed site (snapshot.json + sha256 ID)."""
    from daw.commons.export import export_snapshot
    chosen = [(k, v) for k, v in (("board", board or None), ("thread", thread), ("question", question)) if v]
    if len(chosen) != 1:
        raise DawError("invalid_export_scope", "choose exactly one of --board, --thread POST, --question AGENT/QID")
    kind, value = chosen[0]
    with _board(ctx) as commons:
        emit(export_snapshot(commons, acting(as_), kind, None if kind == "board" else value, output))


@federation_app.command("import")
def federation_import(ctx: typer.Context, directory: Path,
                      expect: Annotated[str | None, typer.Option(help="Snapshot ID the citation names")] = None,
                      as_: As = "operator"):
    """Verify every hash in DIR/snapshot.json, store the snapshot read-only under <commons>/federation/<id>/ and
    index its claim and artifact ids (V7: `snapshot:<id>/claim_…` pointers then resolve to bytes). The import
    is attributed to the --as participant (receipt, events, /me)."""
    from daw.commons.federation import import_and_index
    from daw.community import Community
    with Community(ctx.obj) as board:
        info = import_and_index(board, directory, actor=acting(as_), expect=expect,
                                origin={"directory": str(directory)})
    emit({k: v for k, v in info.items() if k != "files"} | {"file_count": len(info["files"])})


@federation_app.command("list")
def federation_list(ctx: typer.Context):
    """Imported snapshots (foreign, untrusted, read-only)."""
    from daw.commons.export import list_snapshots
    emit(list_snapshots(Path(ctx.obj).expanduser().resolve()))


@federation_app.command("verify")
def federation_verify(ctx: typer.Context, snapshot: str):
    """Re-hash every file of an imported snapshot."""
    from daw.commons.export import snapshot_info
    info = snapshot_info(Path(ctx.obj).expanduser().resolve(), snapshot, verify=True)
    emit({k: v for k, v in info.items() if k != "files"})
    if not info.get("verified"):
        raise typer.Exit(1)


@replication_app.command("check")
def replication_check(ctx: typer.Context, request: str, as_: As = "operator"):
    """Record the confirmation (reproduced mark + reply) or the mismatch correction for a delivered replication."""
    from daw.commons.studio import replication_check as check
    with _board(ctx) as commons:
        emit(check(commons, request, actor=acting(as_)))


@review_app.command("marks")
def review_marks(ctx: typer.Context, post: str, as_: As = "operator"):
    """Record the marks of a review post (idempotent; the runtime does this after each review delivery)."""
    from daw.commons.studio import record_review_marks
    with _board(ctx) as commons:
        emit(record_review_marks(commons, post, actor=acting(as_)))


@review_app.command("submit")
def review_submit(ctx: typer.Context, target_kind: str, target_id: str,
                  verdicts: Annotated[Path, typer.Option(help="JSON list of {criterion, verdict, note, pointers}")],
                  as_: As = "operator", summary: str = ""):
    """A person's review: a reply post with structured verdicts, shown as marks on the target."""
    from daw.commons.studio import submit_review
    with _board(ctx) as commons:
        emit(submit_review(commons, acting(as_), target_kind, target_id, json.loads(verdicts.read_text()), summary))


@digest_app.command("skeleton")
def digest_skeleton(ctx: typer.Context, since: str | None = None, until: str | None = None, query: str | None = None,
                    question: Annotated[list[str] | None, typer.Option("--question")] = None,
                    post: Annotated[list[str] | None, typer.Option("--post")] = None,
                    markdown: Annotated[bool, typer.Option("--markdown", help="Print only the Markdown")] = False):
    """The deterministic digest skeleton a writer receives as input context."""
    from daw.commons.archive import Archive
    from daw.commons.studio import digest_skeleton as skeleton
    with Archive(ctx.obj) as view:
        value = skeleton(view, _scope(query, question, post), since, until)
    typer.echo(value["markdown"]) if markdown else emit(value)


@digest_app.command("commission")
def digest_commission(ctx: typer.Context, target: Annotated[str, typer.Option()], as_: As = "operator",
                      since: str | None = None, until: str | None = None, query: str | None = None,
                      question: Annotated[list[str] | None, typer.Option("--question")] = None,
                      post: Annotated[list[str] | None, typer.Option("--post")] = None, minutes: int | None = None,
                      tokens: int | None = None, download_bytes: int | None = None, deadline: str | None = None,
                      note: str | None = None):
    """Commission one digest of a scope and period; the request carries the skeleton."""
    from daw.commons.studio import commission_digest
    with _board(ctx) as commons:
        emit(commission_digest(commons, acting(as_), target, _scope(query, question, post),
                               _budget(minutes, tokens, download_bytes), since=since, until=until, deadline=deadline,
                               note=note))


@digest_app.command("schedule")
def digest_schedule(ctx: typer.Context, target: Annotated[str, typer.Option()],
                    cadence: Annotated[str, typer.Option(help="daily, weekly or a number of days")] = "weekly",
                    as_: As = "operator", query: str | None = None,
                    question: Annotated[list[str] | None, typer.Option("--question")] = None,
                    post: Annotated[list[str] | None, typer.Option("--post")] = None, minutes: int | None = None,
                    tokens: int | None = None, download_bytes: int | None = None, start: str | None = None):
    """Record a standing digest commission (person, cadence, scope); `digest tick` creates each request."""
    from daw.commons.studio import schedule_digest
    with _board(ctx) as commons:
        emit(schedule_digest(commons, acting(as_), target, _scope(query, question, post),
                             int(cadence) if cadence.isdigit() else cadence, _budget(minutes, tokens, download_bytes),
                             start=start))


@digest_app.command("tick")
def digest_tick(ctx: typer.Context, as_: As = "operator", at: str | None = None):
    """Operator cron: create the next request of every due standing digest, attributed to its person."""
    from daw.commons.studio import digest_tick as tick
    with _board(ctx) as commons:
        emit(tick(commons, acting(as_), at=at))


@digest_app.command("list")
def digest_list(ctx: typer.Context):
    from daw.commons.archive import Archive
    from daw.commons.studio import schedule_row
    with Archive(ctx.obj) as view:
        emit([schedule_row(r) for r in view.rows("SELECT * FROM digest_schedule ORDER BY created,id")])


@digest_app.command("cancel")
def digest_cancel(ctx: typer.Context, schedule: str, as_: As = "operator"):
    from daw.commons.studio import cancel_digest
    with _board(ctx) as commons:
        emit(cancel_digest(commons, acting(as_), schedule))


@writeup_app.command("check")
def writeup_check(ctx: typer.Context, post: str):
    """Render a write-up; exits 1 with every unpointed number and unresolved pointer when refused."""
    from daw.commons.archive import Archive
    from daw.commons.writeup import render_writeup
    with Archive(ctx.obj) as view:
        result = render_writeup(view, post, with_map=False)
    emit({k: result.get(k) for k in ("post", "status", "problems", "stats", "verdict", "regeneration_required")})
    if result["status"] != "rendered":
        raise typer.Exit(1)


@writeup_app.command("record")
def writeup_record(ctx: typer.Context, post: str, as_: As = "operator"):
    """Re-check a write-up and record the verdict (`writeup_check` event; operator, permission dispatch).
    The runtime records it at delivery; this is for verdicts that must be re-taken after the ledger changed."""
    from daw.commons.checks import record
    from daw.commons.permissions import require
    with _board(ctx) as commons:
        actor = require(commons, commons.agent(acting(as_)), "dispatch")
        emit(record(commons, post, actor=actor["id"]))
