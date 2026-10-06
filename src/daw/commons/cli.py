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
