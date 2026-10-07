"""`bio commons preprint|directory|tour|public-demo|federation-demo|harness-check|invite|pilot-report` and
`bio commons federation reindex|records|citations|cited-by` (spec v2 V3, V7, V8; v3 V16, B9).

Each command calls the same function as the HTTP API. Commands that write take an explicit acting participant
(`--as`); agents act through `bio community` in their own checkout instead.
"""
import os
from pathlib import Path
from typing import Annotated

import typer

from daw.util import DawError, canonical

directory_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None,
                            help="Public commons directory: publish, list and fetch content-addressed snapshots.")
tour_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None,
                       help="Curated reading paths (board -> thread -> number -> bytes), re-checked on every read.")
As = Annotated[str, typer.Option("--as", help="Acting participant (name or id)")]


def emit(value):
    typer.echo(canonical(value).decode())


def acting(value):
    if os.environ.get("BIO_AGENT"):
        raise DawError("agents_use_community_cli", "agents publish, ask and answer with bio community")
    return value


def preprint_command(ctx: typer.Context, post: str, as_: As = "operator",
                     output: Annotated[Path | None, typer.Option(help="Empty or new folder (default <commons>/exports/<id>/)")] = None):
    """Export a write-up as a verifiable preprint: cited claims, artifact bytes, verdicts and verify.py."""
    from daw.commons.preprint import export_preprint
    from daw.community import Community
    with Community(ctx.obj) as board:
        emit(export_preprint(board, acting(as_), post, output))


@directory_app.command("publish")
def directory_publish(snapshot: Path,
                      directory: Annotated[Path, typer.Option("--directory", help="directory.json (or its folder)")],
                      lab: Annotated[str, typer.Option(help="Publishing lab or commons name")],
                      title: str | None = None,
                      location: Annotated[str | None, typer.Option(help="Where the snapshot is already hosted (relative path or http(s) URL); default: copy it under the directory")] = None,
                      publisher: str | None = None, note: str | None = None):
    """Verify a snapshot folder and list it in a directory file (copies it beside the directory by default)."""
    from daw.commons.directory import publish
    emit(publish(snapshot, directory, lab=lab, title=title, location=location, publisher=publisher, note=note))


@directory_app.command("list")
def directory_list(source: str):
    """Read and validate a directory from a path, a file:// URL or an http(s) URL."""
    from daw.commons.directory import listing
    emit(listing(source))


@directory_app.command("fetch")
def directory_fetch(ctx: typer.Context, source: str, snapshot: str, as_: As = "operator"):
    """Fetch a listed snapshot into this commons: verified byte for byte, imported read-only and indexed, the
    import attributed to the --as participant."""
    from daw.commons.directory import fetch
    from daw.community import Community
    with Community(ctx.obj) as board:
        emit(fetch(board, source, snapshot, actor=acting(as_)))


@directory_app.command("show")
def directory_show(ctx: typer.Context):
    """This commons' own directory, the directories it fetched from, and what is imported and indexed."""
    from daw.commons.archive import Archive
    from daw.commons.directory import known
    with Archive(ctx.obj) as view:
        emit(known(view))


def federation_reindex(ctx: typer.Context, as_: As = "operator"):
    """Rebuild the federation index from <commons>/federation/ (snapshots that no longer verify drop out)."""
    from daw.commons.federation import reindex
    from daw.community import Community
    with Community(ctx.obj) as board:
        emit(reindex(board, acting(as_)))


def federation_records(ctx: typer.Context, snapshot: str):
    """Indexed claims and artifacts of an imported snapshot, with their pointer forms."""
    from daw.commons.archive import Archive
    from daw.commons.federation import records
    with Archive(ctx.obj) as view:
        emit(records(view, snapshot))


def federation_citations(ctx: typer.Context):
    """Which imported snapshots this board's posts cite, by question (recorded citations only)."""
    from daw.commons.archive import Archive
    from daw.commons.federation import citations
    with Archive(ctx.obj) as view:
        emit(citations(view))


def federation_cited_by(ctx: typer.Context, record: Annotated[str | None, typer.Argument(help="claim_… or artifact_… of this board")] = None):
    """Posts of imported snapshots that cite records of snapshots this board exported (V16; recorded only)."""
    from daw.commons.archive import Archive
    from daw.commons.federation import cited_by
    with Archive(ctx.obj) as view:
        emit({"cited_by": cited_by(view, record)})


@tour_app.command("list")
def tour_list(ctx: typer.Context):
    """Tours available to this commons and whether each applies (its steps resolve here)."""
    from daw.commons.archive import Archive
    from daw.commons.tour import listing
    with Archive(ctx.obj) as view:
        emit(listing(view))


@tour_app.command("verify")
def tour_verify(ctx: typer.Context, path: Path):
    """Re-check every step of a tour file against this commons; exit 1 when a step is broken."""
    from daw.commons.archive import Archive
    from daw.commons.tour import load, resolve
    with Archive(ctx.obj) as view:
        resolved = resolve(view, load(path))
    emit({"summary": resolved["summary"], "steps": [{k: s.get(k) for k in ("step", "final", "ok", "problems", "clicks_to_bytes")}
                                                    for s in resolved["steps"]]})
    if resolved["summary"]["broken"]:
        raise typer.Exit(1)


@tour_app.command("locate")
def tour_locate(ctx: typer.Context, post: str, offset: Annotated[int, typer.Option(help="The number's offset in the post body")],
                artifact: str | None = None):
    """Curation aid: locators where a number's value occurs in the artifacts its post names (candidates only)."""
    from daw.commons.archive import Archive
    from daw.commons.tour import candidates
    with Archive(ctx.obj) as view:
        emit(candidates(view, post, offset, artifact))


def public_demo_command(out: Path, fixture: Annotated[Path | None, typer.Option(help="Real-data fixture (default fixtures/pmp22-cohort)")] = None,
                        tour: Annotated[Path | None, typer.Option(help="Tour JSON (default docs/colloquy/tours/pmp22-cohort.json)")] = None,
                        snapshot: Annotated[Path | None, typer.Option(help="Also export the board as a citable snapshot here")] = None):
    """Build the PMP22 cohort as a public demo commons: verified copy of the fixture, checked tour, PUBLIC.json."""
    from daw.commons.publicdemo import build
    emit(build(out, fixture=fixture, tour=tour, snapshot=snapshot))


def federation_demo_command(out: Path,
                            cited: Annotated[str, typer.Option(help="cohort (the public PMP22 cohort; artifact cells, it has no claims yet) or demo (a synthetic commons with claims)")] = "cohort",
                            fixture: Annotated[Path | None, typer.Option(help="Real-data fixture for --cited cohort (default fixtures/pmp22-cohort)")] = None):
    """Build a second commons that imports and cites a snapshot, and the cited commons that imports the citing
    snapshot back, so the citation shows on both sides (V16). Offline; the second commons is synthetic."""
    from daw.commons.federationdemo import build
    emit(build(out, cited=cited, fixture=fixture))


def harness_check_command(harness: Annotated[str, typer.Option(help="codex, claude or hermes")],
                          executable: Annotated[str | None, typer.Option(help="Harness CLI (default: on PATH)")] = None,
                          model: str | None = None,
                          workdir: Annotated[Path | None, typer.Option(help="New folder for the throwaway commons")] = None,
                          output: Annotated[Path | None, typer.Option(help="Receipt path (live default docs/v3/receipts/harness-check-<harness>.json)")] = None,
                          scripted: Annotated[bool, typer.Option(help="Offline: the scripted stand-in speaks the harness protocol (not a live receipt)")] = False):
    """Two-turn assignment with resume through the real runtime; writes a compact receipt (DAW_LIVE=1 for live)."""
    import tempfile

    from daw.commons import harnesscheck
    if os.environ.get("BIO_AGENT"):
        raise DawError("operator_dispatch_required")
    if scripted and output is None:
        raise DawError("output_required", "a scripted check is not a live receipt: pass --output")
    folder = workdir or Path(tempfile.mkdtemp(prefix="colloquy-harness-check-")) / "commons"
    receipt = harnesscheck.run(harness, folder, executable=executable, model=model, scripted=scripted)
    path = harnesscheck.write(receipt, output)
    emit({"receipt": path, "verdict": receipt["verdict"], "failures": receipt["failures"], "live": receipt["live"]})
    if receipt["verdict"] != "pass":
        raise typer.Exit(1)


def invite_command(ctx: typer.Context, name: str, as_: As = "operator", display_name: str | None = None,
                   affiliation: str | None = None, orcid: str | None = None,
                   minutes: Annotated[int | None, typer.Option(help="Promotion/commission allowance (agent-minutes)")] = None,
                   url: Annotated[str | None, typer.Option(help="Public URL of this commons, for the login line")] = None,
                   output: Annotated[Path | None, typer.Option(help="Invitation file (default <commons>/invitations/NAME.md)")] = None):
    """Invite an external researcher: human participant, token (in the invitation file only) and allowance."""
    from daw.commons.pilotkit import invite
    from daw.community import Community
    with Community(ctx.obj) as board:
        emit(invite(board, acting(as_), name, display_name=display_name, affiliation=affiliation, orcid=orcid,
                    minutes=minutes, url=url, output=output))


def pilot_report_command(ctx: typer.Context,
                         participant: Annotated[list[str] | None, typer.Option("--participant", help="Name or id (repeatable; default: invited people)")] = None):
    """Comments, marks, promotions and commissions per person, and whether each request changed an agent's work."""
    from daw.commons.archive import Archive
    from daw.commons.pilotkit import report
    with Archive(ctx.obj) as view:
        emit(report(view, participant))


def register(app, federation_app):
    """Attach the commands to `bio commons` (called from daw.commons.cli)."""
    app.command("preprint")(preprint_command)
    app.command("public-demo")(public_demo_command)
    app.command("federation-demo")(federation_demo_command)
    app.command("harness-check")(harness_check_command)
    app.command("invite")(invite_command)
    app.command("pilot-report")(pilot_report_command)
    app.add_typer(directory_app, name="directory")
    app.add_typer(tour_app, name="tour")
    federation_app.command("reindex")(federation_reindex)
    federation_app.command("records")(federation_records)
    federation_app.command("citations")(federation_citations)
    federation_app.command("cited-by")(federation_cited_by)
