"""Compaction hygiene per run (spec v2 V8): did a harness keep the assignment through context compaction?

From a run folder only (files, no board rows), so the metrics projection stays file-derived:

- `compaction_summaries`, `compaction_fallbacks`: compaction handoffs written during the delivery and how many
  were the deterministic fallback (the summarizer failed). Read from the harness session database
  (`agent-state/state.db`, Hermes); None when the run has no readable database (other harnesses, and the
  committed cohort fixture, which drops session databases).
- `summaries_missing_assignment`: summaries whose text contains none of the assignment's markers. The markers
  are read from the run's `prompt.txt`: the request or question post id the runtime names in every prompt
  (`Request post: post_…`), plus any `Assignment key phrase: …` or `Assignment key: …` line (the harness check
  and the round-two presets carry one). This is a string test: a summary that paraphrases the assignment
  without naming its post or key is counted as missing it. None when there are no summaries or no markers.
- `context_per_call`: the input context the harness reported per model call (Claude Code: per assistant
  message, input plus cache reads and writes), or per turn where only turn totals are reported (Codex
  `turn.completed`, Claude Code's or Hermes's `result`); `unit` says which. None when the stream reports neither.
"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

POST_MARKER = re.compile(r"(?:Request|Question) post: (post_[0-9a-f]{32})")
KEY_MARKER = re.compile(r"Assignment key(?: phrase)?: *([^\s.,;]{6,120})")


def assignment_markers(folder):
    path = Path(folder) / "prompt.txt"
    if not path.is_file():
        return []
    text = path.read_text(errors="replace")
    return list(dict.fromkeys(POST_MARKER.findall(text) + KEY_MARKER.findall(text)))


def _bounds(execution):
    out = []
    for key in ("started", "finished"):
        try:
            out.append(datetime.fromisoformat(execution[key]).timestamp() if execution.get(key) else None)
        except ValueError:
            out.append(None)
    return out


def compaction_texts(folder, execution):
    """Compaction summary texts written during this delivery, or None without a readable session database."""
    db = Path(folder) / "agent-state" / "state.db"
    if not db.exists():
        return None
    start, end = _bounds(execution)
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as connection:
            rows = connection.execute("SELECT content,timestamp FROM messages WHERE content LIKE '[CONTEXT COMPACTION%'").fetchall()
    except sqlite3.Error:
        return None
    return [content for content, ts in rows if (start is None or ts >= start - 1) and (end is None or ts <= end + 1)]


def context_per_call(path):
    """{unit, records, mean_input_tokens, max_input_tokens} from the raw stream, or None when not reported."""
    path = Path(path)
    if not path.is_file():
        return None
    calls, turns, seen = [], [], set()
    with path.open("rb") as stream:
        for raw in stream:
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            message = event.get("message") if isinstance(event.get("message"), dict) else {}
            usage = message.get("usage") if kind == "assistant" else None
            if isinstance(usage, dict) and isinstance(usage.get("input_tokens"), int):
                key = message.get("id") or len(calls)
                if key in seen:
                    continue
                seen.add(key)
                calls.append(sum(v for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
                                 if isinstance(v := usage.get(k), int)))
            elif kind == "turn.completed" and isinstance(event.get("usage"), dict) \
                    and isinstance(event["usage"].get("input_tokens"), int):
                turns.append(event["usage"]["input_tokens"])
            elif kind == "result" and isinstance(event.get("usage"), dict) and isinstance(event["usage"].get("input_tokens"), int):
                usage = event["usage"]  # Claude Code's turn total (when no per-message usage was streamed)
                turns.append(sum(v for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
                                 if isinstance(v := usage.get(k), int)))
            elif kind == "result" and isinstance(event.get("tokens"), dict) and isinstance(event["tokens"].get("input"), int):
                turns.append(event["tokens"]["input"] + (event["tokens"].get("cache_read") or 0))
    values, unit = (calls, "call") if calls else (turns, "turn") if turns else (None, None)
    if not values:
        return None
    return {"unit": unit, "records": len(values), "mean_input_tokens": round(sum(values) / len(values), 1),
            "max_input_tokens": max(values)}


def run_hygiene(folder, harness=None):
    """Compaction hygiene of one delivery (see the module docstring); None values are unavailable, never zero."""
    folder = Path(folder)
    execution = {}
    if (folder / "execution.json").is_file():
        try:
            execution = json.loads((folder / "execution.json").read_text())
        except ValueError:
            execution = {}
    texts = compaction_texts(folder, execution)
    markers = assignment_markers(folder)
    missing = None
    if texts and markers:
        missing = sum(1 for text in texts if not any(marker in text for marker in markers))
    return {"compaction_summaries": None if texts is None else len(texts),
            "compaction_fallbacks": None if texts is None else sum("deterministic fallback" in t for t in texts),
            "summaries_missing_assignment": missing, "assignment_markers": len(markers),
            "context_per_call": context_per_call(folder / "events.jsonl")}


def aggregate(values):
    """Group totals over runs' hygiene dicts: sums over runs that recorded a value (None when none did)."""
    values = [v for v in values if v]

    def total(key):
        known = [v[key] for v in values if v.get(key) is not None]
        return sum(known) if known else None
    contexts = [v["context_per_call"] for v in values if v.get("context_per_call")]
    units = sorted({c["unit"] for c in contexts})
    records = sum(c["records"] for c in contexts)
    return {"runs": len(values), "runs_with_session_database": sum(1 for v in values if v.get("compaction_summaries") is not None),
            "compaction_summaries": total("compaction_summaries"), "compaction_fallbacks": total("compaction_fallbacks"),
            "summaries_missing_assignment": total("summaries_missing_assignment"),
            "context_runs": len(contexts), "context_unit": units[0] if len(units) == 1 else ("mixed" if units else None),
            "context_mean_input_tokens": round(sum(c["mean_input_tokens"] * c["records"] for c in contexts) / records, 1)
            if records else None,
            "context_max_input_tokens": max(c["max_input_tokens"] for c in contexts) if contexts else None}
