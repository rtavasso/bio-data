"""Offline evidence inspection. Mechanical checks are not biological grading."""
import html
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from daw.util import file_hash, read_json, write_json

from .capture import parse_events, transcript_text
from .fixtures import catalog_snapshot
from .mechanisms import inspect_mechanisms
from .discoveries import inspect_discoveries
from .investigations import analysis_activity, inspect_queue
from .runner import safe_path

STYLE = """:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#101820;color:#e5eef4}
body{max-width:1150px;margin:3rem auto;padding:0 1.5rem}h1{font-size:2.1rem}h2{margin-top:2rem}
a{color:#82d5c5}code,pre{font-family:ui-monospace,monospace}pre{white-space:pre-wrap;overflow-wrap:anywhere;
background:#15232e;padding:1rem;border-radius:8px;max-height:40rem;overflow:auto;font-size:.85rem}
.muted{color:#acbac7}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:1rem}
.card,details{background:#192935;border:1px solid #354956;padding:1rem;border-radius:10px;margin:1rem 0}
.tag{font-size:.8rem;padding:.2rem .5rem;border-radius:5px;background:#354956}.pass,.complete{color:#86dfb9}
.fail,.failed,.timed_out{color:#ffaaa0}.unknown,.not_run{color:#e8c482}table{border-collapse:collapse;width:100%}
td,th{text-align:left;padding:.7rem;border-bottom:1px solid #354956;vertical-align:top}input{padding:.7rem;width:95%;
background:#15232e;color:#fff;border:1px solid #597080;border-radius:8px}summary{cursor:pointer}li{margin:.5rem 0}
"""


def escape(value):
    return html.escape(str(value), quote=True)


def page(title, body):
    return ("<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        "<meta http-equiv=Content-Security-Policy content=\"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        f"<title>{escape(title)}</title><style>{STYLE}</style><body>{body}</body></html>")


def preview(path, limit=16000):
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if b"\0" in data:
        return None
    return data[:limit].decode("utf-8", errors="replace") + ("\n[Preview truncated; full bytes preserved]" if len(data) > limit else "")


def inventory(trial, limit=300, file_limit=10000):
    files, omitted, omitted_previews = [], 0, 0
    questions = safe_path(trial, "workspace/questions")
    for path in sorted(questions.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        rel = str(path.relative_to(trial))
        if len(files) >= file_limit:
            omitted += 1
            continue
        try:
            path = safe_path(trial, rel)
            if not path.is_file():
                continue
            show_preview = len(files) < limit
            omitted_previews += not show_preview
            files.append({"path": rel, "bytes": path.stat().st_size, "sha256": file_hash(path),
                          "preview": preview(path) if show_preview else "[Display budget reached; inspect the native file.]"})
        except (ValueError, OSError) as e:
            files.append({"path": rel, "error": str(e)})
    return {"files": files, "omitted_files": omitted, "omitted_previews": omitted_previews, "complete": omitted == 0}


def checks_for(folder, case, execution, parsed, artifacts):
    trial = folder / "trial"
    checks = []

    def add(key, ok, detail, evidence):
        checks.append({"id": key, "status": "unknown" if ok is None else "pass" if ok else "fail", "detail": detail, "evidence": evidence})

    started = bool(execution)
    complete = execution.get("state") == "exited" and parsed["turns_completed"] > 0 and not parsed["errors"]
    add("agent_completed", complete if started else None, "Successful process plus completed turn, without reported turn failure", ["execution.json", "events.jsonl"])
    final = folder / "final.md"
    add("final_answer", bool(final.exists() and final.stat().st_size) if started else None, "Final answer exists; content still requires review", ["final.md"])
    add("transcript_parseable", not parsed["malformed_lines"] if started else None,
        f"Unparsed JSONL lines: {parsed['malformed_lines']}", ["events.jsonl"])
    baseline = read_json(folder / "baseline.json")
    project = read_json(folder / "project-files.json")
    changed = []
    for name, expected in project.items():
        try:
            if file_hash(safe_path(trial, name)) != expected:
                changed.append(name)
        except (OSError, ValueError):
            changed.append(name)
    add("project_unchanged", not changed, "Changed or missing snapshot files: " + str(changed), ["project-files.json", *changed])
    broken = []
    for blob in baseline["blob"]:
        try:
            if file_hash(safe_path(trial / "workspace", blob["path"])) != blob["sha256"]:
                broken.append(blob["sha256"])
        except (OSError, ValueError):
            broken.append(blob["sha256"])
    add("preserved_inputs", not broken, "Missing or changed baseline immutable blobs: " + str(broken), ["baseline.json"])
    state = {}
    try:
        safe_path(trial, "workspace/catalog.sqlite")
        state = catalog_snapshot(trial / "workspace")
        add("catalog_integrity", state["integrity"] == "ok", state["integrity"], ["trial/workspace/catalog.sqlite"])
    except (ValueError, OSError, sqlite3.DatabaseError) as e:
        add("catalog_integrity", False, str(e), ["trial/workspace/catalog.sqlite"])
    new_questions = [q for q in state.get("question", []) if q["id"] not in {r["id"] for r in baseline["question"]}]
    continuation_file = folder / "continuation.json"
    continuation = read_json(continuation_file).get("question") if continuation_file.exists() else None
    new_questions += [q for q in state.get("question", []) if q["id"] == continuation]
    qids = {q["id"] for q in new_questions}
    links = [r for r in state.get("question_artifact", []) if r["question_id"] in qids]
    events = [r for r in state.get("work_event", []) if r["question_id"] in qids
              and r["id"] not in {e["id"] for e in baseline["work_event"]}]
    synced = []
    for q in new_questions:
        before = next((b for b in baseline["question"] if b["id"] == q["id"]), None)
        if before and before["current_work"] == q["current_work"]:
            continue
        snapshots = [s for s in state.get("work_snapshot", []) if s["question_id"] == q["id"]]
        if len(snapshots) < 2:
            continue
        current = next((s for s in snapshots if s["id"] == q["current_work"]), None)
        if current:
            try:
                body = read_json(safe_path(trial / "workspace", f"blobs/sha256/{current['body_blob'][:2]}/{current['body_blob']}"))
                notebook = safe_path(trial / "workspace", q["path"] + "/LABBOOK.md")
                if (body["files"].get("LABBOOK.md") == file_hash(notebook)
                        and baseline.get("question_files", {}).get(q["path"] + "/LABBOOK.md") != file_hash(notebook)):
                    synced.append(q["id"])
            except (OSError, ValueError, KeyError):
                pass
    script_files = [f["path"] for f in artifacts["files"] if any(q in f["path"].split("/") for q in qids)
                    and "/scripts/" in f["path"] and not f.get("error")
                    and baseline.get("question_files", {}).get(f["path"].removeprefix("workspace/")) != f.get("sha256")]
    activity = analysis_activity(trial, baseline, state, new_questions, parsed, artifacts["files"])
    script_files = sorted(set(script_files) | {p for r in activity["new_registered_results"]
                           if r["execution_evidence"] for p in r["code_files"]})
    queue_records = []
    for q in new_questions:
        if "investigation_queue" not in case["expect"]:
            continue
        try:
            linked_ids = {a["artifact_id"] for a in links if a["question_id"] == q["id"]}
            record = inspect_queue(trial, q, linked_ids)
            queue_path = q["path"] + "/outputs/investigations.json"
            record["changed"] = baseline.get("question_files", {}).get(queue_path) != file_hash(safe_path(trial / "workspace", queue_path))
            queue_records.append(record)
        except (ValueError, OSError) as e:
            queue_records.append({"question": q["id"], "error": str(e)})
    discovery_records = []
    if "discovery_ledger" in case["expect"]:
        for q in new_questions:
            try:
                linked_ids = {a["artifact_id"] for a in links if a["question_id"] == q["id"]}
                record = inspect_discoveries(trial, q, linked_ids, parsed)
                path = q["path"] + "/outputs/discoveries.json"
                record["changed"] = baseline.get("question_files", {}).get(path) != file_hash(safe_path(trial / "workspace", path))
                discovery_records.append(record)
            except (ValueError, OSError) as e:
                discovery_records.append({"question": q["id"], "error": str(e)})
    observations = {
        "question": (bool(qids), f"New or explicitly continued question IDs: {sorted(qids)}"),
        "notebook": (bool(synced), f"New question notebooks edited and synced: {synced}"),
        "script": (bool(script_files), f"Saved analysis scripts: {script_files}"),
        "registered_output": (any(a["relationship"] == "produced" and a["artifact_id"] not in {r["id"] for r in baseline["artifact"]} for a in links), "New output registered as produced for this investigation"),
        "reuse": (any(a["relationship"] == "reused" and a["artifact_id"] in {r["id"] for r in baseline["artifact"]} for a in links), "Existing artifact attached as reused to a new question"),
        "gap": (any(e["kind"] == "retrieval_gap" for e in events), "New retrieval-gap event; quality requires review"),
        "investigation_queue": (any(r.get("changed") and not r.get("error") for r in queue_records),
                                "Changed queue with registered results or preserved blockers; closure and evidence quality need review: " + str(queue_records)),
        "executed_analysis": (any(r["execution_evidence"] for r in activity["new_registered_results"]),
                              "New result with intact input/output bytes, matching saved code and a successful literal invocation; dynamic execution and scientific validity require manual review"),
        "discovery_ledger": (any(r.get("changed") and not r.get("error") for r in discovery_records),
                             "Changed discovery record with artifact links and intact prediction hashes; no automatic novelty or prospective credit")}
    mechanism_keys = {"mechanism_map", "mechanism_revision", "evidence_coverage"}
    mechanism_records = inspect_mechanisms(trial, new_questions) if mechanism_keys & set(case["expect"]) else []
    for record in mechanism_records:
        if record["question"] == continuation:
            q = next(q for q in new_questions if q["id"] == continuation)
            for key, name in (("mechanism_map", "mechanisms.json"), ("evidence_coverage", "evidence-coverage.tsv")):
                path = q["path"] + "/outputs/" + name
                try:
                    record[key] &= baseline.get("question_files", {}).get(path) != file_hash(safe_path(trial / "workspace", path))
                except (OSError, ValueError):
                    record[key] = False
            record["mechanism_revision"] &= record.get("revision", 0) > (baseline.get("mechanism_revision") or 0)
    details = {
        "mechanism_map": "Structurally valid network with resolved IDs and attributed claims; does not validate biology",
        "mechanism_revision": "Initial and later numbered maps plus a change rationale; actual timing and substantive revision require transcript review",
        "evidence_coverage": "Coverage rows reference real edge IDs and distinguish planned, located, inspected and analyzed work; claims still require source review"}
    for key in mechanism_keys:
        if key in case["expect"]:
            observations[key] = (any(r[key] for r in mechanism_records), details[key] + "; " + str(mechanism_records))
    for key in case["expect"]:
        ok, detail = observations[key]
        add(key, ok if started and state else None, detail, ["trial/workspace/catalog.sqlite", "artifacts.json"])
    add("scientific_review", None, "Biological validity, appropriateness of reuse and quality of reasoning require attributed review", ["final.md", "transcript.md", "artifacts.json"])
    return checks, activity, queue_records, discovery_records


def case_report(folder, case):
    parsed = parse_events(folder / "events.jsonl")
    execution = read_json(folder / "execution.json") if (folder / "execution.json").exists() else {}
    (folder / "transcript.md").write_text(transcript_text(parsed))
    try:
        artifacts = inventory(folder / "trial")
    except (ValueError, OSError) as e:
        artifacts = {"files": [], "complete": False, "error": str(e)}
    write_json(folder / "artifacts.json", artifacts)
    checks, activity, investigations, discoveries = checks_for(folder, case, execution, parsed, artifacts)
    complete = next(c for c in checks if c["id"] == "agent_completed")["status"] == "pass"
    status = "complete" if complete else execution.get("state", "not_run")
    if status == "exited":
        status = "incomplete"
    commands = [i for i in parsed["items"] if i.get("type") == "command_execution"]
    result = {"case_id": case["id"], "question": case["question"], "status": status, "checks": checks,
        "review_focus": case["review_focus"], "review_rubric": case.get("review_rubric", "standard"), "execution": execution, "thread_ids": parsed["thread_ids"],
        "usage": parsed["usage"], "usd": None, "tool_counts": dict(Counter(i.get("type", "unknown") for i in parsed["items"])),
        "failed_commands": [{"line": i["line"], "command": i.get("command"), "exit_code": i.get("exit_code")} for i in commands if i.get("exit_code") not in (None, 0)],
        "artifacts": artifacts, "malformed_lines": parsed["malformed_lines"], "errors": parsed["errors"],
        "activity": activity, "investigations": investigations, "discoveries": discoveries,
        "assessment": "mechanical checks only; unknown is not pass; no global scientific score"}
    write_json(folder / "report.json", result)
    final = preview(folder / "final.md", 50000) if (folder / "final.md").exists() and not (folder / "final.md").is_symlink() else "No final answer captured."
    rows = "".join(f"<tr><td>{escape(c['id'])}</td><td class={c['status']}>{c['status']}</td><td>{escape(c['detail'])}</td></tr>" for c in checks)
    outputs = ""
    for f in artifacts["files"]:
        native = f"<a href='trial/{quote(f['path'], safe='/')}'>Open native file</a>" if not f.get("error") else ""
        outputs += f"<details class=output><summary>{escape(f['path'])}</summary><p class=muted>{escape(f.get('sha256',f.get('error','')))}</p>{native}<pre>{escape(f.get('preview') or 'Binary file; inspect the recorded hash and native artifact.')}</pre></details>"
    failures = "".join(f"<details><summary>Exit {escape(c['exit_code'])} · events.jsonl line {c['line']}</summary><pre>{escape(c['command'])}</pre></details>" for c in result["failed_commands"])
    transcript_links = " · ".join(f"<a href={name}>{title}</a>" for name, title in
        (("events.jsonl", "Raw JSONL"), ("transcript.md", "Full readable transcript"), ("stderr.log", "CLI diagnostics")) if (folder / name).is_file())
    body = (f"<p><a href=../../report.html>← Evaluation run</a></p><h1>{escape(case['id'])}</h1><span class='tag {escape(status)}'>{escape(status)}</span>"
        f"<p>{escape(case['question'])}</p><p class=muted>Wall seconds: {escape(execution.get('wall_seconds','unmeasured'))} · Tokens: {escape(parsed['usage'])} · USD: unmeasured</p>"
        f"<h2>Checks</h2><p>Observable workflow checks are separate from scientific review.</p><table><tr><th>Check</th><th>Status</th><th>Evidence</th></tr>{rows}</table>"
        f"<h2>New research activity</h2><p>Inherited work is excluded. Acquisition volume is descriptive, not a quality score.</p><pre>{escape(activity)}</pre>"
        f"<h2>Investigation queue</h2><pre>{escape(investigations)}</pre>"
        f"<h2>Discovery records</h2><pre>{escape(discoveries)}</pre>"
        f"<h2>Final answer</h2><pre>{escape(final)}</pre><h2>Outputs and notebook</h2><input id=filter aria-label='Filter outputs' placeholder='Filter files by name or content…'>{outputs}"
        f"<h2>Transcript</h2><p>{transcript_links}</p>"
        f"<h3>Failed commands</h3>{failures or '<p>No failed command exits recorded.</p>'}"
        f"<details><summary>Transcript preview</summary><pre>{escape(preview(folder / 'transcript.md', 120000))}</pre></details>"
        "<script>document.getElementById('filter').addEventListener('input',e=>{for(const d of document.querySelectorAll('.output'))d.hidden=!d.textContent.toLowerCase().includes(e.target.value.toLowerCase())})</script>")
    (folder / "report.html").write_text(page(case["id"], body))
    return result


def build_report(root):
    root = Path(root).resolve()
    manifest = read_json(root / "manifest.json")
    cases = {c["id"]: c for c in manifest["suite"]["cases"]}
    reports = [case_report(safe_path(root, e["path"]), cases[e["case_id"]]) for e in manifest["trials"]]
    result = {"manifest": manifest, "cases": reports, "review_state": "pending", "review": None, "review_provenance": None,
              "interpretation": "Run-local evidence and checks; no automatic biological pass/fail or cost estimate"}
    provenance_path = root / "review" / "provenance.json"
    if provenance_path.exists() and not provenance_path.is_symlink():
        result["review_provenance"] = read_json(provenance_path)
        result["review_state"] = result["review_provenance"].get("state", "pending")
    review_path = root / "review" / "review.json"
    if review_path.exists() and not review_path.is_symlink():
        result.update(review_state="recorded", review=read_json(review_path))
    write_json(root / "report.json", result)
    cards = ""
    for r in reports:
        counts = Counter(c["status"] for c in r["checks"])
        cards += (f"<article class=card><h2><a href='cases/{escape(r['case_id'])}/report.html'>{escape(r['case_id'])}</a></h2>"
            f"<span class='tag {escape(r['status'])}'>{escape(r['status'])}</span><p>{escape(r['question'])}</p>"
            f"<p>{counts['pass']} checks passed · {counts['fail']} failed · {counts['unknown']} unresolved</p>"
            f"<p class=muted>{escape(r['execution'].get('wall_seconds','—'))} seconds · {len(r['failed_commands'])} failed commands</p></article>")
    body = (f"<p class=muted>BIO · Agent evaluation</p><h1>{escape(manifest['suite']['name'])}</h1><p>{escape(manifest['suite']['description'])}</p>"
        f"<p>Skills: {'enabled' if manifest['skills_enabled'] else 'disabled'} · Model: {escape(manifest['requested_model'] or 'CLI default (not pinned)')} · Runner: {escape(manifest.get('runner_version','not launched'))}</p>"
        f"<p class=muted>Source revision {escape(manifest['source_revision'])}; actual source and prompt hashes are pinned in the manifest. Output and transcript text is displayed as untrusted evidence.</p>"
        f"<div class=cards>{cards}</div><h2>Diagnosis</h2>")
    if result["review"]:
        review = result["review"]
        body += f"<p>{escape(review['summary'])}</p>"
        if review.get("assessments"):
            body += "<h3>Scientific investigation audit</h3><p>Attributed reviewer judgments; artifact checks alone do not establish these outcomes.</p><table><tr><th>Case / criterion</th><th>Verdict</th><th>Evidence and reasoning</th></tr>"
            for assessment in review["assessments"]:
                evidence = " · ".join(f"<a href='{quote(c['path'], safe='/')}'>{escape(c['path'])}</a> {escape(c['locator'])}" for c in assessment["evidence"])
                body += f"<tr><td>{escape(assessment['case_id'])}<br>{escape(assessment['criterion'])}</td><td>{escape(assessment['verdict'])}</td><td>{escape(assessment['justification'])}<p class=muted>{evidence}</p></td></tr>"
            body += "</table>"
        for finding in review["findings"]:
            evidence = " · ".join(f"<a href='{quote(c['path'], safe='/')}'>{escape(c['path'])}</a> {escape(c['locator'])}" for c in finding["evidence"])
            body += (f"<article class=card><span class=tag>{escape(finding['severity'])} · {escape(finding['category'])}</span>"
                     f"<h3>{escape(finding['case_id'])}</h3><p>{escape(finding['observation'])}</p>"
                     f"<p class=muted>{evidence}</p><p><b>Suggested change:</b> {escape(finding['suggested_change'])}</p>"
                     f"<p><b>Validate:</b> {escape(finding['validation_test'])}</p></article>")
        for key, title in (("strengths", "What worked"), ("unresolved", "Still unresolved"), ("next_experiments", "Next experiments")):
            body += f"<h3>{title}</h3><ul>" + "".join(f"<li>{escape(s)}</li>" for s in review[key]) + "</ul>"
        body += "<p><a href=review/review.json>Full review JSON</a> · <a href=review/provenance.json>Review provenance</a></p>"
        if (root / "review/transcript.md").is_file():
            body += "<p><a href=review/transcript.md>Reviewer transcript</a></p>"
    else:
        body += f"<p>Review state: {escape(result['review_state'])}. Scientific assessment remains unresolved.</p>"
        if result["review_provenance"]:
            body += f"<p>{escape(result['review_provenance'].get('error', 'Review did not produce a validated result.'))}</p><p><a href=review/provenance.json>Review provenance</a> · <a href=review/transcript.md>Reviewer transcript</a></p>"
        else:
            body += "<p>Use the recorded evidence to add an attributed review or run the optional agent reviewer.</p>"
    body += "<p><a href=report.json>Machine report</a> · <a href=manifest.json>Run manifest</a></p>"
    (root / "report.html").write_text(page("BIO agent evaluation", body))
    return result


def compare(before, after):
    a, b = (read_json(Path(p) / "report.json") for p in (before, after))
    cases_a, cases_b = ({c["case_id"]: c for c in r["cases"]} for r in (a, b))
    rows = []
    for key in sorted(cases_a.keys() | cases_b.keys()):
        left, right = cases_a.get(key), cases_b.get(key)
        if not left or not right:
            rows.append({"case_id": key, "comparison": "missing arm", "missing": "before" if not left else "after"})
            continue
        ac, bc = ({c["id"]: c["status"] for c in r["checks"]} for r in (left, right))
        lt, rt = (r["execution"].get("wall_seconds") for r in (left, right))
        rows.append({"case_id": key, "before_status": left["status"], "after_status": right["status"],
            "check_changes": [{"check": k, "before": ac.get(k, "missing"), "after": bc.get(k, "missing")} for k in sorted(ac.keys() | bc.keys()) if ac.get(k) != bc.get(k)],
            "wall_seconds_delta": rt - lt if rt is not None and lt is not None else None})
    return {"before": str(before), "after": str(after), "cases": rows,
            "limitations": "Descriptive comparison only. Inspect prompts, snapshots, models, skills, setup and repeated trials before attributing causality."}
