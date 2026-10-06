"""Generic MCP-tool harness: an operator-configured command that speaks a documented JSONL stream.

The agent's bio tools reach the harness as the stdio MCP server `bio mcp serve`
(staged as `<home>/mcp.json`). The operator configures the launch line in the
agent's `harness_options`:

    {"executable": "my-agent",                      # default executable (dispatch may override)
     "args": ["--model", "{model}", "--mcp-config", "{mcp_config}", "--cwd", "{trial}"],
     "resume_args": ["--resume", "{session}"],      # optional; without it every delivery starts fresh
     "provider_hosts": ["api.example.org"]}         # optional model host for the sandbox egress proxy

Placeholders: {model} {effort} {provider} {trial} {home} {mcp_config} and, in
resume_args only, {session}. The prompt arrives on stdin. Each argument is one
argv item; nothing passes through a shell.

Stream format `bio-harness-jsonl/1` (stdout, one JSON object per line):

    {"type": "session", "id": "..."}                                   native conversation identity
    {"type": "tool_call", "id": "c1", "name": "...", "input": {...}}
    {"type": "tool_result", "id": "c1", "output": "...", "exit_code": 0, "is_error": false}
    {"type": "message", "text": "..."}                                 assistant text; the last one is the answer
    {"type": "turn_completed", "usage": {"input_tokens": 1, "cached_input_tokens": 0,
                                         "output_tokens": 1, "reasoning_output_tokens": null}}
    {"type": "error", "message": "..."}

Lines that are not JSON objects with a string `type` are malformed; other types are kept as events
and otherwise ignored. `exit_code` is recorded only when it is an integer. The harness's native state
is opaque to the platform: it is not snapshotted, and a resumed session is the harness's own claim.
"""
import json
import string
from pathlib import Path

from daw.harness.base import Adapter
from daw.util import DawError, digest, write_json

FORMAT = "bio-harness-jsonl/1"
PLACEHOLDERS = {"model", "effort", "provider", "trial", "home", "mcp_config"}
SHELL_TOOLS = {"terminal", "shell", "bash", "run_command"}
USAGE = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")


def _fields(template):
    return {field for _, field, _, _ in string.Formatter().parse(template) if field is not None}


def check_options(options):
    options = dict(options or {})
    unknown = set(options) - {"executable", "args", "resume_args", "provider_hosts"}
    if unknown:
        raise DawError("invalid_harness_options", f"unknown {', '.join(sorted(unknown))}")
    for key, allowed in (("args", PLACEHOLDERS), ("resume_args", PLACEHOLDERS | {"session"}),
                         ("provider_hosts", set())):
        value = options.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
            raise DawError("invalid_harness_options", f"{key} must be a list of non-empty strings")
        for item in value:
            try:
                extra = _fields(item) - allowed
            except ValueError as e:
                raise DawError("invalid_harness_options", f"{key}: {e}") from e
            if extra:
                raise DawError("invalid_harness_options", f"{key} placeholder {sorted(extra)} not allowed")
    if options.get("resume_args") and not any("{session}" in a for a in options["resume_args"]):
        raise DawError("invalid_harness_options", "resume_args must name {session}")
    return options


class McpAdapter(Adapter):
    name = "mcp"
    home_dir = ".mcp-home"
    default_executable = None

    def options(self, config):
        return check_options(config.get("harness_options"))

    def resumable(self, config):
        return bool(self.options(config).get("resume_args"))

    def hosts(self, config):
        return tuple(self.options(config).get("provider_hosts", []))

    def stage(self, trial, home, config):
        options = self.options(config)
        server = {"command": str(Path(trial) / "bin/bio"), "args": ["mcp", "serve"], "cwd": str(trial),
                  "env": {"BIO_CHECKOUT": str(trial)}}
        write_json(home / "mcp.json", {"mcpServers": {"bio": server}})
        return digest({"mcp": server, "options": options})

    def command(self, executable, trial, config, *, resume=None, fork=False):
        if fork:
            raise DawError("harness_fork_unsupported", "mcp")
        options = self.options(config)
        executable = executable or options.get("executable")
        if not executable:
            raise DawError("harness_command_unconfigured", "set harness_options.executable or pass the executable")
        values = {"model": config.get("model") or "", "effort": config.get("effort") or "",
                  "provider": config.get("provider") or "", "trial": str(trial), "home": str(self.home(trial)),
                  "mcp_config": str(self.home(trial) / "mcp.json")}
        argv = [executable, *(a.format(**values) for a in options.get("args", []))]
        if resume:
            argv += [a.format(**values, session=resume) for a in options["resume_args"]]
        return argv

    def environment(self, base, trial):
        env = super().environment(base, trial)
        env["BIO_CHECKOUT"] = str(trial)
        return env

    def session_exists(self, home, identity):
        # The harness's own store is opaque; resumption is the harness's claim, recorded in the stream.
        if not identity:
            raise DawError("saved_session_required")

    def parse(self, path):
        return parse(Path(path))


def parse(path):
    events, malformed, items, errors, sessions, turns = [], [], [], [], [], []
    calls = {}
    if path.exists():
        for line, raw in enumerate(path.read_bytes().splitlines(), 1):
            try:
                event = json.loads(raw)
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise ValueError("invalid event")
            except (ValueError, UnicodeDecodeError):
                malformed.append(line)
                continue
            events.append({"line": line, "event": event})
            kind = event["type"]
            if kind == "session" and isinstance(event.get("id"), str):
                sessions.append(event["id"])
            elif kind == "tool_call":
                native = str(event.get("name", "unknown"))
                tool_input = event.get("input") if isinstance(event.get("input"), dict) else {}
                shell = native in SHELL_TOOLS
                item = {"line": line, "type": "command_execution" if shell else native, "native_name": native,
                        "name": "terminal" if shell else native, "status": "in_progress", "exit_code": None,
                        "input": tool_input, "command": tool_input.get("command", "") if shell else ""}
                items.append(item)
                calls[event.get("id")] = item
            elif kind == "tool_result":
                item = calls.pop(event.get("id"), None)
                if item:
                    item.update(status="completed", aggregated_output=event.get("output", ""), result_line=line)
                    if type(event.get("exit_code")) is int:
                        item["exit_code"] = event["exit_code"]
                    elif event.get("is_error"):
                        item["exit_code"] = 1
            elif kind == "message":
                items.append({"line": line, "type": "agent_message", "text": event.get("text", "")})
            elif kind == "turn_completed":
                turns.append(event.get("usage"))
            elif kind == "error":
                errors.append({"line": line, "event": event})
    usage = None
    if turns:
        usage = {f: sum(u[f] for u in turns) if all(isinstance(u, dict) and type(u.get(f)) is int and u[f] >= 0
                                                     for u in turns) else None for f in USAGE}
    return {"events": events, "items": items, "malformed_lines": malformed, "turns_completed": len(turns),
            "errors": errors, "usage": usage, "thread_ids": sessions,
            "limitations": [f"Stream format {FORMAT}; tool calls and usage are whatever the configured harness reports."]}


ADAPTER = McpAdapter()
