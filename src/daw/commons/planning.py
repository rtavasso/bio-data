"""Frontier as the planning surface (spec v2 V5): the board view, shared experiments and the wishlist proposal.

- **Board view.** Frontier items by state in five columns (open, blocked, candidate evidence, promoted,
  closed) with the request each promotion created (target, task type, budget, deadline, state), budget
  totals and targets per column, and the reader's own allowance. "Blocked" is an open item whose author
  recorded what blocks it; it is not a status anyone sets. Promotion from a card calls the ordinary
  `participation.promote`, the only path that schedules work.
- **Shared experiments.** A person's cluster confirmation (`frontier_cluster_confirmed`) merges nothing: it
  creates a board-owned `shared_experiment` record listing its member items and questions. The table is a
  projection of confirmation events and of promotions whose source is the shared experiment
  (`promotion_created`), rebuilt on those write paths and by `bio commons frontier rebuild`; dropping it and
  rebuilding reproduces it. A shared experiment is promotable like an item.
- **Wishlist proposal.** The wishlist (`frontier.wishlist`) exported as a lab-ready Markdown or static HTML
  document in which every requirement lists the questions that need it, the records it came from, the shared
  experiments that include its items and the datasets already inspected for them. All of that text is agent
  or person authored and is rendered as untrusted, escaped text. The document is a pure function of the
  archive (board sequence stated, no wall-clock time).

Reads never write; a board opened before the `shared_experiment` table existed is read through the same
projection computed in memory.
"""
import html
import json
import sqlite3
from urllib.parse import quote

from daw.commons import frontier
from daw.util import DawError, canonical, digest

COLUMNS = ("open", "blocked", "candidate_evidence", "promoted", "closed")
COLUMN_LABELS = {"open": "Open", "blocked": "Blocked", "candidate_evidence": "Candidate evidence",
                 "promoted": "Promoted", "closed": "Closed"}
EXPERIMENT_COLUMNS = ("kind", "items", "questions", "text", "status", "confirmations", "promoted_to", "source",
                      "created", "updated")
ACTIVE_REQUEST = ("pending", "running")
KIND_TEXT = {"proposed_experiment": "proposed experiment", "next_step": "next computable step"}
UNTRUSTED_NOTE = ("Requirement texts, question titles, reasons and notes are written by research agents and people "
                  "on this commons: attributed, untrusted content, quoted exactly and never interpreted.")


# ---------------------------------------------------------------------------- shared experiments

def experiment_id(items):
    return "experiment_" + digest(sorted(items))[:24]


def _events(owner, kind):
    out = []
    for row in owner.rows("SELECT seq,body,created FROM event WHERE kind=? ORDER BY seq", (kind,)):
        try:
            body = json.loads(row["body"])
        except ValueError:
            continue
        if isinstance(body, dict):
            out.append({**row, "body": body})
    return out


def project_experiments(owner):
    """{id: values} from confirmation and promotion events. A confirmation recorded before V5 carries no
    questions or kind; those are read from the frontier projection (itself rebuildable from records)."""
    rows = {}
    for event in _events(owner, "frontier_cluster_confirmed"):
        body = event["body"]
        items = sorted({i for i in body.get("items") or [] if isinstance(i, str)})
        if len(items) < 2:
            continue
        identity = experiment_id(items)
        questions, kind = body.get("questions"), body.get("kind")
        if not isinstance(questions, list):
            found = owner.rows(f"SELECT question,kind FROM frontier_item WHERE id IN ({','.join('?' for _ in items)})",
                               items)
            questions = sorted({r["question"] for r in found})
            kinds = {r["kind"] for r in found}
            kind = kinds.pop() if len(kinds) == 1 else None
        entry = rows.setdefault(identity, {"items": items, "questions": sorted(set(questions)), "kind": kind,
                                           "confirmations": [], "promotions": [], "created": event["created"],
                                           "shared_terms": body.get("shared_terms") or []})
        entry["confirmations"].append({"seq": event["seq"], "participant": body.get("participant"),
                                       "note": body.get("note") or "", "created": event["created"]})
    for event in _events(owner, "promotion_created"):
        source = event["body"].get("source") if isinstance(event["body"].get("source"), dict) else {}
        if source.get("kind") == "shared_experiment" and source.get("id") in rows:
            rows[source["id"]]["promotions"].append({"request": event["body"].get("request"),
                                                     "actor": event["body"].get("actor"), "event_seq": event["seq"],
                                                     "created": event["created"]})
    out = {}
    for identity, entry in rows.items():
        promotion = entry["promotions"][-1] if entry["promotions"] else None
        label = KIND_TEXT.get(entry["kind"], "experiment")
        terms = entry["shared_terms"]
        text = (f"Shared {label} confirmed across {len(entry['questions'])} questions"
                + (f" (shared terms: {', '.join(terms)})" if terms else ""))
        times = [c["created"] for c in entry["confirmations"]] + [p["created"] for p in entry["promotions"]]
        out[identity] = {"kind": entry["kind"], "items": canonical(entry["items"]).decode(),
                         "questions": canonical(entry["questions"]).decode(), "text": text,
                         "status": "promoted" if promotion else "open",
                         "confirmations": canonical(entry["confirmations"]).decode(),
                         "promoted_to": promotion["request"] if promotion else None,
                         "source": canonical({"shared_terms": terms, "promotions": entry["promotions"],
                                              "events": [c["seq"] for c in entry["confirmations"]]}).decode(),
                         "created": entry["created"], "updated": max(times)}
    return out


def rebuild_experiments(board, *, reason=None):
    """Bring the shared_experiment projection up to date. Caller holds `board.writer()` (the confirmation and
    promotion write paths, and `bio commons frontier rebuild`). Emits an event only when rows changed."""
    rows = project_experiments(board)
    existing = {r["id"]: r for r in board.rows("SELECT * FROM shared_experiment")}
    orphaned = sorted(set(existing) - set(rows))
    changed = 0
    with board.db:
        for identity, values in rows.items():
            old = existing.get(identity)
            if old and all(old[c] == values[c] for c in EXPERIMENT_COLUMNS):
                continue
            changed += 1
            board.db.execute("INSERT INTO shared_experiment(id," + ",".join(EXPERIMENT_COLUMNS) + ") VALUES(?,"
                             + ",".join("?" for _ in EXPERIMENT_COLUMNS) + ") ON CONFLICT(id) DO UPDATE SET "
                             + ",".join(f"{c}=excluded.{c}" for c in EXPERIMENT_COLUMNS),
                             [identity] + [values[c] for c in EXPERIMENT_COLUMNS])
        if orphaned:
            board.db.execute(f"DELETE FROM shared_experiment WHERE id IN ({','.join('?' for _ in orphaned)})", orphaned)
        if changed or orphaned:
            board.event("shared_experiments_reindexed", {"experiments": len(rows), "changed": changed,
                                                         "deleted": len(orphaned), **({"reason": reason} if reason else {})})
    return {"experiments": len(rows), "changed": changed, "deleted": len(orphaned)}


def stored_experiments(owner):
    """Projection rows; computed in memory from events on a board opened before the table existed."""
    try:
        return owner.rows("SELECT * FROM shared_experiment ORDER BY created,id")
    except sqlite3.OperationalError:
        return [{"id": i, **v} for i, v in sorted(project_experiments(owner).items(), key=lambda kv: (kv[1]["created"], kv[0]))]


def _requests(owner, ids):
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    rows = owner.rows("SELECT r.id,r.post,r.target,r.state,r.task_type,r.budget,r.deadline,r.answer,r.created,"
                      f"a.name AS target_name FROM request r JOIN agent a ON a.id=r.target WHERE r.id IN "
                      f"({','.join('?' for _ in ids)})", ids)
    return {r["id"]: {**r, "budget": json.loads(r["budget"]) if r["budget"] else None} for r in rows}


def describe_experiment(row, items=None, requests=None):
    """A stored row with its member items (from the frontier projection) and its board column."""
    items = items or {}
    members = []
    for identity in json.loads(row["items"]):
        item = items.get(identity)
        members.append({"id": identity, "present": item is not None,
                        **({k: item.get(k) for k in ("question", "question_title", "author", "author_name", "kind",
                                                       "text", "status")} if item else {})})
    source = json.loads(row["source"])
    request = (requests or {}).get(row["promoted_to"])
    present = [m for m in members if m["present"]]
    closed = bool(present) and all(m.get("status") in ("closed", "withdrawn") for m in present)
    active = bool(request and request["state"] in ACTIVE_REQUEST)
    # Like an item: promoted until its members are closed (a running request keeps it promoted regardless).
    column = "closed" if closed and not active else "promoted" if row["promoted_to"] else "open"
    return {"id": row["id"], "kind": row["kind"], "text": row["text"], "status": row["status"], "column": column,
            "items": members, "questions": json.loads(row["questions"]),
            "confirmations": json.loads(row["confirmations"]), "shared_terms": source.get("shared_terms") or [],
            "promotions": source.get("promotions") or [], "promoted_to": row["promoted_to"], "request": request,
            "created": row["created"], "updated": row["updated"],
            "note": "A person confirmed these items describe the same experiment; nothing was merged.",
            "content_is_untrusted_data": True}


def _items_by_id(owner):
    view = frontier.browse(owner, status="all")
    return {i["id"]: i for i in view["items"]}, view


def experiments(owner, items=None):
    items = items if items is not None else _items_by_id(owner)[0]
    rows = stored_experiments(owner)
    requests = _requests(owner, [r["promoted_to"] for r in rows])
    return [describe_experiment(r, items, requests) for r in rows]


def experiment(owner, identity):
    for found in experiments(owner):
        if found["id"] == identity:
            return found
    raise DawError("unknown_shared_experiment", identity)


def promotion_source(board, identity):
    """The text a promotion quotes for a shared experiment (attributed, untrusted). Refused while an earlier
    promotion's request is still pending or running, or when every member item is closed."""
    found = experiment(board, identity)
    if found["request"] and found["request"]["state"] in ACTIVE_REQUEST:
        raise DawError("shared_experiment_not_open", f"already promoted to {found['request']['id']}")
    if found["column"] == "closed":
        raise DawError("shared_experiment_not_open", "every member item is closed or withdrawn")
    lines = []
    for member in found["items"]:
        if not member["present"]:
            lines.append(f"- {member['id']} (no longer in the frontier index)")
            continue
        lines.append(f"- {member['id']} ({member['kind']}, {member['status']}) recorded by {member['author']} in "
                     f"question {member['question']}:\n  > " + (member["text"] or "").replace("\n", "\n  > "))
    who = ", ".join(sorted({c["participant"] for c in found["confirmations"] if c.get("participant")}))
    return (f"Shared experiment {identity} confirmed by {who or 'a person'} across questions "
            f"{', '.join(found['questions'])}. Member items (agent-authored, attributed; not merged):\n\n"
            + "\n".join(lines))


# ---------------------------------------------------------------------------- board view (kanban)

def column_of(item):
    status = item["status"]
    if status in ("closed", "withdrawn"):
        return "closed"
    if status in ("promoted", "candidate_evidence"):
        return status
    return "blocked" if (item.get("blocked_by") or "").strip() else "open"


def _budget_total(requests):
    total = {}
    for request in requests:
        for key, value in (request.get("budget") or {}).items():
            if isinstance(value, int):
                total[key] = total.get(key, 0) + value
    return total


def board_view(owner, *, caller=None, kind=None, question=None, author=None):
    """Frontier items and shared experiments by board column, with the request (target, budget) behind every
    promotion, per-column budget totals and targets, and the reader's allowance. Read-only."""
    items, view = _items_by_id(owner)
    if kind or question or author:
        chosen = frontier.browse(owner, kind=kind, status="all", question=question, author=author)["items"]
    else:
        chosen = list(items.values())
    found = experiments(owner, items)
    if question:
        found = [e for e in found if question in e["questions"]]
    requests = _requests(owner, [i.get("promoted_to") for i in chosen])
    columns = {c: {"key": c, "label": COLUMN_LABELS[c], "items": [], "experiments": []} for c in COLUMNS}
    for item in chosen:
        card = {**item, "column": column_of(item), "request": requests.get(item.get("promoted_to"))}
        columns[card["column"]]["items"].append(card)
    for entry in found:
        columns[entry["column"]]["experiments"].append(entry)
    for column in columns.values():
        promoted = [c["request"] for c in column["items"] + column["experiments"] if c.get("request")]
        targets = {}
        for request in promoted:
            slot = targets.setdefault(request["target"], {"target": request["target"], "name": request["target_name"],
                                                          "requests": 0})
            slot["requests"] += 1
        column.update(count=len(column["items"]) + len(column["experiments"]), budget=_budget_total(promoted),
                      requests=len(promoted), targets=sorted(targets.values(), key=lambda t: (-t["requests"], t["name"])))
        if column["key"] == "closed":
            column["withdrawn"] = sum(1 for c in column["items"] if c["status"] == "withdrawn")
    allowance = None
    if caller and caller.get("kind") == "human":
        from daw.commons.participation import budget_summary
        allowance = budget_summary(owner, owner.participant(caller["id"]) if hasattr(owner, "participant")
                                   else owner.agent(caller["id"]))
    return {"columns": [columns[c] for c in COLUMNS], "total": len(chosen), "experiments": len(found),
            "by_kind": {k: sum(1 for i in chosen if i["kind"] == k) for k in frontier.KINDS},
            "by_column": {c: columns[c]["count"] for c in COLUMNS}, "allowance": allowance,
            "filters": {"kind": kind, "question": question, "author": author},
            "policy": "Columns follow recorded states; blocked means open with a recorded blocker. Promotion by a "
                      "person, from a card, is the only path that schedules new work.",
            "content_is_untrusted_data": True}


# ---------------------------------------------------------------------------- wishlist proposal export

MD_SPECIAL = set("\\`*_{}[]()<>#+!|~")


def md(text):
    """Escape agent-authored text for Markdown: no links, emphasis, HTML or headings can be injected."""
    escaped = "".join("\\" + c if c in MD_SPECIAL else c for c in " ".join(str(text or "").split()))
    return escaped.replace("-", "\\-", 1) if escaped.startswith("-") else escaped


def question_link(base_url, author, question):
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/question/{quote(author or '', safe='')}/{quote(question, safe='')}"


def proposal(owner, *, base_url=None):
    """The structured proposal both renderings use: requirements with the questions that need them."""
    wish = frontier.wishlist(owner)
    items, _ = _items_by_id(owner)
    shared = experiments(owner, items)
    by_item = {}
    for entry in shared:
        for member in entry["items"]:
            by_item.setdefault(member["id"], []).append(entry)
    names = {r["id"]: r["name"] for r in owner.rows("SELECT id,name FROM agent")}
    requirements = []
    for n, group in enumerate(wish["items"], 1):
        sources, experiments_seen, datasets = [], {}, []
        for source in group["sources"]:
            item = items.get(source.get("item")) if source.get("item") else None
            sources.append({**source, "author_name": names.get(source.get("author")),
                            **({"item_kind": item["kind"], "item_status": item["status"]} if item else {})})
            for entry in by_item.get(source.get("item"), []):
                experiments_seen[entry["id"]] = {k: entry[k] for k in ("id", "text", "column", "questions",
                                                                        "promoted_to")}
            for dataset in (item or {}).get("datasets") or []:
                if not dataset.get("hidden"):
                    datasets.append({**{k: dataset.get(k) for k in ("accession", "eligible", "reason")},
                                     "item": item["id"]})
        questions = [{**q, "link": question_link(base_url, q["author"], q["question"])} for q in group["questions"]]
        requirements.append({"n": n, "text": group["text"], "normalized": group["normalized"],
                             "distinct_questions": group["distinct_questions"], "questions": questions,
                             "sources": sources, "shared_experiments": list(experiments_seen.values()),
                             "datasets_inspected": datasets})
    return {"title": "Dataset wishlist: a proposal for data generation", "sequence": owner.sequence(),
            "requirements": requirements, "total": len(requirements),
            "questions": len({q["question"] for r in requirements for q in r["questions"]}),
            "grouping": wish["grouping"], "untrusted": UNTRUSTED_NOTE, "content_is_untrusted_data": True}


def _source_text(source):
    if source["kind"] == "labbook":
        return f"LABBOOK line {source.get('line')} of notebook snapshot {source.get('snapshot')}"
    label = "retrieval gap" if source["kind"] == "gap" else "frontier item"
    return (f"{label} {source.get('item')}" + (f" ({source.get('item_kind')}, {source.get('item_status')})"
                                               if source.get("item_kind") else ""))


def render_markdown(doc):
    out = [f"# {doc['title']}", "",
           f"Exported from board sequence {doc['sequence']}: {doc['total']} requirements needed by "
           f"{doc['questions']} distinct questions, most-needed first. Requirements are exact missing-measurement "
           f"statements grouped by {doc['grouping']}.", "", f"> {doc['untrusted']}", ""]
    if not doc["requirements"]:
        out += ["No missing measurements are recorded on this commons.", ""]
    for req in doc["requirements"]:
        count = req["distinct_questions"]
        out += [f"## {req['n']}. {md(req['text'])}", "",
                f"Needed by {count} question{'s' if count != 1 else ''}:", ""]
        for q in req["questions"]:
            title = md(q.get("title") or q["question"])
            label = f"[{title}]({q['link']})" if q.get("link") else title
            out.append(f"- {label} (`{q['question']}`, researcher {md(q.get('author_name') or q['author'])})")
        out += ["", "Recorded as:", ""]
        out += [f"- {_source_text(s)} by {md(s.get('author_name') or s.get('author'))} in `{s['question']}`"
                for s in req["sources"]]
        if req["shared_experiments"]:
            out += ["", "Shared experiments that include it (confirmed by a person; nothing merged):", ""]
            out += [f"- `{e['id']}` ({e['column'].replace('_', ' ')}): {md(e['text'])}" for e in req["shared_experiments"]]
        if req["datasets_inspected"]:
            out += ["", "Datasets already inspected for it:", ""]
            out += [f"- `{md(d['accession'])}`: {'eligible' if d['eligible'] else 'rejected'}: {md(d['reason'])}"
                    for d in req["datasets_inspected"]]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


CSS = ("body{font:15px/1.5 system-ui,sans-serif;max-width:52rem;margin:2rem auto;padding:0 1rem;color:#1d1d1f}"
       "h1{font-size:1.6rem}h2{font-size:1.15rem;margin-top:2rem;border-top:1px solid #ddd;padding-top:1rem}"
       ".untrusted{border-left:3px solid #c80;padding:.2rem .8rem;background:#fff8ec}.muted{color:#666}"
       "code{font-size:.9em}ul{padding-left:1.3rem}")


def render_html(doc):
    e = html.escape
    parts = ["<!doctype html>", "<html lang=\"en\"><head><meta charset=\"utf-8\">",
             "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
             f"<title>{e(doc['title'])}</title><style>{CSS}</style></head><body>",
             f"<h1>{e(doc['title'])}</h1>",
             f"<p>Exported from board sequence {doc['sequence']}: {doc['total']} requirements needed by "
             f"{doc['questions']} distinct questions, most-needed first. Requirements are exact missing-measurement "
             f"statements grouped by {e(doc['grouping'])}.</p>",
             f"<p class=\"untrusted\">{e(doc['untrusted'])}</p>"]
    if not doc["requirements"]:
        parts.append("<p>No missing measurements are recorded on this commons.</p>")
    for req in doc["requirements"]:
        count = req["distinct_questions"]
        parts.append(f"<section><h2>{req['n']}. <span class=\"untrusted-text\">{e(req['text'])}</span></h2>")
        parts.append(f"<p>Needed by {count} question{'s' if count != 1 else ''}:</p><ul>")
        for q in req["questions"]:
            title = e(q.get("title") or q["question"])
            label = f"<a href=\"{e(q['link'], quote=True)}\">{title}</a>" if q.get("link") else title
            parts.append(f"<li>{label} (<code>{e(q['question'])}</code>, researcher "
                         f"{e(q.get('author_name') or q['author'])})</li>")
        parts.append("</ul><p>Recorded as:</p><ul>")
        parts += [f"<li>{e(_source_text(s))} by {e(s.get('author_name') or s.get('author') or '')} in "
                  f"<code>{e(s['question'])}</code></li>" for s in req["sources"]]
        parts.append("</ul>")
        if req["shared_experiments"]:
            parts.append("<p>Shared experiments that include it (confirmed by a person; nothing merged):</p><ul>")
            parts += [f"<li><code>{e(x['id'])}</code> ({e(x['column'].replace('_', ' '))}): {e(x['text'])}</li>"
                      for x in req["shared_experiments"]]
            parts.append("</ul>")
        if req["datasets_inspected"]:
            parts.append("<p>Datasets already inspected for it:</p><ul>")
            parts += [f"<li><code>{e(d['accession'] or '')}</code>: {'eligible' if d['eligible'] else 'rejected'}: "
                      f"{e(d['reason'] or '')}</li>" for d in req["datasets_inspected"]]
            parts.append("</ul>")
        parts.append("</section>")
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


FORMATS = {"md": ("text/markdown; charset=utf-8", render_markdown), "html": ("text/html; charset=utf-8", render_html)}


def export_wishlist(owner, fmt="md", *, base_url=None):
    """(text, media type) of the wishlist proposal in Markdown or static HTML (no scripts)."""
    if fmt not in FORMATS:
        raise DawError("invalid_export_format", "md or html")
    if base_url is not None and not (isinstance(base_url, str) and base_url.startswith(("http://", "https://"))
                                     and len(base_url) <= 500):
        raise DawError("invalid_base_url", "an absolute http(s) URL of the commons")
    media, render = FORMATS[fmt]
    return render(proposal(owner, base_url=base_url)), media
