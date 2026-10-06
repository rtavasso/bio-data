"""Copy a selected artifact's provenance closure between local bio workspaces.

Only catalog records and immutable bytes travel. Nothing is executed, interpreted,
or promoted to a destination's current source/curation/profile head.
"""
import json

from daw.artifacts import artifact_info, derivation_key
from daw.profiles import verify_object
from daw.search import index_document
from daw.substrate_models import ArtifactRegistration
from daw.util import DawError, digest, read_json


TABLES = ("resource", "snapshot", "asset_revision", "link", "assertion", "identifier",
          "review_decision", "curation_revision", "inspection", "dataset_profile",
          "artifact", "artifact_input")


def collect_artifacts(ws, identities):
    """Capture dependencies by identity, including source receipts and interpretations."""
    if not identities:
        raise DawError("no_artifacts_selected")
    rows = {table: {} for table in TABLES}
    blobs, expanded = set(), set()

    def blob(sha):
        if sha:
            verify_object(ws, sha)
            blobs.add(sha)

    def add(table, row):
        if row is None:
            raise DawError("missing_publication_dependency", table)
        key = digest(row)
        if key in rows[table]:
            return
        rows[table][key] = row
        for fk in ws.rows(f"PRAGMA foreign_key_list({table})"):
            value = row[fk["from"]]
            if value is None:
                continue
            if fk["table"] == "blob":
                blob(value)
            elif fk["table"] in rows:
                add(fk["table"], ws.one(f'SELECT * FROM {fk["table"]} WHERE {fk["to"]}=?', (value,)))
            else:
                raise DawError("unsupported_publication_dependency", fk["table"])

    def asset(aid):
        if aid in expanded:
            return
        expanded.add(aid)
        row = ws.one("SELECT * FROM asset_revision WHERE id=?", (aid,))
        add("asset_revision", row)
        body = json.loads(row["body"])
        for parent in body.get("selector", {}).get("chain", []):
            archive = ws.asset(parent["parent"])
            if archive["blob"] != parent["blob"]:
                raise DawError("archive_parent_blob_mismatch", parent["parent"])
            asset(parent["parent"])
            blob(parent["blob"])
        metadata = body.get("metadata", {})
        if metadata.get("listed_revision"):
            asset(metadata["listed_revision"])
        if metadata.get("source_metadata_snapshot"):
            add("snapshot", ws.one("SELECT * FROM snapshot WHERE id=?", (metadata["source_metadata_snapshot"],)))
        rid = row["resource_id"]
        for link in ws.rows("SELECT * FROM link WHERE object=? OR subject=?", (rid, rid)):
            add("link", link)
        resources = {rid}
        resources.update(r["subject"] for r in rows["link"].values() if r["object"] == rid)
        for resource in resources:
            for table, column in (("assertion", "subject"), ("identifier", "resource_id"), ("review_decision", "subject")):
                for record in ws.rows(f"SELECT * FROM {table} WHERE {column}=?", (resource,)):
                    add(table, record)
        for table in ("curation_revision", "inspection"):
            for record in ws.rows(f"SELECT * FROM {table} WHERE asset_revision=?", (aid,)):
                add(table, record)
        for record in ws.rows("SELECT * FROM dataset_profile WHERE subject=?", (aid,)):
            add("dataset_profile", record)
            for evidence in read_json(ws.blob_path(record["body_blob"])).get("evidence", []):
                blob(evidence["blob"])

    def artifact(aid):
        if aid in expanded:
            return
        expanded.add(aid)
        info = artifact_info(ws, aid)
        registration = ArtifactRegistration.model_validate({k: v for k, v in info["manifest"].items()
                                                            if k in ArtifactRegistration.model_fields})
        key = derivation_key(ws, registration.derivation)
        expected = "artifact_" + digest([key, registration.output_role, info["output_blob"]])
        if (key != info["derivation_key"] or expected != aid
                or info["manifest"]["output"]["blob"] != info["output_blob"]):
            raise DawError("artifact_identity_mismatch", aid)
        add("artifact", ws.one("SELECT * FROM artifact WHERE id=?", (aid,)))
        for record in ws.rows("SELECT * FROM artifact_input WHERE artifact_id=?", (aid,)):
            add("artifact_input", record)
        for item in registration.derivation.inputs:
            blob(item.blob)
            if item.source_identity.startswith("artifact_"):
                artifact(item.source_identity)
            elif item.source_identity.startswith("asset_"):
                asset(item.source_identity)
        for sha in registration.derivation.code + registration.derivation.references:
            blob(sha)

    for aid in sorted(set(identities)):
        artifact(aid)
    return {"format_version": 1, "roots": sorted(set(identities)),
            "records": {table: sorted(values.values(), key=digest) for table, values in rows.items()},
            "blobs": sorted(blobs),
            "scope": "selected derivations, source receipts and recorded input interpretations; no mutable heads"}


def transfer_artifacts(source, target, identities):
    """Caller owns target's writer lock; source catalog records are immutable.

    Preflight all identities before copying. A failed copy can leave unreferenced
    blobs, but cannot expose a partially imported artifact graph.
    """
    manifest = collect_artifacts(source, identities)
    schemas = {}
    for table in TABLES:
        columns = target.rows(f"PRAGMA table_info({table})")
        keys = [c["name"] for c in sorted(columns, key=lambda c: c["pk"]) if c["pk"]]
        schemas[table] = ([c["name"] for c in columns], keys)
        for row in manifest["records"][table]:
            found = target.one(f"SELECT * FROM {table} WHERE " + " AND ".join(f"{k}=?" for k in keys),
                               [row[k] for k in keys])
            if found and any(found[k] != v for k, v in row.items() if k != "created"):
                raise DawError("publication_identity_conflict", f"{table}: {[row[k] for k in keys]}")
    for sha in manifest["blobs"]:
        row = source.one("SELECT * FROM blob WHERE sha256=?", (sha,))
        if not row:
            raise DawError("missing_publication_blob", sha)
        if target.one("SELECT sha256 FROM blob WHERE sha256=?", (sha,)):
            verify_object(target, sha)
        elif target.put_file(source.blob_path(sha), row["classification"]) != sha:
            raise DawError("publication_source_changed", sha)
    with target.db:
        # A source revision can refer to another row later in this closure.
        target.db.execute("PRAGMA defer_foreign_keys=ON")
        for table in TABLES:
            columns, _ = schemas[table]
            for row in manifest["records"][table]:
                target.db.execute(f"INSERT OR IGNORE INTO {table} ({','.join(columns)}) VALUES "
                                  f"({','.join('?' for _ in columns)})", [row[c] for c in columns])
    for row in manifest["records"]["artifact"]:
        info = artifact_info(target, row["id"])
        body = info["manifest"]
        index_document(target, key="artifact:" + row["id"], family="artifact", subject=row["id"],
                       record_id=row["id"], title=body["title"], summary=body["summary"],
                       body_blob=row["manifest_blob"], detail={"kind": body["kind"], "limitations": body["limitations"],
                                                             "parameters": body["derivation"]["parameters"]}, level=3)
    receipt = target.put_json(manifest)
    return {"manifest_blob": receipt, "artifacts": manifest["roots"], "blobs": len(manifest["blobs"]),
            "scope": manifest["scope"]}
