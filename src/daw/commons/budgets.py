"""Per-task budgets and clocks (M3.5).

A typed request's budget (`daw.commons.tasks.normalize_budget`) is applied by the
runtime around one delivery:

- minutes: the execution timeout. `agent_capture.execute` bounds both the
  monotonic and the wall clock, so host sleep cannot extend a task.
- tokens: harness telemetry is read from the parsed stream after the turn and
  reported. Stock harnesses cannot be stopped at a token count mid-turn, so the
  limit is checked, never enforced. Missing telemetry is "unavailable", never 0.
- download_bytes: written into the checkout's workspace transport budget
  (`bundle_bytes` per transport command and `asset_bytes` per file) for the
  duration of the task, then the original config bytes are restored. The
  transport enforces per command; the task total is the agent's instruction.
"""
import contextlib
import hashlib
import tomllib
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


@contextlib.contextmanager
def download_budget(workspace, budget, receipt, keep=None):
    """Apply a task's download budget to a workspace config for the duration of the block; always restore.

    `receipt` (a dict) records the original and applied values and the restoration. If the config
    changed during the task, the changed bytes are kept at `keep` for audit before the original returns.
    The caller holds the agent's session lock, so no other delivery reads the temporary config.
    """
    limit = (budget or {}).get("download_bytes")
    receipt["download_bytes"] = None
    if not limit:
        yield receipt
        return
    path = Path(workspace) / "config.toml"
    original = path.read_bytes()
    document = tomllib.loads(original.decode())
    budgets = dict(document.get("budgets", {}))
    previous = {k: budgets.get(k, 0) for k in ("bundle_bytes", "asset_bytes")}
    budgets.update({k: min(v, limit) if v else limit for k, v in previous.items()})
    temporary = dump_toml({**document, "budgets": budgets}).encode()
    path.write_bytes(temporary)
    receipt["download_bytes"] = {"limit": limit, "previous": previous, "applied": {k: budgets[k] for k in previous},
                                 "applied_at": now(), "config_sha256": hashlib.sha256(original).hexdigest(),
                                 "enforcement": "per transport command and per file; the task total is instructed"}
    try:
        yield receipt
    finally:
        current = path.read_bytes()
        if current != temporary and keep:
            Path(keep).write_bytes(current)
        path.write_bytes(original)
        receipt["download_bytes"].update(restored=path.read_bytes() == original, restored_at=now(),
                                         changed_during_task=current != temporary)
