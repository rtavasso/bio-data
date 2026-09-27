"""Additive migration: preserve v1 history, make research indexing primary."""

VERSION = 3
MIGRATION = """
CREATE TABLE identifier (
 resource_id TEXT NOT NULL REFERENCES resource(id), namespace TEXT NOT NULL, value TEXT NOT NULL,
 evidence_blob TEXT REFERENCES blob(sha256), locator TEXT NOT NULL,
 PRIMARY KEY(resource_id,namespace,value,locator));
CREATE INDEX identifier_lookup ON identifier(namespace,value);
CREATE TABLE dataset_profile (
 id TEXT PRIMARY KEY, subject TEXT NOT NULL, origin TEXT NOT NULL, level INTEGER NOT NULL,
 body_blob TEXT NOT NULL REFERENCES blob(sha256), created TEXT NOT NULL);
CREATE TABLE profile_head (
 subject TEXT NOT NULL, origin TEXT NOT NULL, profile_id TEXT NOT NULL REFERENCES dataset_profile(id),
 PRIMARY KEY(subject,origin));
CREATE TABLE search_document (
 id TEXT PRIMARY KEY, family TEXT NOT NULL, subject TEXT NOT NULL, record_id TEXT NOT NULL,
 title TEXT NOT NULL, summary TEXT NOT NULL, provider TEXT NOT NULL, format TEXT NOT NULL,
 level INTEGER NOT NULL, body_blob TEXT NOT NULL REFERENCES blob(sha256), fingerprint TEXT NOT NULL);
CREATE INDEX search_filter ON search_document(family,provider,format,level);
CREATE VIRTUAL TABLE search_fts USING fts5(id UNINDEXED,title,summary,detail, tokenize='unicode61');
CREATE TABLE feature_term (
 profile_id TEXT NOT NULL REFERENCES dataset_profile(id), value TEXT NOT NULL, namespace TEXT NOT NULL,
 locator TEXT NOT NULL, PRIMARY KEY(profile_id,value,namespace,locator));
CREATE INDEX feature_lookup ON feature_term(value,profile_id);
CREATE TABLE search_embedding (
 document_id TEXT NOT NULL REFERENCES search_document(id), model TEXT NOT NULL,
 fingerprint TEXT NOT NULL, dimensions INTEGER NOT NULL, vector TEXT NOT NULL,
 PRIMARY KEY(document_id,model));
CREATE TABLE question (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
 created TEXT NOT NULL, updated TEXT NOT NULL, current_work TEXT);
CREATE TABLE work_snapshot (
 id TEXT PRIMARY KEY, question_id TEXT NOT NULL REFERENCES question(id),
 body_blob TEXT NOT NULL REFERENCES blob(sha256), created TEXT NOT NULL);
CREATE TABLE work_event (
 id TEXT PRIMARY KEY, question_id TEXT NOT NULL REFERENCES question(id),
 kind TEXT NOT NULL, body_blob TEXT NOT NULL REFERENCES blob(sha256), created TEXT NOT NULL);
CREATE INDEX event_question ON work_event(question_id,created);
CREATE TABLE artifact (
 id TEXT PRIMARY KEY, derivation_key TEXT NOT NULL, output_role TEXT NOT NULL,
 output_blob TEXT NOT NULL REFERENCES blob(sha256), manifest_blob TEXT NOT NULL REFERENCES blob(sha256),
 created TEXT NOT NULL);
CREATE INDEX artifact_derivation ON artifact(derivation_key,output_role);
CREATE TABLE artifact_input (
 artifact_id TEXT NOT NULL REFERENCES artifact(id), blob TEXT NOT NULL REFERENCES blob(sha256),
 role TEXT NOT NULL, source_identity TEXT NOT NULL, PRIMARY KEY(artifact_id,blob,role,source_identity));
CREATE TABLE question_artifact (
 question_id TEXT NOT NULL REFERENCES question(id), artifact_id TEXT NOT NULL REFERENCES artifact(id),
 relationship TEXT NOT NULL, event_id TEXT NOT NULL REFERENCES work_event(id),
 PRIMARY KEY(question_id,artifact_id,relationship));
CREATE TABLE index_job (
 id TEXT PRIMARY KEY, plan_blob TEXT NOT NULL REFERENCES blob(sha256), state TEXT NOT NULL,
 created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE index_task (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES index_job(id), stage TEXT NOT NULL,
 target TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 result_blob TEXT REFERENCES blob(sha256), updated TEXT NOT NULL,
 UNIQUE(job_id,stage,target));
CREATE INDEX index_pending ON index_task(job_id,state,stage);
CREATE TABLE index_feed (
 id TEXT PRIMARY KEY, plan_blob TEXT NOT NULL REFERENCES blob(sha256), interval_seconds INTEGER NOT NULL,
 next_due REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE bulk_import (
 source_blob TEXT PRIMARY KEY REFERENCES blob(sha256), byte_offset INTEGER NOT NULL DEFAULT 0,
 records INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL, updated TEXT NOT NULL);
PRAGMA user_version=3;
"""

for _table in ("dataset_profile", "work_snapshot", "work_event", "artifact", "artifact_input", "question_artifact", "identifier"):
    for _verb in ("UPDATE", "DELETE"):
        MIGRATION += f"""
CREATE TRIGGER immutable_{_table}_{_verb.lower()} BEFORE {_verb} ON {_table}
 BEGIN SELECT RAISE(ABORT,'immutable history'); END;
"""
