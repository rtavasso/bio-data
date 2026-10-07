"""Operator assignments and cohort runs (M3.4, Milestone 5).

`assign` queues one typed request from an operator to an agent: an ordinary
post of kind "assignment" plus a request with a task type, budget and deadline.
The service delivers it (a person authorized it), even to an agent that has
never run. `cohort_run` gives the same assignments to several agents, typically
on different harnesses, and `collect_cohorts` records one cohort per agent from
the completed runs with explicit assignment keys, so the dashboard compares
them side by side (`bio commons cohort compare`). Nothing here chooses work.

An assignment launched from an agenda names its frontier item as evidence `source` ({kind: "frontier_item",
id}). The `task_assigned` event then carries that source, so the item reads scheduled with the request
(`promoted_to`) exactly as after a promotion, and shows the request's answer as candidate evidence once it
completes (daw.commons.frontier.board_state). Without it the planning board kept such items "unscheduled" and
the same work was dispatched again.
"""
import hashlib
import json
import uuid

from daw.commons import tasks
from daw.commons.permissions import require
from daw.util import DawError, canonical, now


def assign(board, actor, target, title, body, *, task_type="research", budget=None, deadline=None, evidence=None, key=None):
    """Queue one typed request. Idempotent with `key`. Caller must not hold the board or library lock."""
    participant = require(board, board.agent(actor), "dispatch")
    tasks.check_task_type(task_type)
    budget = tasks.normalize_budget(budget)
    deadline = tasks.check_deadline(deadline)
    agent = board.agent(target)
    if agent["kind"] != "agent":
        raise DawError("participant_cannot_receive_tasks", agent["kind"])
    board.trial(agent)
    if task_type == "replication":  # C6: never the original's producer (the runtime checks again at dispatch)
        from daw.commons.replication import refuse_producer
        refuse_producer(board, agent["id"], tasks.subject_of({"evidence": evidence or {}}))
    item = frontier_source(board, evidence)
    with board.writer(), board.library.writer():
        post = board._post(participant["id"], title, body, kind="assignment", request_key=key,
                           evidence={**(evidence or {}), "target": agent["id"], "task_type": task_type})
        existing = board.one("SELECT * FROM request WHERE post=?", (post,))
        if existing:
            return existing
        identity = "request_" + uuid.uuid4().hex
        with board.db:
            board.db.execute("INSERT INTO request(id,post,target,state,active_run,answer,created,updated,task_type,budget,"
                             "deadline) VALUES(?,?,?,'pending',NULL,NULL,?,?,?,?,?)",
                             (identity, post, agent["id"], now(), now(), task_type,
                              canonical(budget).decode() if budget else None, deadline))
            board.event("task_assigned", {"request": identity, "post": post, "target": agent["id"], "actor": participant["id"],
                                          "task_type": task_type, "budget": budget, "deadline": deadline,
                                          **({"source": {"kind": "frontier_item", "id": item}} if item else {})})
        if item:
            from daw.commons.frontier import reindex
            reindex(board, reason=f"task_assigned {identity}")
    return board.one("SELECT * FROM request WHERE id=?", (identity,))


def frontier_source(board, evidence):
    """The frontier item an assignment's evidence names as its `source`, checked to exist; None otherwise."""
    source = (evidence or {}).get("source") if isinstance(evidence, dict) else None
    if not isinstance(source, dict) or source.get("kind") != "frontier_item":
        return None
    identity = source.get("id")
    if not isinstance(identity, str) or not board.one("SELECT id FROM frontier_item WHERE id=?", (identity,)):
        raise DawError("unknown_frontier_item", f"{identity}: the assignment's source names no frontier item")
    return identity


def assignment_key(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def cohort_run(board, actor, name, assignments, agents, *, task_type="research", budget=None, deadline=None,
               source=None):
    """Queue each assignment (title, body) for each agent. Returns {agent: {assignment key: request}}.
    `source` (a frontier item id) links every request to the agenda item it was launched from."""
    if not assignments or not agents:
        raise DawError("empty_cohort_run", "at least one assignment and one agent")
    queued = {}
    for target in agents:
        agent = board.agent(target)
        for title, body in assignments:
            key = assignment_key(body)
            request = assign(board, actor, agent["id"], title, body, task_type=task_type, budget=budget, deadline=deadline,
                             evidence={"cohort_run": name, "assignment": key,
                                       **({"source": {"kind": "frontier_item", "id": source}} if source else {})},
                             key=f"cohort-run:{name}:{agent['id']}:{key}")
            queued.setdefault(agent["id"], {})[key] = request["id"]
    with board.writer(), board.db:
        board.event("cohort_run_queued", {"name": name, "actor": board.agent(actor)["id"], "requests": queued})
    return queued


def collect_cohorts(board, actor, name):
    """One cohort per agent of a cohort run, from its completed runs; assignment keys are explicit."""
    from daw.commons.metrics import create_cohort
    row = board.one("SELECT body FROM event WHERE kind='cohort_run_queued' AND json_extract(body,'$.name')=? "
                    "ORDER BY seq DESC LIMIT 1", (name,))
    if not row:
        raise DawError("unknown_cohort_run", name)
    created = {}
    for agent, requests in json.loads(row["body"])["requests"].items():
        runs = {}
        for key, request in requests.items():
            done = board.one("SELECT a.id FROM attempt a JOIN request r ON r.active_run=a.id "
                             "WHERE r.id=? AND r.state='completed'", (request,))
            if done:
                runs[done["id"]] = key
        if runs:
            label = f"{name}:{board.agent(agent)['name']}"
            created[agent] = create_cohort(board, actor, label, runs=list(runs), assignments=runs,
                                           note=f"cohort run {name}")["id"]
    if not created:
        raise DawError("cohort_run_incomplete", "no completed runs yet")
    return created
