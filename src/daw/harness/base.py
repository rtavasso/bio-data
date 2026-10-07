"""Shared adapter behaviour: private harness homes, explicit credential links, session files.

Every non-Hermes harness keeps its native state under one directory inside the
checkout (`home_dir`). Only allowlisted session files are snapshotted or
restored; credentials are linked from an operator-named file outside the
commons and never copied into receipts or checkpoints.
"""
import shutil
from pathlib import Path

from daw.hermes import state_hashes
from daw.util import DawError, digest, file_hash, read_json


class Adapter:
    name = ""
    home_dir = ""
    default_executable = ""
    default_model = None
    default_provider = None
    # Model provider hosts the sandbox egress proxy must allow for this harness.
    provider_hosts = ()
    # (environment variable naming an external credential file, its name inside the home)
    auth = None
    # Directories/files under the home that hold native conversation state.
    state_globs = ()
    supports_fork = False
    limitations = ()
    # Staged harness configuration under the home (spec v2 C7). The runtime seals a platform-owned copy
    # outside the checkout, restores it before every turn, mounts it read-only in the sandbox and records
    # changes. Files listed in `scratch_config_files` are files the harness itself must write: they get a
    # fresh writable per-turn copy instead of a read-only mount.
    config_files = ()
    scratch_config_files = ()
    # Whether the harness stream marks context compactions (C10): when it does not, compaction counts are
    # unavailable (None), never zero.
    emits_compactions = False
    # Where the run folder's session snapshot records compaction summaries and fallbacks (spec v2 V6), read
    # after the turn into runs/<run>/compactions.jsonl; None: this harness does not expose them (unavailable).
    compaction_store = None

    def reports_compactions(self, config):
        return self.emits_compactions

    def home(self, trial):
        return Path(trial) / self.home_dir

    def prepare(self, trial, config, checkpoint=None):
        home = self.home(trial)
        home.mkdir(mode=0o700)
        parent = self.restore(checkpoint, home, trial) if checkpoint else None
        staged = self.stage(trial, home, config)
        hashes = self.snapshot(home, Path(trial).parent / "learning-before")
        return {"harness": self.name, "staged_sha256": staged, "state_sha256": digest(hashes),
                "parent_checkpoint": parent}

    def stage(self, trial, home, config):
        """Write harness configuration into the home; return a digest of what was written."""
        return None

    def command(self, executable, trial, config, *, resume=None, fork=False):
        raise NotImplementedError

    def environment(self, base, trial):
        env = {k: v for k, v in base.items() if not k.startswith("HERMES_")}
        env.update(PYTHONUNBUFFERED="1", PYTHONPATH=str(Path(trial) / "src"))
        return env

    def link_auth(self, env, trial, forbidden_root):
        """Symlink the operator's credential file into the home; refuse files inside the commons."""
        if not self.auth or not env.get(self.auth[0]):
            return None
        source = Path(env[self.auth[0]]).expanduser().resolve(strict=True)
        if source.is_relative_to(forbidden_root):
            raise DawError("credentials_must_be_external")
        destination = self.home(trial) / self.auth[1]
        if destination.is_symlink():
            if destination.resolve() != source:
                raise DawError("unexpected_auth_link")
        elif destination.exists():
            raise DawError("unexpected_auth_file")
        else:
            destination.symlink_to(source)
        return source

    def auth_files(self, env):
        """Credential files a sandbox must mount read-only (never copied)."""
        if self.auth and env.get(self.auth[0]):
            return [Path(env[self.auth[0]]).expanduser().resolve()]
        return []

    def state_files(self, home):
        for pattern in self.state_globs:
            for path in sorted(Path(home).glob(pattern)):
                if path.is_symlink():
                    raise ValueError(f"session state refuses symlink: {path.name}")
                if path.is_file():
                    yield path

    def snapshot(self, home, destination):
        """Allowlisted native session state; never credentials or global config."""
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=False)
        home = Path(home)
        if home.is_symlink():
            raise ValueError("harness home must not be a symlink")
        for path in self.state_files(home) if home.exists() else ():
            target = destination / path.relative_to(home)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        return state_hashes(destination)

    def restore(self, checkpoint, home, trial):
        checkpoint = Path(checkpoint).resolve()
        receipt = read_json(checkpoint / "checkpoint.json")
        if receipt.get("format_version") != 1 or not receipt.get("restorable"):
            raise DawError("checkpoint_not_restorable")
        source = checkpoint / "agent"
        if state_hashes(source) != receipt["agent_files"]:
            raise DawError("learning_checkpoint_changed")
        for name in receipt["agent_files"]:
            path = self.restored_path(Path(name), trial)
            if not any(Path(name).match(pattern) for pattern in self.state_globs):
                raise DawError("unexpected_checkpoint_file", name)
            target = home / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
        return file_hash(checkpoint / "checkpoint.json")

    def restored_path(self, relative, trial):
        return relative

    def resumable(self, config):
        """Whether deliveries continue a saved conversation (otherwise each starts fresh)."""
        return True

    def hosts(self, config):
        """Model provider hosts the sandbox egress proxy must allow."""
        return tuple(self.provider_hosts)

    def session_exists(self, home, identity):
        raise NotImplementedError

    def native_session(self, executable, home, identity, cwd, *, fork=False):
        """Select (or fork on launch) a saved conversation without a model call."""
        self.session_exists(home, identity)
        if fork and not self.supports_fork:
            raise DawError("harness_fork_unsupported", self.name)
        return {"session": identity, "parent": identity if fork else None, "forked": False,
                "fork_on_launch": bool(fork), "cwd": str(cwd), "harness": self.name}

    def parse(self, path):
        raise NotImplementedError

    def receipt_fields(self, config):
        return {"harness": self.name}

