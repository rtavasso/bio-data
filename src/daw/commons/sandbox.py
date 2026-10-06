"""Container sandbox for agent checkouts (M3.6).

Configured per commons in `<commons>/sandbox.toml`:

    engine = "docker"                  # or "podman"
    image = "colloquy-agent:latest"    # built from deploy/agent.Dockerfile
    network = "colloquy-egress"        # an internal network whose only route out is the egress proxy;
                                       # omitted: --network none (no egress at all)
    proxy = "http://egress:3128"       # `bio commons egress` on that network
    allow_hosts = []                   # extra data hosts for the proxy (source adapter hosts are built in)
    model_hosts = []                   # extra model provider hosts (each harness adds its own)
    scratch_bytes = 2147483648         # size-limited tmpfs at /tmp
    memory = "8g"
    cpus = "4"
    pids_limit = 1024
    env = ["ANTHROPIC_API_KEY"]        # host variables the harness may receive (names only)
    ro_mounts = []                     # host paths mounted read-only at the same path (e.g. a harness install)
    mount_host_python = false          # mount this interpreter read-only when the image does not provide it

The checkout's harness runs with the trial mounted read-write at its own path,
its platform code (src, skills, bin and instructions) mounted read-only over it,
a size-limited tmpfs scratch, a read-only root filesystem, no capabilities,
and only explicitly named environment variables and credential files. Other
agents' checkouts, run transcripts and service state are hidden. Secrets reach
the container by name (`--env NAME`), never in argv.

Multi-tenant serving (`bio commons serve --mode accounts` records tenancy)
refuses live dispatch without a sandbox unless the operator overrides it with a
recorded reason. Limitation: agents still write the board database and library
through the bio CLI inside the container, so the board root is mounted
read-write; a board-writing agent is trusted not to bypass the CLI.
"""
import os
import sys
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from daw.commons.egress import SOURCE_HOSTS
from daw.util import DawError, now, read_json, write_json

ENGINES = ("docker", "podman")
PLATFORM_PATHS = ("src", ".agents", "bin", "AGENTS.md", "README.md", "pyproject.toml", "uv.lock", "contracts", "examples", "docs")
HIDDEN = ("agents", "runs", "service", "demo-harness")
# Environment the harness and bio CLI need inside the container; anything else stays on the host.
ENV_PREFIXES = ("BIO_", "HERMES_", "CLAUDE_", "CODEX_")
ENV_NAMES = ("PYTHONPATH", "PYTHONUNBUFFERED", "TERMINAL_CWD", "DISABLE_AUTOUPDATER", "LANG", "LC_ALL", "TZ")
CLIENT_ENV = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT", "XDG_RUNTIME_DIR", "CONTAINER_HOST")


@dataclass(frozen=True)
class Config:
    engine: str = "docker"
    image: str = "colloquy-agent:latest"
    network: str | None = None
    proxy: str | None = None
    allow_hosts: tuple = ()
    model_hosts: tuple = ()
    scratch_bytes: int = 2 * 2**30
    memory: str | None = "8g"
    cpus: str | None = None
    pids_limit: int = 1024
    env: tuple = ()
    ro_mounts: tuple = ()
    mount_host_python: bool = False


def load(root):
    """The commons sandbox configuration, or None when the commons has none."""
    path = Path(root) / "sandbox.toml"
    if not path.is_file():
        return None
    raw = tomllib.loads(path.read_text())
    known = {f.name for f in fields(Config)}
    unknown = set(raw) - known
    if unknown:
        raise DawError("invalid_sandbox_config", f"unknown keys {', '.join(sorted(unknown))}")
    values = {k: tuple(v) if isinstance(v, list) else v for k, v in raw.items()}
    config = Config(**values)
    if config.engine not in ENGINES:
        raise DawError("invalid_sandbox_config", "engine is docker or podman")
    if not isinstance(config.scratch_bytes, int) or config.scratch_bytes <= 0 or config.pids_limit <= 0:
        raise DawError("invalid_sandbox_config", "scratch_bytes and pids_limit must be positive integers")
    if config.proxy and not config.network:
        raise DawError("invalid_sandbox_config", "a proxy needs the internal network it is reachable on")
    for path in config.ro_mounts:
        if not Path(path).is_absolute():
            raise DawError("invalid_sandbox_config", "ro_mounts are absolute host paths")
    return config


def record_tenancy(root, mode):
    """`commons serve` records multi-tenant serving; once accounts mode has served, it stays recorded."""
    path = Path(root) / "tenancy.json"
    if mode == "accounts" or not path.is_file():
        write_json(path, {"mode": mode, "recorded": now(),
                          "note": "accounts mode is sticky; delete this file only when the commons no longer serves accounts"})


def tenancy(root):
    path = Path(root) / "tenancy.json"
    return read_json(path).get("mode", "local") if path.is_file() else "local"


def policy(root, override=None):
    """Decide before any state changes whether this dispatch may run, and how."""
    config = load(root)
    mode = tenancy(root)
    if override is not None and not str(override).strip():
        raise DawError("override_reason_required", "say why this dispatch may run without a sandbox")
    if config is None and mode == "accounts" and override is None:
        raise DawError("sandbox_required", "multi-tenant commons: configure sandbox.toml or override with a reason")
    return {"config": config, "tenancy": mode, "override": override if config is None and override else None}


def hosts(config, harness_hosts=()):
    """The egress allowlist: source adapter hosts, configured extras, and the harnesses' model providers."""
    return sorted({*SOURCE_HOSTS, *(config.allow_hosts if config else ()), *(config.model_hosts if config else ()),
                   *harness_hosts})


def container_env(env, config):
    names = set(config.env)
    inside = {k: v for k, v in env.items() if k.startswith(ENV_PREFIXES) or k in ENV_NAMES or k in names}
    if config.proxy:
        inside.update(HTTPS_PROXY=config.proxy, HTTP_PROXY=config.proxy, https_proxy=config.proxy,
                      http_proxy=config.proxy, NO_PROXY="", no_proxy="")
    return inside


def container_argv(config, argv, env, *, trial, board_root, auth_files=(), name):
    """(argv for the engine client, environment for the client process). Pure: no engine is called."""
    trial, board_root = Path(trial).resolve(), Path(board_root).resolve()
    inside = container_env(env, config)
    args = [config.engine, "run", "--rm", "-i", "--init", "--name", name, "--label", f"colloquy.run={name}",
            "--network", config.network or "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", str(config.pids_limit),
            "--user", f"{os.getuid()}:{os.getgid()}", "--workdir", str(trial),
            "--tmpfs", f"/tmp:rw,size={config.scratch_bytes},mode=1777"]
    if config.memory:
        args += ["--memory", str(config.memory)]
    if config.cpus:
        args += ["--cpus", str(config.cpus)]
    mounts = [f"type=bind,src={board_root},dst={board_root}"]
    mounts += [f"type=tmpfs,dst={board_root / hidden},tmpfs-size=65536" for hidden in HIDDEN
               if (board_root / hidden).exists()]
    mounts.append(f"type=bind,src={trial},dst={trial}")
    mounts += [f"type=bind,src={trial / p},dst={trial / p},readonly" for p in PLATFORM_PATHS if (trial / p).exists()]
    read_only = [Path(p) for p in (*auth_files, *config.ro_mounts)]
    if config.mount_host_python:
        read_only += sorted({Path(sys.prefix), Path(sys.base_prefix)})
    mounts += [f"type=bind,src={p},dst={p},readonly" for p in read_only]
    for mount in mounts:
        args += ["--mount", mount]
    args += ["--env", f"HOME={trial}", "--env", "TMPDIR=/tmp"]
    for key in sorted(inside):
        args += ["--env", key]
    client = {k: v for k, v in env.items() if k in CLIENT_ENV}
    client.setdefault("PATH", os.environ.get("PATH", "/usr/bin:/bin"))
    return [*args, config.image, *argv], {**client, **inside}


def apply(decision, argv, env, *, trial, board_root, adapter, agent_config, run):
    """Wrap a harness argv per the dispatch decision; returns (argv, env, receipt or None)."""
    config = decision["config"]
    if config is None:
        if decision["override"]:
            return argv, env, {"sandboxed": False, "override": decision["override"], "tenancy": decision["tenancy"],
                               "recorded": now()}
        return argv, env, None
    name = "colloquy-" + run
    wrapped, client_env = container_argv(config, argv, env, trial=trial, board_root=board_root,
                                         auth_files=adapter.auth_files(env), name=name)
    receipt = {"sandboxed": True, "engine": config.engine, "image": config.image, "network": config.network or "none",
               "proxy": config.proxy, "container": name, "harness_argv": argv,
               "environment_names": sorted(k for k in client_env if k not in CLIENT_ENV),
               "egress_allowlist": hosts(config, adapter.hosts(agent_config)), "recorded": now(),
               "cleanup": [config.engine, "rm", "-f", name]}
    return wrapped, client_env, receipt


def cleanup(receipt):
    """Remove a container whose client was stopped (timeout, stall timeout, interrupt); never raises."""
    import subprocess
    if receipt and receipt.get("sandboxed"):
        try:
            subprocess.run(receipt["cleanup"], capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            pass
