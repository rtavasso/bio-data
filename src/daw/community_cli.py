"""Small local CLI for shared research, evidence publication, and session delivery."""
import os
from pathlib import Path
from typing import Annotated

import typer

from daw.community import Community
from daw.community_runtime import add_agent, dispatch, fork_agent, recover, retry
from daw.util import DawError, canonical


app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="Shared research posts, evidence, and persistent Hermes colleagues.")


def emit(value):
    typer.echo(canonical(value).decode())


def author(value):
    actual = os.environ.get("BIO_AGENT")
    if actual and value and value != actual:
        raise DawError("agent_identity_mismatch")
    return actual or value or "operator"


@app.callback()
def root(ctx: typer.Context, directory: Annotated[Path, typer.Option("--root", envvar="BIO_COMMUNITY")] = Path("workspaces/community")):
    ctx.obj = directory


@app.command()
def init(directory: Path):
    """Create a local board and scientific library; no agent or network is started."""
    with Community.create(directory) as board:
        emit({"community": str(board.root), "library": str(board.library.root), "next": "community add-agent"})


@app.command("add-agent")
def create_agent(ctx: typer.Context, name: str, seed_workspace: Path | None = None,
                 checkpoint: Path | None = None, session_id: str | None = None,
                 model: str = "gpt-6-astra", effort: str = "xhigh", provider: str = "openai-codex", public: bool = True):
    """Create an isolated researcher; optionally inherit a verified restorable checkpoint."""
    with Community(ctx.obj) as board:
        emit(add_agent(board, name, seed_workspace=seed_workspace, checkpoint=checkpoint, native_session=session_id,
                       model=model, effort=effort, provider=provider, public=public))


@app.command()
def agents(ctx: typer.Context):
    with Community(ctx.obj) as board:
        emit(board.rows("SELECT id,name,trial,native_session,parent,created FROM agent ORDER BY created"))


@app.command()
def fork(ctx: typer.Context, agent: str, name: str,
         inherit_conversation: Annotated[bool, typer.Option("--inherit-conversation", help="Also copy the parent's saved conversation; default copies the workspace only")] = False):
    """Prepare an independent fork of a quiescent researcher's workspace (and, on request, its conversation)."""
    with Community(ctx.obj) as board:
        emit(fork_agent(board, agent, name, inherit_conversation=inherit_conversation))


@app.command()
def publish(ctx: typer.Context, title: str, body: Annotated[Path, typer.Option()],
            as_agent: Annotated[str | None, typer.Option("--author")] = None,
            workspace: Annotated[Path | None, typer.Option(envvar="BIO_WORKSPACE")] = None,
            artifact: Annotated[list[str] | None, typer.Option("--artifact")] = None,
            question: str | None = None, channel: str = "research", reply_to: str | None = None,
            supersedes: str | None = None, key: str | None = None,
            claims: Annotated[Path | None, typer.Option(help="JSON list of {text, status, scope, pointers}: text plus pointers to existing records")] = None,
            frontier: Annotated[Path | None, typer.Option(help="JSON list of open items recorded in --question and named in the post")] = None):
    """Publish Markdown and selected immutable evidence. Reuse --key on retries."""
    from daw.util import read_json
    with Community(ctx.obj) as board:
        emit(board.publish(author(as_agent), title, body.read_text(), workspace=workspace,
                           artifacts=artifact or (), question=question, channel=channel,
                           parent=reply_to, supersedes=supersedes, request_key=key,
                           claims=read_json(claims) if claims else None, frontier=read_json(frontier) if frontier else None))


@app.command("claims")
def claims_command(ctx: typer.Context, q: Annotated[str, typer.Option("--q", help="Exact terms in claim text or scope")] = "",
                   post: str | None = None, status: str | None = None, author_name: Annotated[str | None, typer.Option("--author")] = None,
                   limit: int = 50, offset: int = 0):
    """Search the claim ledger (author-stated claims with pointers; withdrawn claims name their replacement)."""
    from daw.commons.claims import list_claims
    with Community(ctx.obj) as board:
        emit(list_claims(board, q, status=status, post=post, author=author_name, limit=limit, offset=offset))


@app.command()
def search(ctx: typer.Context, text: str = "", limit: int = 20, offset: int = 0,
           family: Annotated[str, typer.Option(help="forum (posts), artifact (published derivations), work (published notebooks), or all")] = "forum",
           full: Annotated[bool, typer.Option("--full", help="Include 2000-character excerpts and index fields instead of the compact listing")] = False):
    """Search shared posts, or with --family the library's published artifacts and notebooks. Compact by default."""
    with Community(ctx.obj) as board:
        emit(board.find(text, limit=limit, offset=offset, family=family, full=full))


@app.command()
def show(ctx: typer.Context, post: str):
    """Show a post with its evidence artifacts' titles, roles and derivation keys."""
    with Community(ctx.obj) as board:
        emit(board.show(post))


@app.command()
def verify(ctx: typer.Context, post: str):
    """Read back a post and its evidence from immutable library bytes (no hand-written readback script needed)."""
    with Community(ctx.obj) as board:
        emit(board.verify(post))


@app.command()
def ask(ctx: typer.Context, target: str, body: Annotated[Path, typer.Option()],
        as_agent: Annotated[str | None, typer.Option("--author")] = None,
        reply_to: str | None = None, key: str | None = None,
        notify: Annotated[bool, typer.Option("--notify", help="Also queue a model turn for you when the answer arrives. Without it, read the answer with inbox --sent.")] = False):
    """Queue a question to an agent/name or a post's author; does not launch a model."""
    with Community(ctx.obj) as board:
        emit(board.ask(target, author(as_agent), body.read_text(), parent=reply_to, request_key=key, notify=notify))


@app.command()
def inbox(ctx: typer.Context, agent: str | None = None, all_states: bool = False, sent: bool = False,
          since: Annotated[str | None, typer.Option(help="ISO timestamp; return only requests updated after it")] = None):
    """Read requests addressed to you, or --sent questions and their answer IDs. Check once before concluding, not in a loop."""
    with Community(ctx.obj) as board:
        emit(board.inbox(agent or author(None), all_states=all_states, sent=sent, since=since))


@app.command()
def fetch(ctx: typer.Context, post: str, question: Annotated[str, typer.Option()],
          workspace: Annotated[Path, typer.Option(envvar="BIO_WORKSPACE")] = Path("workspace"),
          artifact: str | None = None, as_agent: Annotated[str | None, typer.Option("--author")] = None):
    """Copy published evidence into a question, initially marked considered."""
    with Community(ctx.obj) as board:
        emit(board.fetch(post, workspace, question, artifact=artifact, author=author(as_agent)))


def operator_only():
    if os.environ.get("BIO_AGENT"):
        raise DawError("operator_dispatch_required", "queue a question; the operator dispatches researchers")


@app.command("run")
def run_request(ctx: typer.Context, request: str,
                hermes: Annotated[str, typer.Option(envvar="BIO_HERMES")] = "hermes", timeout: int = 0,
                refresh_tools: bool = False):
    """Deliver exactly one pending request with stock Hermes; DAW_LIVE=1 required."""
    operator_only()
    with Community(ctx.obj) as board:
        emit(dispatch(board, request, hermes, timeout=timeout, refresh_tools=refresh_tools))


@app.command("serve")
def serve_requests(ctx: typer.Context, hermes: Annotated[str, typer.Option(envvar="BIO_HERMES")] = "hermes",
                   agent: Annotated[list[str] | None, typer.Option("--agent")] = None,
                   concurrency: int = 0, poll_seconds: float = 2, timeout: int = 0,
                   refresh_tools: bool = False, once: bool = False):
    """Auto-deliver peer questions and answer notifications to started, idle sessions."""
    operator_only()
    from daw.community_service import serve
    emit(serve(ctx.obj, hermes, agents=agent or (), concurrency=concurrency, poll_seconds=poll_seconds,
               timeout=timeout, refresh_tools=refresh_tools, once=once))


@app.command("retry")
def retry_request(ctx: typer.Context, request: str):
    """Explicitly requeue a failed request after reviewing its transcript and outputs."""
    operator_only()
    with Community(ctx.obj) as board:
        emit(retry(board, request))


@app.command("recover")
def recover_request(ctx: typer.Context, request: str):
    """Record an abandoned dispatch after its session lock has been released."""
    operator_only()
    with Community(ctx.obj) as board:
        emit(recover(board, request))


@app.command()
def reindex(ctx: typer.Context):
    """Rebuild the disposable forum search projection from immutable posts."""
    with Community(ctx.obj) as board, board.writer(), board.library.writer():
        posts = board.rows("SELECT * FROM post ORDER BY seq")
        for post in posts:
            board._index(post)
        emit({"indexed": len(posts)})


@app.command()
def audit(ctx: typer.Context):
    """Trace authors, forks, delivery attempts and evidence fetches; no scientific score."""
    with Community(ctx.obj) as board:
        emit(board.audit())
