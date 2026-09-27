"""Compare recorded benchmark arms; never generate or score biological truth.

Usage: uv run python -m benchmarks.evaluate RUN.json --output WORKSPACE/report.json
"""
import argparse
import math
from collections import Counter, defaultdict

from daw.util import DawError, canonical, digest, read_json, write_json

COST_FIELDS = ("tool_calls", "tool_seconds", "agent_seconds", "tokens", "usd")


def require_text(record, fields):
    for field in fields:
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise DawError("invalid_benchmark", f"{field} must be nonempty text")


def costs(runs):
    output = {}
    for field in COST_FIELDS:
        values = [r.get("cost", {}).get(field) for r in runs]
        for value in values:
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                raise DawError("invalid_benchmark_cost", field)
        known = [v for v in values if v is not None]
        incomplete = sum(v is None or field in r.get("unmeasured_cost_fields", []) for r, v in zip(runs, values, strict=True))
        output[field] = {"known_total": sum(known) if known else None,
                         "complete": bool(runs) and not incomplete, "unmeasured_runs": incomplete}
    return output


def assessments(records, key):
    output = {}
    for record in records:
        require_text(record, (key, "reviewer", "reason"))
        if not isinstance(record.get("evidence"), list) or not record["evidence"]:
            raise DawError("assessment_evidence_required", record[key])
        if record[key] in output:
            raise DawError("duplicate_assessment", record[key])
        output[record[key]] = record
    return output


def retrieval_report(run):
    questions = run.get("questions", [])
    if not questions or len(set(questions)) != len(questions) or any(not isinstance(q, str) or not q for q in questions):
        raise DawError("invalid_benchmark_questions")
    arms, items, appearances = {}, {}, defaultdict(set)
    for arm in run["conditions"]:
        key = (arm["question"], arm["arm"])
        if key[0] not in questions or key[1] not in {"runtime", "substrate"} or key in arms:
            raise DawError("invalid_or_duplicate_benchmark_arm", str(key))
        if arm.get("state") not in {"complete", "partial", "not_run"}:
            raise DawError("invalid_benchmark_arm_state")
        arms[key] = arm
        if arm["state"] == "not_run" and arm.get("discoveries"):
            raise DawError("unrun_arm_has_discoveries")
        for item in arm.get("discoveries", []):
            require_text(item, ("id", "dataset", "file", "analysis", "information_group"))
            if not isinstance(item.get("evidence"), list) or not item["evidence"]:
                raise DawError("discovery_evidence_required", item["id"])
            identity = {k: item[k] for k in ("dataset", "file", "analysis", "information_group")}
            identity["question"] = key[0]
            if item["id"] in items and items[item["id"]]["identity"] != identity:
                raise DawError("opportunity_identity_collision", item["id"])
            items.setdefault(item["id"], {"identity": identity, "records": []})["records"].append(item)
            appearances[key].add(item["id"])
    reviews = assessments(run.get("reviews", []), "opportunity")
    if set(reviews) - set(items):
        raise DawError("assessment_of_unknown_opportunity")
    for review in reviews.values():
        if review.get("verdict") not in {"useful", "false_positive", "unresolved"}:
            raise DawError("invalid_opportunity_verdict")
        for field in ("relevant", "independent_information", "tests_uncertainty", "would_analyze"):
            if review.get(field) is not None and not isinstance(review[field], bool):
                raise DawError("invalid_opportunity_assessment", field)
    reports, missing = [], []
    for question in questions:
        for name in ("runtime", "substrate"):
            if (question, name) not in arms or arms[(question, name)]["state"] == "not_run":
                missing.append({"question": question, "arm": name})
        runtime, substrate = appearances[(question, "runtime")], appearances[(question, "substrate")]
        only = substrate - runtime
        valuable, excluded, counted_groups = [], [], set()
        # Additional files/representations of already found information are not
        # new independent evidence opportunities, even if bytes differ.
        runtime_groups = {items[i]["identity"]["information_group"] for i in runtime}
        paired = all((question, name) in arms and arms[(question, name)]["state"] == "complete" for name in ("runtime", "substrate"))
        for oid in sorted(only):
            review = reviews.get(oid, {})
            good = review.get("verdict") == "useful" and all(review.get(f) is True for f in
                ("relevant", "independent_information", "tests_uncertainty", "would_analyze"))
            group = items[oid]["identity"]["information_group"]
            if good and paired and group not in runtime_groups | counted_groups:
                valuable.append(oid)
                counted_groups.add(group)
            else:
                excluded.append({"opportunity": oid, "reason": "paired runs incomplete" if not paired else
                    "same information already found" if group in runtime_groups | counted_groups else "usefulness/independence not established"})
        reports.append({"question": question, "paired_complete": paired,
            "common": sorted(runtime & substrate), "runtime_only": sorted(runtime - substrate), "deep_index_only": sorted(only),
            "scientifically_valuable_index_only": valuable, "index_only_not_counted": excluded,
            "false_positive_burden": {name: {"discoveries": len(appearances[(question, name)]),
                "false_positives": sum(reviews.get(i, {}).get("verdict") == "false_positive" for i in appearances[(question, name)]),
                "unreviewed": sum(i not in reviews for i in appearances[(question, name)])} for name in ("runtime", "substrate")}})
    return {"kind": "retrieval", "questions": reports, "missing_conditions": missing,
        "totals": {key: sum(len(q[key]) for q in reports) for key in ("common", "runtime_only", "deep_index_only", "scientifically_valuable_index_only")},
        "cost": {name: costs([a for a in arms.values() if a["arm"] == name]) for name in ("runtime", "substrate")},
        "opportunities": items, "reviews": reviews,
        "comparison_scope": "only in these recorded arms, not proof of global discoverability or biological truth",
        "scaling_decision": "No automatic expansion. Review usefulness, independent information, burden, coverage and measured costs."}


def edge_key(edge):
    require_text(edge, ("source", "target", "species"))
    # Endpoint recall is compared separately from mechanism/sign agreement.
    return digest([edge["source"], edge["target"], edge["species"]])


def prior_report(run):
    node_set = set(run["nodes"])
    if not node_set:
        raise DawError("empty_prior_node_set")
    groups = {name: defaultdict(list) for name in ("model", "database")}
    for name in groups:
        if run[name].get("state") not in {"complete", "partial", "not_run"}:
            raise DawError("invalid_benchmark_arm_state", name)
        if run[name]["state"] == "not_run" and run[name]["edges"]:
            raise DawError("unrun_arm_has_discoveries")
        for edge in run[name]["edges"]:
            if edge["target"] not in node_set:
                raise DawError("prior_edge_outside_node_set")
            groups[name][edge_key(edge)].append(edge)
    model, database = set(groups["model"]), set(groups["database"])
    only = database - model
    reviews = assessments(run.get("reviews", []), "edge")
    if set(reviews) - only:
        raise DawError("prior_assessment_must_be_database_only")
    categories = Counter()
    for key in only:
        category = reviews.get(key, {}).get("importance", "unreviewed")
        if category not in {"important", "useful_but_minor", "irrelevant_or_context_inappropriate", "unreviewed"}:
            raise DawError("invalid_prior_assessment")
        categories[category] += 1
    shared = []
    for key in sorted(model & database):
        shared.append({"edge": key, "model": groups["model"][key], "database": groups["database"][key],
            "effect_or_scope_disagreement": {(e.get("effect"), e.get("scope")) for e in groups["model"][key]} !=
                {(e.get("effect"), e.get("scope")) for e in groups["database"][key]}})
    return {"kind": "prior_recall", "nodes": sorted(node_set),
        "paired_complete": all(run[name]["state"] == "complete" for name in groups),
        "model_only": {k: groups["model"][k] for k in sorted(model - database)},
        "database_only": {k: groups["database"][k] for k in sorted(only)}, "shared": shared,
        "counts": {"model_only": len(model - database), "database_only": len(only), "shared": len(shared)},
        "database_only_assessments": dict(categories), "reviews": reviews,
        "review_complete": not categories["unreviewed"],
        "comparison_scope": "source/target/species recall; shared pairs do not imply identical signs, mechanisms, directness or contexts",
        "cost": {name: costs([run[name]]) for name in ("model", "database")},
        "mirroring_decision": "Keep runtime federation unless repeated, context-relevant important omissions and retrieval costs justify a separate proposal."}


def evaluate(run):
    if run.get("kind") == "retrieval":
        report = retrieval_report(run)
    elif run.get("kind") == "prior_recall":
        report = prior_report(run)
    else:
        raise DawError("unknown_benchmark_kind")
    return {**report, "input_sha256": digest(run), "limitations": run.get("limitations", []),
            "assessment_policy": "Explicit reviewer judgments for this evaluation only; no global scientific scoring or graph"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        report = evaluate(read_json(args.run))
        write_json(args.output, report)
        print(canonical({"output": args.output, "kind": report["kind"], "input_sha256": report["input_sha256"]}).decode())
    except (DawError, KeyError, TypeError, ValueError) as e:
        print(canonical({"error": str(e)}).decode())
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
