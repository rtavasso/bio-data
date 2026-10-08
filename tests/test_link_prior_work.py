"""Linking others' work (2026-10-08): a question's reused peer artifacts are listed at turn start and a draft that
does not credit them is warned, so a peer's contribution is not lost from the ledger."""
import json

from daw.prior_work import prior_work, uncredited


class FakeWS:
    """The two tables and blobs prior_work reads."""

    def __init__(self, events, links, blobs):
        self.events, self.links, self.blobs = events, links, blobs

    def rows(self, sql, params):
        if "community_evidence_fetched" in sql:
            return [{"body_blob": b} for b in self.events]
        return self.links

    def one(self, sql, params):
        return {"body_blob": params[0]} if params[0] in self.blobs else None

    def blob_path(self, sha):
        return self.blobs[sha]


def test_prior_work_lists_reused_peer_artifacts_and_flags_uncredited_ones(tmp_path):
    fetched = tmp_path / "fetch.json"
    fetched.write_text(json.dumps({"post": "post_a", "author": "agent_peer", "artifacts": ["artifact_1", "artifact_2"]}))
    reason = tmp_path / "reuse.json"
    reason.write_text(json.dumps({"artifact": "artifact_1", "reason": "peer lipid table sets the comparator"}))
    ws = FakeWS(["fetch"], [{"artifact_id": "artifact_1", "relationship": "considered", "event_id": "e0"},
                            {"artifact_id": "artifact_1", "relationship": "reused", "event_id": "reuse"},
                            {"artifact_id": "artifact_2", "relationship": "considered", "event_id": "e2"},
                            {"artifact_id": "artifact_own", "relationship": "produced", "event_id": "e3"}],
                {"fetch": fetched, "reuse": reason})
    items = prior_work(ws, "q")
    assert [(i["artifact"], i["relationship"]) for i in items] == [("artifact_1", "reused"), ("artifact_2", "considered")]
    assert items[0]["post"] == "post_a" and items[0]["reason"].startswith("peer lipid table")
    assert [m["artifact"] for m in uncredited(items, "My finding.")] == ["artifact_1"]
    assert uncredited(items, "Built on post_a.") == []
    claims = [{"text": "x", "pointers": [{"kind": "locator", "id": "artifact_1#row=a;col=b"}]}]
    assert uncredited(items, "My finding.", claims) == []
    assert uncredited(items, "My finding.", [{"pointers": [{"kind": "artifact", "id": "artifact_9"}]}])[0]["artifact"] == "artifact_1"
