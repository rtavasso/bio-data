"""Hermes adapter: a thin delegation to `daw.hermes` and the pinned session bridge.

Hermes behaviour, prompts and receipts are byte-identical to the pre-adapter
runtime: every call forwards to the functions the evaluator and community
runtime already used.
"""
import sqlite3
from pathlib import Path

from daw import hermes
from daw.harness.base import Adapter
from daw.util import DawError


class HermesAdapter(Adapter):
    name = "hermes"
    home_dir = ".hermes"
    default_executable = "hermes"
    default_model = "gpt-6-astra"
    default_provider = "openai-codex"
    provider_hosts = ("chatgpt.com", "api.openai.com", "auth.openai.com")
    auth = ("BIO_HERMES_AUTH_FILE", "auth.json")
    supports_fork = True
    config_files = ("config.yaml",)
    emits_compactions = True  # "⟳ compacting context…" in the stream (daw.hermes.parse: runtime_status)
    compaction_store = "agent-state/state.db"  # "[CONTEXT COMPACTION…" messages, fallbacks marked in the text
    limitations = ("Hermes stream tool outputs are capped upstream at 5000 characters; inspect state.db for full messages.",)

    def prepare(self, trial, config, checkpoint=None):
        return hermes.prepare_home(Path(trial), config["model"], config["effort"], config["provider"], checkpoint)

    def command(self, executable, trial, config, *, resume=None, fork=False):
        if fork:
            raise DawError("hermes_forks_through_bridge", "native_session prepares Hermes branches before launch")
        return hermes.command(executable, trial, config["model"], config["provider"], config["public"], resume=resume)

    def environment(self, base, trial):
        return hermes.environment(base, Path(trial))

    def parse(self, path):
        return hermes.parse(Path(path))

    def snapshot(self, home, destination):
        return hermes.snapshot_state(Path(home), destination)

    def session_exists(self, home, identity):
        path = Path(home) / "state.db"
        if not path.is_file() or not identity:
            raise DawError("saved_session_required")
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            if not db.execute("SELECT id FROM sessions WHERE id=?", (identity,)).fetchone():
                raise DawError("unknown_saved_session", identity)

    def native_session(self, executable, home, identity, cwd, *, fork=False):
        # Looked up at call time: tests and the demo substitute the bridge offline.
        # The bridge branches before launch, so the receipt carries no fork_on_launch key.
        from daw import community_runtime
        return community_runtime.native_session(executable, home, identity, cwd, fork=fork)

    def refresh_config(self, name, sealed, current, agent_config=None):
        """Platform-owned config.yaml keys merged into the sealed copy before each turn (sandbox.turn_harness_config)."""
        return hermes.refresh_config(name, sealed, current, agent_config)

    def config_migration(self, name, sealed, observed):
        """Hermes's own `_config_version` migration of the sealed config.yaml is benign, not an agent change."""
        return hermes.config_migration(name, sealed, observed)

    def receipt_fields(self, config):
        return {}


ADAPTER = HermesAdapter()
