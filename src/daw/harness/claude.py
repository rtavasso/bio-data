"""Claude Code CLI adapter: `claude -p --output-format stream-json --verbose`.

The harness home is CLAUDE_CONFIG_DIR inside the checkout. A staged user
settings file (the only setting source loaded) restricts file tools to the
checkout, denies edits to platform code and to the home itself, disables
permission prompts (`dontAsk`: anything not allowed is refused) and keeps
session transcripts from age-based cleanup. Stock Claude Code still runs its
own loop; the Bash tool is not path-confined, which is why multi-tenant
deployments run checkouts in the M3.6 container sandbox.
"""
import json
import re
import shutil
from pathlib import Path

from daw.harness.base import Adapter
from daw.hermes import safe_files
from daw.util import DawError, digest, file_hash, write_json

EFFORTS = ("low", "medium", "high", "xhigh", "max")
TOOLS = ("Bash", "Read", "Edit", "Write", "Glob", "Grep")
PUBLIC_TOOLS = ("WebFetch", "WebSearch")
NAMES = {"Bash": ("terminal", "command_execution"), "Write": ("write_file", "write_file"),
         "Read": ("read_file", "read_file"), "Edit": ("patch", "patch")}


def project_slug(cwd):
    """Claude Code files sessions under projects/<cwd with every non-alphanumeric character as '-'>."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def settings(trial, public):
    trial = Path(trial)
    root = "//" + str(trial).lstrip("/")
    protected = [f"{root}/{name}/**" for name in (".claude-home", "src", ".agents", "bin")]
    return {"permissions": {"defaultMode": "dontAsk",
                            "allow": ["Bash", f"Read({root}/**)", f"Edit({root}/**)", f"Write({root}/**)", "Glob", "Grep",
                                      *(PUBLIC_TOOLS if public else ())],
                            "deny": [f"{verb}({path})" for path in protected for verb in ("Edit", "Write")]},
            # Research conversations are resumed months later; never age them out.
            "cleanupPeriodDays": 36500, "includeCoAuthoredBy": False, "autoUpdates": False}


class ClaudeAdapter(Adapter):
    name = "claude"
    home_dir = ".claude-home"
    default_executable = "claude"
    default_model = "opus"
    default_provider = "anthropic"
    provider_hosts = ("api.anthropic.com", "statsig.anthropic.com")
    auth = ("BIO_CLAUDE_AUTH_FILE", ".credentials.json")
    state_globs = ("projects/*/*.jsonl",)
    supports_fork = True
    config_files = ("settings.json", "CLAUDE.md")

    def stage(self, trial, home, config):
        trial = Path(trial)
        write_json(home / "settings.json", settings(trial, config["public"]))
        (home / "CLAUDE.md").write_text(
            "Follow AGENTS.md in your working directory, the research checkout. Research skills are under "
            ".agents/skills/<name>/SKILL.md and are also listed as your skills. Use ./bin/bio and ./bin/python.\n")
        skills = trial / ".agents/skills"
        if skills.is_dir():
            shutil.copytree(skills, home / "skills", dirs_exist_ok=True)
        staged = [p for p in safe_files(home) if not p.is_relative_to(home / "projects")]
        return digest({str(p.relative_to(home)): file_hash(p) for p in staged})

    def command(self, executable, trial, config, *, resume=None, fork=False):
        home = self.home(trial)
        argv = [executable, "-p", "--output-format", "stream-json", "--verbose", "--model", config["model"]]
        if config.get("effort") in EFFORTS:
            argv += ["--effort", config["effort"]]
        argv += ["--permission-mode", "dontAsk", "--settings", str(home / "settings.json"), "--setting-sources", "user",
                 "--strict-mcp-config", "--tools", ",".join(TOOLS + (PUBLIC_TOOLS if config["public"] else ()))]
        if resume:
            argv += ["--resume", resume]
            if fork:
                argv.append("--fork-session")
        elif fork:
            raise DawError("saved_session_required")
        return argv

    def environment(self, base, trial):
        env = super().environment(base, trial)
        env.update(CLAUDE_CONFIG_DIR=str(self.home(trial)), DISABLE_AUTOUPDATER="1",
                   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
        return env

    def restored_path(self, relative, trial):
        # Sessions are filed by working directory; a restored conversation moves to this checkout.
        return Path("projects", project_slug(trial), relative.name)

    def session_exists(self, home, identity):
        if not identity:
            raise DawError("saved_session_required")
        if not any(p.name == identity + ".jsonl" for p in self.state_files(home)):
            raise DawError("unknown_saved_session", identity)

    def parse(self, path):
        return parse(Path(path))


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def parse(path):
    """Claude Code stream-json: system init, assistant tool_use, user tool_result, result with usage."""
    events, malformed, items, results, sessions = [], [], [], [], []
    pending = {}
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
            if kind == "system" and event.get("subtype") == "init" and event.get("session_id"):
                sessions.append(event["session_id"])
            elif kind == "assistant":
                for block in (event.get("message") or {}).get("content") or []:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    native = block.get("name", "unknown")
                    name, item_type = NAMES.get(native, (native, native))
                    given = block.get("input") if isinstance(block.get("input"), dict) else {}
                    tool_input = {**({"path": given["file_path"]} if "file_path" in given else {}), **given}
                    item = {"line": line, "type": item_type, "name": name, "native_name": native, "status": "in_progress",
                            "exit_code": None, "input": tool_input, "command": tool_input.get("command", "")}
                    items.append(item)
                    pending[block.get("id")] = item
            elif kind == "user":
                for block in (event.get("message") or {}).get("content") or []:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    item = pending.pop(block.get("tool_use_id"), None)
                    if item:
                        # Claude Code reports is_error, not shell exit codes: success stays unknown.
                        item.update(status="completed", aggregated_output=_text(block.get("content")), result_line=line)
                        if block.get("is_error"):
                            item["exit_code"] = 1
            elif kind == "result":
                results.append({"line": line, "event": event})
                if event.get("session_id"):
                    sessions.append(event["session_id"])
                items.append({"line": line, "type": "agent_message", "text": event.get("result") or ""})
    ok = [r for r in results if r["event"].get("subtype") == "success" and not r["event"].get("is_error")]
    usage = None
    if results:
        values = [r["event"].get("usage") for r in results]

        def total(required, *optional):
            """Sum over turns; unavailable (None) unless every turn reports the field as an integer."""
            if not all(isinstance(u, dict) and all(type(u.get(f, 0)) is int for f in optional)
                       and type(u.get(required)) is int for u in values):
                return None
            return sum(u[required] + sum(u.get(f, 0) for f in optional) for u in values)
        usage = {"input_tokens": total("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"),
                 "cached_input_tokens": total("cache_read_input_tokens"), "output_tokens": total("output_tokens"),
                 "reasoning_output_tokens": None}
    return {"events": events, "items": items, "malformed_lines": malformed, "turns_completed": len(ok),
            "errors": [r for r in results if r not in ok], "usage": usage,
            "thread_ids": sessions,
            "limitations": ["Claude Code reports tool errors, not shell exit codes; a successful command's exit code is unknown.",
                            "input_tokens include cache creation and cache reads; cached_input_tokens are cache reads."]}


ADAPTER = ClaudeAdapter()
