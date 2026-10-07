"""Codex CLI adapter. `codex_command` is the evaluator's launch line (moved from benchmarks/agent/runner.py).

The evaluator runs Codex ephemerally with the operator's own Codex home and
`--ignore-user-config`. Community agents keep their conversation in a private
CODEX_HOME inside the checkout so `codex exec resume` can continue it; Codex has
no native branch, so conversation forks are refused (workspace forks work).
The JSONL stream is parsed by `daw.agent_capture.parse_events`.
"""
import json
from pathlib import Path

from daw.agent_capture import parse_events
from daw.harness.base import Adapter
from daw.util import DawError, digest

DEFAULT_MODEL = "gpt-6-astra"
DEFAULT_REASONING_EFFORT = "xhigh"


def codex_command(executable, cwd, output, *, model=DEFAULT_MODEL, reasoning_effort=DEFAULT_REASONING_EFFORT,
                  public=False, schema=None, readonly=False, ephemeral=True, resume=None):
    argv = [executable, "--no-daemon", "--ask-for-approval", "never", "exec", "--json"]
    if ephemeral:
        argv.append("--ephemeral")
    argv += ["--ignore-user-config", "--sandbox", "read-only" if readonly else "workspace-write", "--skip-git-repo-check",
             "--color", "never", "--cd", str(cwd)]
    if output:
        argv += ["--output-last-message", str(output)]
    argv += ["-c", 'web_search="live"' if public else 'web_search="disabled"',
             "-c", "sandbox_workspace_write.network_access=" + ("true" if public else "false")]
    if model:
        argv += ["--model", model]
    if reasoning_effort:
        argv += ["-c", "model_reasoning_effort=" + json.dumps(reasoning_effort)]
    if schema:
        argv += ["--output-schema", str(schema)]
    if resume:
        argv += ["resume", resume]
    return argv + ["-"]


def normalize(parsed):
    """Name Codex items like the Hermes adapter so behavioural metrics compare across harnesses."""
    items = []
    for item in parsed["items"]:
        kind = item.get("type")
        if kind == "command_execution":
            items.append({**item, "name": "terminal", "native_name": kind, "command": item.get("command", ""),
                          "input": {"command": item.get("command", "")}})
        elif kind == "file_change":
            changes = [c for c in item.get("changes") or [] if isinstance(c, dict)] or [{}]
            items += [{**item, "name": "write_file", "native_name": kind, "input": {"path": c.get("path", "")}}
                      for c in changes]
        elif kind == "agent_message":
            items.append({**item, "text": item.get("text", "")})
        else:
            items.append({**item, "name": kind or "unknown", "native_name": kind})
    return {**parsed, "items": items,
            "limitations": ["Codex reports per-turn usage on turn.completed; reasoning tokens only when the provider does.",
                            "Command exit codes are Codex's own; file changes are reported as patches, not file bytes."]}


class CodexAdapter(Adapter):
    name = "codex"
    home_dir = ".codex"
    default_executable = "codex"
    default_model = DEFAULT_MODEL
    default_provider = "openai"
    provider_hosts = ("api.openai.com", "chatgpt.com", "auth.openai.com")
    auth = ("BIO_CODEX_AUTH_FILE", "auth.json")
    state_globs = ("sessions/**/*.jsonl",)
    # Codex reads config.toml from CODEX_HOME; none is staged (settings travel as -c flags), so the sealed
    # copy is an empty file: an agent-written config.toml cannot change the next turn.
    config_files = ("config.toml",)

    def stage(self, trial, home, config):
        (home / "sessions").mkdir(exist_ok=True)
        return digest({"model": config["model"], "effort": config["effort"], "public": config["public"]})

    def command(self, executable, trial, config, *, resume=None, fork=False):
        if fork:
            raise DawError("harness_fork_unsupported", "codex")
        return codex_command(executable, trial, None, model=config["model"], reasoning_effort=config["effort"],
                             public=config["public"], ephemeral=False, resume=resume)

    def environment(self, base, trial):
        env = super().environment(base, trial)
        env["CODEX_HOME"] = str(self.home(trial))
        return env

    def session_exists(self, home, identity):
        if not identity:
            raise DawError("saved_session_required")
        if not any(p.name.endswith(identity + ".jsonl") for p in self.state_files(home)):
            raise DawError("unknown_saved_session", identity)

    def parse(self, path):
        return normalize(parse_events(Path(path)))


ADAPTER = CodexAdapter()
