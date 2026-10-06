"""Participants (M7.1): one table of identities for agents, humans, operators and system roles.

Humans are agent rows with kind=human and no trial: they publish, reply, ask and
correct through the same board functions. System participants (watcher, exporter)
author posts the platform makes on a person's behalf; their content is untrusted
like any other post. Agents are created by `community_runtime.add_agent`.
"""
import json
import re
import uuid

from daw.commons.schema import PARTICIPANT_KINDS
from daw.util import DawError, canonical, now

ORCID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
PROFILE_FIELDS = {"display_name", "affiliation", "orcid", "role"}


def clean_profile(profile):
    profile = dict(profile or {})
    unknown = set(profile) - PROFILE_FIELDS
    if unknown:
        raise DawError("unknown_profile_field", ", ".join(sorted(unknown)))
    for key, value in profile.items():
        if not isinstance(value, str) or len(value) > 300:
            raise DawError("invalid_profile_field", key)
    if profile.get("orcid") and not ORCID.match(profile["orcid"]):
        raise DawError("invalid_orcid", "use the 0000-0000-0000-0000 form")
    return {k: v.strip() for k, v in profile.items() if v.strip()}


def add_participant(board, name, kind, *, profile=None):
    """Create a non-agent participant. Agents need a research checkout: use add_agent."""
    if kind not in PARTICIPANT_KINDS or kind == "agent":
        raise DawError("invalid_participant_kind", "human, operator or system; agents are created with add-agent")
    name = name.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name):
        raise DawError("invalid_participant_name", "letters, digits, '.', '_' or '-' (max 64)")
    config = {"profile": clean_profile(profile)}
    identity = {"human": "human_", "operator": "operator_", "system": "system_"}[kind] + uuid.uuid4().hex
    with board.writer(), board.db:
        if board.one("SELECT id FROM agent WHERE name=? OR id=?", (name, name)):
            raise DawError("participant_name_unavailable", name)
        board.db.execute("INSERT INTO agent(id,name,trial,native_session,parent,config,created,kind) "
                         "VALUES(?,?,NULL,NULL,NULL,?,?,?)", (identity, name, canonical(config).decode(), now(), kind))
        board.event("participant_created", {"participant": identity, "name": name, "kind": kind})
    return board.agent(identity)


def ensure_system(board, name):
    """Idempotently return the named system participant (e.g. watcher, exporter)."""
    row = board.one("SELECT id,kind FROM agent WHERE name=?", (name,))
    if row:
        if row["kind"] != "system":
            raise DawError("participant_name_unavailable", name)
        return board.agent(row["id"])
    return add_participant(board, name, "system")


def update_profile(board, identity, profile):
    participant = board.agent(identity)
    if participant["kind"] == "agent":
        raise DawError("agent_config_is_runtime_owned")
    config = {**participant["config"], "profile": clean_profile(profile)}
    with board.writer(), board.db:
        board.db.execute("UPDATE agent SET config=? WHERE id=?", (canonical(config).decode(), participant["id"]))
        board.event("participant_profile_updated", {"participant": participant["id"]})
    return board.agent(participant["id"])


def describe(row):
    """Public participant fields. Agents expose harness, model and effort; never runtime paths or tool hashes."""
    config = row["config"] if isinstance(row["config"], dict) else json.loads(row["config"] or "{}")
    public = {"id": row["id"], "name": row["name"], "kind": row.get("kind", "agent"), "parent": row.get("parent"),
              "created": row["created"]}
    if public["kind"] == "agent":
        public.update(harness=config.get("harness", "hermes"), model=config.get("model"),
                      effort=config.get("effort"), started=bool(row.get("native_session")))
    else:
        public["profile"] = config.get("profile", {})
    return public
