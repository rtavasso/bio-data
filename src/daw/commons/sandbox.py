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

Multi-tenant serving (`bio commons serve --mode accounts`, `bio commons host`)
records tenancy and refuses live dispatch without a sandbox unless the operator
overrides it with a recorded reason.

A replication dispatch executes the fetched derivation's code (the AGENTS.md
carve-out), so it needs a sandbox with egress off: on a multi-tenant commons it
is refused without `sandbox.toml` and no override is accepted. Inside the
sandbox its allowlist holds only the harness's model hosts (no data sources,
no configured extras); with no proxy network the container has no network at
all, and `replicate.py` strips proxy variables from the executed code's
environment. Local single-user mode runs it unsandboxed with a recorded
`replication_unsandboxed` warning (`runs/<run>/sandbox.json` and an event).

The board root is never mounted into the container. The checkout's `bio
community` commands reach the board through the operator's board service
(`daw.commons.boardservice`, `bio commons board-service`): only the agent's own
socket directory is mounted (read-only), and `BIO_BOARD_URL` and the agent's
`BIO_BOARD_TOKEN` are passed by name. Other agents' checkouts, the library,
`runs/`, `service/`, `secrets/` and the board database are absent.

Spec v2 C7. Egress is token-scoped: each dispatch writes its own allowlist as a
policy file under `<commons>/service/egress/policies/` and the container gets a
proxy credential bound to it (inside HTTPS_PROXY, by name); `release` revokes it
when the run ends. The task budget (`.colloquy/`) and the sealed harness
configuration are mounted read-only. A sandboxed Hermes resume runs the session
bridge inside the agent image (`hermes_native_session`).
"""
import hashlib
import os
import sys
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from daw.commons.egress import SOURCE_HOSTS
from daw.util import DawError, now, read_json, write_json

ENGINES = ("docker", "podman")
# Platform code plus `.colloquy` (the platform-owned task budget, daw.commons.budgets), all read-only.
PLATFORM_PATHS = ("src", ".agents", "bin", "AGENTS.md", "README.md", "pyproject.toml", "uv.lock", "contracts", "examples", "docs",
                  ".colloquy")
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


REPLICATION_WARNING = ("replication_unsandboxed: local single-user mode executes the fetched derivation's code "
                       "without a container sandbox or egress control")


def policy(root, override=None, task_type=None):
    """Decide before any state changes whether this dispatch may run, and how."""
    config = load(root)
    mode = tenancy(root)
    if override is not None and not str(override).strip():
        raise DawError("override_reason_required", "say why this dispatch may run without a sandbox")
    replication = task_type == "replication"
    if config is None and mode == "accounts" and (override is None or replication):
        raise DawError("sandbox_required", "multi-tenant commons: a replication executes fetched code and needs "
                       "sandbox.toml (no override)" if replication else
                       "multi-tenant commons: configure sandbox.toml or override with a reason")
    decision = {"config": config, "tenancy": mode, "override": override if config is None and override else None}
    if replication:
        decision["replication_egress"] = ("unsandboxed" if config is None else "model_hosts_only" if config.network
                                          else "none")
        if config is None:
            decision["warning"] = REPLICATION_WARNING
    return decision


def hosts(config, harness_hosts=()):
    """The egress allowlist: source adapter hosts, configured extras, and the harnesses' model providers."""
    return sorted({*SOURCE_HOSTS, *(config.allow_hosts if config else ()), *(config.model_hosts if config else ()),
                   *harness_hosts})


def container_env(env, config, proxy=None):
    """Variables the container receives by name. `proxy` is the dispatch's credentialed proxy URL
    (default: the configured proxy, unauthenticated); an empty string means no proxy at all."""
    names = set(config.env)
    inside = {k: v for k, v in env.items() if k.startswith(ENV_PREFIXES) or k in ENV_NAMES or k in names}
    proxy = config.proxy if proxy is None else proxy
    if proxy:
        inside.update(HTTPS_PROXY=proxy, HTTP_PROXY=proxy, https_proxy=proxy, http_proxy=proxy, NO_PROXY="", no_proxy="")
    return inside


def container_argv(config, argv, env, *, trial, board_root, auth_files=(), name, board=None, proxy=None,
                   network=None, ro_files=()):
    """(argv for the engine client, environment for the client process). Pure: no engine is called.

    `board` is the agent's board-service endpoint ({dir, url, token}, `boardservice.provision`); without
    it the container has no board access at all. `board_root` itself is never mounted. `proxy` is the
    dispatch's credentialed proxy URL; `network="none"` isolates the container (no proxy). `ro_files`
    are (host file, container path) pairs mounted read-only, the sealed harness configuration."""
    trial, board_root = Path(trial).resolve(), Path(board_root).resolve()
    if not trial.is_relative_to(board_root):
        raise DawError("unsafe_agent_path", "the checkout must live under its commons")
    network = network or config.network or "none"
    inside = container_env(env, config, "" if network == "none" else proxy)
    inside.pop("BIO_BOARD_URL", None)
    inside.pop("BIO_BOARD_TOKEN", None)
    if board:
        inside.update(BIO_BOARD_URL=board["url"], BIO_BOARD_TOKEN=board["token"])
    args = [config.engine, "run", "--rm", "-i", "--init", "--name", name, "--label", f"colloquy.run={name}",
            "--network", network, "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", str(config.pids_limit),
            "--user", f"{os.getuid()}:{os.getgid()}", "--workdir", str(trial),
            "--tmpfs", f"/tmp:rw,size={config.scratch_bytes},mode=1777"]
    if config.memory:
        args += ["--memory", str(config.memory)]
    if config.cpus:
        args += ["--cpus", str(config.cpus)]
    mounts = [f"type=bind,src={trial},dst={trial}"]
    mounts += [f"type=bind,src={trial / p},dst={trial / p},readonly" for p in PLATFORM_PATHS if (trial / p).exists()]
    mounts += [f"type=bind,src={Path(src)},dst={Path(dst)},readonly" for src, dst in ro_files]
    read_only = [Path(p) for p in (*auth_files, *config.ro_mounts)]
    if config.mount_host_python:
        read_only += sorted({Path(sys.prefix), Path(sys.base_prefix)})
    if board:
        read_only.append(Path(board["dir"]))
    mounts += [f"type=bind,src={p},dst={p},readonly" for p in read_only]
    for mount in mounts:
        args += ["--mount", mount]
    args += ["--env", f"HOME={trial}", "--env", "TMPDIR=/tmp"]
    for key in sorted(inside):
        args += ["--env", key]
    client = {k: v for k, v in env.items() if k in CLIENT_ENV}
    client.setdefault("PATH", os.environ.get("PATH", "/usr/bin:/bin"))
    return [*args, config.image, *argv], {**client, **inside}


# ---- sealed harness configuration (spec v2 C7) -------------------------------------------------
#
# The harness home's configuration (`.claude-home/settings.json`, `.hermes/config.yaml`, the Codex
# home's config.toml, the MCP harness's mcp.json) decides what the harness may do, and the agent can
# write its own checkout. A platform-owned copy is sealed outside the checkout, in
# `<commons>/agents/<id>/harness-config/`, when the agent is created (or at its first dispatch for
# agents created before this existed). Before every turn the runtime writes a fresh per-turn copy into
# the home and records any difference it overwrote; in the sandbox the sealed files are also mounted
# read-only over the home, except files the adapter lists as scratch (written by the harness itself),
# which keep only the per-turn copy. After the turn, changes are recorded in `harness-config.json`.

def harness_config_dir(trial):
    return Path(trial).parent / "harness-config"


def _config_bytes(path):
    if path.is_symlink():
        raise DawError("unsafe_harness_config", str(path))
    return path.read_bytes() if path.is_file() else None


def seal_harness_config(trial, adapter):
    """Copy the adapter's staged configuration out of the checkout (an unstaged file seals as empty)."""
    home, folder = adapter.home(trial), harness_config_dir(trial)
    folder.mkdir(exist_ok=True, mode=0o700)
    files = {}
    for name in adapter.config_files:
        data = _config_bytes(home / name)
        (folder / name).write_bytes(data or b"")
        files[name] = {"sha256": hashlib.sha256(data or b"").hexdigest(), "staged": data is not None}
    write_json(folder / "manifest.json", {"format": 1, "harness": adapter.name, "files": files, "sealed": now()})
    return files


def turn_harness_config(trial, adapter):
    """Before a turn: write the per-turn copy of every sealed file into the home; returns the receipt."""
    home, folder = adapter.home(trial), harness_config_dir(trial)
    sealed_now = not (folder / "manifest.json").is_file()
    if sealed_now:
        seal_harness_config(trial, adapter)
    files = read_json(folder / "manifest.json")["files"]
    restored = []
    for name in files:
        sealed = (folder / name).read_bytes()
        target = home / name
        if target.is_symlink():
            target.unlink()
            restored.append(name)
        elif (_config_bytes(target) or b"") != sealed:
            restored.append(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(sealed)
    return {"harness": adapter.name, "files": {k: v["sha256"] for k, v in files.items()}, "sealed_at_dispatch": sealed_now,
            "restored_before_turn": restored, "scratch": sorted(set(adapter.scratch_config_files) & set(files)),
            "observed": now()}


def check_harness_config(trial, adapter, receipt):
    """After a turn: which sealed files differ from the per-turn copy (recorded, restored next turn)."""
    home = adapter.home(trial)
    changed = []
    for name, sha in receipt["files"].items():
        try:
            data = _config_bytes(home / name)
        except DawError:
            changed.append(name)
            continue
        if hashlib.sha256(data or b"").hexdigest() != sha:
            changed.append(name)
    receipt.update(changed_during_turn=changed, checked=now())
    return receipt


def harness_config_mounts(trial, adapter):
    """(sealed file, home path) pairs the sandbox mounts read-only."""
    files, scratch = getattr(adapter, "config_files", ()), getattr(adapter, "scratch_config_files", ())
    if not files:
        return []
    folder, home = harness_config_dir(trial), adapter.home(Path(trial).resolve())
    return [(folder.resolve() / name, home / name) for name in files if name not in scratch and (folder / name).is_file()]


# ---- Hermes session bridge inside the agent image (spec v2 C7) -----------------------------------
#
# Resuming or branching a Hermes conversation runs Hermes's own SessionDB code (hermes_session_bridge.py)
# with Hermes's interpreter. Unsandboxed, that is the host's Hermes install. Sandboxed, the host need not
# have Hermes at all: the bridge runs in the agent image (`--network none`, the same mounts), with the
# interpreter named by the image's `hermes` entry point shebang.

BRIDGE_SHELL = ('exe=$(command -v "$1") || { echo hermes_executable_missing >&2; exit 3; }; '
                'py=$(sed -n "1s/^#![[:space:]]*//p" "$exe"); '
                'case "$py" in ""|*[[:space:]]*) echo hermes_python_unavailable >&2; exit 3;; esac; '
                'shift; exec "$py" "$@"')


def hermes_bridge_argv(config, executable, home, identity, trial, *, fork, env, board_root, name):
    trial = Path(trial).resolve()
    bridge = trial / "src" / "daw" / "hermes_session_bridge.py"
    inner = ["sh", "-c", BRIDGE_SHELL, "colloquy-bridge", executable or "hermes", str(bridge),
             "--database", str(Path(home) / "state.db"), "--session", identity, "--cwd", str(trial)]
    if fork:
        inner.append("--fork")
    bridge_env = {k: v for k, v in env.items() if not k.startswith("HERMES_") and k not in ("PYTHONPATH", "BIO_BOARD_URL",
                                                                                              "BIO_BOARD_TOKEN")}
    bridge_env.update(HERMES_HOME=str(home), HERMES_CWD=str(trial))
    return container_argv(config, inner, bridge_env, trial=trial, board_root=board_root, name=name, network="none")


def hermes_native_session(config, executable, home, identity, trial, *, fork=False, env, board_root, name):
    """Select or branch a saved Hermes conversation with the bridge inside the agent image."""
    import json
    import subprocess
    argv, client = hermes_bridge_argv(config, executable, home, identity, trial, fork=fork, env=env,
                                      board_root=board_root, name=name)
    try:
        result = subprocess.run(argv, env=client, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        raise DawError("native_session_prepare_failed", f"sandboxed Hermes bridge ({config.engine}): {e}") from e
    if result.returncode:
        if "hermes_python_unavailable" in result.stderr or "hermes_executable_missing" in result.stderr:
            raise DawError("hermes_python_unavailable",
                           f"the agent image {config.image} has no Hermes entry point with a Python shebang")
        raise DawError("native_session_prepare_failed", result.stderr[-4000:])
    try:
        prepared = json.loads(result.stdout.splitlines()[-1])
    except (ValueError, IndexError) as e:
        raise DawError("native_session_invalid_response") from e
    return {**prepared, "bridge": "agent image", "bridge_container": name}


# ---- dispatch ----------------------------------------------------------------------------------

def apply(decision, argv, env, *, trial, board_root, adapter, agent_config, run, timeout=0):
    """Wrap a harness argv per the dispatch decision; returns (argv, env, receipt or None).

    With a proxy, the dispatch's allowlist is written as a token-scoped egress policy (revoked by
    `release` when the run ends); the credential reaches the container only inside HTTPS_PROXY, by name."""
    config = decision["config"]
    if config is None:
        if decision["override"] or decision.get("warning"):
            return argv, env, {"sandboxed": False, "tenancy": decision["tenancy"], "recorded": now(),
                               **{k: decision[k] for k in ("override", "warning", "replication_egress") if decision.get(k)}}
        return argv, env, None
    from daw.commons import boardservice, egress
    name = "colloquy-" + run
    agent = env["BIO_AGENT"]
    board = boardservice.provision(board_root, agent)
    # A replication (spec v2 C6) reaches only its harness's model provider; the token-scoped policy below
    # makes the proxy enforce exactly this list, so replication egress is enforced at the proxy (C7).
    allowlist = (sorted(set(adapter.hosts(agent_config))) if decision.get("replication_egress")
                 else hosts(config, adapter.hosts(agent_config)))
    proxy, scope = None, {"scope": "none: --network none"} if not config.network else {
        "scope": f"network {config.network} without a proxy"}
    if config.proxy:
        token, record = egress.issue(board_root, allowlist, run=run, agent=agent, seconds=timeout)
        proxy = egress.proxy_url(config.proxy, run, token)
        scope = {"scope": "token-scoped policy", "policy": record["policy"], "expires": record["expires"],
                 "policy_file": str(egress.policy_dir(board_root).relative_to(Path(board_root)) / (record["policy"] + ".json")),
                 "credential": "in HTTPS_PROXY, passed by environment name; never recorded"}
    ro_files = harness_config_mounts(trial, adapter)
    wrapped, client_env = container_argv(config, argv, env, trial=trial, board_root=board_root,
                                         auth_files=adapter.auth_files(env), name=name, board=board, proxy=proxy,
                                         ro_files=ro_files)
    receipt = {"sandboxed": True, "engine": config.engine, "image": config.image, "network": config.network or "none",
               "proxy": config.proxy, "container": name, "harness_argv": argv,
               "environment_names": sorted(k for k in client_env if k not in CLIENT_ENV),
               "egress_allowlist": allowlist, "egress": scope, "board_mounted": False,
               "board_service": {"url": board["url"], "socket": str(board["socket"]), "index": board["index"],
                                 "link": str(board["link"]), "listening": board["socket"].is_socket()},
               "harness_config_read_only": [str(dst) for _, dst in ro_files], "recorded": now(),
               "cleanup": [config.engine, "rm", "-f", name]}
    if decision.get("replication_egress"):
        receipt["replication_egress"] = decision["replication_egress"]
    return wrapped, client_env, receipt


def release(board_root, receipt):
    """Revoke the run's egress policy (idempotent); records when. Never raises."""
    from daw.commons import egress
    policy_id = ((receipt or {}).get("egress") or {}).get("policy")
    if policy_id and not receipt["egress"].get("revoked"):
        try:
            egress.revoke(board_root, policy_id)
        except OSError:
            return receipt
        receipt["egress"]["revoked"] = now()
    return receipt


def cleanup(receipt):
    """Remove a container whose client was stopped (timeout, stall timeout, interrupt); never raises."""
    import subprocess
    if receipt and receipt.get("sandboxed"):
        try:
            subprocess.run(receipt["cleanup"], capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            pass
