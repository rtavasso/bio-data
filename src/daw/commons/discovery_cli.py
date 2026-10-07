"""`bio commons watch …` and `bio commons embed`: operator commands for watchers and the embedding batch."""
from typing import Annotated

import typer

from daw.util import DawError, canonical

watch_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None,
                        help="Scoped discovery watchers on frontier items (retrieval only). Run `tick` weekly from cron.")


def emit(value):
    typer.echo(canonical(value).decode())


def _board(ctx):
    from daw.community import Community
    return Community(ctx.obj)


@watch_app.command("add")
def watch_add(ctx: typer.Context, item: str, query: Annotated[str, typer.Option(help="Provider query text")],
              provider: Annotated[str, typer.Option(help="europepmc, zenodo, encode, chipatlas, pride, cellxgene, gtex, or "
                                                      "europepmc-fulltext (query: one PMID, PMCID or DOI)")],
              filter: Annotated[list[str] | None, typer.Option(help="FIELD=VALUE literal equality on returned hits")] = None,
              interval: Annotated[int, typer.Option(help="Seconds between runs (default one week)")] = 604800,
              max_pages: int = 1, page_size: int = 25,
              actor: Annotated[str, typer.Option("--as", help="Participant attaching the watcher")] = "operator"):
    """Attach a scoped discovery query to a frontier item; due at the next tick."""
    from daw.commons.watchers import add_watcher
    filters = {}
    for value in filter or []:
        key, sep, literal = value.partition("=")
        if not sep or not key:
            raise DawError("invalid_watcher_query", "filters use FIELD=VALUE")
        filters[key] = literal
    with _board(ctx) as board:
        emit(add_watcher(board, actor, item, {"query": query, "filters": filters, "max_pages": max_pages,
                                              "page_size": page_size}, provider, interval))


@watch_app.command("list")
def watch_list(ctx: typer.Context, item: str | None = None, runs: bool = False):
    from daw.commons import watchers
    with _board(ctx) as board:
        rows = watchers.list_watchers(board, item)
        if runs:
            for row in rows:
                row["run_history"] = watchers.runs(board, row["id"])
        emit({"items": rows})


@watch_app.command("tick")
def watch_tick(ctx: typer.Context, max_watchers: int = 10,
               actor: Annotated[str, typer.Option("--as", help="Operator running the tick")] = "operator"):
    """Run due watchers once (bounded). Schedule weekly, e.g. cron `17 3 * * 1 bio commons --root R watch tick`."""
    from daw.commons.watchers import tick
    with _board(ctx) as board:
        emit(tick(board, max_watchers=max_watchers, actor=actor))


@watch_app.command("disable")
def watch_disable(ctx: typer.Context, watcher: str,
                  actor: Annotated[str, typer.Option("--as", help="Watcher author or an operator")] = "operator"):
    from daw.commons.watchers import disable_watcher
    with _board(ctx) as board:
        emit(disable_watcher(board, actor, watcher))


def embed(ctx: typer.Context,
          model: Annotated[str | None, typer.Option(help="hashing-ngram-v1 (default) or sentence-transformers:<name>@<revision>")] = None,
          family: str | None = None, workspaces: Annotated[bool, typer.Option(help="Also embed agent workspaces")] = True,
          allow_download: bool = False):
    """Embed the library's and agent workspaces' index documents (changed documents only)."""
    from daw.commons.embeddings import embed_commons
    with _board(ctx) as board:
        emit(embed_commons(board, model, family=family, workspaces=workspaces, allow_download=allow_download))
