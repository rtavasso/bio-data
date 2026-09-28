"""Persistent, bounded progressive indexing. No model or scientific planner."""
import json
import time
import uuid
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from daw.adapters import Sources
from daw.inspectors import extract_members, inspect_asset
from daw.profiles import add_profile, profile_asset, profile_manifest
from daw.models import Evidence
from daw.substrate_models import GraphRecord, IndexPlan, Profile, ResourceRef
from daw.transport import Transport
from daw.util import DawError, canonical, digest, now, read_json


def raw_asset(body):
    name = body["name"].lower()
    for suffix in (".gz", ".bz2", ".xz", ".zst"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return body["raw"] or name.endswith((".fastq", ".fq", ".sam", ".bam", ".cram", ".sra", ".bcl", ".cbcl", ".pod5", ".fast5"))


def enqueue(ws, job, stage, target, payload=None):
    tid = "task_" + digest([job, stage, target])[:32]
    with ws.db:
        ws.db.execute("INSERT OR IGNORE INTO index_task(id,job_id,stage,target,payload,state,updated) VALUES(?,?,?,?,?,'pending',?)",
                      (tid, job, stage, target, canonical(payload or {}).decode(), now()))
    return tid


def enqueue_asset(ws, job, aid, plan):
    enqueue(ws, job, "manifest", aid)
    if plan.level < 2:
        return
    asset = ws.asset(aid)
    if raw_asset(asset["body"]):
        return  # Archive inventories may not carry a repository-supplied raw flag.
    if asset["access"] == "available_full":
        enqueue(ws, job, "profile", aid)
    elif plan.fetch_processed and not asset["body"]["raw"]:
        chain = asset["body"]["selector"].get("chain")
        if chain:
            if plan.extract_archives:
                enqueue(ws, job, "extract", aid, chain[-1])
        else:
            enqueue(ws, job, "fetch", aid)


def create_job(ws, plan: IndexPlan):
    for scope in plan.scope:
        if not ws.one("SELECT id FROM resource WHERE id=? UNION SELECT id FROM asset_revision WHERE id=?", (scope, scope)):
            raise DawError("unknown_index_scope", scope)
    jid = "index_" + uuid.uuid4().hex[:16]
    blob = ws.put_json(plan.model_dump())
    with ws.db:
        ws.db.execute("INSERT INTO index_job VALUES(?,?,'pending',?,?)", (jid, blob, now(), now()))
    for seed in plan.seeds:
        enqueue(ws, jid, "resolve", digest(seed.model_dump()), seed.model_dump())
    for request in plan.searches:
        enqueue(ws, jid, "discover", digest(request.model_dump()), request.model_dump())
    if plan.include_existing:
        if plan.level == 0:
            resources = ws.rows("SELECT id FROM resource ORDER BY id")
            for resource in resources:
                if not plan.scope or resource["id"] in plan.scope:
                    enqueue(ws, jid, "manifest", resource["id"])
        else:
            for asset in ws.assets(plan.scope):
                enqueue_asset(ws, jid, asset["id"], plan)
            for scope in plan.scope:
                if ws.one("SELECT id FROM resource WHERE id=?", (scope,)):
                    enqueue(ws, jid, "manifest", scope)
    return index_status(ws, jid)


def _perform(ws, task, plan, source):
    job, stage, target = task["job_id"], task["stage"], task["target"]
    payload = json.loads(task["payload"])
    if stage == "manifest":
        return "done", profile_manifest(ws, target)
    if stage == "resolve":
        result = source.add(payload["reference"], payload.get("provider"))
        enqueue(ws, job, "manifest", result["bundle"])
        if plan.level >= 1:
            for aid in result["assets"]:
                enqueue_asset(ws, job, aid, plan)
        return "done" if result["outcome"] == "inventoried" else "blocked", result
    if stage == "discover":
        from daw.models import Discovery
        request = {k: v for k, v in payload.items() if k not in {"cursor", "prior_resources", "visited_cursors"}}
        result = source.discover(Discovery.model_validate(request), cursor=payload.get("cursor"),
                                 prior_resources=payload.get("prior_resources", []))
        for rid in result["resources"]:
            enqueue(ws, job, "manifest", rid)
            if plan.level >= 1:
                resource = ws.one("SELECT native_id,body FROM resource WHERE id=?", (rid,))
                body = json.loads(resource["body"])
                native = str(body.get("pmcid") or resource["native_id"])
                seed = {"reference": native, "provider": payload["provider"]}
                enqueue(ws, job, "resolve", digest(seed), seed)
        if not result["exhausted"] and result.get("next_cursor"):
            visited = set(payload.get("visited_cursors", []))
            cursor = payload.get("cursor") or ("*" if request["provider"] == "europepmc" else "1")
            for page in result["pages"]:
                visited.add(cursor)
                cursor = page.get("next_cursor")
            if result["next_cursor"] in visited:
                return "partial", {**result, "warnings": result["warnings"] + ["repeated_cursor_across_index_runs"]}
            continuation = {**request, "cursor": result["next_cursor"], "prior_resources": result["resources"],
                            "visited_cursors": sorted(visited)}
            with ws.db:
                ws.db.execute("UPDATE index_task SET payload=? WHERE id=?", (canonical(continuation).decode(), task["id"]))
            # Retry transport failures explicitly; page-budget boundaries are normal checkpoints.
            return ("pending" if result["warnings"] == ["page_budget_exhausted"] else "blocked"), result
        return "done" if result["exhausted"] else "partial", result
    if stage in {"fetch", "extract"}:
        asset = ws.asset(target)
        if raw_asset(asset["body"]):
            return "deferred", {"reason": "raw acquisition is never scheduled by the indexer", "asset_revision": target}
        if stage == "fetch":
            result = source.http.acquire(target)
            aid = result["asset_revision"]
            enqueue(ws, job, "manifest", aid)
            if result["outcome"] != "available_full":
                return "blocked", result
        else:
            child = extract_members(ws, payload["parent"], [payload["member"]])[0]
            result, aid = child, child["asset_revision"]
        enqueue(ws, job, "profile", aid)
        return "done", result
    if stage == "profile":
        asset = ws.asset(target)
        result = profile_asset(ws, target)
        row = ws.one("SELECT blob FROM inspection WHERE asset_revision=? ORDER BY created DESC LIMIT 1", (target,))
        structure = read_json(ws.blob_path(row["blob"])) if row else {}
        if structure.get("kind") in {"archive", "gzip"}:
            # Refresh the inventory to expose registered children even on a cached inspection.
            inspection = inspect_asset(ws, target)
            for child in inspection.get("listed_child_assets", []):
                enqueue(ws, job, "manifest", child)
                body = ws.asset(child)["body"]
                lower = body["name"].lower()
                processed = lower.endswith((".xlsx", ".csv", ".tsv", ".txt", ".h5ad", ".bed", ".narrowpeak", ".cool", ".mcool", ".zip", ".gz"))
                raw = raw_asset(body)
                if plan.extract_archives and processed and not raw and len(body["selector"]["chain"]) <= ws.budgets.archive_depth:
                    enqueue(ws, job, "extract", child, body["selector"]["chain"][-1])
        complete = structure.get("status") == "structure_inspected" and structure.get("complete", False)
        return "done" if complete and result.get("content_complete", False) else "partial", result
    if stage == "semantic":
        rows = ws.rows("SELECT p.id FROM dataset_profile p JOIN profile_head h ON p.id=h.profile_id WHERE p.subject=? AND p.level=3", (target,))
        return ("done", {"profiles": [r["id"] for r in rows]}) if rows else (
            "deferred", {"reason": "agent-authored affordance profile not supplied", "subject": target,
                         "next": "inspect sources and add a descriptive profile with bio data profile; no model is invoked"})
    raise DawError("unknown_index_stage", stage)


def run_job(ws, jid, *, max_tasks=None, seconds=None, transport=None, retry=False):
    job = ws.one("SELECT * FROM index_job WHERE id=?", (jid,))
    if not job:
        raise DawError("unknown_index_job")
    plan = IndexPlan.model_validate(read_json(ws.blob_path(job["plan_blob"])))
    tasks_limit = max_tasks if max_tasks is not None else plan.max_tasks
    time_limit = seconds if seconds is not None else plan.max_seconds
    if tasks_limit < 1 or time_limit < 1:
        raise DawError("invalid_index_run_bounds")
    original = ws.budgets
    ws.budgets = original.model_copy(update={"requests": min(original.requests or plan.max_requests, plan.max_requests),
        "bundle_bytes": min(original.bundle_bytes or plan.max_download_bytes, plan.max_download_bytes),
        "asset_bytes": min(original.asset_bytes or plan.max_asset_bytes, plan.max_asset_bytes)})
    http = transport or Transport(ws)
    source = Sources(ws, http)
    source.native_metadata_only = True  # No subprocess can bypass transport accounting.
    attempt, _ = ws.start_run("index", {"job": jid, "plan": plan.model_dump(), "max_tasks": tasks_limit, "seconds": time_limit})
    started, outcomes = time.monotonic(), []
    try:
        with ws.db:
            ws.db.execute("UPDATE index_task SET state='pending' WHERE job_id=? AND state='running' AND stage!='semantic'", (jid,))
            if retry:
                ws.db.execute("UPDATE index_task SET state='pending' WHERE job_id=? AND stage!='semantic' AND state IN ('blocked','deferred','partial')", (jid,))
            ws.db.execute("UPDATE index_job SET state='running',updated=? WHERE id=?", (now(), jid))
        while len(outcomes) < tasks_limit and time.monotonic() - started < time_limit:
            if http.requests >= ws.budgets.requests or http.transferred >= ws.budgets.bundle_bytes:
                break
            task = ws.one("SELECT * FROM index_task WHERE job_id=? AND state='pending' AND stage!='semantic' ORDER BY CASE stage "
                "WHEN 'discover' THEN 0 WHEN 'resolve' THEN 1 WHEN 'manifest' THEN 2 WHEN 'fetch' THEN 3 "
                "WHEN 'extract' THEN 4 WHEN 'profile' THEN 5 ELSE 6 END,id LIMIT 1", (jid,))
            if not task:
                break
            with ws.db:
                ws.db.execute("UPDATE index_task SET state='running',attempts=attempts+1,updated=? WHERE id=?", (now(), task["id"]))
            try:
                state, result = _perform(ws, task, plan, source)
            except (DawError, OSError, ValueError, ImportError, KeyError) as e:
                state, result = "blocked", {"reason": str(e), "type": type(e).__name__}
            result_blob = ws.put_json(result)
            with ws.db:
                ws.db.execute("UPDATE index_task SET state=?,result_blob=?,updated=? WHERE id=?", (state, result_blob, now(), task["id"]))
            outcomes.append({"task": task["id"], "stage": task["stage"], "target": task["target"], "state": state, "result_blob": result_blob})
        counts = Counter(r["state"] for r in ws.rows("SELECT state FROM index_task WHERE job_id=?", (jid,)))
        required = Counter(r["state"] for r in ws.rows("SELECT state FROM index_task WHERE job_id=? AND stage!='semantic'", (jid,)))
        state = completion_state(required)
        with ws.db:
            ws.db.execute("UPDATE index_job SET state=?,updated=? WHERE id=?", (state, now(), jid))
        output = {"job": jid, "attempt": attempt, "state": state, "tasks": outcomes, "counts": dict(counts),
                  "required_counts": dict(required), "enrichment": enrichment_status(ws, jid),
                  "requests": http.requests, "transferred_bytes": http.transferred,
                  "wall_seconds": round(time.monotonic() - started, 4),
                  "budget_scope": "this resumable invocation; active task also has worker/transport limits"}
        ws.finish_run(attempt, output)
        return output
    except BaseException as e:
        ws.finish_run(attempt, {"tasks": outcomes, "job": jid}, type(e).__name__)
        raise
    finally:
        ws.budgets = original
        if transport is None:
            http.close()


def completion_state(counts):
    if counts.get("pending", 0) or counts.get("running", 0):
        return "pending"
    return "partial" if any(counts.get(s, 0) for s in ("partial", "blocked", "deferred")) else "complete"


def enrichment_status(ws, jid):
    subjects = ws.rows("SELECT DISTINCT target FROM index_task WHERE job_id=? AND stage='profile'", (jid,))
    enriched = ws.one("SELECT count(DISTINCT p.subject) AS n FROM dataset_profile p JOIN profile_head h ON p.id=h.profile_id "
        "WHERE p.level=3 AND p.subject IN (SELECT target FROM index_task WHERE job_id=? AND stage='profile')", (jid,))["n"]
    return {"optional": True, "candidate_subjects": len(subjects), "with_semantic_profile": enriched,
            "without_semantic_profile": len(subjects) - enriched,
            "legacy_tasks": ws.rows("SELECT state,count(*) AS count FROM index_task WHERE job_id=? AND stage='semantic' GROUP BY state", (jid,)),
            "note": "Agent-authored descriptions are opportunistic; levels 0–2 determine completion"}


def index_status(ws, jid=None, *, limit=30):
    if jid:
        row = ws.one("SELECT * FROM index_job WHERE id=?", (jid,))
        if not row:
            raise DawError("unknown_index_job")
        counts = ws.rows("SELECT stage,state,count(*) AS count FROM index_task WHERE job_id=? GROUP BY stage,state ORDER BY stage,state", (jid,))
        frontier = ws.rows("SELECT id,stage,target,state,attempts,result_blob FROM index_task WHERE job_id=? AND stage!='semantic' AND state!='done' ORDER BY stage,id LIMIT ?", (jid, limit))
        required = Counter()
        for count in counts:
            if count["stage"] != "semantic":
                required[count["state"]] += count["count"]
        return {**row, "recorded_state": row["state"], "state": completion_state(required),
                "plan": read_json(ws.blob_path(row["plan_blob"])), "counts": counts, "frontier": frontier,
                "enrichment": enrichment_status(ws, jid),
                "frontier_display_limit": limit, "exhausts_public_data": False}
    jobs = ws.rows("SELECT * FROM index_job ORDER BY created DESC LIMIT ?", (limit,))
    for job in jobs:
        required = Counter(r["state"] for r in ws.rows("SELECT state FROM index_task WHERE job_id=? AND stage!='semantic'", (job["id"],)))
        job["recorded_state"], job["state"] = job["state"], completion_state(required)
    return {"jobs": jobs,
        "profiles": ws.rows("SELECT p.level,p.origin,count(*) AS count FROM dataset_profile p JOIN profile_head h ON h.profile_id=p.id GROUP BY p.level,p.origin"),
        "documents": ws.rows("SELECT family,count(*) AS count FROM search_document GROUP BY family"),
        "assets": ws.rows("SELECT a.access,count(*) AS count FROM asset_revision a JOIN current_asset c ON a.id=c.revision GROUP BY a.access"),
        "feature_labels": ws.one("SELECT count(*) AS count FROM feature_term f JOIN profile_head h ON f.profile_id=h.profile_id")["count"],
        "historical_feature_labels": ws.one("SELECT count(*) AS count FROM feature_term")["count"],
        "feeds": ws.rows("SELECT * FROM index_feed ORDER BY id"),
        "bulk_imports": ws.rows("SELECT * FROM bulk_import ORDER BY updated DESC LIMIT ?", (limit,))}


def import_graph(ws, path, *, max_records=1000):
    """Streaming JSONL bulk boundary with a checkpoint after every source record."""
    if not 1 <= max_records <= 100000:
        raise DawError("invalid_import_bound")
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise DawError("bulk_source_requires_regular_file")
    blob = ws.put_file(path, "source")
    source_size = ws.blob_path(blob).stat().st_size
    old = ws.one("SELECT * FROM bulk_import WHERE source_blob=?", (blob,))
    if old and old["state"] == "complete":
        return {**old, "reused": True}
    with ws.db:
        ws.db.execute("INSERT OR IGNORE INTO bulk_import VALUES(?,0,0,'pending',?)", (blob, now()))
    old = ws.one("SELECT * FROM bulk_import WHERE source_blob=?", (blob,))
    offset, records, done = old["byte_offset"], old["records"], 0
    sid = ws.snapshot(str(path.resolve()), "available_full", {"format": "resource_graph_jsonl", "resumed_offset": offset}, blob)
    with ws.blob_path(blob).open("rb") as stream:
        stream.seek(offset)
        while done < max_records:
            raw = stream.readline(2**20 + 1)
            if not raw:
                break
            if len(raw) > 2**20:
                raise DawError("over_budget", "bulk record exceeds 1 MiB")
            try:
                record = GraphRecord.model_validate(json.loads(raw))
                targets = [(ResourceRef.model_validate(link["target"]), str(link["relationship"])) for link in record.relationships]
            except (ValueError, KeyError, ValidationError) as e:
                raise DawError("invalid_bulk_record", f"byte offset {offset}; checkpoint retained: {type(e).__name__}") from e
            rid = ws.resource(record.kind, record.provider, record.native_id, record.body)
            locator = f"line:{records + 1};byte:{offset}"
            for target, relationship in targets:
                target_id = ws.resource(target.kind, target.provider, target.native_id)
                ws.link(rid, target_id, relationship, sid, locator)
            with ws.db:
                for namespace, values in record.identifiers.items():
                    ws.db.executemany("INSERT OR IGNORE INTO identifier VALUES(?,?,?,?,?)", [(rid, namespace, value, blob, locator) for value in values])
            record_blob = ws.put_bytes(raw, "source_record")
            add_profile(ws, Profile(subject=rid, origin="bulk:" + blob, level=0,
                title=str(record.body.get("title") or record.native_id),
                summary=str(record.body.get("summary") or record.body.get("description") or "Imported research graph record")[:16000],
                facts={"record": record.model_dump(), "source_blob": blob, "source_locator": locator},
                evidence=[Evidence(blob=record_blob, locator="", method="exact source JSONL line; parent blob and byte offset preserved")]))
            offset, records, done = stream.tell(), records + 1, done + 1
            state = "complete" if offset == source_size else "pending"
            with ws.db:
                ws.db.execute("UPDATE bulk_import SET byte_offset=?,records=?,state=?,updated=? WHERE source_blob=?", (offset, records, state, now(), blob))
    if offset == source_size:
        with ws.db:
            ws.db.execute("UPDATE bulk_import SET state='complete',updated=? WHERE source_blob=?", (now(), blob))
    return {**ws.one("SELECT * FROM bulk_import WHERE source_blob=?", (blob,)), "imported_this_call": done, "snapshot": sid}


def schedule_feed(ws, plan, every):
    if every < 60:
        raise DawError("feed_interval_too_short", "minimum 60 seconds")
    body = ws.put_json(plan.model_dump())
    fid = "feed_" + digest([body, every])[:24]
    with ws.db:
        ws.db.execute("INSERT OR IGNORE INTO index_feed VALUES(?,?,?,0,1)", (fid, body, every))
    return {"feed": fid, "every_seconds": every, "next": "Run bio index tick periodically using your normal scheduler"}


def tick(ws, *, max_feeds=1):
    if not 1 <= max_feeds <= 20:
        raise DawError("invalid_feed_bound")
    outputs = []
    for feed in ws.rows("SELECT * FROM index_feed WHERE enabled=1 AND next_due<=? ORDER BY next_due,id LIMIT ?", (time.time(), max_feeds)):
        plan = IndexPlan.model_validate(read_json(ws.blob_path(feed["plan_blob"])))
        # Drain the previous bounded run before refreshing this feed's inventory.
        # A crash leaves the feed due and its running task resumable.
        prior = ws.one("SELECT id FROM index_job WHERE plan_blob=? AND state IN ('pending','running') ORDER BY created,id LIMIT 1",
                       (feed["plan_blob"],))
        job = prior or create_job(ws, plan)
        result = run_job(ws, job["id"])
        if result["state"] != "pending":
            with ws.db:
                ws.db.execute("UPDATE index_feed SET next_due=? WHERE id=?", (time.time() + feed["interval_seconds"], feed["id"]))
        outputs.append({"feed": feed["id"], "resumed": bool(prior), "result": result})
    return {"feeds_run": outputs, "bounded": True}
