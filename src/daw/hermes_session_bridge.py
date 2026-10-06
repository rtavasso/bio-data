"""Run with the installed Hermes interpreter, never the bio environment.

Use native SessionDB's resume projection (including compaction) and message
serialization. The bridge only selects/branches a saved conversation and sets
its new working directory. No model calls or research loop live here.
"""
import argparse
import json
from pathlib import Path


def main():
    from hermes_state import SessionDB
    from hermes_state_ids import new_session_id
    from hermes_cli.cli_commands_mixin import _BRANCH_COPY_KEYS, extract_api_content_sidecar, message_identity

    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--fork", action="store_true")
    args = parser.parse_args()
    db = SessionDB(args.database)
    try:
        if not db.get_session(args.session):
            raise ValueError("saved Hermes session does not exist")
        parent = db.resolve_resume_session_id(args.session)
        metadata = db.get_session(parent)
        session = parent
        if args.fork:
            history, _ = db.get_resume_conversations(parent)
            if not history:
                raise ValueError("cannot fork an empty saved conversation")
            session = new_session_id()
            config = metadata.get("model_config") or {}
            if isinstance(config, str):
                config = json.loads(config)
            config = {**config, "_branched_from": parent}
            db.create_session(session, source="cli", model=metadata.get("model"),
                              parent_session_id=parent, system_prompt=metadata.get("system_prompt"),
                              model_config=config, cwd=args.cwd)
            messages = [{"role": msg["role"], "tool_name": msg.get("tool_name") or msg.get("name"),
                         "api_content": extract_api_content_sidecar(msg),
                         **{key: msg.get(key) for key in _BRANCH_COPY_KEYS},
                         **message_identity(msg, with_tool_uids=True)}
                        for msg in history if msg.get("role") != "session_meta"]
            # Unlike the interactive CLI's best-effort copy, a failed durable copy
            # aborts this preparation; an incomplete branch is never launched.
            db.append_messages_batch(session, messages, chunk_rows=500)
            restored, _ = db.get_resume_conversations(session)
            if len(restored) != len(messages):
                raise ValueError("incomplete native branch copy")
        # Startup CLI restores cwd again after --no-restore-cwd parsing. Retarget
        # the exact selected row in this private home using its native API.
        db.update_session_cwd(session, args.cwd)
        print(json.dumps({"session": session, "parent": parent if args.fork else None,
                          "forked": args.fork, "cwd": args.cwd}))
    finally:
        db.close()


if __name__ == "__main__":
    main()
