"""Question-independent source facts, structures and agent-authored affordance notes."""
import csv
import json
import os
import subprocess
import sys
import uuid
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from daw.inspectors import inspect_asset, inspect_hdf, archive_inventory
from daw.models import Evidence
from daw.search import index_document
from daw.substrate_models import Profile
from daw.util import DawError, digest, file_hash, now, read_json, write_json

PROFILE_VERSION = "1"


def reader_identity():
    versions = {}
    for package in ("h5py", "openpyxl"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "not installed"
    directory = Path(__file__).parent
    return {"packages": versions, "code": {name: file_hash(directory / name)
        for name in ("profiles.py", "inspectors.py", "worker.py")}}


def verify_object(ws, sha):
    path = ws.blob_path(sha)
    if file_hash(path) != sha:
        raise DawError("integrity_failed", sha)
    return path


def subject_info(ws, subject):
    if ws.one("SELECT id FROM asset_revision WHERE id=?", (subject,)):
        asset = ws.asset(subject)
        resource = ws.one("SELECT * FROM resource WHERE id=?", (asset["resource_id"],))
        return {"provider": resource["provider"], "format": Path(asset["body"]["name"]).suffix.lower().lstrip("."),
                "name": asset["body"]["name"], "asset": asset, "resource": resource}
    resource = ws.one("SELECT * FROM resource WHERE id=?", (subject,))
    if resource:
        return {"provider": resource["provider"], "format": "", "name": resource["native_id"], "resource": resource}
    raise DawError("unknown_profile_subject", subject)


def add_profile(ws, profile: Profile, terms=()):
    info = subject_info(ws, profile.subject)
    # A profile is a sourced annotation, not a globally accepted interpretation.
    # Alternative authors/scopes coexist; history is retained for each origin.
    from daw.curation import evidence_value
    for evidence in profile.evidence:
        evidence_value(ws, evidence)
    if profile.level == 3 and not profile.evidence:
        raise DawError("profile_source_evidence_required", "cite a preserved source or work artifact")
    body = profile.model_dump()
    body["profile_schema"] = PROFILE_VERSION
    body["scientific_applicability"] = "question_local; not certified by this profile"
    blob = ws.put_json(body)
    pid = "profile_" + blob
    with ws.db:
        ws.db.execute("INSERT OR IGNORE INTO dataset_profile VALUES(?,?,?,?,?,?)", (pid, profile.subject, profile.origin, profile.level, blob, now()))
        ws.db.execute("INSERT INTO profile_head VALUES(?,?,?) ON CONFLICT(subject,origin) DO UPDATE SET profile_id=excluded.profile_id",
                      (profile.subject, profile.origin, pid))
        ws.db.executemany("INSERT OR IGNORE INTO feature_term VALUES(?,?,?,?)",
                          [(pid, t["value"], t["namespace"], t["locator"]) for t in terms])
    key = "data:" + digest([profile.subject, profile.origin])
    index_document(ws, key=key, family="data", subject=profile.subject, record_id=pid, title=profile.title,
                   summary=profile.summary, body_blob=blob, detail={"facts": profile.facts, "affordances": profile.apparent_affordances,
                   "limitations": profile.limitations}, provider=info["provider"], format=info["format"], level=profile.level)
    return {"profile": pid, "blob": blob, "document": key, "level": profile.level, "subject": profile.subject}


def source_context(ws, info):
    resource = info["resource"]
    subjects = {resource["id"]}
    if "asset" in info:
        subjects.add(ws.bundle_for(info["asset"]))
    records = []
    for subject in sorted(subjects):
        records.extend(ws.rows("SELECT DISTINCT r.id,r.kind,r.native_id,r.body FROM resource r JOIN link l ON r.id=l.object "
            "WHERE l.subject=? AND l.relationship IN ('contains_sample','describes','source_relationship') ORDER BY r.id LIMIT 24", (subject,)))
    return [{**r, "body": json.loads(r["body"])} for r in records]


def profile_manifest(ws, subject):
    info = subject_info(ws, subject)
    if "asset" in info:
        asset = info["asset"]
        facts = {"source_manifest": asset["body"], "access": asset["access"], "blob": asset["blob"],
                 "related_source_context": source_context(ws, info)}
        title = info["name"]
        summary = f"{info['provider']} file inventory; {asset['access']}; source-defined metadata retained."
        level = 1
    else:
        facts = {"source_record": json.loads(info["resource"]["body"]), "related_source_context": source_context(ws, info)}
        title = str(facts["source_record"].get("title") or info["name"])
        summary = f"{info['resource']['kind']} from {info['provider']}; source metadata, no inference of scientific suitability."
        level = 0
    facts["identifiers"] = ws.rows("SELECT namespace,value,evidence_blob,locator FROM identifier WHERE resource_id=?", (info["resource"]["id"],))
    return add_profile(ws, Profile(subject=subject, origin="source_manifest", title=title, summary=summary, level=level, facts=facts,
        limitations=["Metadata enumeration does not mean bytes were acquired or features measured"]))


def content_terms(path, name, budgets):
    """Worker-only scan of literal labels; never reads matrix values or runs formulas."""
    terms, seen, cells, complete = [], set(), 0, True
    cap = min(budgets.max_cells, 200000)
    def add(value, namespace, locator):
        nonlocal complete
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if not isinstance(value, str) or not value or len(value) > 160 or value.startswith("="):
            return
        key = (namespace, value)
        if key not in seen:
            if len(terms) >= cap:
                complete = False
                return
            seen.add(key)
            terms.append({"value": value, "namespace": namespace, "locator": locator})
    suffix = name.lower().rsplit(".", 1)[-1]
    axes = {}
    if suffix in {"xlsx", "xlsm"}:
        import openpyxl
        archive_inventory(path, budgets)
        with open(path, "rb") as stream:
            book = openpyxl.load_workbook(stream, read_only=True, data_only=False, keep_links=False)
            try:
                for sheet in book:
                    for number, row in enumerate(sheet, 1):
                        cells += len(row)
                        if cells > budgets.max_cells or number > budgets.max_rows:
                            complete = False
                            break
                        for cell in row:
                            if isinstance(cell.value, str) and cell.data_type != "f":
                                add(cell.value, "literal_table_cell", f"sheet:{sheet.title}!{cell.coordinate}")
                    if not complete:
                        break
            finally:
                book.close()
    elif suffix in {"csv", "tsv", "txt", "bed", "narrowpeak", "broadpeak"}:
        with open(path, newline="", encoding="utf-8-sig") as stream:
            for number, row in enumerate(csv.reader(stream, delimiter="," if suffix == "csv" else "\t"), 1):
                cells += len(row)
                if cells > budgets.max_cells or number > budgets.max_rows:
                    complete = False
                    break
                for col, value in enumerate(row, 1):
                    # Numerical measurements are not useful feature-search labels.
                    try:
                        float(value)
                    except ValueError:
                        add(value, "literal_table_cell", f"row:{number}:column:{col}")
    elif suffix == "h5ad":
        import h5py
        inspect_hdf(path, budgets)
        with h5py.File(path, "r") as handle:
            for group_name in ("var", "raw/var"):
                if group_name not in handle:
                    continue
                group = handle[group_name]
                columns = list(group.dtype.names or ()) if isinstance(group, h5py.Dataset) else list(group)
                axes[group_name] = {"columns": columns, "index": str(group.attrs.get("_index", "index"))}
                for column in columns:
                    # Dictionary-encoded categories are not the ordered feature axis.
                    obj = group if isinstance(group, h5py.Dataset) else group[column]
                    dtype = group.dtype[column] if isinstance(group, h5py.Dataset) else getattr(obj, "dtype", None)
                    if dtype is None or dtype.kind not in "OSU" or len(obj.shape) != 1:
                        continue
                    size = len(obj)
                    count = min(size, budgets.max_rows, max(0, budgets.max_cells - cells))
                    if count * max(64, dtype.itemsize) > budgets.worker_memory_bytes // 4:
                        complete = False
                        continue
                    values = group.fields(column)[:count] if isinstance(group, h5py.Dataset) else obj[:count]
                    for i, value in enumerate(values):
                        add(value, group_name + "/" + column, f"/{group_name}/{column}[{i}]")
                    cells += count
                    if count < size:
                        complete = False
    return {"terms": terms, "axes": axes, "cells_scanned": cells, "complete": complete,
            "policy": "literal labels at source locators; indexing is not a measured-feature or count-semantics assertion"}


def profile_asset(ws, aid, *, isolated=True):
    asset = ws.asset(aid)
    info = subject_info(ws, aid)
    if not asset["blob"] or asset["access"] != "available_full":
        return profile_manifest(ws, aid)
    path = verify_object(ws, asset["blob"])
    reader = reader_identity()
    key = digest([asset["blob"], asset["body"]["name"], ws.budgets.model_dump(), PROFILE_VERSION, reader])
    cached = ws.one("SELECT body FROM resource WHERE kind='profile_cache' AND provider='internal' AND native_id=?", (key,))
    if cached:
        content = read_json(verify_object(ws, json.loads(cached["body"])["blob"]))
    elif isolated:
        job = ws.root / "staging" / ("profile-" + uuid.uuid4().hex + ".json")
        output = job.with_suffix(".out.json")
        write_json(job, {"action": "profile", "path": str(path), "name": asset["body"]["name"],
                         "blob": asset["blob"], "budgets": ws.budgets.model_dump()})
        try:
            proc = subprocess.run([sys.executable, "-m", "daw.worker", str(job), str(output)], capture_output=True,
                timeout=ws.budgets.worker_seconds, env={"PATH": os.environ.get("PATH", ""),
                    "PYTHONPATH": str(Path(__file__).resolve().parents[1]), "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
            if not output.exists():
                raise DawError("profile_worker_failed", str(proc.returncode))
            content = read_json(output)
            if "error" in content:
                raise DawError(content["error"], content.get("detail", ""))
        except subprocess.TimeoutExpired as e:
            raise DawError("over_budget", "content profiling wall limit") from e
        finally:
            job.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
    else:
        content = content_terms(path, asset["body"]["name"], ws.budgets)
    content_blob = ws.put_json(content)
    ws.resource("profile_cache", "internal", key, {"blob": content_blob})
    prior = ws.one("SELECT blob FROM inspection WHERE asset_revision=? ORDER BY created DESC LIMIT 1", (aid,))
    structure = read_json(ws.blob_path(prior["blob"])) if prior else inspect_asset(ws, aid)
    kind = structure.get("kind", "unsupported")
    labels = {"workbook": ["inspect supplementary tables", "literal feature lookup"],
              "delimited": ["literal table lookup"], "bigwig": ["native interval signal extraction"],
              "hdf5": ["inspect matrix axes and layers"], "cooler": ["inspect native contact bins"],
              "archive": ["discover nested representations"], "gzip": ["inspect compressed member"]}
    facts = {"source_manifest": asset["body"], "source_blob": asset["blob"], "structure": structure,
             "content_index": {k: v for k, v in content.items() if k != "terms"},
             "indexed_literal_labels": len(content["terms"]), "content_index_blob": content_blob,
             "reader": reader,
             "related_source_context": source_context(ws, info)}
    receipt = ws.put_json({"structure": structure, "content_index": {k: v for k, v in content.items() if k != "terms"}, "source_blob": asset["blob"]})
    result = add_profile(ws, Profile(subject=aid, origin="structural", title=asset["body"]["name"], level=2,
        summary=f"{kind} structure; {len(content['terms'])} distinct source labels indexed. No normalization or interpretation applied.",
        facts=facts, apparent_affordances=labels.get(kind, []), evidence=[Evidence(blob=receipt, locator="/source_blob", method="deterministic structural profiling")],
        limitations=["Literal content indexing does not certify measured feature universe, replication, units, or scientific applicability",
                     "Content scan is partial" if not content["complete"] else "Content scan completed within the declared format scope"]), content["terms"])
    return {**result, "content_complete": content["complete"], "indexed_literal_labels": len(content["terms"])}


def show_data(ws, subject):
    info = subject_info(ws, subject)
    rows = ws.rows("SELECT p.* FROM dataset_profile p JOIN profile_head h ON p.id=h.profile_id WHERE p.subject=? ORDER BY p.level,p.origin", (subject,))
    return {"subject": subject, "source": info, "path": str(verify_object(ws, info["asset"]["blob"])) if info.get("asset", {}).get("blob") else None,
            "profiles": [read_json(ws.blob_path(r["body_blob"])) for r in rows],
            "relationships": ws.rows("SELECT * FROM link WHERE subject=? OR object=?", (info["resource"]["id"], info["resource"]["id"])),
            "note": "Question-local scripts may use these bytes directly; no curation acceptance required"}
