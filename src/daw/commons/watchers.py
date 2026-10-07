"""Watchers (M5.2, Flow C): scoped discovery queries that bring new evidence to open items.

A frontier item (an open question, gap, proposed experiment, ...) can carry a
discovery query `{query, filters}` against one adapter provider. The operator runs
`bio commons watch tick` from cron or a systemd timer (weekly is the intended
cadence; the minimum interval is one hour). A tick re-runs each due query through
`daw.adapters.Sources.discover` in a scratch discovery workspace under the commons
(`<commons>/watchers/workspace`, an ordinary bio workspace that holds the catalog
writes; agent workspaces are never touched), copies the provider responses into
the library, and records an immutable `watcher_run` with the receipt and every
accession found. Accessions not seen in earlier runs of the same watcher produce a
notice to the item's author ("New evidence may fit <item>") and move an open item
to `candidate_evidence`. That is all: retrieval only. Whether a hit fits the item
is the author's decision, recorded in their notebook; a watcher never closes an
item, never schedules work and never reads the hits as evidence.

`filters` are literal top-level field equalities applied to the returned hits
(e.g. `{"source": "MED"}`); they never rewrite the provider query.

The `europepmc-fulltext` watcher is the "new full text for a known article" watcher:
its query names one article (PMID, PMCID or DOI) and each run asks Europe PMC
whether full text is now available for it. Full text that was not available in an
earlier run produces a notice ("New full text may fit <item>") that says how to
fetch it (`bio data fulltext PMCID`); the watcher never downloads the article.

Titles in notices and receipts are provider-supplied third-party text and are
labelled so; they are never read as instructions or as evidence.
"""
import json
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

from daw.adapters import EPMC, VERSION, Sources
from daw.catalog import Workspace
from daw.commons.notices import notify
from daw.commons.permissions import require
from daw.community import PROVIDER_CITATION
from daw.models import Discovery
from daw.transport import Transport
from daw.util import DawError, canonical, digest, now

WEEK = 7 * 24 * 3600
MIN_INTERVAL = 3600
FULLTEXT = "europepmc-fulltext"
PROVIDERS = Discovery.model_fields["provider"].annotation.__args__ + (FULLTEXT,)
TITLE_FIELDS = ("title", "name", "description", "fields")
THIRD_PARTY = "provider-supplied title, third-party text"
ARTICLE_REFERENCE = re.compile(r'(?i)^\s*(?:(?:pmcid:)?(pmc\d+)|(?:pmid:|ext_id:)?(\d+)|(?:doi:)?(10\.\d{4,9}/[^\s"]+))\s*$')


def article_reference(text):
    """Canonical `PMCID:PMC…`, `PMID:…` or `DOI:10.…` for the full-text watcher; anything else is refused."""
    match = ARTICLE_REFERENCE.match(text or "")
    if not match:
        raise DawError("invalid_watcher_query", "the full-text watcher names one article: PMID, PMCID or DOI")
    pmcid, pmid, doi = match.groups()
    return f"PMCID:{pmcid.upper()}" if pmcid else f"PMID:{pmid}" if pmid else f"DOI:{doi}"


def workspace_path(root):
    return Path(root) / "watchers" / "workspace"


def open_workspace(root):
    """The scratch discovery workspace for watcher queries (created on first use)."""
    path = workspace_path(root)
    return Workspace(path) if (path / "catalog.sqlite").is_file() else Workspace.create(path)


def _participant(board, actor):
    return actor if isinstance(actor, dict) else board.agent(actor)


def normalize_query(query, provider):
    """`query` is text or {query, filters, max_pages, page_size}; returns the stored canonical form."""
    spec = {"query": query} if isinstance(query, str) else dict(query or {})
    unknown = set(spec) - {"query", "filters", "max_pages", "page_size"}
    if unknown:
        raise DawError("invalid_watcher_query", f"unknown fields {', '.join(sorted(unknown))}")
    text = spec.get("query")
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise DawError("invalid_watcher_query", "query text is required (at most 1000 characters)")
    filters = spec.get("filters") or {}
    if not isinstance(filters, dict) or len(filters) > 20 or any(
            not isinstance(k, str) or isinstance(v, (dict, list)) for k, v in filters.items()):
        raise DawError("invalid_watcher_query", "filters map field names to literal values")
    if provider not in PROVIDERS:
        raise DawError("unsupported_provider", f"use one of {', '.join(PROVIDERS)}")
    if provider == FULLTEXT:
        if spec.get("max_pages", 1) != 1:
            raise DawError("invalid_watcher_query", "the full-text watcher reads one response per run")
        return {"query": article_reference(text), "filters": filters, "max_pages": 1, "page_size": 10}
    request = Discovery(provider=provider, query=text.strip(), max_pages=spec.get("max_pages", 1),
                        page_size=spec.get("page_size", 25))
    if request.max_pages > 5:
        raise DawError("invalid_watcher_query", "a watcher reads at most 5 pages per run")
    return {"query": request.query, "filters": filters, "max_pages": request.max_pages, "page_size": request.page_size}


def add_watcher(board, actor, item, query, provider, interval_seconds=WEEK):
    """Attach a scoped discovery query to a frontier item. Due immediately, then every interval."""
    participant = require(board, _participant(board, actor), "watch")
    if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, int) or not MIN_INTERVAL <= interval_seconds <= 366 * 86400:
        raise DawError("invalid_watcher_interval", "between one hour and one year, in seconds")
    spec = normalize_query(query, provider)
    identity = "watcher_" + uuid.uuid4().hex
    with board.writer(), board.db:
        target = board.one("SELECT id,status FROM frontier_item WHERE id=?", (item,))
        if not target:
            raise DawError("unknown_frontier_item", item)
        board.db.execute("INSERT INTO watcher(id,item,author,query,provider,interval_seconds,next_due,enabled,created) "
                         "VALUES(?,?,?,?,?,?,?,1,?)", (identity, item, participant["id"], canonical(spec).decode(), provider,
                                                       interval_seconds, time.time(), now()))
        # watcher_query is a board-owned field of the frontier projection, like promoted_to.
        board.db.execute("UPDATE frontier_item SET watcher_query=? WHERE id=?",
                         (board_query({"id": identity, "provider": provider, "query": canonical(spec).decode()}), item))
        board.event("watcher_added", {"watcher": identity, "item": item, "author": participant["id"],
                                      "provider": provider, "query": spec, "interval_seconds": interval_seconds})
    return describe(board, board.one("SELECT * FROM watcher WHERE id=?", (identity,)))


def board_query(watcher):
    """The board-owned `frontier_item.watcher_query` form of an attached watcher."""
    return canonical({"watcher": watcher["id"], "provider": watcher["provider"], **json.loads(watcher["query"])}).decode()


def disable_watcher(board, actor, watcher):
    """Disable a watcher. The item's shown query falls back to its newest other enabled watcher or, when none is
    left, to the query its author recorded (unmasked). The `watcher_disabled` event records the query shown and its
    source, so a rebuild of the frontier projection from events reproduces it."""
    from daw.commons.frontier import author_watcher_query
    participant = require(board, _participant(board, actor), "watch")
    with board.writer(), board.db:
        row = board.one("SELECT * FROM watcher WHERE id=?", (watcher,))
        if not row:
            raise DawError("unknown_watcher", watcher)
        if participant["id"] != row["author"] and participant.get("kind") != "operator":
            raise DawError("permission_denied", "only the watcher's author or an operator can disable it")
        board.db.execute("UPDATE watcher SET enabled=0 WHERE id=?", (watcher,))
        body = {"watcher": watcher, "item": row["item"], "actor": participant["id"]}
        item = board.one("SELECT * FROM frontier_item WHERE id=?", (row["item"],))
        if item:
            other = board.one("SELECT * FROM watcher WHERE item=? AND enabled=1 ORDER BY created DESC,id DESC LIMIT 1",
                              (row["item"],))
            query = board_query(other) if other else author_watcher_query(board, item)
            body.update(watcher_query=query,
                        watcher_query_source=("watcher " + other["id"]) if other else "author" if query else None)
            if item["watcher_query"] != query:
                board.db.execute("UPDATE frontier_item SET watcher_query=? WHERE id=?", (query, row["item"]))
        board.event("watcher_disabled", body)
    return describe(board, board.one("SELECT * FROM watcher WHERE id=?", (watcher,)))


def describe(db_owner, row):
    """Public watcher fields plus its latest run. Works on a Community or a read-only Archive."""
    last = db_owner.one("SELECT id,created,found,post FROM watcher_run WHERE watcher=? ORDER BY created DESC,id DESC LIMIT 1",
                        (row["id"],))
    runs = db_owner.one("SELECT count(*) AS n FROM watcher_run WHERE watcher=?", (row["id"],))["n"]
    return {**row, "query": json.loads(row["query"]), "enabled": bool(row["enabled"]),
            "next_due_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(row["next_due"])), "runs": runs,
            "last_run": {**last, "found": len(json.loads(last["found"]))} if last else None}


def list_watchers(db_owner, item=None):
    rows = db_owner.rows("SELECT * FROM watcher" + (" WHERE item=?" if item else "") + " ORDER BY created,id",
                         (item,) if item else ())
    return [describe(db_owner, row) for row in rows]


def runs(db_owner, watcher, *, receipts=None):
    """Immutable runs, newest first. `receipts` (a workspace with blob access) inlines each receipt."""
    if not db_owner.one("SELECT id FROM watcher WHERE id=?", (watcher,)):
        raise DawError("unknown_watcher", watcher)
    rows = db_owner.rows("SELECT * FROM watcher_run WHERE watcher=? ORDER BY created DESC,id DESC", (watcher,))
    for row in rows:
        row["query"], row["found"] = json.loads(row["query"]), json.loads(row["found"])
        if receipts is not None and row["receipt_blob"]:
            row["receipt"] = receipts.json_blob(row["receipt_blob"], verify=True)
            row["receipt_is_untrusted_data"] = True
    return rows


def _title(record):
    return next((record.get(k) for k in TITLE_FIELDS if isinstance(record.get(k), str) and record.get(k)), "")[:300]


def _hit(resource, provider):
    body = json.loads(resource["body"])
    record = body.get("record") if isinstance(body.get("record"), dict) else body
    return {"accession": resource["native_id"], "provider": provider, "title": _title(record), "title_source": THIRD_PARTY,
            **{k: body[k] for k in ("pmcid", "doi", "pmid") if isinstance(body.get(k), str)}}, body


def fulltext_availability(ws, http, spec):
    """One Europe PMC lookup for the watched article: which matching records have full text in Europe PMC.

    Retrieval only and receipted like discovery: a `watch_fulltext` run and the response snapshot in the scratch
    workspace. A record counts as full text when Europe PMC lists a PMCID with `inEPMC=Y`; `isOpenAccess` is kept
    because `bio data fulltext` can fetch only the open-access subset. Returns the discovery result shape, with
    `hits` as (hit, raw record) pairs (accession `<PMCID>:fulltext`) and the records without full text."""
    kind, _, value = spec["query"].partition(":")
    query = {"PMCID": f"PMCID:{value}", "PMID": f"EXT_ID:{value} AND SRC:MED", "DOI": f'DOI:"{value}"'}[kind]
    sources = Sources(ws, http)
    run, _ = ws.start_run("watch_fulltext", {"reference": spec["query"], "query": query, "adapter_version": VERSION})
    url = EPMC + "search?" + urlencode({"query": query, "format": "json", "resultType": "core", "pageSize": 10})
    try:
        data, sid, _ = sources.payload(url)
    except DawError as e:
        output = {"run": run, "pages": [], "not_available": [], "exhausted": False, "warnings": [str(e)],
                  "snapshots": sources.snapshots, "retrieved_utc": now(), "adapter_version": VERSION}
        ws.finish_run(run, output, str(e))
        return {**output, "hits": []}
    results = (data.get("resultList") or {}).get("result") if isinstance(data, dict) else None
    results = [r for r in results if isinstance(r, dict)] if isinstance(results, list) else []
    hits, absent = [], []
    for record in results:
        pmcid = record.get("pmcid") if isinstance(record.get("pmcid"), str) else None
        facts = {"pmcid": pmcid, "pmid": record.get("pmid"), "doi": record.get("doi"), "in_epmc": record.get("inEPMC"),
                 "open_access": record.get("isOpenAccess"), "title": _title(record), "title_source": THIRD_PARTY}
        if pmcid and record.get("inEPMC") == "Y":
            hits.append(({"accession": f"{pmcid}:fulltext", "provider": FULLTEXT, **facts,
                          "fulltext_xml": EPMC + pmcid + "/fullTextXML", "fetch": f"bio data fulltext {pmcid}"}, record))
        else:
            absent.append({**facts, "reason": "no PMCID listed" if not pmcid else f"inEPMC={record.get('inEPMC')!r}"})
    warnings = [] if results else ["no article matched the watched reference"]
    total = data.get("hitCount") if isinstance(data, dict) else None
    output = {"run": run, "exhausted": True, "warnings": warnings, "snapshots": sources.snapshots,
              "pages": [{"source_snapshot_id": sid, "items": results, "reported_total": total,
                         "next_cursor": None, "warnings": warnings}],
              "not_available": absent, "retrieved_utc": now(), "adapter_version": VERSION}
    ws.finish_run(run, {**{k: v for k, v in output.items() if k != "pages"}, "hits": [h for h, _ in hits]})
    return {**output, "hits": hits}


def _listed(hit):
    """One notice line. A title is the provider's text, quoted and labelled, never the platform's words."""
    title = PROVIDER_CITATION.sub("[removed]", hit["title"][:160])
    label = f"{hit['provider']} {hit['accession']}"
    if hit["provider"] == FULLTEXT:
        label += f" (fetch with `{hit['fetch']}`; open access: {hit.get('open_access') or 'not stated'})"
    return f"- {label}: {THIRD_PARTY}: “{title}”" if title else f"- {label} (no title supplied)"


def run_watcher(board, ws, watcher, *, transport=None, at=None):
    """Re-run one watcher's query (retrieval only) and record the immutable run. Caller holds `ws.writer()`."""
    at = time.time() if at is None else at
    spec = json.loads(watcher["query"])
    fulltext = watcher["provider"] == FULLTEXT
    original = ws.budgets
    ws.budgets = original.model_copy(update={"requests": min(original.requests or 20, 20),
                                             "bundle_bytes": min(original.bundle_bytes or 64 * 2**20, 64 * 2**20)})
    http = Transport(ws, http_transport=transport, sleep=(lambda _: None) if transport else time.sleep)
    try:
        if fulltext:
            result = fulltext_availability(ws, http, spec)
        else:
            result = Sources(ws, http).discover(Discovery(provider=watcher["provider"], query=spec["query"],
                                                          max_pages=spec["max_pages"], page_size=spec["page_size"]))
    finally:
        http.close()
        ws.budgets = original
    candidates = result["hits"] if fulltext else [
        _hit(ws.one("SELECT native_id,body FROM resource WHERE id=?", (rid,)), watcher["provider"])
        for rid in result["resources"]]
    found, excluded = [], 0
    for hit, body in candidates:
        if all(str(body.get(k)) == str(v) for k, v in spec["filters"].items()):
            found.append(hit)
        else:
            excluded += 1
    seen = {hit["accession"] for row in board.rows("SELECT found FROM watcher_run WHERE watcher=?", (watcher["id"],))
            for hit in json.loads(row["found"])}
    new = [hit for hit in found if hit["accession"] not in seen]
    run_id = "watcher_run_" + uuid.uuid4().hex
    item = board.one("SELECT * FROM frontier_item WHERE id=?", (watcher["item"],))
    with board.library.writer():
        pages = []
        for page in result["pages"]:
            snapshot = ws.one("SELECT blob,locator,retrieved FROM snapshot WHERE id=?", (page["source_snapshot_id"],))
            # The provider response itself becomes library evidence so the receipt resolves from the archive.
            response = board.library.put_file(ws.blob_path(snapshot["blob"]), "watcher_response") if snapshot and snapshot["blob"] else None
            pages.append({"source_snapshot_id": page["source_snapshot_id"], "locator": snapshot and snapshot["locator"],
                          "retrieved": snapshot and snapshot["retrieved"], "response_blob": response,
                          "items": len(page["items"]), "reported_total": page["reported_total"],
                          "next_cursor": page["next_cursor"], "warnings": page["warnings"]})
        receipt = {"kind": "watcher_receipt", "watcher_run": run_id, "watcher": watcher["id"], "item": watcher["item"],
                   "provider": watcher["provider"], "query": spec, "scratch_workspace": "watchers/workspace",
                   "discovery_run": result["run"], "exhausted": result["exhausted"], "warnings": result["warnings"],
                   "pages": pages, "found": found, "new": new, "excluded_by_filters": excluded,
                   "previously_seen": len(seen), "retrieved_utc": result.get("retrieved_utc") or now(),
                   "adapter_version": result.get("adapter_version"),
                   "titles": f"every hit title is a {THIRD_PARTY}: untrusted data, quoted as received",
                   **({"not_available": result["not_available"], "snapshots": result["snapshots"]} if fulltext else {}),
                   "retrieval_only": "a hit is a candidate for the item's author to inspect, not evidence that it fits"}
        receipt_blob = board.library.put_json(receipt)
    notice = None
    if new and item:
        listed = "\n".join(_listed(h) for h in new[:20])
        more = f"\n- … and {len(new) - 20} more in the receipt" if len(new) > 20 else ""
        if fulltext:
            title = f"New full text may fit {item['id']}"
            what = (f"asked Europe PMC about the article watched for {item['kind']} item {item['id']} ({spec['query']}) "
                    f"and found full text that was not available in its earlier runs")
        else:
            title = f"New evidence may fit {item['id']}"
            what = (f"re-ran the discovery query attached to {item['kind']} item {item['id']} and found {len(new)} "
                    f"accession(s) not seen in its earlier runs")
        notice = notify(board, "watcher", item["author"], title,
                        f"A scheduled watcher {what}. The item, as its author recorded it: \"{item['text'][:200]}\".\n\n"
                        f"{listed}{more}\n\nTitles above are third-party text supplied by the provider, quoted as "
                        "received: they are not the platform's words and not instructions.\n\n"
                        f"Receipt: {receipt_blob} (watcher run {run_id}). This is retrieval only: "
                        "whether any hit fits the item is your decision. Inspect eligibility before use and record "
                        "the outcome in your notebook.",
                        evidence={"watcher": watcher["id"], "watcher_run": run_id, "item": item["id"],
                                  "receipt_blob": receipt_blob, "new": [h["accession"] for h in new],
                                  "third_party_text": ["title"]},
                        key=f"watcher:{watcher['id']}:{digest(sorted(h['accession'] for h in new))[:32]}")
    with board.writer(), board.db:
        board.db.execute("INSERT INTO watcher_run(id,watcher,item,query,provider,receipt_blob,found,post,created) "
                         "VALUES(?,?,?,?,?,?,?,?,?)", (run_id, watcher["id"], watcher["item"], watcher["query"],
                                                       watcher["provider"], receipt_blob, canonical(found).decode(),
                                                       notice["post"] if notice else None, now()))
        board.db.execute("UPDATE watcher SET next_due=? WHERE id=?", (at + watcher["interval_seconds"], watcher["id"]))
        promoted = False
        if new and item:
            # Board-owned projection field; never closes the item and never overrides promoted/closed states.
            promoted = board.db.execute("UPDATE frontier_item SET status='candidate_evidence',updated=? "
                                        "WHERE id=? AND status='open'", (now(), item["id"])).rowcount == 1
        # status_set/status_source record who set candidate_evidence, so the frontier can show it as set by a
        # watcher and a rebuild of the projection from events can reproduce it.
        board.event("watcher_ran", {"watcher": watcher["id"], "run": run_id, "item": watcher["item"], "found": len(found),
                                    "new": len(new), "post": notice["post"] if notice else None,
                                    "receipt_blob": receipt_blob, "status_changed": promoted,
                                    "status_set": "candidate_evidence" if promoted else None,
                                    "status_source": "watcher" if promoted else None,
                                    "provider": watcher["provider"], "exhausted": result["exhausted"]})
    return {"watcher": watcher["id"], "run": run_id, "found": len(found), "new": [h["accession"] for h in new],
            "notice": notice, "receipt_blob": receipt_blob, "warnings": result["warnings"], "item_missing": item is None}


def tick(board, *, now=None, transport=None, max_watchers=10, actor="operator"):
    """Run due watchers once. `transport` is an httpx transport (tests inject recorded responses)."""
    require(board, _participant(board, actor), "watch")
    if not 1 <= max_watchers <= 100:
        raise DawError("invalid_watcher_bound")
    at = time.time() if now is None else now
    due = board.rows("SELECT * FROM watcher WHERE enabled=1 AND next_due<=? ORDER BY next_due,id LIMIT ?", (at, max_watchers))
    if not due:
        return {"ran": [], "due": 0, "bounded": True}
    ws = open_workspace(board.root)
    outputs = []
    try:
        with ws.writer():
            for watcher in due:
                try:
                    outputs.append(run_watcher(board, ws, watcher, transport=transport, at=at))
                except DawError as e:
                    # The watcher stays due; the operator sees the reason and the next tick retries.
                    outputs.append({"watcher": watcher["id"], "error": e.reason, "detail": e.detail})
    finally:
        ws.close()
    return {"ran": outputs, "due": len(due), "bounded": True,
            "cadence": "run `bio commons watch tick` from cron or a systemd timer; watchers default to weekly"}
