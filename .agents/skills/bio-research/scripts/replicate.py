"""Replicate one fetched artifact by executing its derivation's own saved code (replication tasks only).

Example (inside a replication task, after `bio community fetch POST --question Q --artifact ARTIFACT`):
  ./bin/python .agents/skills/bio-research/scripts/replicate.py ARTIFACT --question Q

This is the single execution carve-out in AGENTS.md: a replication may execute only the code blobs named
in the fetched derivation, after hash verification, through run_analysis.py, inside a sandbox with egress
off. Never use it outside a replication task, and never execute any other fetched code. The helper:

1. reads the artifact's manifest from this workspace (`bio artifact show`); it must already be fetched;
2. copies each code and input blob out of the workspace store into the question
   (scripts/replication-ID-rNNN/, inputs/replication-ID-rNNN/) and checks every copy's sha256 against
   the derivation; any mismatch stops before anything runs;
3. runs the entry code blob through run_analysis.py with a fresh receipt
   (outputs/replication-ID-rNNN/execution.json): `INTERPRETER CODE INPUT... OUTPUT`, inputs in
   derivation order and the output path last, in a minimal environment without proxy, board-token or
   credential variables (BIO_REPLICATION_INPUTS and BIO_REPLICATION_OUTPUT carry the same paths);
4. stores the receipt bytes (`bio object add`) and, when the receipt is complete, registers the output
   with the original derivation unchanged (`bio register --manifest`);
5. records a `replication_execution` work event naming the original, the replica, the receipt blob and
   whether the bytes are identical. A failed run is recorded too and registers nothing.

It never edits the code, inputs or parameters and never copies the original's output bytes. The
platform confirms a replication only from such a receipt; identical bytes are not a scientific verdict.
A derivation with several code blobs needs `--entry SHA`; the others are copied beside it but are not
importable by their original names. A derivation that recorded a command is still run with the
convention above (the recorded command is reported, not executed).
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_ANALYSIS = HERE / "run_analysis.py"
# Variables the executed code may see. Proxies, board tokens and model credentials never reach it.
KEEP_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR", "SYSTEMROOT", "SSL_CERT_FILE")


class Refused(Exception):
    def __init__(self, reason, detail=""):
        super().__init__(reason)
        self.reason, self.detail = reason, detail


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def bio(base, *argv):
    done = subprocess.run([*base, *argv], capture_output=True, text=True, check=False)
    lines = done.stdout.strip().splitlines()
    if done.returncode != 0 or not lines:
        raise Refused("bio_command_failed", f"{' '.join(argv[:2])}: {(done.stderr or done.stdout).strip()[-800:]}")
    return json.loads(lines[-1])


def copy_verified(base, sha, destination):
    """Copy one stored blob out of the workspace and check the copy against its content address."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha or ""):
        raise Refused("invalid_blob_hash", str(sha))
    stored = bio(base, "object", "show", sha)  # verify_object: the stored bytes hash to their address
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(stored["path"], destination)
    if sha256(destination) != sha:
        raise Refused("blob_hash_mismatch", f"{sha} copied to {destination}")
    return destination


def fresh_run(question_path, short):
    for n in range(1, 1000):
        name = f"replication-{short}-r{n:03d}"
        if not any((question_path / part / name).exists() for part in ("scripts", "inputs", "outputs")):
            return name
    raise Refused("too_many_replication_runs", short)


def minimal_env(inputs, output):
    env = {k: v for k, v in os.environ.items() if k in KEEP_ENV}
    env.update(BIO_REPLICATION_INPUTS=json.dumps([str(p) for p in inputs]), BIO_REPLICATION_OUTPUT=str(output),
               PYTHONDONTWRITEBYTECODE="1")
    return env


def replicate(artifact, question, *, bio_cli, interpreter, entry=None):
    base = shlex.split(bio_cli)
    info = bio(base, "artifact", "show", artifact)
    manifest = info["manifest"]
    derivation = manifest["derivation"]
    codes = list(derivation["code"])
    if entry is None and len(codes) != 1:
        raise Refused("entry_required", f"the derivation names {len(codes)} code blobs; choose one with --entry")
    entry = entry or codes[0]
    if entry not in codes:
        raise Refused("entry_not_in_derivation", entry)
    question_path = Path(bio(base, "work", "show", question)["path"])
    name = fresh_run(question_path, artifact.removeprefix("artifact_")[:12])
    language = "R" if Path(interpreter).name.lower().startswith("rscript") else "py"
    scripts = question_path / "scripts" / name
    entry_path = None
    for n, sha in enumerate(codes):
        path = copy_verified(base, sha, scripts / f"code-{n}-{sha[:12]}.{language}")
        entry_path = path if sha == entry else entry_path
    inputs = [copy_verified(base, item["blob"], question_path / "inputs" / name / f"input-{n}-{item['blob'][:12]}")
              for n, item in enumerate(derivation["inputs"])]
    outdir = question_path / "outputs" / name
    outdir.mkdir(parents=True)
    output = outdir / Path(manifest.get("output", {}).get("name") or "replica.out").name
    receipt = outdir / "execution.json"
    command = [interpreter, str(RUN_ANALYSIS), "--receipt", str(receipt), "--output", str(output), "--",
               interpreter, str(entry_path), *map(str, inputs), str(output)]
    env = minimal_env(inputs, output)
    executed = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    if not receipt.is_file():
        raise Refused("no_receipt_written", (executed.stderr or executed.stdout).strip()[-800:])
    value = json.loads(receipt.read_text())
    stored = bio(base, "object", "add", str(receipt), "--classification", "work")["blob"]
    payload = {"original": artifact, "derivation_key": info["derivation_key"], "code_blob": entry,
               "receipt_blob": stored, "receipt_path": str(receipt.relative_to(question_path)),
               "exit_code": value.get("exit_code"), "complete": bool(value.get("complete")),
               "original_output_blob": info["output_blob"], "environment_names": sorted(env),
               "recorded_command": derivation.get("command") or [], "replica": None, "output_blob": None,
               "byte_identical": None}
    if value.get("complete") and value.get("code_sha256") == entry:
        spec = {"title": f"Replication of {manifest['title']}"[:500],
                "summary": (f"Output of executing code blob {entry} of derivation {info['derivation_key']} on its "
                            f"recorded inputs through run_analysis.py (replication of {artifact}; receipt blob "
                            f"{stored})."),
                "derivation": derivation, "output_role": manifest["output_role"], "kind": manifest.get("kind", "file"),
                "limitations": list(manifest.get("limitations") or [])}
        spec_path = outdir / "registration.json"
        spec_path.write_text(json.dumps(spec, indent=2, allow_nan=False))
        registered = bio(base, "register", str(output), "--manifest", str(spec_path), "--question", question)
        payload.update(replica=registered["artifact"], output_blob=registered["output_blob"],
                       byte_identical=registered["output_blob"] == info["output_blob"])
    event_path = outdir / "replication-event.json"
    event_path.write_text(json.dumps(payload, indent=2, allow_nan=False))
    event = bio(base, "work", "event", question, "--kind", "replication_execution", "--payload", str(event_path))
    return {"event": "replication_executed" if payload["replica"] else "replication_execution_failed",
            "work_event": event["id"], **payload, "receipt": str(receipt)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("artifact", help="the fetched original artifact ID")
    parser.add_argument("--question", required=True, help="question the replica is registered in")
    parser.add_argument("--entry", default=None, help="code blob to run when the derivation names several")
    parser.add_argument("--interpreter", default="./bin/python" if Path("bin/python").is_file() else sys.executable,
                        help="Python or Rscript interpreter (default ./bin/python)")
    parser.add_argument("--bio", default=os.environ.get("BIO_CLI", "./bin/bio"), help="bio command (shell words)")
    args = parser.parse_args(argv)
    try:
        result = replicate(args.artifact, args.question, bio_cli=args.bio, interpreter=args.interpreter, entry=args.entry)
    except Refused as refused:
        print(json.dumps({"event": "replication_refused", "reason": refused.reason, "detail": refused.detail,
                          "note": "nothing was executed" if refused.reason != "no_receipt_written" else
                                  "run_analysis.py did not write a receipt"}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0 if result["replica"] else 1


if __name__ == "__main__":
    sys.exit(main())
