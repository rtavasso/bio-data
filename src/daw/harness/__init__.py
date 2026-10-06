"""Stock agent harness adapters (M3.3).

One interface for every harness a commons can dispatch to. An adapter stages a
harness home inside the agent's checkout, builds the stock CLI's argv, parses
its raw stream into the shape `daw.hermes.parse` returns, and snapshots
allowlisted session state. Adapters never add a research loop: the harness's
own agent loop does the work, and the bio CLI and skills staged by
`agent_setup.copy_research_tools` are identical for every harness.

    prepare(trial, config, checkpoint=None) -> runtime receipt
    command(executable, trial, config, *, resume=None, fork=False) -> argv
    environment(base, trial) -> env
    parse(stream_path) -> {events, items, malformed_lines, turns_completed, errors, usage, thread_ids, limitations}
    snapshot(home, destination) -> {relative path: sha256}
    session_exists(home, identity)          raises DawError when a saved session is missing
    native_session(executable, home, identity, cwd, *, fork=False) -> {"session", "fork_on_launch", ...}

Parsed items are normalized so behavioural metrics compare across harnesses:
shell calls are `{"name": "terminal", "type": "command_execution", "command"}`,
file writes are `{"name": "write_file", "input": {"path"}}`, and final answers
are `{"type": "agent_message", "text"}`. `native_name` keeps the harness's own
tool name. Exit codes are recorded only when the harness reports them.
"""
from daw.util import DawError

NAMES = ("hermes", "codex", "claude", "mcp", "scripted")
DEFAULT = "hermes"


def get(name):
    """The adapter for a harness name; agents created before harnesses existed are Hermes."""
    name = name or DEFAULT
    if name == "hermes":
        from daw.harness.hermes import ADAPTER
    elif name == "codex":
        from daw.harness.codex import ADAPTER
    elif name == "claude":
        from daw.harness.claude import ADAPTER
    elif name == "mcp":
        from daw.harness.mcp import ADAPTER
    elif name == "scripted":
        from daw.harness.scripted import ADAPTER
    else:
        raise DawError("unknown_harness", f"use one of {', '.join(NAMES)}")
    return ADAPTER


def for_agent(agent):
    return get(agent["config"].get("harness", DEFAULT))
