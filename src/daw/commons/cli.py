"""`bio commons`: serve the web application, build the synthetic demo, manage participants."""
import json
from pathlib import Path
from typing import Annotated

import typer

from daw.commons.discovery_cli import embed, watch_app
from daw.commons.studio_cli import (demo_command, digest_app, export_command, federation_app, replication_app,
                                    review_app, writeup_app)
from daw.util import DawError, canonical

app = typer.Typer(no_args_is_help=True, rich_markup_mode=None,
                  help="Colloquy research commons: web observatory and attributed human participation.")
app.add_typer(watch_app, name="watch")
fixture_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None,
                         help="Real-data fixtures: redacted, committable copies of a commons (C0).")
app.add_typer(fixture_app, name="fixture")


@fixture_app.command("build")
def fixture_build(source: Path, out: Path, name: str | None = None):
    """Copy a real commons without downloaded bytes, session databases or tool outputs; writes FIXTURE.json."""
    from daw.commons.fixture import build_fixture
    emit(build_fixture(source, out, name=name))


@fixture_app.command("verify")
def fixture_verify(root: Path):
    """Check every file in FIXTURE.json against its recorded sha256."""
    from daw.commons.fixture import verify_fixture
    emit(verify_fixture(root))
app.command("embed")(embed)
app.command("export")(export_command)
app.command("demo-studio")(demo_command)
for _name, _sub in (("federation", federation_app), ("replication", replication_app), ("review", review_app),
                    ("digest", digest_app), ("writeup", writeup_app)):
    app.add_typer(_sub, name=_name)


def emit(value):
    typer.echo(canonical(value).decode())


@app.callback()
def root(ctx: typer.Context, directory: Annotated[Path, typer.Option("--root", envvar="BIO_COMMUNITY")] = Path("workspaces/community")):
    ctx.obj = directory


@app.command()
def serve(ctx: typer.Context, host: str = "127.0.0.1", port: int = 8765,
          mode: Annotated[str, typer.Option(help="local (single user, no login) or accounts")] = "local",
          user: Annotated[str, typer.Option(help="Human participant used in local mode")] = "local",
          static_dir: Annotated[Path | None, typer.Option(help="Built web app (default web/dist)")] = None,
          forwarded_allow_ips: Annotated[str | None, typer.Option(help="Reverse-proxy addresses trusted for X-Forwarded-For (login rate limits count client addresses)")] = None):
    """Serve the read API, write API, event stream and built web app for one commons."""
    uvicorn = _uvicorn()
    from daw.commons.app import create_app
    if host not in {"127.0.0.1", "localhost", "::1"} and mode == "local":
        raise DawError("local_mode_is_loopback_only", "use --mode accounts to listen on other interfaces")
    app = create_app(ctx.obj, mode=mode, local_user=user, static_dir=static_dir)
    from daw.commons.sandbox import record_tenancy
    # Live dispatch on a commons that serves accounts requires a sandbox (M3.6).
    record_tenancy(Path(ctx.obj).expanduser().resolve(), mode)
    uvicorn.run(app, host=host, port=port, **_forwarded(forwarded_allow_ips))


def _uvicorn():
    try:
        import uvicorn
    except ImportError as e:
        raise DawError("commons_extra_required", "install with: uv sync --extra commons") from e
    return uvicorn


def _forwarded(value):
    return {"proxy_headers": True, "forwarded_allow_ips": value} if value else {}


@app.command("host")
def host_command(config: Annotated[Path, typer.Option("--config", help="tenants.toml")], host: str = "127.0.0.1",
                 port: int = 8765,
                 static_dir: Annotated[Path | None, typer.Option(help="Built web app (overrides [host] static_dir)")] = None,
                 forwarded_allow_ips: Annotated[str | None, typer.Option(help="Reverse-proxy addresses trusted for X-Forwarded-For")] = None):
    """Serve one commons per organisation from one process, each at /c/<tenant>/ in accounts mode (M7.4)."""
    import dataclasses

    uvicorn = _uvicorn()
    from daw.commons import tenants
    from daw.commons.sandbox import record_tenancy
    loaded = tenants.load(config)
    if static_dir:
        loaded = dataclasses.replace(loaded, static_dir=static_dir.resolve())
    app = tenants.create_host_app(loaded)
    for tenant in loaded.tenants:
        record_tenancy(tenant.root, "accounts")  # every tenant is multi-tenant: live dispatch needs its sandbox
    typer.echo(canonical({"listen": f"{host}:{port}", "tenants": {t.name: {"base": t.base, "root": str(t.root)}
                                                                 for t in loaded.tenants}}).decode())
    uvicorn.run(app, host=host, port=port, **_forwarded(forwarded_allow_ips))


@app.command()
def demo(directory: Path):
    """Build a synthetic demo commons (scripted harness; no model, credential or network)."""
    from daw.commons.demo import build_demo
    emit({"commons": str(directory.resolve()), **build_demo(directory),
          "next": f"bio commons --root {directory} serve"})


@app.command("demo-deliver")
def demo_deliver(ctx: typer.Context, request: str,
                 answer: Annotated[Path, typer.Option(help="Markdown file: the scripted agent's answer")],
                 hook: Annotated[Path | None, typer.Option(help="Fixture Python run in the agent's checkout before it answers")] = None,
                 replicate: Annotated[bool, typer.Option(help="Replication request: the hook runs the research skill's replicate.py on its subject")] = False):
    """Deliver one pending request on a synthetic demo commons with the scripted harness (operator; demo only)."""
    acting("operator")
    from daw.commons.demo import deliver_scripted
    emit(deliver_scripted(ctx.obj, request, answer.read_text(), hook=hook.read_text() if hook else None,
                          replicate=replicate))


@app.command("demo-watch-tick")
def demo_watch_tick(ctx: typer.Context,
                    response: Annotated[Path, typer.Option(help="Recorded Europe PMC search JSON served to due watchers")],
                    as_: Annotated[str, typer.Option("--as", help="Operator running the tick")] = "operator",
                    max_watchers: int = 10):
    """Run due watchers on a synthetic demo commons against a recorded response (no network; demo only)."""
    acting("operator")
    from daw.commons.demo import watch_tick_recorded
    try:
        payload = json.loads(response.read_text())
    except ValueError as e:
        raise DawError("invalid_recorded_response", str(e)) from e
    emit(watch_tick_recorded(ctx.obj, payload, actor=as_, max_watchers=max_watchers))


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


# Attributed writes for operators and people without the web app (M2.4–M2.8, M7). Each command calls the
# same function as the HTTP write API. Agents act through `bio community` in their checkout instead.

As = Annotated[str, typer.Option("--as", help="Acting participant (name or id)")]


def acting(value):
    import os
    if os.environ.get("BIO_AGENT"):
        raise DawError("agents_use_community_cli", "agents publish, ask and answer with bio community")
    return value


def run(ctx, function, *args, **kwargs):
    from daw.community import Community
    with Community(ctx.obj) as board:
        emit(function(board, *args, **kwargs))


def budget_option(minutes, tokens, download_bytes):
    return {k: v for k, v in {"minutes": minutes, "tokens": tokens, "download_bytes": download_bytes}.items() if v is not None}


@app.command("post")
def post_command(ctx: typer.Context, title: str, body: Annotated[Path, typer.Option()], as_: As = "operator",
                 parent: str | None = None, supersedes: str | None = None,
                 upload: Annotated[list[str] | None, typer.Option("--upload", help="Upload id to attach")] = None):
    """Publish a human post or reply; uploads attach as evidence of kind upload."""
    from daw.commons.participation import post
    run(ctx, post, acting(as_), title, body.read_text(), parent=parent, supersedes=supersedes, upload_ids=upload or ())


@app.command("upload")
def upload_command(ctx: typer.Context, file: Path, as_: As = "operator",
                   media_type: str = "application/octet-stream", name: str | None = None):
    """Store a file as a library object with a receipt (never executed or registered as a derivation)."""
    from daw.commons.participation import upload
    run(ctx, upload, acting(as_), name or file.name, file.read_bytes(), media_type)


@app.command("comment")
def comment_command(ctx: typer.Context, target_kind: str, target_id: str, text: Annotated[str, typer.Option("--text")],
                    as_: As = "operator",
                    anchor: Annotated[str | None, typer.Option(help='JSON locator, e.g. {"kind":"paragraph",'
                                                                    '"blob":"<sha>","offset":0,"length":10}')] = None,
                    ask_author: Annotated[bool, typer.Option("--ask-author", help="Make the comment a request")] = False):
    """Comment on a post, question, artifact, claim, run or map node, optionally at an anchor."""
    import json
    from daw.commons.participation import comment
    run(ctx, comment, acting(as_), target_kind, target_id, text, anchor=json.loads(anchor) if anchor else None,
        ask_author=ask_author)


@app.command("ask")
def ask_command(ctx: typer.Context, target: str, text: Annotated[str, typer.Option("--text")], as_: As = "operator",
                parent: str | None = None):
    """Ask a participant (or a post's author) a durable question."""
    from daw.commons.participation import ask
    run(ctx, ask, acting(as_), target, text, parent=parent)


@app.command("mark")
def mark_command(ctx: typer.Context, target_kind: str, target_id: str, kind: str,
                 note: Annotated[str, typer.Option()], as_: As = "operator",
                 pointer: Annotated[list[str] | None, typer.Option("--pointer", help="kind:id[:locator]")] = None):
    """Record a verification mark (checked_source, reproduced, disputed): attribution, never a status change."""
    from daw.commons.participation import mark
    pointers = []
    for text in pointer or ():
        pointer_kind, _, rest = text.partition(":")
        identity, _, locator = rest.partition(":")
        pointers.append({"kind": pointer_kind, "id": identity, **({"locator": locator} if locator else {})})
    run(ctx, mark, acting(as_), target_kind, target_id, kind, note, pointers)


@app.command("promote")
def promote_command(ctx: typer.Context, source_kind: str, source_id: str,
                    task_type: Annotated[str, typer.Option()], target: Annotated[str, typer.Option()],
                    as_: As = "operator", minutes: int | None = None, tokens: int | None = None,
                    download_bytes: int | None = None, deadline: str | None = None, note: str | None = None):
    """Promote a frontier item, post or claim into a typed request with a budget (the only scheduling path)."""
    from daw.commons.participation import promote
    run(ctx, promote, acting(as_), source_kind, source_id, task_type, target,
        budget_option(minutes, tokens, download_bytes), deadline=deadline, note=note)


@app.command("commission")
def commission_command(ctx: typer.Context, task_type: str, target: Annotated[str, typer.Option()],
                       note: Annotated[str, typer.Option()], as_: As = "operator", minutes: int | None = None,
                       tokens: int | None = None, download_bytes: int | None = None, deadline: str | None = None,
                       subject_kind: str | None = None, subject_id: str | None = None):
    """Commission a review, replication, writing or digest task with a stated scope and budget."""
    from daw.commons.participation import commission
    run(ctx, commission, acting(as_), task_type, target, budget_option(minutes, tokens, download_bytes),
        deadline=deadline, subject_kind=subject_kind, subject_id=subject_id, note=note)


@app.command("allowance")
def allowance_command(ctx: typer.Context, participant: str, as_: As = "operator", minutes: int | None = None,
                      tokens: int | None = None, download_bytes: int | None = None):
    """Set a human's promotion/commission allowance (no limits given clears it to the commons default)."""
    from daw.commons.participation import set_allowance
    run(ctx, set_allowance, acting(as_), participant, budget_option(minutes, tokens, download_bytes))


MODERATION_HELP = {"hide": "Hide a post (reversible, event-logged; bytes are kept).", "unhide": "Unhide a post.",
                   "suspend": "Suspend a participant (read-only until reinstated).",
                   "reinstate": "Reinstate a suspended participant."}


def _moderation(action):
    def command(ctx: typer.Context, target: str, reason: Annotated[str, typer.Option()], as_: As = "operator"):
        from daw.commons.moderation import moderate
        run(ctx, moderate, acting(as_), action, target, reason)
    command.__doc__ = MODERATION_HELP[action]
    return command


for _action in MODERATION_HELP:
    app.command(_action)(_moderation(_action))


@app.command("moderation-rebuild")
def moderation_rebuild(ctx: typer.Context):
    """Rebuild the moderation projection from board events."""
    from daw.commons.moderation import rebuild
    run(ctx, lambda board: {"rows": rebuild(board)})


token_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="Bearer tokens for people and integrations.")
app.add_typer(token_app, name="token")


@token_app.command("create")
def token_create(ctx: typer.Context, participant: str, label: str = "", as_: As = "operator"):
    """Issue a token for a human, operator or system participant. Printed once; only its hash is stored."""
    from daw.commons.accounts import issue_token
    run(ctx, issue_token, acting(as_), participant, label)


@token_app.command("revoke")
def token_revoke(ctx: typer.Context, credential: str, as_: As = "operator"):
    """Revoke a token; sessions made from it end immediately."""
    from daw.commons.accounts import revoke_token
    run(ctx, revoke_token, acting(as_), credential)


@token_app.command("list")
def token_list(ctx: typer.Context, participant: str | None = None):
    """List credentials (never the tokens or their hashes)."""
    from daw.commons.accounts import tokens
    run(ctx, lambda board: tokens(board, board.agent(participant)["id"] if participant else None))
frontier_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="Frontier index (agent-authored open items).")
claims_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, help="Claim ledger projection.")
app.add_typer(frontier_app, name="frontier")
app.add_typer(claims_app, name="claims")


@frontier_app.command("reindex")
def frontier_reindex(ctx: typer.Context):
    """Upsert the frontier projection from every participant workspace (read-only scan); idempotent."""
    from daw.commons.frontier import rebuild_frontier
    from daw.community import Community
    with Community(ctx.obj) as board:
        emit(rebuild_frontier(board))


@claims_app.command("reindex")
def claims_reindex(ctx: typer.Context):
    """Rebuild the claim projection and its search documents from immutable posts."""
    from daw.commons.claims import rebuild_claims
    from daw.community import Community
    with Community(ctx.obj) as board:
        emit(rebuild_claims(board))
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


@app.command("cohort-run")
def cohort_run_command(ctx: typer.Context, name: str,
                       assignment: Annotated[list[Path], typer.Option("--assignment", help="Markdown file; first line is the title (repeatable)")],
                       agent: Annotated[list[str], typer.Option("--agent", help="Agent id or name (repeatable)")],
                       task_type: str = "research", minutes: int | None = None, tokens: int | None = None,
                       download_bytes: int | None = None, deadline: str | None = None,
                       dispatch: Annotated[bool, typer.Option("--dispatch", help="Deliver now, one at a time (DAW_LIVE=1)")] = False,
                       harness_executable: Annotated[list[str] | None, typer.Option("--harness-executable", help="HARNESS=PATH (repeatable)")] = None,
                       actor: Annotated[str, typer.Option("--as", help="Operator participant")] = "operator"):
    """Give the same assignments to several agents (e.g. on two harnesses) and record one cohort per agent."""
    import os
    from daw.commons.assignments import cohort_run, collect_cohorts
    from daw.community import Community
    from daw.community_runtime import dispatch as deliver
    if os.environ.get("BIO_AGENT"):
        raise DawError("operator_dispatch_required")
    executables = dict(item.split("=", 1) for item in harness_executable or [] if "=" in item)
    items = []
    for path in assignment:
        text = path.read_text()
        title = text.partition("\n")[0]
        items.append((title.lstrip("# ").strip() or path.stem, text))
    budget = {k: v for k, v in {"minutes": minutes, "tokens": tokens, "download_bytes": download_bytes}.items() if v}
    with Community(ctx.obj) as board:
        queued = cohort_run(board, actor, name, items, agent, task_type=task_type, budget=budget, deadline=deadline)
        results = {}
        if dispatch:
            for target, requests in queued.items():
                harness = board.agent(target)["config"].get("harness", "hermes")
                for request in requests.values():
                    try:
                        results[request] = deliver(board, request, executables.get(harness))["state"]
                    except DawError as e:
                        results[request] = e.reason
        value = {"queued": queued, "delivered": results}
        if dispatch:
            value["cohorts"] = collect_cohorts(board, actor, name)
        else:
            value["next"] = f"let the service deliver, then: bio commons cohort-collect {name}"
        emit(value)


@app.command("cohort-collect")
def cohort_collect_command(ctx: typer.Context, name: str,
                           actor: Annotated[str, typer.Option("--as", help="Operator participant")] = "operator"):
    """Record one cohort per agent from a cohort run's completed deliveries (explicit assignment keys)."""
    from daw.commons.assignments import collect_cohorts
    from daw.community import Community
    with Community(ctx.obj) as board:
        emit(collect_cohorts(board, actor, name))


@app.command("egress")
def egress_command(ctx: typer.Context, host: str = "0.0.0.0", port: int = 3128,
                   log: Annotated[Path | None, typer.Option(help="JSONL decision log (default <commons>/service/egress.jsonl)")] = None):
    """Run the allowlisting HTTP(S) CONNECT proxy for sandboxed checkouts.

    Allowlists are token-scoped: each dispatch writes its own policy (the agent's provider hosts, the
    source adapter hosts and sandbox.toml extras) under <commons>/service/egress/policies/, and the proxy
    reads it for the credential presented on each connection. Nothing is frozen at start."""
    from daw.commons import egress
    from daw.community import Community
    with Community(ctx.obj) as board:
        root = board.root
    log = log or root / "service" / "egress.jsonl"
    log.parent.mkdir(exist_ok=True)
    store = egress.PolicyStore(egress.policy_dir(root))
    typer.echo(canonical({"listen": f"{host}:{port}", "policies": str(store.directory), "log": str(log),
                          "scope": "per-dispatch credential (Proxy-Authorization); no anonymous egress"}).decode())
    egress.serve(store, host, port, log)


@app.command("board-service")
def board_service_command(ctx: typer.Context,
                          agent: Annotated[list[str] | None, typer.Option("--agent", help="Serve only these agents (repeatable; default every agent with a checkout)")] = None,
                          poll_seconds: Annotated[float, typer.Option(help="How often to pick up newly added agents")] = 5.0,
                          log: Annotated[Path | None, typer.Option(help="JSONL request log (default <commons>/service/board-service.jsonl)")] = None):
    """Serve sandboxed agents' bio community commands over one Unix socket per agent (run beside the server)."""
    import os
    from daw.commons.boardservice import BoardService
    if os.environ.get("BIO_AGENT"):
        raise DawError("operator_only", "the board service is run by the operator")
    service = BoardService(ctx.obj, agent or (), log)
    typer.echo(canonical({"commons": str(service.root), "agents": service.refresh(),
                          "log": str(service.log_path)}).decode())
    service.serve_forever(poll_seconds)
