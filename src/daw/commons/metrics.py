"""Evaluation metrics, cohorts, comparisons and cost accounting (M9.2–M9.4).

`run_metrics` rows are a disposable projection of runs/ files: each stores the
per-delivery metrics of `daw.commons.runmetrics` plus token telemetry and a
fingerprint of the files they were computed from. `refresh_metrics` (operator
CLI) is its only writer; views compute stale or missing rows in memory and never
write. Labels (participant, harness, task type, assignment) are read from board
rows at view time, so the projection holds only what the run files say.

A cohort is a named, explicit set of runs: its body lists every run id with the
request it answered and an assignment key (an explicit key, or the sha256 of the
request post's body text). Comparisons group runs by that key and keep criteria
separate: yield, calibration, corrections, cost. No composite score exists here.

Values a harness or record did not report are None ("unavailable"), never zero.
Counts are behaviour, not scientific value.
"""
import json
import re
import statistics
import tomllib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from daw import hermes
from daw.artifacts import reuse_links
from daw.commons.permissions import require
from daw.commons.runmetrics import run_metrics
from daw.community import PROVIDER_CITATION
from daw.util import DawError, canonical, digest, now, read_json

METRICS_VERSION = 1
# Files a run's metrics are computed from; size and mtime changes mark the projection stale.
RUN_FILES = ("events.jsonl", "execution.json", "final.md", "agent-state/state.db")


class _HarnessParsers(dict):
    """Stream parsers per harness name, looked up from the harness adapters (daw.harness)."""

    def get(self, name, default=None):
        from daw import harness
        try:
            return harness.get(name or harness.DEFAULT).parse
        except DawError:
            return default

    def __getitem__(self, name):
        parser = self.get(name)
        if parser is None:
            raise KeyError(name)
        return parser


# Run streams are parsed by the adapter of the agent's harness (default Hermes).
PARSERS = _HarnessParsers()
DIMENSIONS = ("cohort", "participant", "harness", "task_type")
CLAIM_STATUSES = ("supported", "descriptive", "untestable", "withdrawn")
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens")
LIMITATIONS = [
    "Counts are behaviour, not scientific value; read receipts and notebooks before claiming improvement.",
    "None means unavailable (not reported or not recorded); it is never zero.",
    "Wall time includes host sleep; monotonic time does not. Suspensions are wall-minus-monotonic gaps over 60 s.",
    "Minutes per executed analysis divide monotonic minutes by run_analysis.py invocations, failed ones included.",
    "Reuse links come from agent workspaces; links inherited by a fork (older than the fork) are excluded. "
    "Run-scoped groups count links and registrations whose workspace event falls inside one of their runs.",
    "Participant and harness panels count posts by author; cohort and task-type panels count posts made during their runs.",
    "Human marks are marks by human or operator participants; a mark is attribution, never a status change.",
    "Token totals and costs are given only when every run in the group reported them; partial sums are labelled.",
]
_RUN_CACHE, _POST_CACHE = {}, {}


# ---------------------------------------------------------------- per-run metrics (files only)

def run_folder(root, attempt):
    path = (Path(root) / attempt["path"]).resolve()
    if not path.is_relative_to(Path(root).resolve() / "runs"):
        raise DawError("unsafe_run_path", attempt["id"])
    return path


def fingerprint(folder):
    """Size and mtime of each metrics input, plus the metrics version; a change marks the row stale."""
    parts = [METRICS_VERSION]
    for name in RUN_FILES:
        path = folder / name
        stat = path.stat() if path.is_file() else None
        parts.append([name, stat.st_size if stat else None, stat.st_mtime_ns if stat else None])
    return digest(parts)


def token_usage(parsed):
    """Effective token counts. A completed turn that reports zero input and output tokens is a harness
    that emits zero for missing telemetry, so it is unavailable rather than free."""
    usage = parsed.get("usage")
    if not usage:
        return None, "harness reported no token telemetry"
    values = {key: usage.get(key) if type(usage.get(key)) is int else None for key in TOKEN_FIELDS}
    if values["input_tokens"] is None or values["output_tokens"] is None:
        return None, "harness did not report input and output tokens"
    if parsed["turns_completed"] and values["input_tokens"] == 0 and values["output_tokens"] == 0:
        return None, "harness reported zero tokens for a completed turn"
    return values, None


def compute_run(folder, harness="hermes"):
    """File-derived metrics for one delivery (no board rows): behaviour counts plus token telemetry."""
    parsed = PARSERS.get(harness, hermes.parse)(folder / "events.jsonl")
    metrics = {k: v for k, v in run_metrics(folder, parsed).items() if k != "limitations"}
    tokens, note = token_usage(parsed)
    metrics.update(turns_completed=parsed["turns_completed"], malformed_lines=len(parsed["malformed_lines"]),
                   usage_reported=parsed.get("usage"), tokens=tokens, tokens_note=note)
    return metrics


def current_metrics(folder, harness, stored=None):
    """Stored projection when its fingerprint matches the files; otherwise computed in memory (cached)."""
    mark = fingerprint(folder)
    if stored and stored.get("fingerprint") == mark and stored.get("version") == METRICS_VERSION:
        return stored["metrics"], True
    key = (str(folder), harness, mark)
    if key not in _RUN_CACHE:
        if len(_RUN_CACHE) > 4096:
            _RUN_CACHE.clear()
        _RUN_CACHE[key] = compute_run(folder, harness)
    return _RUN_CACHE[key], False


def refresh_metrics(board, actor="operator"):
    """Recompute projection rows whose run files changed (idempotent). One event when anything changed."""
    participant = board.agent(actor)
    require(board, participant, "cohort")
    with board.writer():
        stored = {r["run"]: r for r in board.rows("SELECT * FROM run_metrics")}
        primary = _primary_cohorts(board)
        agents = {a["id"]: json.loads(a["config"] or "{}") for a in board.rows("SELECT id,config FROM agent")}
        changed = []
        for attempt in board.rows("SELECT * FROM attempt ORDER BY created,id"):
            folder = run_folder(board.root, attempt)
            mark = fingerprint(folder)
            old = stored.get(attempt["id"])
            body = json.loads(old["metrics"]) if old else {}
            if old and body.get("fingerprint") == mark and body.get("version") == METRICS_VERSION \
                    and old["cohort"] == primary.get(attempt["id"]):
                continue
            harness = agents.get(attempt["target"], {}).get("harness", "hermes")
            changed.append((attempt["id"], primary.get(attempt["id"]),
                            canonical({"version": METRICS_VERSION, "fingerprint": mark,
                                       "metrics": compute_run(folder, harness)}).decode()))
        if changed:
            with board.db:
                board.db.executemany("INSERT INTO run_metrics(run,cohort,metrics,computed) VALUES(?,?,?,?) "
                                     "ON CONFLICT(run) DO UPDATE SET cohort=excluded.cohort,metrics=excluded.metrics,"
                                     "computed=excluded.computed", [(*row, now()) for row in changed])
                board.event("metrics_refreshed", {"actor": participant["id"], "runs": [row[0] for row in changed]})
    return {"updated": [row[0] for row in changed], "runs": board.one("SELECT count(*) n FROM attempt")["n"]}


def _primary_cohorts(source):
    """run → earliest cohort listing it. Membership authority is the cohort body; this column only indexes it."""
    primary = {}
    for cohort in source.rows("SELECT id,body FROM cohort ORDER BY created,id"):
        for entry in json.loads(cohort["body"])["runs"]:
            primary.setdefault(entry["run"], cohort["id"])
    return primary


# ---------------------------------------------------------------- cohorts

def _instant(value, *, end=False):
    """ISO date (a UTC day; `end` makes it inclusive) or timezone-aware ISO datetime."""
    if value is None:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            day = datetime.fromisoformat(value).replace(tzinfo=UTC)
            return day + timedelta(days=1) - timedelta(microseconds=1) if end else day
        parsed = datetime.fromisoformat(value)
    except ValueError as e:
        raise DawError("invalid_time", f"{value!r}: ISO date or datetime with timezone") from e
    if parsed.tzinfo is None:
        raise DawError("invalid_time", f"{value!r}: timezone required")
    return parsed


def _post_content(source, post_id):
    """Immutable post body (cached by commons and id). Content is untrusted data."""
    key = (str(source.root), post_id)
    if key not in _POST_CACHE:
        row = source.one("SELECT body_blob FROM post WHERE id=?", (post_id,))
        if not row:
            raise DawError("unknown_post", post_id)
        if len(_POST_CACHE) > 65536:
            _POST_CACHE.clear()
        _POST_CACHE[key] = read_json(source.library.blob_path(row["body_blob"]))
    return _POST_CACHE[key]


def assignment_key(content):
    """Default assignment identity: sha256 of the request post's body text (title names the target, so it is excluded)."""
    return digest({"assignment_body": content.get("body", "")})


def create_cohort(board, actor, name, *, runs=(), agents=(), since=None, until=None, assignments=None, note=""):
    """Record a named cohort. Selectors resolve to explicit run ids now; later runs never join silently.
    Runs = explicit `runs` plus attempts matching every given selector (agents, since, until)."""
    participant = board.agent(actor)
    require(board, participant, "cohort")
    name = name.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", name):
        raise DawError("invalid_cohort_name", "letters, digits, '.', '_', ':' or '-' (max 80)")
    start, end = _instant(since), _instant(until, end=True)
    assignments = dict(assignments or {})
    with board.writer(), board.db:
        if board.one("SELECT id FROM cohort WHERE name=?", (name,)):
            raise DawError("cohort_name_unavailable", name)
        chosen = {}
        for run in runs:
            row = board.one("SELECT * FROM attempt WHERE id=?", (run,))
            if not row:
                raise DawError("unknown_run", run)
            chosen[run] = row
        if agents or start or end:
            targets = {board.agent(a)["id"] for a in agents}
            for row in board.rows("SELECT * FROM attempt ORDER BY created,id"):
                created = datetime.fromisoformat(row["created"])
                if (not targets or row["target"] in targets) and (not start or created >= start) \
                        and (not end or created <= end):
                    chosen.setdefault(row["id"], row)
        if not chosen:
            raise DawError("empty_cohort", "no run matched")
        unknown = set(assignments) - set(chosen)
        if unknown:
            raise DawError("assignment_for_unlisted_run", ", ".join(sorted(unknown)))
        entries = []
        for row in sorted(chosen.values(), key=lambda r: (r["created"], r["id"])):
            request = board.one("SELECT post FROM request WHERE id=?", (row["request"],))
            explicit = assignments.get(row["id"])
            entries.append({"run": row["id"], "request": row["request"], "agent": row["target"],
                            "assignment": explicit or assignment_key(_post_content(board, request["post"])),
                            "assignment_source": "explicit" if explicit else "request_body_sha256"})
        identity = "cohort_" + uuid.uuid4().hex
        body = {"name": name, "runs": entries, "note": note, "created_by": participant["id"],
                "selector": {"runs": list(runs), "agents": list(agents), "since": since, "until": until}}
        board.db.execute("INSERT INTO cohort(id,name,body,created) VALUES(?,?,?,?)",
                         (identity, name, canonical(body).decode(), now()))
        board.event("cohort_created", {"cohort": identity, "name": name, "actor": participant["id"],
                                        "runs": [e["run"] for e in entries]})
    return cohort(board, identity)


def cohort(source, identity):
    row = source.one("SELECT * FROM cohort WHERE id=? OR name=?", (identity, identity))
    if not row:
        raise DawError("unknown_cohort", identity)
    return {**row, "body": json.loads(row["body"])}


def list_cohorts(source):
    return [{"id": c["id"], "name": c["name"], "created": c["created"], "runs": len(c["body"]["runs"]),
             "assignments": len({e["assignment"] for e in c["body"]["runs"]}), "note": c["body"].get("note", "")}
            for c in (cohort(source, r["id"]) for r in source.rows("SELECT id FROM cohort ORDER BY created,id"))]


# ---------------------------------------------------------------- read model (Archive)

def load_pricing(root):
    """Operator price table `<commons>/pricing.toml`, or None. Shape:
    currency = "USD"; [models."MODEL"] input, cached_input, output (per million tokens) and
    input_includes_cached (bool: whether the harness's input count already contains cached tokens)."""
    path = Path(root) / "pricing.toml"
    if not path.is_file():
        return {"available": False, "reason": "no pricing.toml in this commons"}
    try:
        data = tomllib.loads(path.read_text())
        currency, models = data["currency"], data["models"]
        if not isinstance(currency, str) or not isinstance(models, dict) or not models:
            raise ValueError("currency (string) and [models.*] tables are required")
        for model, price in models.items():
            for field in ("input", "cached_input", "output"):
                value = price.get(field)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    raise ValueError(f"models.{model}.{field} must be a non-negative number")
            if not isinstance(price.get("input_includes_cached"), bool):
                raise ValueError(f"models.{model}.input_includes_cached must be true or false")
    except (OSError, KeyError, ValueError, TypeError, tomllib.TOMLDecodeError) as e:
        return {"available": False, "reason": f"invalid pricing.toml: {e}"}
    return {"available": True, "currency": currency, "models": models}


def run_cost(tokens, model, pricing):
    """Currency cost of one run, or None when the price table, the model's price or the telemetry is missing."""
    if not pricing.get("available") or not tokens or model not in pricing["models"]:
        return None
    price = pricing["models"][model]
    cached = tokens.get("cached_input_tokens")
    if cached is None:
        return None
    fresh = tokens["input_tokens"] - cached if price["input_includes_cached"] else tokens["input_tokens"]
    if fresh < 0:
        return None
    return round((fresh * price["input"] + cached * price["cached_input"] + tokens["output_tokens"] * price["output"]) / 1e6, 6)


def task_type_of(request, content):
    """Request task type; untyped requests are legacy peer questions (or answer notifications)."""
    if request.get("task_type"):
        return request["task_type"]
    return "notification" if content.get("kind") == "answer_notification" else "peer_question"


def load_runs(view, pricing=None):
    """Every attempt with labels and metrics (stored projection when fresh, else computed in memory)."""
    pricing = pricing or load_pricing(view.root)
    stored = {r["run"]: json.loads(r["metrics"]) for r in view.rows("SELECT run,metrics FROM run_metrics")}
    agents = {a["id"]: {**a, "config": json.loads(a["config"] or "{}")} for a in view.rows("SELECT * FROM agent")}
    requests = {r["id"]: r for r in view.rows("SELECT * FROM request")}
    memberships = {}
    for c in view.rows("SELECT id,body FROM cohort ORDER BY created,id"):
        for entry in json.loads(c["body"])["runs"]:
            memberships.setdefault(entry["run"], []).append(c["id"])
    runs = []
    for attempt in view.rows("SELECT * FROM attempt ORDER BY created,id"):
        agent = agents[attempt["target"]]
        config = agent["config"]
        harness = config.get("harness", "hermes")
        request = requests[attempt["request"]]
        content = _post_content(view, request["post"])
        metrics, fresh = current_metrics(run_folder(view.root, attempt), harness, stored.get(attempt["id"]))
        runs.append({"run": attempt["id"], "request": attempt["request"], "state": attempt["state"],
                     "created": attempt["created"], "finished": attempt["finished"],
                     "participant": agent["id"], "participant_name": agent["name"], "harness": harness,
                     "model": config.get("model"), "effort": config.get("effort"),
                     "task_type": task_type_of(request, content), "request_kind": content.get("kind"),
                     "assignment": assignment_key(content), "cohorts": memberships.get(attempt["id"], []),
                     "projection": "stored" if fresh else ("stale" if attempt["id"] in stored else "missing"),
                     "metrics": metrics, "cost": run_cost(metrics.get("tokens"), config.get("model"), pricing)})
    return runs


def board_index(view, runs):
    """Posts, marks, claims and workspace links needed by the panels. Read-only."""
    agents = {a["id"]: a for a in view.rows("SELECT id,name,kind,created,trial FROM agent")}
    posts = []
    for row in view.rows("SELECT id,author,parent,supersedes,created FROM post ORDER BY seq"):
        content = _post_content(view, row["id"])
        posts.append({**row, "run": content.get("run"), "kind": content.get("kind"),
                      "provider_citation": bool(PROVIDER_CITATION.search(content.get("body", "")))})
    human = {a for a, row in agents.items() if row["kind"] in ("human", "operator")}
    marks = {}
    for m in view.rows("SELECT participant,target_id FROM mark WHERE target_kind='post'"):
        if m["participant"] in human:
            marks[m["target_id"]] = marks.get(m["target_id"], 0) + 1
    claims = {}
    for c in view.rows("SELECT post,status FROM claim"):
        claims.setdefault(c["post"], []).append(c["status"])
    superseded = {p["supersedes"] for p in posts if p["supersedes"]}
    links = []
    for identity, agent in agents.items():
        if agent["kind"] != "agent" or not agent["trial"]:
            continue
        try:
            ws = view.workspace(identity)
            times = {(r["question_id"], r["artifact_id"], r["relationship"]): r["created"] for r in ws.rows(
                "SELECT qa.question_id,qa.artifact_id,qa.relationship,e.created FROM question_artifact qa "
                "JOIN work_event e ON e.id=qa.event_id")}
            entries = reuse_links(ws)
        except DawError:
            continue  # a participant without a readable catalog contributes nothing, not zero links
        for entry in entries:
            created = times.get((entry["question"], entry["artifact"], entry["relationship"]))
            if created and created < agent["created"]:
                continue  # inherited by a fork: not this participant's reuse
            links.append({**entry, "participant": identity, "created": created})
    return {"posts": posts, "marks": marks, "claims": claims, "claims_recorded": bool(claims),
            "superseded": superseded, "links": links, "agents": agents}


def _total(values):
    present = [v for v in values if v is not None]
    return round(sum(present), 4) if present else None


def _ratio(numerator, denominator, digits=3):
    return round(numerator / denominator, digits) if numerator is not None and denominator else None


def _within(created, windows):
    if not created:
        return False
    stamp = datetime.fromisoformat(created)
    return any(start <= stamp <= end for start, end in windows)


def _windows(runs):
    out = []
    for r in runs:
        start = datetime.fromisoformat(r["created"])
        end = datetime.fromisoformat(r["finished"]) if r["finished"] else datetime.now(UTC)
        out.append((start, end))
    return out


def board_criteria(index, runs, *, authors=None):
    """Posts, corrections, human marks, calibration and links: by author when `authors` is given,
    else for posts made during `runs` and links recorded inside their time windows."""
    run_ids = {r["run"] for r in runs}
    windows = _windows(runs)
    if authors is not None:
        posts = [p for p in index["posts"] if p["author"] in authors]
        links = [link for link in index["links"] if link["participant"] in authors]
    else:
        posts = [p for p in index["posts"] if p["run"] in run_ids]
        participants = {r["participant"] for r in runs}
        links = [link for link in index["links"] if link["participant"] in participants and _within(link["created"], windows)]
    marks = sum(index["marks"].get(p["id"], 0) for p in posts)
    statuses = [s for p in posts for s in index["claims"].get(p["id"], [])]
    reused = [link for link in links if link["relationship"] == "reused"]
    backed = sum(1 for link in reused if link.get("backed"))
    return {"posts": len(posts), "corrections": sum(1 for p in posts if p["supersedes"]),
            "posts_superseded": sum(1 for p in posts if p["id"] in index["superseded"]),
            "human_marks": marks, "human_marks_per_post": _ratio(marks, len(posts)),
            "provider_citation_posts": sum(1 for p in posts if p["provider_citation"]),
            "registered_artifacts": sum(1 for link in links if link["relationship"] == "produced"),
            "reuse": {"backed": backed, "unbacked": len(reused) - backed, "backed_ratio": _ratio(backed, len(reused))},
            "claims": ({s: statuses.count(s) for s in CLAIM_STATUSES} | {"total": len(statuses)})
            if index["claims_recorded"] else None}


def cost_summary(runs, pricing):
    """Tokens and currency are totals only when every run reported them; otherwise None plus the partial sum."""
    reported = [r for r in runs if r["metrics"].get("tokens")]
    tokens = {}
    for field in TOKEN_FIELDS:
        values = [r["metrics"]["tokens"].get(field) for r in reported]
        known = [v for v in values if v is not None]
        complete = len(known) == len(runs) and runs
        tokens[field] = sum(known) if complete else None
        tokens[field + "_partial"] = None if complete or not known else sum(known)
    costs = [r["cost"] for r in runs if r["cost"] is not None]
    complete = len(costs) == len(runs) and runs
    reasons = sorted({r["metrics"].get("tokens_note") for r in runs if r["metrics"].get("tokens_note")})
    return {"runs": len(runs), "token_reported_runs": len(reported), "tokens": tokens,
            "unavailable_reasons": reasons,
            "compute_hours": _ratio(_total(r["metrics"].get("monotonic_seconds") for r in runs), 3600, 4),
            "currency": pricing.get("currency") if pricing.get("available") else None,
            "priced_runs": len(costs), "amount": round(sum(costs), 6) if complete else None,
            "amount_partial": None if complete or not costs else round(sum(costs), 6),
            "pricing": "available" if pricing.get("available") else pricing.get("reason")}


def run_criteria(runs):
    """Behaviour totals over runs (M9.1 criteria)."""
    m = [r["metrics"] for r in runs]
    mono = _total(x.get("monotonic_seconds") for x in m)
    analyses = sum(x["analysis_receipts"] for x in m)
    scripts = sum(x["scripts_written"] for x in m)
    tails = [x["minutes_after_last_successful_analysis"] for x in m if x.get("minutes_after_last_successful_analysis") is not None]
    return {"runs": len(runs), "completed": sum(r["state"] == "completed" for r in runs),
            "failed": sum(r["state"] == "failed" for r in runs),
            "wall_hours": _ratio(_total(x.get("wall_seconds") for x in m), 3600, 4),
            "monotonic_hours": _ratio(mono, 3600, 4),
            "suspensions": sum(1 for x in m if x["suspended_seconds"]),
            "suspended_hours": round(sum(x["suspended_seconds"] for x in m) / 3600, 4),
            "tool_calls": sum(x["tool_calls"] for x in m), "inbox_calls": sum(x["inbox_calls"] for x in m),
            "analysis_receipts": analyses, "analysis_failures": sum(x["analysis_failures"] for x in m),
            "minutes_per_executed_analysis": _ratio(mono / 60 if mono is not None else None, analyses, 3),
            "scripts_written": scripts, "plumbing_scripts": sum(x["plumbing_scripts"] for x in m),
            "plumbing_share": _ratio(sum(x["plumbing_scripts"] for x in m), scripts),
            "compactions": sum(x["compactions"] for x in m),
            "compaction_summaries": _total(x.get("compaction_summaries") for x in m),
            "compaction_fallbacks": _total(x.get("compaction_fallbacks") for x in m),
            "ceremony_tail_minutes": {"runs": len(tails), "median": round(statistics.median(tails), 1) if tails else None,
                                      "mean": round(statistics.fmean(tails), 1) if tails else None,
                                      "max": max(tails) if tails else None},
            "provider_citation_finals": sum(1 for x in m if x.get("provider_citation_in_final"))}


def bucket_of(created, bucket):
    stamp = datetime.fromisoformat(created).astimezone(UTC)
    if bucket == "day":
        return stamp.date().isoformat()
    year, week, _ = stamp.isocalendar()
    return f"{year}-W{week:02d}"


def trend(runs, bucket="week"):
    """Per day or ISO week: ceremony tail, compaction fallbacks and minutes per executed analysis."""
    if bucket not in ("day", "week"):
        raise DawError("invalid_bucket", "day or week")
    groups = {}
    for r in runs:
        groups.setdefault(bucket_of(r["created"], bucket), []).append(r)
    out = []
    for key in sorted(groups):
        c = run_criteria(groups[key])
        out.append({"bucket": key, "runs": c["runs"], "ceremony_tail_median": c["ceremony_tail_minutes"]["median"],
                    "compactions": c["compactions"], "compaction_fallbacks": c["compaction_fallbacks"],
                    "minutes_per_executed_analysis": c["minutes_per_executed_analysis"],
                    "monotonic_hours": c["monotonic_hours"]})
    return out


def group(label, key, runs, index, pricing, bucket, *, authors=None):
    return {"key": key, "label": label, **run_criteria(runs),
            "board": board_criteria(index, runs, authors=authors), "cost": cost_summary(runs, pricing),
            "trend": trend(runs, bucket), "posts_scope": "author" if authors is not None else "run"}


def select_runs(view, runs, *, cohort_id=None, participant=None, harness=None, task_type=None):
    if cohort_id:
        members = {e["run"] for e in cohort(view, cohort_id)["body"]["runs"]}
        runs = [r for r in runs if r["run"] in members]
    if participant:
        identity = view.participant(participant)["id"]
        runs = [r for r in runs if r["participant"] == identity]
    if harness:
        runs = [r for r in runs if r["harness"] == harness]
    if task_type:
        runs = [r for r in runs if r["task_type"] == task_type]
    return runs


def dashboard(view, *, cohort_id=None, participant=None, harness=None, task_type=None, bucket="week"):
    """Panels per cohort, participant, harness and task type over the filtered runs (M9.2)."""
    pricing = load_pricing(view.root)
    everything = load_runs(view, pricing)
    runs = select_runs(view, everything, cohort_id=cohort_id, participant=participant, harness=harness, task_type=task_type)
    index = board_index(view, runs)
    filtered = bool(cohort_id or participant or harness or task_type)
    agents = index["agents"]
    panels = {"cohort": [], "participant": [], "harness": [], "task_type": []}
    for c in list_cohorts(view):
        members = [r for r in runs if c["id"] in r["cohorts"]]
        if members:
            panels["cohort"].append(group(c["name"], c["id"], members, index, pricing, bucket))
    by_participant = {}
    for r in runs:
        by_participant.setdefault(r["participant"], []).append(r)
    if not filtered:  # people and agents with posts but no runs (humans) still have marks per post
        for p in index["posts"]:
            by_participant.setdefault(p["author"], [])
    for identity, members in by_participant.items():
        panels["participant"].append(group(agents[identity]["name"], identity, members, index, pricing, bucket,
                                           authors={identity}))
    for dimension in ("harness", "task_type"):
        keys = sorted({r[dimension] for r in runs})
        for key in keys:
            members = [r for r in runs if r[dimension] == key]
            authors = {r["participant"] for r in members} if dimension == "harness" else None
            panels[dimension].append(group(key, key, members, index, pricing, bucket, authors=authors))
    panels["participant"].sort(key=lambda g: g["label"])
    return {"sequence": view.sequence(), "bucket": bucket,
            "filters": {"cohort": cohort_id, "participant": participant, "harness": harness, "task_type": task_type},
            "options": {"cohorts": [{"id": c["id"], "name": c["name"]} for c in list_cohorts(view)],
                        "participants": [{"id": i, "name": n} for i, n in
                                         sorted({(r["participant"], r["participant_name"]) for r in everything})],
                        "harnesses": sorted({r["harness"] for r in everything}),
                        "task_types": sorted({r["task_type"] for r in everything})},
            "summary": group("all runs" if not filtered else "filtered runs", "all", runs, index, pricing, bucket,
                             authors=None if filtered else set(agents)),
            "panels": panels, "projection": _projection_state(everything),
            "pricing": {k: v for k, v in pricing.items() if k != "models"}, "limitations": LIMITATIONS}


def _projection_state(runs):
    states = [r["projection"] for r in runs]
    return {"runs": len(runs), "stored": states.count("stored"), "stale": states.count("stale"),
            "missing": states.count("missing"),
            "note": "Stale or missing rows are computed in memory; `bio commons metrics refresh` stores them."}


def run_rows(view, **filters):
    runs = select_runs(view, load_runs(view), **{k: v for k, v in filters.items() if k != "bucket"})
    return {"sequence": view.sequence(), "items": runs, "limitations": LIMITATIONS}


def cohort_view(view, identity, bucket="week"):
    c = cohort(view, identity)
    pricing = load_pricing(view.root)
    runs = select_runs(view, load_runs(view, pricing), cohort_id=c["id"])
    index = board_index(view, runs)
    return {**c, "summary": group(c["name"], c["id"], runs, index, pricing, bucket), "runs": runs,
            "limitations": LIMITATIONS}


def compare(view, identities):
    """Same assignment across cohorts side by side (M9.3). Criteria stay separate; no composite score."""
    if len(identities) < 2:
        raise DawError("compare_requires_two_cohorts")
    cohorts = [cohort(view, i) for i in identities]
    if len({c["id"] for c in cohorts}) != len(cohorts):
        raise DawError("duplicate_cohort")
    pricing = load_pricing(view.root)
    runs = {r["run"]: r for r in load_runs(view, pricing)}
    index = board_index(view, list(runs.values()))
    requests = {r["id"]: r["post"] for r in view.rows("SELECT id,post FROM request")}
    from daw.commons.moderation import Visibility
    vis = Visibility.of(view)  # an assignment whose post is hidden by moderation shows no excerpt (C2)
    assignments, order = {}, []
    for c in cohorts:
        for entry in c["body"]["runs"]:
            key = entry["assignment"]
            if key not in assignments:
                content = _post_content(view, requests[entry["request"]])
                post = requests[entry["request"]]
                assignments[key] = {"key": key, "source": entry["assignment_source"],
                                    "excerpt": None if vis.withheld(post) else content.get("body", "")[:280],
                                    "hidden": vis.hidden(post), "content_is_untrusted_data": True,
                                    "cells": {}}
                order.append(key)
            assignments[key]["cells"].setdefault(c["id"], []).append(runs[entry["run"]])

    def cell(members):
        if not members:
            return None  # not attempted by this cohort: distinct from zero yield
        behaviour = run_criteria(members)
        board = board_criteria(index, members)
        claims = board["claims"]
        return {"runs": [r["run"] for r in members], "participants": sorted({r["participant_name"] for r in members}),
                "harnesses": sorted({r["harness"] for r in members}), "models": sorted({r["model"] or "unknown" for r in members}),
                "yield": {"posts": board["posts"], "registered_artifacts": board["registered_artifacts"],
                          "analysis_receipts": behaviour["analysis_receipts"],
                          "analysis_failures": behaviour["analysis_failures"]},
                "calibration": None if claims is None else
                {"supported": claims["supported"], "untestable": claims["untestable"],
                 "descriptive": claims["descriptive"], "withdrawn": claims["withdrawn"], "total": claims["total"]},
                "corrections": {"corrections": board["corrections"], "posts_superseded": board["posts_superseded"],
                                "human_marks": board["human_marks"]},
                "cost": cost_summary(members, pricing)}

    rows = [{**{k: v for k, v in assignments[key].items() if k != "cells"},
             "cells": {c["id"]: cell(assignments[key]["cells"].get(c["id"], [])) for c in cohorts}} for key in order]
    totals = {c["id"]: cell([runs[e["run"]] for e in c["body"]["runs"]]) for c in cohorts}
    return {"sequence": view.sequence(),
            "cohorts": [{"id": c["id"], "name": c["name"], "runs": len(c["body"]["runs"]),
                         "harnesses": sorted({runs[e["run"]]["harness"] for e in c["body"]["runs"]}),
                         "models": sorted({runs[e["run"]]["model"] or "unknown" for e in c["body"]["runs"]})}
                        for c in cohorts],
            "criteria": ["yield", "calibration", "corrections", "cost"], "assignments": rows, "totals": totals,
            "shared_assignments": sum(1 for row in rows if all(row["cells"][c["id"]] for c in cohorts)),
            "claims_recorded": index["claims_recorded"], "pricing": {k: v for k, v in pricing.items() if k != "models"},
            "note": "No composite score: each criterion is reported separately. A missing cell means the cohort "
                    "did not attempt that assignment; calibration is unavailable until the claim ledger has rows.",
            "limitations": LIMITATIONS}


# ---------------------------------------------------------------- demo extension

def demo_cohort(board, ctx):
    """Demo: a cohort over every scripted demo delivery, with the metrics projection stored."""
    created = create_cohort(board, "operator", "demo-runs", agents=list(ctx["agents"].values()),
                            note="Every scripted delivery in the synthetic demo; numbers are fixtures.")
    refresh_metrics(board)
    ctx["cohorts"] = {"demo": created["id"]}
