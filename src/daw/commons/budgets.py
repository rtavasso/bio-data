"""Per-task budgets and clocks (M3.5).

A typed request's budget (`daw.commons.tasks.normalize_budget`) is applied by the
runtime around one delivery:

- minutes: the execution timeout. `agent_capture.execute` bounds both the
  monotonic and the wall clock, so host sleep cannot extend a task.
- tokens: harness telemetry is read from the parsed stream after the turn and
  reported. Stock harnesses cannot be stopped at a token count mid-turn, so the
  limit is checked, never enforced; an exceedance is a `token_budget_exceeded`
  board event and an operator notice. Missing telemetry is "unavailable", never 0.
- download_bytes: written to a platform-owned task budget file,
  `<checkout>/.colloquy/task-budget.json`, which the sandbox mounts read-only
  (spec v2 C7). The agent's own `workspace/config.toml` is never touched. The
  transport (`daw.catalog.Workspace`) caps `bundle_bytes` (per transport command)
  and `asset_bytes` (per file) at the task limit whenever the file is present,
  for every workspace under the checkout (v3 B5: `task_budget_files`), not only
  `<checkout>/workspace`; the task total is the agent's instruction. The runtime hashes the file before
  the turn and compares it afterwards: a changed or removed file is a
  `budget_policy_violation` board event plus an operator notice, never a note.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path

from daw.util import DawError, now

TOKEN_FIELDS = ("input_tokens", "output_tokens")


def execution_timeout(timeout, budget):
    """Seconds (0 = unlimited): the stricter of the operator's timeout and the task's minutes."""
    limits = [t for t in (timeout, (budget or {}).get("minutes", 0) * 60) if t]
    return min(limits, default=0)


def token_report(budget, usage):
    """Tokens used from harness telemetry. A turn that reports no (or all-zero) counts is unavailable, not zero."""
    limit = (budget or {}).get("tokens")
    values = [usage.get(f) for f in TOKEN_FIELDS] if isinstance(usage, dict) else []
    if not values or any(type(v) is not int for v in values) or not sum(values):
        used = "unavailable"
    else:
        used = sum(values)
    return {"limit": limit, "used": used, "counted": list(TOKEN_FIELDS),
            "exceeded": None if limit is None or used == "unavailable" else used > limit,
            "enforcement": "checked after the turn from harness telemetry; not enforced mid-turn"}


def _toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise DawError("unsupported_workspace_config", type(value).__name__)


def dump_toml(document, prefix=()):
    """A small TOML writer for workspace configs: tables of scalars and arrays."""
    lines = [f"{key} = {_toml_value(value)}" for key, value in document.items() if not isinstance(value, dict)]
    text = "\n".join(lines) + ("\n" if lines else "")
    for key, value in document.items():
        if isinstance(value, dict):
            name = ".".join((*prefix, key))
            text += f"\n[{name}]\n" + dump_toml(value, (*prefix, key))
    return text


TASK_BUDGET = Path(".colloquy") / "task-budget.json"
CAPS = ("bundle_bytes", "asset_bytes")


def task_budget_path(trial):
    return Path(trial) / TASK_BUDGET


def clear_task_budget(trial):
    """Remove a stale task budget left by an interrupted dispatch; keep the (empty) platform directory
    so the sandbox can mount it read-only. The caller holds the agent's session lock."""
    path = task_budget_path(trial)
    if path.parent.is_symlink():
        path.parent.unlink()
    path.parent.mkdir(exist_ok=True)
    if path.is_symlink() or path.exists():
        with contextlib.suppress(OSError):
            path.chmod(0o600)
        path.unlink()


@contextlib.contextmanager
def download_budget(trial, budget, receipt, keep=None, *, run=None):
    """Write the task's download budget to the platform-owned file for the duration of the block.

    `receipt` (a dict) records the limit and the file's hash and, afterwards, whether the file the agent
    could reach was changed or removed (`policy_violation`; the caller records the board event and the
    operator notice). Changed bytes are kept at `keep` for audit. The file is removed afterwards.
    The caller holds the agent's session lock."""
    limit = (budget or {}).get("download_bytes")
    receipt["download_bytes"] = None
    clear_task_budget(trial)
    if not limit:
        yield receipt
        return
    path = task_budget_path(trial)
    document = {"format": 1, "run": run, "download_bytes": limit, "caps": {k: limit for k in CAPS}, "issued": now(),
                "note": "Platform-owned task budget, read-only in the sandbox; the transport applies these caps."}
    data = json.dumps(document, indent=1, sort_keys=True).encode() + b"\n"
    path.write_bytes(data)
    path.chmod(0o444)
    receipt["download_bytes"] = {"limit": limit, "applied": dict(document["caps"]), "file": str(TASK_BUDGET),
                                 "sha256": hashlib.sha256(data).hexdigest(), "applied_at": now(),
                                 "workspace_config_touched": False,
                                 "enforcement": "per transport command and per file, read by the transport from the "
                                                "platform-owned task budget file; the task total is instructed"}
    try:
        yield receipt
    finally:
        observed = None if path.is_symlink() or not path.is_file() else path.read_bytes()
        changed = observed != data
        if changed and keep and observed is not None:
            Path(keep).write_bytes(observed)
        if path.is_symlink() or path.exists():
            with contextlib.suppress(OSError):
                path.chmod(0o600)
            with contextlib.suppress(OSError):
                path.unlink()
        receipt["download_bytes"].update(
            removed_at=now(), policy_violation=changed,
            observed="removed" if observed is None else ("changed" if changed else "unchanged"),
            observed_sha256=hashlib.sha256(observed).hexdigest() if observed is not None else None)


def task_budget_files(workspace_root, env=None):
    """Task budget files that govern a workspace (v3 B5): the one in every directory above it, so a second
    workspace anywhere inside an agent checkout (`bio init sub/ws`) is under the checkout's budget, and the
    running agent's own checkout (BIO_AGENT's home, the directory holding the BIO_WORKSPACE the runtime set)."""
    env = os.environ if env is None else env
    roots = list(Path(workspace_root).expanduser().resolve().parents)
    if env.get("BIO_AGENT") and env.get("BIO_WORKSPACE"):
        roots.append(Path(env["BIO_WORKSPACE"]).expanduser().resolve().parent)
    return [path for path in dict.fromkeys(root / TASK_BUDGET for root in roots) if path.is_file()]


def read_task_budget(workspace_root, env=None):
    """Caps from the platform-owned task budgets governing a workspace (the stricter wins per cap), or None.

    The agent's workspace is `<checkout>/workspace`; the file is `<checkout>/.colloquy/task-budget.json`.
    A malformed file fails closed: the transport refuses rather than running without the cap."""
    found = None
    for path in task_budget_files(workspace_root, env):
        try:
            caps = json.loads(path.read_text())["caps"]
            caps = {k: caps[k] for k in CAPS}
        except (ValueError, KeyError, TypeError) as e:
            raise DawError("task_budget_invalid", str(path)) from e
        if any(type(v) is not int or v <= 0 for v in caps.values()):
            raise DawError("task_budget_invalid", str(path))
        found = caps if found is None else {k: min(found[k], caps[k]) for k in CAPS}
    return found


def apply_task_caps(budgets, workspace_root):
    """A workspace's transport budgets with the current task's caps applied (the stricter wins; 0 = unlimited)."""
    caps = read_task_budget(workspace_root)
    if not caps:
        return budgets
    current = {k: getattr(budgets, k) for k in caps}
    return budgets.model_copy(update={k: min(current[k], cap) if current[k] else cap for k, cap in caps.items()})
