"""Inspect question-local investigation records and observable new analysis work."""
from pathlib import Path
import re
import shlex
from typing import Literal

from pydantic import Field, model_validator

from daw.util import file_hash, read_json

from .mechanisms import ResearchRecord
from .runner import safe_path


def invoked_scripts(command, *, successful_only=False):
    """Conservative literal invocations, excluding quoted documentation and here-doc bodies.

    Dynamic eval, shell variables, Python -c/-m and inline imports need manual review.
    With successful_only, retain only simple invocations whose status determines
    the shell status, including a terminal && chain. This is not a shell parser
    or proof of the exact code version executed.
    """
    try:
        outer = shlex.split(command)
        if outer and Path(outer[0]).name in {"sh", "bash", "zsh"}:
            option = next((i for i, token in enumerate(outer) if token in {"-c", "-lc"}), None)
            if option is None or len(outer) != option + 2:
                return set()
            command = outer[option + 1]
        lines, pending = [], []
        for line in command.splitlines():
            if pending:
                delimiter, tabs = pending[0]
                if (line.lstrip("\t") if tabs else line) == delimiter:
                    pending.pop(0)
                continue
            if "<<" in line:
                # Skip the declaration too: inline Python/shell data are not saved-script invocations.
                matches = list(re.finditer(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2", line))
                if not matches or "<<<" in line:
                    return set()
                pending.extend((m[3], bool(m[1])) for m in matches)
                lines.append("__heredoc_command__")  # Its exit status must not disappear.
                continue
            lines.append(line)
        if pending:
            return set()
        # Parse one line at a time so a newline cannot become part of an argument.
        segments = []
        for line in lines:
            tokens = shlex.shlex(line, posix=True, punctuation_chars=";&|()<>")
            tokens.whitespace_split = True
            current = []
            for token in tokens:
                if token in {";", "&&", "||", "|", "|&", "&"}:
                    if current:
                        segments.append((current, token))
                    current = []
                else:
                    current.append(token)
            if current:
                segments.append((current, "\n"))
        if successful_only:
            # Complex control flow/pipelines can mask failure or skip an invocation.
            controls = {"if", "then", "else", "elif", "fi", "for", "while", "until", "case", "esac",
                        "do", "done", "function", "!", "(", ")", "{", "}"}
            if any(separator in {"||", "|", "|&", "&"} or any(t in controls or "$" in t or "`" in t for t in tokens)
                   for tokens, separator in segments):
                return set()
            start = len(segments) - 1
            while start > 0 and segments[start - 1][1] == "&&":
                start -= 1
            segments = segments[max(0, start):]
        found = set()
        for tokens, _ in segments:
            if not tokens:
                continue
            executable = Path(tokens[0]).name
            if re.fullmatch(r"python(?:[23](?:\.\d+)?)?", executable) or executable == "Rscript":
                args = tokens[1:]
                while args and args[0] in {"-u", "-B", "-E", "-I", "-s", "-S", "-O", "-OO", "-q", "--vanilla"}:
                    args = args[1:]
                if args and not args[0].startswith("-"):
                    found.add(args[0])
            elif "/" in tokens[0]:
                found.add(tokens[0])  # A saved executable script can have its own shebang.
        return {s for s in found if not any(c in s for c in "$`\n")}
    except ValueError:
        return set()


class Investigation(ResearchRecord):
    id: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"]
    question: str = Field(min_length=1)
    alternatives: list[str] = Field(min_length=2)
    readout: str = Field(min_length=1)
    assets: list[str]
    prerequisites: list[str]
    status: Literal["open", "ready", "running", "analyzed", "blocked", "deferred"]
    artifacts: list[str]
    finding: str
    limitation: str
    next_action: str = Field(min_length=1)
    blocker_evidence: list[str]  # Paths relative to the question, not arbitrary host paths.

    @model_validator(mode="after")
    def evidenced_disposition(self):
        if self.status == "analyzed" and (not self.artifacts or not self.finding.strip()):
            raise ValueError("analyzed investigation requires registered results and a finding")
        if self.status == "blocked" and (not self.blocker_evidence or not self.limitation.strip()):
            raise ValueError("blocked investigation requires preserved evidence and a specific limitation")
        if self.status == "deferred" and not self.limitation.strip():
            raise ValueError("deferral requires a reason and remains unfinished")
        return self


class InvestigationQueue(ResearchRecord):
    revision: int = Field(ge=1, strict=True)
    scope: str = Field(min_length=1)
    status: Literal["in_progress", "bounded_complete"]
    stopping_reason: str = Field(min_length=1)
    items: list[Investigation] = Field(min_length=1)

    @model_validator(mode="after")
    def honest_closure(self):
        if len({i.id for i in self.items}) != len(self.items):
            raise ValueError("duplicate investigation IDs")
        if not any(i.priority == "high" for i in self.items):
            raise ValueError("declare at least one high-priority investigation")
        if self.status == "bounded_complete" and any(
                i.priority == "high" and i.status not in {"analyzed", "blocked"} for i in self.items):
            raise ValueError("open or deferred high-priority work is not bounded complete")
        return self


def inspect_queue(trial, question, artifact_ids):
    folder = safe_path(trial / "workspace", question["path"])
    path = safe_path(folder, "outputs/investigations.json")
    if path.stat().st_size > 4 * 2**20:
        raise ValueError("investigation queue exceeds 4 MiB inspection budget")
    queue = InvestigationQueue.model_validate_json(path.read_text())
    for item in queue.items:
        if not set(item.artifacts) <= artifact_ids:
            raise ValueError("investigation refers to an unregistered or unlinked artifact")
        for evidence in item.blocker_evidence:
            if not safe_path(folder, evidence).is_file():
                raise ValueError("blocker evidence file is absent")
    return {"question": question["id"], "revision": queue.revision, "status": queue.status,
            "stopping_reason": queue.stopping_reason,
            "items": [{"id": i.id, "priority": i.priority, "status": i.status, "artifacts": i.artifacts}
                      for i in queue.items]}


def analysis_activity(trial, baseline, state, questions, parsed, files):
    """Correlate saved outputs, registrations, source bytes and command events; no science grading."""
    old_artifacts = {a["id"] for a in baseline["artifact"]}
    qids = {q["id"] for q in questions}
    linked = {a["artifact_id"] for a in state.get("question_artifact", []) if a["question_id"] in qids}
    scripts = [f for f in files if "/scripts/" in f["path"] and f.get("sha256")
               and any(q in f["path"].split("/") for q in qids)]
    commands = [i for i in parsed["items"] if i.get("type") == "command_execution" and i.get("exit_code") == 0]
    invocations = {c["line"]: {(trial / p).resolve() for p in invoked_scripts(c.get("command", ""), successful_only=True)}
                   for c in commands}
    results = []
    for artifact in state.get("artifact", []):
        if artifact["id"] in old_artifacts or artifact["id"] not in linked:
            continue
        try:
            sha = artifact["manifest_blob"]
            manifest = read_json(safe_path(trial / "workspace", f"blobs/sha256/{sha[:2]}/{sha}"))
            matching = [s for s in scripts if s["sha256"] in manifest["derivation"]["code"]]
            mentioned_lines = [c["line"] for c in commands if any(Path(s["path"]).name in c.get("command", "") for s in matching)]
            command_lines = [line for line, paths in invocations.items() if any((trial / s["path"]).resolve() in paths for s in matching)]
            output = artifact["output_blob"]
            valid = file_hash(safe_path(trial / "workspace", f"blobs/sha256/{output[:2]}/{output}")) == output
            inputs = manifest["derivation"]["inputs"]
            for item in inputs:
                sha = item["blob"]
                valid &= file_hash(safe_path(trial / "workspace", f"blobs/sha256/{sha[:2]}/{sha}")) == sha
            results.append({"artifact": artifact["id"], "output_role": artifact["output_role"],
                "output_blob": output, "input_blobs": [i["blob"] for i in inputs],
                "code_files": [s["path"] for s in matching], "command_lines": command_lines, "mention_lines": mentioned_lines,
                "execution_evidence": bool(valid and matching and command_lines),
                "note": "Shell exit status covers a literal saved-script invocation; masked failures and complex control flow need manual review. Matching saved code does not establish the exact executed version or scientific validity."})
        except (ValueError, OSError, KeyError) as e:
            results.append({"artifact": artifact["id"], "execution_evidence": False, "error": str(e)})
    old_assets = {a["id"] for a in baseline.get("asset_revision", [])}
    old_blobs = {b["sha256"] for b in baseline["blob"]}
    acquired = [{"asset": a["id"], "blob": a["blob"]} for a in state.get("asset_revision", [])
                if "asset_revision" in baseline
                if a["id"] not in old_assets and a.get("blob")]
    acquired_blobs = {a["blob"] for a in acquired if a["blob"] not in old_blobs}
    return {"new_registered_results": results, "new_acquired_assets": acquired,
            "acquisition_baseline_available": "asset_revision" in baseline,
            "new_unique_asset_bytes": sum(b["size"] for b in state.get("blob", []) if b["sha256"] in acquired_blobs),
            "note": "Catalog asset acquisitions only. Script downloads preserved as object inputs are excluded; inspect their receipts separately. Unique new bytes are not total HTTP traffic, biological novelty or an acquisition score."}
