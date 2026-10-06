"""Deliver forum mail and person-authorized tasks with stock harnesses. No research planning or retry loop."""
import os
import signal
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from daw.commons.tasks import NOTICE, deadline_passed
from daw.community import Community, exclusive
from daw.community_runtime import STALL_MINUTES, expire
from daw.util import DawError, now, write_json

PEOPLE = ("human", "operator")


def pending_deliveries(board, agents=()):
    """Requests the service may launch now. Only people or peers create them; no scheduler chooses work.

    - peer questions and answer notifications, to started sessions (operator briefs wait for explicit launch);
    - a person's comment that asks its target's author (post kind "comment" by a human), to started sessions;
    - promoted or commissioned requests (a task type other than "notice", created by a human or operator),
      even to an agent that has never run: a person authorized that work. Overdue ones are never launched.
    Notices are read in the inbox and never delivered as a model turn.
    """
    allowed = {board.agent(a)["id"] for a in agents}
    busy = {r["target"] for r in board.rows("SELECT target FROM request WHERE state='running'")}
    selected = []
    for request in board.rows("SELECT r.*,p.author,a.kind AS author_kind FROM request r JOIN post p ON p.id=r.post "
                              "JOIN agent a ON a.id=p.author WHERE r.state='pending' ORDER BY r.created,r.id"):
        target = request["target"]
        if target in busy or (allowed and target not in allowed):
            continue
        agent = board.agent(target)
        if agent["kind"] != "agent" or not agent["trial"] or request["task_type"] == NOTICE:
            continue
        if request["task_type"]:
            if request["author_kind"] not in PEOPLE or deadline_passed(request["deadline"]):
                continue
        else:
            # Creating ten briefs is not authorization to start ten investigations.
            if not agent["native_session"]:
                continue
            kind = board.show(request["post"])["content"]["kind"]
            peer = kind == "question" and request["author"] != "operator"
            comment = kind == "comment" and request["author_kind"] == "human"
            if kind != "answer_notification" and not peer and not comment:
                continue
        selected.append(request)
        busy.add(target)
    return selected


def expire_overdue(board):
    """Fail typed requests whose deadline passed before launch (event deadline_passed); returns their ids."""
    expired = []
    with board.writer():
        for request in board.rows("SELECT * FROM request WHERE state='pending' AND task_type IS NOT NULL "
                                  "AND task_type!=? AND deadline IS NOT NULL", (NOTICE,)):
            if deadline_passed(request["deadline"]):
                expire(board, request)
                expired.append(request["id"])
    return expired


def serve(root, executable="hermes", *, agents=(), concurrency=0, poll_seconds=2, timeout=0,
          refresh_tools=False, once=False, stop=None, executables=None, stall_minutes=STALL_MINUTES, stall_timeout=0,
          allow_unsandboxed=None):
    """One durable queue worker per idle session; failures require explicit retry.

    Worker processes outlive service restarts. Their inherited session locks and
    request state prevent duplicate delivery, including alongside manual runs.
    SIGTERM stops taking new mail and leaves already dispatched turns running.
    `executable` launches Hermes agents; `executables` maps other harness names to their executables.
    """
    if os.environ.get("BIO_AGENT"):
        raise DawError("operator_dispatch_required")
    if os.environ.get("DAW_LIVE") != "1":
        raise DawError("live_opt_in_required")
    executables = dict(executables or {})
    if concurrency < 0 or poll_seconds <= 0 or timeout < 0 or stall_minutes < 0 or stall_timeout < 0:
        raise DawError("invalid_service_limits")
    stop = stop or threading.Event()
    folder = Path(root).expanduser().resolve() / "service"
    folder.mkdir(exist_ok=True)
    children = {}
    previous_handlers = {}
    with Community(root) as board, exclusive(board.root / ".service.lock"):
        # Validate the scope before starting or queuing anything.
        scope = [board.agent(a)["id"] for a in agents]
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous_handlers[sig] = signal.signal(sig, lambda *_: stop.set())
        service_id = "service_" + uuid.uuid4().hex
        with board.writer(), board.db:
            board.event("service_started", {"id": service_id, "pid": os.getpid(), "agents": scope,
                        "concurrency": concurrency, "refresh_tools": refresh_tools})

        def status(state):
            value = {"id": service_id, "pid": os.getpid(), "state": state, "observed": now(),
                     "agents": scope, "concurrency": concurrency, "poll_seconds": poll_seconds,
                     "children": [{"request": rid, "pid": p.pid, "target": target}
                                  for rid, (p, target) in children.items()],
                     "pending": len(board.rows("SELECT id FROM request WHERE state='pending'")),
                     "policy": "peer questions, answer notifications and human comments for started sessions; "
                               "promoted/commissioned tasks before their deadline; never notices; no automatic retries"}
            write_json(folder / "status.json", value)
            return value

        try:
            while not stop.is_set():
                for rid, (process, _) in list(children.items()):
                    if process.poll() is not None:
                        with board.writer(), board.db:
                            board.event("service_worker_exited", {"request": rid, "pid": process.pid,
                                        "returncode": process.returncode})
                        del children[rid]
                board.queue_answer_notifications(scope)
                expire_overdue(board)
                active = {r["target"] for r in board.rows("SELECT target FROM request WHERE state='running'")}
                active.update(target for _, target in children.values())
                for request in pending_deliveries(board, scope):
                    if request["target"] in active or (concurrency and len(active) >= concurrency):
                        continue
                    # Launch the regular CLI, not a second agent implementation.
                    argv = [sys.executable, "-m", "daw.bio_cli", "community", "--root", str(board.root),
                            "run", request["id"], "--hermes", executable, "--timeout", str(timeout)]
                    harness = board.agent(request["target"])["config"].get("harness", "hermes")
                    if harness in executables:
                        argv += ["--executable", executables[harness]]
                    if stall_minutes != STALL_MINUTES or stall_timeout:
                        argv += ["--stall-minutes", str(stall_minutes), "--stall-timeout", str(stall_timeout)]
                    if allow_unsandboxed:
                        argv += ["--allow-unsandboxed", allow_unsandboxed]
                    if refresh_tools:
                        argv.append("--refresh-tools")
                    log = folder / (request["id"] + ".log")
                    with log.open("ab") as stream:
                        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
                                                   start_new_session=True)
                    children[request["id"]] = (process, request["target"])
                    active.add(request["target"])
                    with board.writer(), board.db:
                        board.event("service_worker_started", {"request": request["id"], "pid": process.pid,
                                    "target": request["target"], "log": str(log.relative_to(board.root))})
                value = status("running")
                if once:
                    return value
                stop.wait(poll_seconds)
        finally:
            status("stopped")
            with board.writer(), board.db:
                board.event("service_stopped", {"id": service_id, "workers_continue": list(children)})
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
