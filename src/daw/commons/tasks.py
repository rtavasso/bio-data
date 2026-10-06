"""Task types (M3.4) and request budgets (M2.7, M3.5).

A promotion or commission creates a request with one of these task types, a
target participant, a budget and an optional deadline. The vocabulary is fixed
here so the board, the runtime and the web app agree; prompt templates and
completion criteria per type live with the runtime.
"""
from datetime import datetime

from daw.util import DawError

TASK_TYPES = ("research", "review", "replication", "scouting", "writing", "digest")
# Studio commissions (M6) are the narrative/checking subset; research and scouting come from promotions.
COMMISSION_TYPES = ("review", "replication", "writing", "digest")
BUDGET_FIELDS = ("minutes", "tokens", "download_bytes")


def check_task_type(task_type, allowed=TASK_TYPES):
    if task_type not in allowed:
        raise DawError("invalid_task_type", f"use one of {', '.join(allowed)}")
    return task_type


def normalize_budget(budget):
    """Positive integer limits; a missing field means no limit for that resource. Never zero-as-unknown."""
    budget = dict(budget or {})
    unknown = set(budget) - set(BUDGET_FIELDS)
    if unknown:
        raise DawError("invalid_budget", f"unknown fields {', '.join(sorted(unknown))}")
    clean = {}
    for key in BUDGET_FIELDS:
        value = budget.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise DawError("invalid_budget", f"{key} must be a positive integer")
        clean[key] = value
    return clean


def check_deadline(deadline):
    if deadline is None:
        return None
    try:
        parsed = datetime.fromisoformat(deadline)
    except (TypeError, ValueError) as e:
        raise DawError("invalid_deadline", "ISO 8601 with timezone") from e
    if parsed.tzinfo is None:
        raise DawError("invalid_deadline", "timezone required")
    return parsed.isoformat()
