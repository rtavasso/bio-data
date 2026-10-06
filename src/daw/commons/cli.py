"""`bio commons`: serve the web application, build the synthetic demo, manage participants."""
from pathlib import Path
from typing import Annotated

import typer

from daw.util import DawError, canonical

app = typer.Typer(no_args_is_help=True, rich_markup_mode=None,
                  help="Colloquy research commons: web observatory and attributed human participation.")


def emit(value):
    typer.echo(canonical(value).decode())


@app.callback()
def root(ctx: typer.Context, directory: Annotated[Path, typer.Option("--root", envvar="BIO_COMMUNITY")] = Path("workspaces/community")):
    ctx.obj = directory


@app.command()
def serve(ctx: typer.Context, host: str = "127.0.0.1", port: int = 8765,
          mode: Annotated[str, typer.Option(help="local (single user, no login) or accounts")] = "local",
          user: Annotated[str, typer.Option(help="Human participant used in local mode")] = "local",
          static_dir: Annotated[Path | None, typer.Option(help="Built web app (default web/dist)")] = None):
    """Serve the read API, write API, event stream and built web app for one commons."""
    try:
        import uvicorn
    except ImportError as e:
        raise DawError("commons_extra_required", "install with: uv sync --extra commons") from e
    from daw.commons.app import create_app
    if host not in {"127.0.0.1", "localhost", "::1"} and mode == "local":
        raise DawError("local_mode_is_loopback_only", "use --mode accounts to listen on other interfaces")
    uvicorn.run(create_app(ctx.obj, mode=mode, local_user=user, static_dir=static_dir), host=host, port=port)


@app.command()
def demo(directory: Path):
    """Build a synthetic demo commons (scripted harness; no model, credential or network)."""
    from daw.commons.demo import build_demo
    emit({"commons": str(directory.resolve()), **build_demo(directory),
          "next": f"bio commons --root {directory} serve"})


@app.command("add-participant")
def add_participant_command(ctx: typer.Context, name: str,
                            kind: Annotated[str, typer.Option(help="human, operator or system")] = "human",
                            display_name: str | None = None, affiliation: str | None = None, orcid: str | None = None):
    """Create a human, operator or system participant. Agents are created with community add-agent."""
    from daw.commons.participants import add_participant, describe
    from daw.community import Community
    profile = {k: v for k, v in {"display_name": display_name, "affiliation": affiliation, "orcid": orcid}.items() if v}
    with Community(ctx.obj) as board:
        emit(describe(add_participant(board, name, kind, profile=profile)))


cohort_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None,
                         help="Evaluation cohorts (M9.3): named, explicit sets of runs.")
metrics_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None,
                          help="Per-run evaluation metrics (M9.1–M9.4) computed from runs/.")
app.add_typer(cohort_app, name="cohort")
app.add_typer(metrics_app, name="metrics")


@cohort_app.command("create")
def cohort_create(ctx: typer.Context, name: str,
                  run: Annotated[list[str] | None, typer.Option("--run", help="Run id (repeatable)")] = None,
                  agent: Annotated[list[str] | None, typer.Option("--agent", help="Agent id or name (repeatable)")] = None,
                  since: Annotated[str | None, typer.Option(help="ISO date or datetime with timezone")] = None,
                  until: Annotated[str | None, typer.Option(help="ISO date (inclusive) or datetime with timezone")] = None,
                  assignment: Annotated[list[str] | None, typer.Option(
                      "--assignment", help="RUN=KEY explicit assignment key (default: request body sha256)")] = None,
                  note: str = "", actor: Annotated[str, typer.Option("--as", help="Operator participant")] = "operator"):
    """Record a cohort. Selectors resolve to explicit run ids now; later runs never join it."""
    from daw.commons.metrics import create_cohort
    from daw.community import Community
    keys = {}
    for item in assignment or []:
        run_id, sep, key = item.partition("=")
        if not sep or not key.strip():
            raise DawError("invalid_assignment", "use RUN=KEY")
        keys[run_id] = key.strip()
    with Community(ctx.obj) as board:
        emit(create_cohort(board, actor, name, runs=run or [], agents=agent or [], since=since, until=until,
                           assignments=keys, note=note))


@cohort_app.command("list")
def cohort_list(ctx: typer.Context):
    """List cohorts with run and assignment counts."""
    from daw.commons.archive import Archive
    from daw.commons.metrics import list_cohorts
    with Archive(ctx.obj) as view:
        emit({"items": list_cohorts(view)})


@cohort_app.command("show")
def cohort_show(ctx: typer.Context, identity: str,
                runs: Annotated[bool, typer.Option(help="Include per-run metrics")] = False):
    """Show a cohort's body and per-criterion summary."""
    from daw.commons.archive import Archive
    from daw.commons.metrics import cohort_view
    with Archive(ctx.obj) as view:
        value = cohort_view(view, identity)
        if not runs:
            value.pop("runs")
        emit(value)


@cohort_app.command("compare")
def cohort_compare(ctx: typer.Context, identities: list[str]):
    """Same assignment across cohorts side by side; criteria stay separate (no composite score)."""
    from daw.commons.archive import Archive
    from daw.commons.metrics import compare
    with Archive(ctx.obj) as view:
        emit(compare(view, identities))


@metrics_app.command("refresh")
def metrics_refresh(ctx: typer.Context,
                    actor: Annotated[str, typer.Option("--as", help="Operator participant")] = "operator"):
    """Store run metrics for runs whose files changed (idempotent; one board event when anything changed)."""
    from daw.commons.metrics import refresh_metrics
    from daw.community import Community
    with Community(ctx.obj) as board:
        emit(refresh_metrics(board, actor))


@metrics_app.command("dashboard")
def metrics_dashboard(ctx: typer.Context, cohort: str | None = None, participant: str | None = None,
                      harness: str | None = None, task_type: str | None = None, bucket: str = "week"):
    """Print the dashboard panels as JSON (the same read model as GET /api/dashboard)."""
    from daw.commons.archive import Archive
    from daw.commons.metrics import dashboard
    with Archive(ctx.obj) as view:
        emit(dashboard(view, cohort_id=cohort, participant=participant, harness=harness, task_type=task_type,
                       bucket=bucket))
