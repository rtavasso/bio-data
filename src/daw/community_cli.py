"""Small local CLI for shared research, evidence publication, and session delivery."""
import json
import os
from pathlib import Path
from typing import Annotated

import typer

from daw.community import Community
from daw.community_runtime import STALL_MINUTES, add_agent, dispatch, fork_agent, recover, retry
from daw.util import DawError, canonical


app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="Shared research posts, evidence, and persistent colleagues on stock agent harnesses.")


def emit(value):
    typer.echo(canonical(value).decode())


def emit_publication(value):
    """A publication's JSON on stdout; its non-fatal warnings (V1: evidence without claims) also on stderr."""
    for warning in (value.get("warnings") or []) if isinstance(value, dict) else []:
        typer.echo(f"warning: {warning.get('code')}: {warning.get('message')}", err=True)
    emit(value)


def author(value):
    actual = os.environ.get("BIO_AGENT")
    if actual and value and value != actual:
        raise DawError("agent_identity_mismatch")
    return actual or value or "operator"


# In a sandboxed checkout the board is not mounted: BIO_BOARD_URL names the operator's board service
# (daw.commons.boardservice), which runs these commands as this agent. Nothing else is available there.
REMOTE = {"publish", "answer", "ask", "inbox", "fetch", "show", "search", "verify", "claims", "agents"}


def remote():
    from daw.commons.boardservice import BoardClient
    return BoardClient.from_env()


@app.callback()
def root(ctx: typer.Context, directory: Annotated[Path, typer.Option("--root", envvar="BIO_COMMUNITY")] = Path("workspaces/community")):
    if os.environ.get("BIO_BOARD_URL") and ctx.invoked_subcommand not in REMOTE:
        raise DawError("board_service_only", f"this checkout reaches the board through its board service: "
                                             f"{', '.join(sorted(REMOTE))}")
    ctx.obj = directory


@app.command()
def init(directory: Path):
    """Create a local board and scientific library; no agent or network is started."""
    with Community.create(directory) as board:
        emit({"community": str(board.root), "library": str(board.library.root), "next": "community add-agent"})


@app.command("add-agent")
def create_agent(ctx: typer.Context, name: str, seed_workspace: Path | None = None,
                 checkpoint: Path | None = None, session_id: str | None = None,
                 model: Annotated[str | None, typer.Option(help="Default: the harness's default (Hermes: gpt-6-astra)")] = None,
                 effort: str = "xhigh",
                 provider: Annotated[str | None, typer.Option(help="Default: the harness's default (Hermes: openai-codex)")] = None,
                 public: bool = True,
                 harness: Annotated[str, typer.Option(help="hermes, codex, claude, mcp or scripted")] = "hermes",
                 harness_options: Annotated[str | None, typer.Option(help="JSON options (mcp: executable, args, resume_args, provider_hosts; scripted: stream_format)")] = None):
    """Create an isolated researcher on a stock harness; optionally inherit a verified restorable checkpoint."""
    try:
        options = json.loads(harness_options) if harness_options else None
    except ValueError as e:
        raise DawError("invalid_harness_options", "JSON object required") from e
    with Community(ctx.obj) as board:
        emit(add_agent(board, name, seed_workspace=seed_workspace, checkpoint=checkpoint, native_session=session_id,
                       model=model, effort=effort, provider=provider, public=public, harness=harness,
                       harness_options=options))


@app.command()
def agents(ctx: typer.Context):
    """List participants (on the host: with checkout, saved session and harness; through the board service: public fields only)."""
    from daw.commons.boardservice import local_agents as listing
    if client := remote():
        return emit(client.call("agents", {}))
    with Community(ctx.obj) as board:
        emit(listing(board))


@app.command()
def fork(ctx: typer.Context, agent: str, name: str,
         inherit_conversation: Annotated[bool, typer.Option("--inherit-conversation", help="Also copy the parent's saved conversation; default copies the workspace only")] = False):
    """Prepare an independent fork of a quiescent researcher's workspace (and, on request, its conversation)."""
    with Community(ctx.obj) as board:
        emit(fork_agent(board, agent, name, inherit_conversation=inherit_conversation))


def _evidence(artifact, question, key, claims, frontier, workspace):
    """Publication options shared by publish and answer; files are read here and travel as content."""
    from daw.util import read_json
    return {"artifacts": list(artifact or ()), "question": question, "key": key,
            "claims": read_json(claims) if claims else None, "frontier": read_json(frontier) if frontier else None,
            "workspace": str(workspace.resolve()) if workspace else None}


def _local_publication(options):
    return {"artifacts": options["artifacts"], "question": options["question"], "request_key": options["key"],
            "claims": options["claims"], "frontier": options["frontier"], "workspace": options["workspace"]}


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
    options = _evidence(artifact, question, key, claims, frontier, workspace)
    if client := remote():
        return emit_publication(client.call("publish", {"title": title, "body": body.read_text(), "author": as_agent,
                                                        "channel": channel, "reply_to": reply_to,
                                                        "supersedes": supersedes, **options}))
    with Community(ctx.obj) as board:
        emit_publication(board.publish(author(as_agent), title, body.read_text(), channel=channel, parent=reply_to,
                           supersedes=supersedes, **_local_publication(options)))


@app.command()
def answer(ctx: typer.Context, request: str, body: Annotated[Path, typer.Option()],
           title: Annotated[str | None, typer.Option(help="Default: Re: <question title>")] = None,
           as_agent: Annotated[str | None, typer.Option("--author")] = None,
           workspace: Annotated[Path | None, typer.Option(envvar="BIO_WORKSPACE")] = None,
           artifact: Annotated[list[str] | None, typer.Option("--artifact")] = None,
           question: str | None = None, key: str | None = None,
           claims: Annotated[Path | None, typer.Option(help="JSON list of {text, status, scope, pointers}")] = None,
           frontier: Annotated[Path | None, typer.Option(help="JSON list of open items recorded in --question")] = None):
    """Answer a request addressed to you: publish a reply to its question post (settles a pending request)."""
    from daw.commons.boardservice import answer as answer_request
    options = _evidence(artifact, question, key, claims, frontier, workspace)
    if client := remote():
        return emit_publication(client.call("answer", {"request": request, "body": body.read_text(), "title": title,
                                                       "author": as_agent, **options}))
    with Community(ctx.obj) as board:
        emit_publication(answer_request(board, author(as_agent), request, body.read_text(), title=title,
                            **_local_publication(options)))


@app.command("claims")
def claims_command(ctx: typer.Context, q: Annotated[str, typer.Option("--q", help="Exact terms in claim text or scope")] = "",
                   post: str | None = None, status: str | None = None, author_name: Annotated[str | None, typer.Option("--author")] = None,
                   limit: int = 50, offset: int = 0):
    """Search the claim ledger (author-stated claims with pointers; withdrawn claims name their replacement)."""
    if client := remote():
        return emit(client.call("claims", {"q": q, "post": post, "status": status, "author": author_name,
                                           "limit": limit, "offset": offset}))
    from daw.commons.claims import list_claims
    with Community(ctx.obj) as board:
        emit(list_claims(board, q, status=status, post=post, author=author_name, limit=limit, offset=offset))


@app.command()
def search(ctx: typer.Context, text: str = "", limit: int = 20, offset: int = 0,
           family: Annotated[str, typer.Option(help="forum (posts), artifact (published derivations), work (published notebooks), or all")] = "forum",
           full: Annotated[bool, typer.Option("--full", help="Include 2000-character excerpts and index fields instead of the compact listing")] = False):
    """Search shared posts, or with --family the library's published artifacts and notebooks. Compact by default."""
    if client := remote():
        return emit(client.call("search", {"text": text, "limit": limit, "offset": offset, "family": family,
                                           "full": full}))
    with Community(ctx.obj) as board:
        emit(board.find(text, limit=limit, offset=offset, family=family, full=full))


@app.command()
def show(ctx: typer.Context, post: str):
    """Show a post with its evidence artifacts' titles, roles and derivation keys."""
    if client := remote():
        return emit(client.call("show", {"post": post}))
    with Community(ctx.obj) as board:
        emit(board.show(post))


@app.command()
def verify(ctx: typer.Context, post: str):
    """Read back a post and its evidence from immutable library bytes (no hand-written readback script needed)."""
    if client := remote():
        return emit(client.call("verify", {"post": post}))
    with Community(ctx.obj) as board:
        emit(board.verify(post))


@app.command()
def ask(ctx: typer.Context, target: str, body: Annotated[Path, typer.Option()],
        as_agent: Annotated[str | None, typer.Option("--author")] = None,
        reply_to: str | None = None, key: str | None = None,
        notify: Annotated[bool, typer.Option("--notify", help="Also queue a model turn for you when the answer arrives. Without it, read the answer with inbox --sent.")] = False):
    """Queue a question to an agent/name or a post's author; does not launch a model."""
    if client := remote():
        return emit(client.call("ask", {"target": target, "body": body.read_text(), "author": as_agent,
                                        "reply_to": reply_to, "key": key, "notify": notify}))
    with Community(ctx.obj) as board:
        emit(board.ask(target, author(as_agent), body.read_text(), parent=reply_to, request_key=key, notify=notify))


@app.command()
def inbox(ctx: typer.Context, agent: str | None = None, all_states: bool = False, sent: bool = False,
          since: Annotated[str | None, typer.Option(help="ISO timestamp; return only requests updated after it")] = None):
    """Read requests addressed to you, or --sent questions and their answer IDs. Check once before concluding, not in a loop."""
    if client := remote():
        return emit(client.call("inbox", {"agent": agent, "all_states": all_states, "sent": sent, "since": since}))
    with Community(ctx.obj) as board:
        emit(board.inbox(agent or author(None), all_states=all_states, sent=sent, since=since))


@app.command()
def fetch(ctx: typer.Context, post: str, question: Annotated[str, typer.Option()],
          workspace: Annotated[Path, typer.Option(envvar="BIO_WORKSPACE")] = Path("workspace"),
          artifact: str | None = None, as_agent: Annotated[str | None, typer.Option("--author")] = None):
    """Copy published evidence into a question, initially marked considered."""
    if client := remote():
        return emit(client.call("fetch", {"post": post, "question": question, "workspace": str(workspace.resolve()),
                                          "artifact": artifact, "author": as_agent}))
    with Community(ctx.obj) as board:
        emit(board.fetch(post, workspace, question, artifact=artifact, author=author(as_agent)))



def operator_only():
    if os.environ.get("BIO_AGENT"):
        raise DawError("operator_dispatch_required", "queue a question; the operator dispatches researchers")


@app.command("run")
def run_request(ctx: typer.Context, request: str,
                hermes: Annotated[str, typer.Option(envvar="BIO_HERMES")] = "hermes", timeout: int = 0,
                refresh_tools: bool = False,
                executable: Annotated[str | None, typer.Option(help="Harness executable for a non-Hermes agent (default: the harness's own name)")] = None,
                stall_minutes: Annotated[float, typer.Option(help="Notify the operator after this many minutes without output")] = STALL_MINUTES,
                stall_timeout: Annotated[int, typer.Option(help="Seconds without output after which the run is stopped (0: never)")] = 0,
                allow_unsandboxed: Annotated[str | None, typer.Option(help="Recorded reason to run without a sandbox on a multi-tenant commons")] = None):
    """Deliver exactly one pending request with the target's stock harness; DAW_LIVE=1 required."""
    operator_only()
    with Community(ctx.obj) as board:
        target = board.one("SELECT target FROM request WHERE id=?", (request,))
        harness = board.agent(target["target"])["config"].get("harness", "hermes") if target else "hermes"
        emit(dispatch(board, request, executable or (hermes if harness == "hermes" else None), timeout=timeout,
                      refresh_tools=refresh_tools, stall_minutes=stall_minutes, stall_timeout=stall_timeout,
                      allow_unsandboxed=allow_unsandboxed))


@app.command("serve")
def serve_requests(ctx: typer.Context, hermes: Annotated[str, typer.Option(envvar="BIO_HERMES")] = "hermes",
                   agent: Annotated[list[str] | None, typer.Option("--agent")] = None,
                   concurrency: int = 0, poll_seconds: float = 2, timeout: int = 0,
                   refresh_tools: bool = False, once: bool = False,
                   harness_executable: Annotated[list[str] | None, typer.Option("--harness-executable", help="HARNESS=PATH for non-Hermes agents (repeatable)")] = None,
                   stall_minutes: float = STALL_MINUTES, stall_timeout: int = 0,
                   allow_unsandboxed: Annotated[str | None, typer.Option(help="Recorded reason to run without a sandbox on a multi-tenant commons")] = None):
    """Auto-deliver peer questions, answer notifications, human comments and person-authorized tasks to idle sessions."""
    operator_only()
    from daw.community_service import serve
    executables = {}
    for item in harness_executable or []:
        name, sep, path = item.partition("=")
        if not sep or not path:
            raise DawError("invalid_harness_executable", "use HARNESS=PATH")
        executables[name] = path
    emit(serve(ctx.obj, hermes, agents=agent or (), concurrency=concurrency, poll_seconds=poll_seconds,
               timeout=timeout, refresh_tools=refresh_tools, once=once, executables=executables,
               stall_minutes=stall_minutes, stall_timeout=stall_timeout, allow_unsandboxed=allow_unsandboxed))


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
