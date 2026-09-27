"""Derivation-keyed artifacts shared across questions without canonical interpretations."""
import shutil
from pathlib import Path

from daw.profiles import verify_object
from daw.search import index_document
from daw.substrate_models import ArtifactRegistration, Derivation
from daw.util import DawError, digest, file_hash, now, read_json
from daw.work import question_record, record_event


def derivation_key(ws, derivation: Derivation):
    for item in derivation.inputs:
        verify_object(ws, item.blob)
        if item.source_identity:
            if item.source_identity.startswith("asset_"):
                if ws.asset(item.source_identity)["blob"] != item.blob:
                    raise DawError("input_source_identity_mismatch")
            elif item.source_identity.startswith("artifact_"):
                other = ws.one("SELECT output_blob FROM artifact WHERE id=?", (item.source_identity,))
                if not other or other["output_blob"] != item.blob:
                    raise DawError("input_source_identity_mismatch")
            else:
                raise DawError("unknown_input_source_identity", "use exact asset revision or artifact ID")
    for sha in derivation.code + derivation.references:
        verify_object(ws, sha)
    return digest({"derivation_schema": 1, **derivation.model_dump()})


def register_artifact(ws, path, registration: ArtifactRegistration, *, question=None):
    if question:
        question_record(ws, question)
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise DawError("artifact_requires_regular_file")
    if path.stat().st_size > ws.budgets.asset_bytes:
        raise DawError("over_budget", "artifact registration")
    key = derivation_key(ws, registration.derivation)
    output = ws.put_file(path, "derived")
    aid = "artifact_" + digest([key, registration.output_role, output])
    prior = ws.one("SELECT * FROM artifact WHERE id=?", (aid,))
    if not prior:
        manifest = {**registration.model_dump(), "output": {"blob": output, "name": path.name, "bytes": path.stat().st_size},
                    "derivation_key": key, "execution": "registered by operator; code is preserved, never automatically executed",
                    "scientific_applicability": "assessed at question time"}
        body = ws.put_json(manifest)
        with ws.db:
            ws.db.execute("INSERT INTO artifact VALUES(?,?,?,?,?,?)", (aid, key, registration.output_role, output, body, now()))
            ws.db.executemany("INSERT OR IGNORE INTO artifact_input VALUES(?,?,?,?)",
                [(aid, item.blob, item.role, item.source_identity) for item in registration.derivation.inputs])
        index_document(ws, key="artifact:" + aid, family="artifact", subject=aid, record_id=aid,
                       title=registration.title, summary=registration.summary, body_blob=body,
                       detail={"kind": registration.kind, "parameters": registration.derivation.parameters,
                               "limitations": registration.limitations}, format=path.suffix.lstrip("."), level=3)
    if question:
        attach_artifact(ws, question, aid, "produced" if not prior else "reused")
    count = ws.one("SELECT count(*) AS n FROM artifact WHERE derivation_key=? AND output_role=?", (key, registration.output_role))["n"]
    return {"artifact": aid, "derivation_key": key, "output_blob": output, "path": str(ws.blob_path(output)),
            "reused": bool(prior), "conflicting_outputs": count > 1,
            "warning": "same derivation has different bytes; inspect variants before reuse" if count > 1 else None}


def artifact_info(ws, aid):
    row = ws.one("SELECT * FROM artifact WHERE id=?", (aid,))
    if not row:
        raise DawError("unknown_artifact", aid)
    manifest = read_json(verify_object(ws, row["manifest_blob"]))
    return {**row, "manifest": manifest, "path": str(verify_object(ws, row["output_blob"])),
            "questions": ws.rows("SELECT question_id,relationship FROM question_artifact WHERE artifact_id=?", (aid,))}


def find_derivation(ws, derivation: Derivation, output_role="result"):
    key = derivation_key(ws, derivation)
    found = ws.rows("SELECT id FROM artifact WHERE derivation_key=? AND output_role=? ORDER BY id", (key, output_role))
    artifacts = [artifact_info(ws, item["id"]) for item in found]
    return {"derivation_key": key, "state": "missing" if not artifacts else "reusable" if len(artifacts) == 1 else "ambiguous_outputs",
            "artifacts": artifacts, "question_independent": True,
            "note": "Identical derivation permits byte reuse, not an assertion of scientific applicability"}


def attach_artifact(ws, qid, aid, relationship="reused", *, name=None):
    _, path = question_record(ws, qid)
    artifact = artifact_info(ws, aid)
    if relationship not in {"produced", "reused", "considered"}:
        raise DawError("invalid_artifact_relationship")
    destination = None
    if name:
        if Path(name).name != name or name in {".", ".."} or "\\" in name:
            raise DawError("unsafe_artifact_name")
        directory = path / "outputs"
        if directory.is_symlink() or not directory.resolve().is_relative_to(path.resolve()):
            raise DawError("unsafe_question_path")
        destination = directory / name
        if destination.is_symlink() or destination.exists() and file_hash(destination) != artifact["output_blob"]:
            raise DawError("artifact_copy_destination_exists")
        if not destination.exists():
            ws.check_disk(Path(artifact["path"]).stat().st_size)
            shutil.copyfile(artifact["path"], destination)
    old = ws.one("SELECT event_id FROM question_artifact WHERE question_id=? AND artifact_id=? AND relationship=?", (qid, aid, relationship))
    if not old:
        event = record_event(ws, qid, "artifact_" + relationship, {"artifact": aid, "output_blob": artifact["output_blob"]})
        with ws.db:
            ws.db.execute("INSERT INTO question_artifact VALUES(?,?,?,?)", (qid, aid, relationship, event["id"]))
    return {"question": qid, "artifact": aid, "relationship": relationship, "copy": str(destination) if destination else None}


def provenance(ws, identity, *, depth=3):
    if not 0 <= depth <= 10:
        raise DawError("invalid_provenance_depth")
    nodes, edges, pending = {}, [], [(identity, 0)]
    while pending:
        item, level = pending.pop(0)
        if item in nodes:
            continue
        if len(nodes) >= 500:
            raise DawError("over_budget", "provenance graph limited to 500 nodes")
        children = []
        if item.startswith("artifact_"):
            info = artifact_info(ws, item)
            nodes[item] = {"kind": "artifact", **info}
            d = info["manifest"]["derivation"]
            children = [(info["output_blob"], "output"), (info["manifest_blob"], "manifest")]
            children += [(entry["source_identity"] or entry["blob"], entry["role"]) for entry in d["inputs"]]
            children += [(sha, "code") for sha in d["code"]] + [(sha, "reference") for sha in d["references"]]
        elif item.startswith("asset_"):
            asset = ws.asset(item)
            nodes[item] = {"kind": "asset", **asset}
            if asset["blob"]:
                children.append((asset["blob"], "exact_bytes"))
            if asset["snapshot_id"]:
                snap = ws.one("SELECT * FROM snapshot WHERE id=?", (asset["snapshot_id"],))
                nodes[item]["source_receipt"] = snap
                if snap["blob"]:
                    children.append((snap["blob"], "source_snapshot"))
            children.extend((p["parent"], "archive_parent") for p in asset["body"]["selector"].get("chain", []))
        elif item.startswith(("profile_", "work_")):
            table = "dataset_profile" if item.startswith("profile_") else "work_snapshot"
            row = ws.one(f"SELECT * FROM {table} WHERE id=?", (item,))
            if not row:
                raise DawError("unknown_provenance_identity", item)
            nodes[item] = {"kind": table, **row, "body": read_json(verify_object(ws, row["body_blob"]))}
            children = [(row["body_blob"], "manifest")]
            if table == "dataset_profile":
                children.extend((e["blob"], "evidence:" + e["locator"]) for e in nodes[item]["body"].get("evidence", []))
            else:
                children.extend((sha, name) for name, sha in nodes[item]["body"]["files"].items())
        else:
            path = verify_object(ws, item)
            nodes[item] = {"kind": "object", "sha256": item, "bytes": path.stat().st_size, "path": str(path)}
            producers = ws.rows("SELECT id FROM artifact WHERE output_blob=?", (item,))
            children.extend((p["id"], "produced_by") for p in producers)
        for child, relationship in children:
            edges.append({"subject": item, "object": child, "relationship": relationship})
            if level < depth:
                pending.append((child, level + 1))
    return {"root": identity, "depth": depth, "nodes": nodes, "edges": edges,
            "frontier": sorted({e["object"] for e in edges} - set(nodes))}
