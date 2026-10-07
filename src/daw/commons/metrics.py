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
import sqlite3
import statistics
import tomllib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from daw import hermes
from daw.artifacts import reuse_links
from daw.commons import economics
from daw.commons.permissions import require
from daw.commons.hygiene import aggregate as hygiene_totals
from daw.commons.hygiene import run_hygiene
from daw.commons.runmetrics import compactions_reported, run_metrics
from daw.community import PROVIDER_CITATION
from daw.util import DawError, canonical, digest, now, read_json

# 2: unavailable clocks, streams and compactions are None, never 0 (spec v2 C10).
# 3: compaction hygiene per run (spec v2 V8, daw.commons.hygiene).
# 4: overview and frontier reads per run (spec v3 V11).
# 5: the run's turn_economics.json record (spec v3 V13, daw.commons.economics).
METRICS_VERSION = 5
# Files a run's metrics are computed from; size and mtime changes mark the projection stale.
RUN_FILES = ("events.jsonl", "execution.json", "final.md", "agent-state/state.db", "prompt.txt", economics.FILE)


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
    "Compaction hygiene reads session databases (Hermes) and prompt.txt: a summary 'missing the assignment' names "
    "neither the request post nor the assignment key; context per call is what the stream reports (per call or per turn).",
    "Number coverage counts numbers in finals (answers of research deliveries) by the write-up checker's rules; "
    "line, claim, cell and text scopes are the author's pointers at the number, post scope is only the post's "
    "evidence list. verified_share counts the author's cell, claim and line pointers only; a text match (a value "
    "found once anywhere in a small output) and a person's curated pointer are counted apart, never as the author's.",
    "Turn economics (V13) are read from each run's turn_economics.json record; runs without one are counted as "
    "unrecorded, never as zero. " + " ".join(economics.LIMITATIONS),
    "Claims authoring (V1) counts ledger claims per post, evidence-carrying posts (artifacts or a notebook) with "
    "claims, refused final-answer claims blocks and the claims' pointer kinds and scopes (cell, key, line from the "
    "locator grammar; record without a locator; invalid for free-text locators).",
    "Frontier closure (v3 G1) counts non-withdrawn frontier items per completed question (its earliest holder's "
    "status) by kind; a final states a next step when its text names one, and matches when its author recorded a "
    "non-gap item during that delivery or the final names the item. Agent reads per turn count captured terminal "
    "commands (community inbox, search, overview, frontier/experiments).",
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


def compute_run(folder, harness="hermes", config=None):
    """File-derived metrics for one delivery (no board rows): behaviour counts plus token telemetry.
    Compactions are counted only for harnesses whose stream marks them (else None)."""
    parsed = PARSERS.get(harness, hermes.parse)(folder / "events.jsonl")
    metrics = {k: v for k, v in run_metrics(folder, parsed, compactions_reported=compactions_reported(harness, config)
                                            ).items() if k != "limitations"}
    tokens, note = token_usage(parsed)
    metrics.update(turns_completed=parsed["turns_completed"], malformed_lines=len(parsed["malformed_lines"]),
                   usage_reported=parsed.get("usage"), tokens=tokens, tokens_note=note,
                   hygiene=run_hygiene(folder, harness), turn_economics=economics.read(folder))
    return metrics


def current_metrics(folder, harness, stored=None, config=None):
    """Stored projection when its fingerprint matches the files; otherwise computed in memory (cached)."""
    mark = fingerprint(folder)
    if stored and stored.get("fingerprint") == mark and stored.get("version") == METRICS_VERSION:
        return stored["metrics"], True
    key = (str(folder), harness, mark, compactions_reported(harness, config))
    if key not in _RUN_CACHE:
        if len(_RUN_CACHE) > 4096:
            _RUN_CACHE.clear()
        _RUN_CACHE[key] = compute_run(folder, harness, config)
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
            config = agents.get(attempt["target"], {})
            harness = config.get("harness", "hermes")
            changed.append((attempt["id"], primary.get(attempt["id"]),
                            canonical({"version": METRICS_VERSION, "fingerprint": mark,
                                       "metrics": compute_run(folder, harness, config)}).decode()))
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
        metrics, fresh = current_metrics(run_folder(view.root, attempt), harness, stored.get(attempt["id"]), config)
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
        evidence = content.get("evidence") if isinstance(content.get("evidence"), dict) else {}
        posts.append({**row, "run": content.get("run"), "kind": content.get("kind"),
                      "provider_citation": bool(PROVIDER_CITATION.search(content.get("body", ""))),
                      # V1: a post that publishes evidence (artifacts or a notebook) is an analysis that should
                      # carry claims; a refused final-answer claims block is recorded in its evidence.
                      "has_evidence": bool(evidence.get("artifacts") or evidence.get("notebook")),
                      "claims_refused": bool(evidence.get("claims_refused"))})
    human = {a for a, row in agents.items() if row["kind"] in ("human", "operator")}
    marks = {}
    for m in view.rows("SELECT participant,target_id FROM mark WHERE target_kind='post'"):
        if m["participant"] in human:
            marks[m["target_id"]] = marks.get(m["target_id"], 0) + 1
    claims, claim_pointers = {}, {}
    for c in view.rows("SELECT post,status,pointers FROM claim"):
        claims.setdefault(c["post"], []).append(c["status"])
        claim_pointers.setdefault(c["post"], []).extend(json.loads(c["pointers"] or "[]"))
    superseded = {p["supersedes"] for p in posts if p["supersedes"]}
    # V13 useful data: claims with a verified number->claim pointer, and frontier items later promoted.
    from daw.commons import checks
    verified = checks.verified_claim_pointers(view)
    claim_rows = [{**c, "verified": c["id"] in verified}
                  for c in view.rows("SELECT id,post,status FROM claim WHERE status!='withdrawn'")]
    try:
        frontier = view.rows("SELECT id,author,created,status,promoted_to FROM frontier_item")
    except sqlite3.Error:
        frontier = []
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
            "claim_pointers": claim_pointers, "claim_rows": claim_rows, "frontier": frontier,
            "superseded": superseded, "links": links, "agents": agents, "numbers": _final_numbers(view)}


def _final_numbers(view):
    """Number coverage of every visible final (C11, V1): {answer post: checks.summarize(...)}."""
    from daw.commons import checks
    from daw.commons.moderation import Visibility
    vis = Visibility.of(view)  # hidden posts and refused write-ups count nothing (not zero)
    return {pid: checks.number_summary(view, pid) for pid in checks.finals(view)
            if not vis.withheld(pid) and not vis.refused(pid)}


def number_coverage(index, posts):
    """Share of numbers in the group's finals with the author's pointer at the number (cell, claim, line or text
    scope), the share the author's pointers verify (cell, claim or line: a text match, spec v3 B6, and a person's
    curated pointer, G2, never count), author pointers, curated pointers and unpointed numbers apart, and the full
    scope/status split. None when the group has no final (unavailable, never zero)."""
    from daw.commons.checks import NUMBER_LEVEL, SCOPES, STATUSES
    rows = [index["numbers"][p["id"]] for p in posts if p["id"] in index.get("numbers", {})]
    if not rows:
        return None
    total = sum(r["numbers"] for r in rows)
    scopes = {k: sum(r["scopes"][k] for r in rows) for k in SCOPES}
    statuses = {k: sum(r["statuses"][k] for r in rows) for k in STATUSES}
    level = sum(scopes[k] for k in NUMBER_LEVEL)
    pointers = {k: sum(r["pointers"][k] for r in rows) for k in ("author", "curated", "unpointed", "unlocatable")}
    author_verified = sum(r["author_verified"] for r in rows)
    return {"finals": len(rows), "numbers": total, "scopes": scopes, "statuses": statuses, "pointers": pointers,
            "number_level": level, "number_level_share": _ratio(level, total, 4),
            "claim_share": _ratio(scopes["claim"], total, 4), "cell_share": _ratio(scopes["cell"], total, 4),
            "author_verified": author_verified, "verified_share": _ratio(author_verified, total, 4),
            "text_verified": sum(r["text_verified"] for r in rows),
            "curated_verified": sum(r["curated_verified"] for r in rows),
            "curated_share": _ratio(pointers["curated"], total, 4)}


POINTER_KINDS = ("artifact", "locator", "post", "receipt", "accession")
POINTER_SCOPES = ("cell", "key", "line", "record", "invalid")


def pointer_scope(pointer):
    """Where a claim pointer points: a table cell, a JSON key or a line (from its locator, V2 grammar), the whole
    record (no locator), or `invalid` (a locator the grammar does not parse, e.g. free text from before V2)."""
    from daw.commons import locators
    text = pointer.get("locator") if isinstance(pointer, dict) else None
    if not text:
        return "record"
    try:
        return locators.target_kind(locators.parse_locator(text)) or "record"
    except locators.LocatorError:
        return "invalid"


def claims_authoring(index, posts):
    """V1: claims per post, the share of evidence-carrying posts (artifacts or a notebook) that state claims,
    refused final-answer claims blocks, and the kind and scope distribution of the claims' pointers. Counts
    are over the group's posts; None where the denominator is zero (unavailable, never zero)."""
    with_claims = [p for p in posts if index["claims"].get(p["id"])]
    evidence = [p for p in posts if p.get("has_evidence")]
    claims = sum(len(index["claims"].get(p["id"], [])) for p in posts)
    pointers = [x for p in posts for x in index.get("claim_pointers", {}).get(p["id"], [])]
    kinds = dict.fromkeys(POINTER_KINDS, 0)
    scopes = dict.fromkeys(POINTER_SCOPES, 0)
    for pointer in pointers:
        kind = pointer.get("kind") if isinstance(pointer, dict) else None
        if kind in kinds:
            kinds[kind] += 1
        scopes[pointer_scope(pointer)] += 1
    return {"posts": len(posts), "posts_with_claims": len(with_claims), "claims": claims,
            "claims_per_post": _ratio(claims, len(posts)),
            "evidence_posts": len(evidence),
            "evidence_posts_with_claims": sum(1 for p in evidence if index["claims"].get(p["id"])),
            "evidence_posts_with_claims_share": _ratio(sum(1 for p in evidence if index["claims"].get(p["id"])),
                                                       len(evidence), 4),
            "claims_refused": sum(1 for p in posts if p.get("claims_refused")),
            "pointers": len(pointers), "pointer_kinds": kinds, "pointer_scopes": scopes,
            "cell_pointer_share": _ratio(scopes["cell"], len(pointers), 4)}


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
            if index["claims_recorded"] else None,
            "numbers": number_coverage(index, posts), "authoring": claims_authoring(index, posts)}


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


READ_CALLS = ("inbox_calls", "forum_searches", "overview_calls", "frontier_reads")


def agent_reads(m):
    """V11: inbox, forum search, overview and frontier calls per turn (one delivery is one turn), from the captured
    terminal commands. A run whose stream (or this metrics version) lacks the count is left out of its mean."""
    out = {}
    for field in READ_CALLS:
        known = [x.get(field) for x in m if x.get(field) is not None]
        out[field] = sum(known) if known else None
        out[field + "_per_turn"] = _ratio(sum(known), len(known)) if known else None
    return out


def run_criteria(runs):
    """Behaviour totals over runs (M9.1 criteria). A total is None when no run recorded the value; runs
    that did not record it are left out of the sum rather than counted as zero (`*_unavailable_runs`)."""
    m = [r["metrics"] for r in runs]
    mono = _total(x.get("monotonic_seconds") for x in m)
    analyses = _total(x.get("analysis_receipts") for x in m)
    scripts = _total(x.get("scripts_written") for x in m)
    plumbing = _total(x.get("plumbing_scripts") for x in m)
    tails = [x["minutes_after_last_successful_analysis"] for x in m if x.get("minutes_after_last_successful_analysis") is not None]
    suspended = [x.get("suspended_seconds") for x in m]
    return {"runs": len(runs), "completed": sum(r["state"] == "completed" for r in runs),
            "failed": sum(r["state"] == "failed" for r in runs),
            "wall_hours": _ratio(_total(x.get("wall_seconds") for x in m), 3600, 4),
            "monotonic_hours": _ratio(mono, 3600, 4),
            "clock_unavailable_runs": sum(1 for s in suspended if s is None),
            "suspensions": sum(1 for s in suspended if s) if any(s is not None for s in suspended) else None,
            "suspended_hours": _ratio(_total(suspended), 3600, 4) if any(s is not None for s in suspended) else None,
            "tool_calls": _total(x.get("tool_calls") for x in m), "inbox_calls": _total(x.get("inbox_calls") for x in m),
            "agent_reads": agent_reads(m),
            "analysis_receipts": analyses, "analysis_failures": _total(x.get("analysis_failures") for x in m),
            "minutes_per_executed_analysis": _ratio(mono / 60 if mono is not None else None, analyses, 3),
            "scripts_written": scripts, "plumbing_scripts": plumbing,
            "plumbing_share": _ratio(plumbing, scripts),
            "compactions": _total(x.get("compactions") for x in m),
            "compaction_unavailable_runs": sum(1 for x in m if x.get("compactions") is None),
            "compaction_summaries": _total(x.get("compaction_summaries") for x in m),
            "compaction_fallbacks": _total(x.get("compaction_fallbacks") for x in m),
            "ceremony_tail_minutes": {"runs": len(tails), "median": round(statistics.median(tails), 1) if tails else None,
                                      "mean": round(statistics.fmean(tails), 1) if tails else None,
                                      "max": max(tails) if tails else None},
            "provider_citation_finals": sum(1 for x in m if x.get("provider_citation_in_final"))
            if any(x.get("provider_citation_in_final") is not None for x in m) else None,
            "compaction_hygiene": hygiene_totals(x.get("hygiene") for x in m)}


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


def useful_data(index, runs, board, *, authors=None):
    """V13: counts of useful data in a group's scope (by author when `authors` is given, else posts and items made
    during its runs): registered artifacts (from `board`), non-withdrawn claims with at least one verified
    number->claim pointer, and frontier items later promoted."""
    if authors is not None:
        posts = {p["id"] for p in index["posts"] if p["author"] in authors}
        items = [f for f in index.get("frontier", []) if f["author"] in authors]
    else:
        run_ids = {r["run"] for r in runs}
        posts = {p["id"] for p in index["posts"] if p["run"] in run_ids}
        participants, windows = {r["participant"] for r in runs}, _windows(runs)
        items = [f for f in index.get("frontier", []) if f["author"] in participants and _within(f["created"], windows)]
    return {"registered_artifacts": board["registered_artifacts"],
            "verified_claims": sum(1 for c in index.get("claim_rows", []) if c["post"] in posts and c["verified"]),
            "promoted_frontier_items": sum(1 for f in items if f["status"] == "promoted" or f.get("promoted_to"))}


def group(label, key, runs, index, pricing, bucket, *, authors=None):
    board = board_criteria(index, runs, authors=authors)
    return {"key": key, "label": label, **run_criteria(runs),
            "board": board, "cost": cost_summary(runs, pricing),
            "turn_economics": economics.criteria(runs, useful_data(index, runs, board, authors=authors)),
            "trend": trend(runs, bucket), "posts_scope": "author" if authors is not None else "run"}


def economics_panels(runs, index):
    """V13: turn economics per skill version (the digest of the skill text staged for each turn; `unrecorded` for
    turns captured before it was recorded) and the skills table (size, budget, reads per turn)."""
    versions = {}
    for r in runs:
        versions.setdefault(economics.skill_version_key(r), []).append(r)
    panels = []
    for key in sorted(versions, key=lambda k: (k == "unrecorded", k)):
        members = versions[key]
        board = board_criteria(index, members)
        panels.append({"key": key, "label": key, "first": min(r["created"] for r in members),
                       "harnesses": sorted({r["harness"] for r in members}),
                       "turn_economics": economics.criteria(members, useful_data(index, members, board))})
    return {"skill_versions": panels, "skills": economics.skill_table(runs), "limitations": economics.LIMITATIONS}


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
            "panels": panels, "economics": economics_panels(runs, index), "projection": _projection_state(everything),
            "frontier": frontier_closure(view),
            "pricing": {k: v for k, v in pricing.items() if k != "models"}, "limitations": LIMITATIONS}


NEXT_STEP = re.compile(r"next (?:computable )?(?:step|experiment|test|analysis)|discriminating (?:test|experiment)",
                       re.IGNORECASE)


def frontier_closure(view):
    """V3 G1: frontier items per completed question by kind, and the share of finals whose stated next step has a
    matching item. Items come from the frontier projection (withdrawn excluded); a question's status is its
    earliest holder's (forks copy questions). None where a denominator is zero (unavailable, never zero)."""
    from daw.commons import checks, frontier, views
    from daw.commons.moderation import Visibility
    holders = {}
    for agent in view.rows("SELECT id FROM agent WHERE trial IS NOT NULL ORDER BY created,id"):
        try:
            ws = view.workspace(agent["id"])
            rows = ws.rows("SELECT id,status FROM question") if ws else []
        except DawError:
            continue
        for row in rows:
            holders.setdefault(row["id"], (agent["id"], row["status"]))
    items = view.rows("SELECT id,author,question,kind,created,source FROM frontier_item WHERE status!='withdrawn'")
    by_question = {}
    for item in items:
        counts = by_question.setdefault(item["question"], dict.fromkeys(frontier.KINDS, 0))
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    completed = [{"question": q, "holder": a, "by_kind": by_question.get(q, dict.fromkeys(frontier.KINDS, 0))}
                 for q, (a, status) in sorted(holders.items()) if status == "completed"]
    for entry in completed:
        entry["non_gap"] = sum(v for k, v in entry["by_kind"].items() if k != "gap")
    kinds = {k: sum(e["by_kind"].get(k, 0) for e in completed) for k in frontier.KINDS}
    vis = Visibility.of(view)
    stated, matched = [], []
    for pid in checks.finals(view):
        if vis.withheld(pid) or vis.refused(pid):
            continue
        post = view.one("SELECT p.author,p.created,p.body_blob,a.created AS started FROM post p JOIN request r "
                        "ON r.answer=p.id LEFT JOIN attempt a ON a.id=r.active_run WHERE p.id=?", (pid,))
        body = views.content(view, post["body_blob"]).get("body") or "" if post else ""
        if not post or not NEXT_STEP.search(body):
            continue
        stated.append(pid)
        for item in items:
            if item["author"] != post["author"] or item["kind"] == "gap":
                continue
            event = (json.loads(item["source"] or "{}") or {}).get("event") or ""
            during = post["started"] and post["started"] <= item["created"] <= post["created"]
            if during or item["id"] in body or (event and event in body):
                matched.append(pid)
                break
    return {"completed_questions": len(completed),
            "completed_with_non_gap_item": sum(1 for e in completed if e["non_gap"]),
            "completed_with_non_gap_share": _ratio(sum(1 for e in completed if e["non_gap"]), len(completed), 4),
            "items_per_completed_question": {k: _ratio(v, len(completed)) for k, v in kinds.items()},
            "items_by_kind": kinds, "questions": completed,
            "finals_stating_next_step": len(stated), "finals_next_step_matched": len(matched),
            "finals_next_step_matched_share": _ratio(len(matched), len(stated), 4)}


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
