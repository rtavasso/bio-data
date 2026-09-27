import copy

import pytest

from benchmarks.evaluate import edge_key, evaluate
from benchmarks.prior.collect import collect
from daw.util import DawError


def opportunity(oid, group=None):
    return {"id": oid, "dataset": "experiment-" + oid, "file": "file-" + oid, "analysis": "distinguish expression from cell-state change",
            "information_group": group or oid, "evidence": ["immutable fixture receipt"]}


def review(oid, **updates):
    return {"opportunity": oid, "verdict": "useful", "reviewer": "fixture assessor", "reason": "Fixture scenario distinguishes the alternatives",
        "evidence": ["source cell inspection"], "relevant": True, "independent_information": True,
        "tests_uncertainty": True, "would_analyze": True, **updates}


def retrieval():
    return {"kind": "retrieval", "questions": ["question"], "conditions": [
        {"question": "question", "arm": "runtime", "state": "complete", "discoveries": [opportunity("common"), opportunity("runtime")],
         "cost": {"tool_calls": 5, "tool_seconds": 10}},
        {"question": "question", "arm": "substrate", "state": "complete", "discoveries": [opportunity("common"), opportunity("hidden"), opportunity("false")],
         "cost": {"tool_calls": 3, "tool_seconds": 2}}], "reviews": [review("hidden"), review("false", verdict="false_positive", relevant=False)]}


def test_retrieval_counts_opportunities_usefulness_burden_and_unknown_cost():
    result = evaluate(retrieval())
    assert result["totals"] == {"common": 1, "runtime_only": 1, "deep_index_only": 2, "scientifically_valuable_index_only": 1}
    assert result["questions"][0]["false_positive_burden"]["substrate"]["false_positives"] == 1
    assert result["cost"]["runtime"]["tool_calls"]["known_total"] == 5
    assert result["cost"]["runtime"]["agent_seconds"]["known_total"] is None
    assert not result["cost"]["runtime"]["agent_seconds"]["complete"]


def test_representations_of_same_information_do_not_inflate_value():
    run = retrieval()
    run["conditions"][1]["discoveries"] += [opportunity("same-info", "common"), opportunity("same-hidden", "hidden")]
    run["reviews"] += [review("same-info"), review("same-hidden")]
    result = evaluate(run)
    assert result["totals"]["deep_index_only"] == 4
    assert result["totals"]["scientifically_valuable_index_only"] == 1


@pytest.mark.parametrize("field", ["relevant", "independent_information", "tests_uncertainty", "would_analyze"])
def test_unresolved_criterion_cannot_be_counted_as_useful(field):
    run = retrieval()
    run["reviews"][0][field] = None
    assert evaluate(run)["totals"]["scientifically_valuable_index_only"] == 0


def test_missing_runtime_arm_is_not_evidence_for_index_unique_value():
    run = retrieval()
    run["conditions"].pop(0)
    result = evaluate(run)
    assert result["missing_conditions"] == [{"question": "question", "arm": "runtime"}]
    assert result["totals"]["scientifically_valuable_index_only"] == 0


def test_opportunity_id_collision_and_unsupported_review_are_rejected():
    run = retrieval()
    run["conditions"][1]["discoveries"][0]["file"] = "different biological representation"
    with pytest.raises(DawError, match="identity_collision"):
        evaluate(run)
    run = retrieval()
    run["reviews"][0]["evidence"] = []
    with pytest.raises(DawError, match="evidence_required"):
        evaluate(run)


def test_repeated_discovery_is_counted_once_and_negative_cost_is_invalid():
    run = retrieval()
    run["conditions"][1]["discoveries"].append(copy.deepcopy(opportunity("hidden")))
    assert evaluate(run)["totals"]["deep_index_only"] == 2
    run["conditions"][0]["cost"]["tokens"] = -1
    with pytest.raises(DawError, match="invalid_benchmark_cost"):
        evaluate(run)


def test_prior_pairs_preserve_sign_disagreement_and_species():
    shared = {"source": "A", "target": "B", "species": "human", "effect": "stimulation", "scope": "activity"}
    extra = {"source": "C", "target": "B", "species": "human", "effect": "inhibition", "scope": "expression"}
    run = {"kind": "prior_recall", "nodes": ["B"], "model": {"state": "complete", "edges": [shared]},
        "database": {"state": "complete", "edges": [{**shared, "effect": "inhibition"}, {**shared, "species": "mouse"}, extra]},
        "reviews": [{"edge": edge_key(extra), "reviewer": "fixture assessor", "reason": "Important omitted mechanism in this fixture",
                     "evidence": ["fixture citation"], "importance": "important"}]}
    result = evaluate(run)
    assert result["counts"] == {"shared": 1, "model_only": 0, "database_only": 2}
    assert result["shared"][0]["effect_or_scope_disagreement"]
    assert result["database_only_assessments"] == {"important": 1, "unreviewed": 1}
    assert not result["review_complete"]


def test_prior_failed_database_is_explicitly_incomplete():
    run = {"kind": "prior_recall", "nodes": ["B"], "model": {"state": "complete", "edges": []},
        "database": {"state": "not_run", "edges": []}, "reviews": []}
    assert not evaluate(run)["paired_complete"]


def test_partial_timing_is_never_reported_as_complete():
    run = retrieval()
    run["conditions"][0]["unmeasured_cost_fields"] = ["tool_seconds"]
    cost = evaluate(run)["cost"]["runtime"]["tool_seconds"]
    assert cost == {"known_total": 10, "complete": False, "unmeasured_runs": 1}


def test_recall_replay_requires_both_requests_and_reads_immutable_bytes(ws):
    model = {"nodes": ["STAT3"], "edges": []}
    with pytest.raises(DawError, match="incomplete_recall_receipts"):
        collect(ws, model, [])
    header = "source\ttarget\tsource_genesymbol\ttarget_genesymbol\tis_stimulation\tis_inhibition\ttype\tsources\treferences\n"
    raw = header + "Q9Y6X2\tP40763\tPIAS3\tSTAT3\tFalse\tTrue\tpost_translational\tSIGNOR\tSIGNOR:9388184\n"
    blob = ws.put_bytes(raw.encode())
    responses = [{"dataset": dataset, "wall_seconds": 1, "receipt": {"outcome": "available_full", "blob": blob, "snapshot": "fixture"},
                  "rows": [{"source_genesymbol": "fabricated edited cache"}]} for dataset in ("omnipath", "tf_target")]
    result = collect(ws, model, responses)
    assert {e["source"] for e in result["database"]["edges"]} == {"PIAS3"}
    responses[1]["receipt"] = {"outcome": "unavailable", "reason": "fixture network failure"}
    result = collect(ws, model, responses)
    assert result["database"]["state"] == "partial" and len(result["database"]["edges"]) == 1
