"""A bounded recall audit, not a biological database adapter or local prior graph.

Seal a model-only JSON first. Supply --responses to replay exact stored receipts;
otherwise DAW_LIVE=1 is required for two small, target-filtered OmniPath requests.
"""
import argparse
import csv
import io
import os
import time
from pathlib import Path
from urllib.parse import urlencode

from daw.catalog import Workspace
from daw.profiles import verify_object
from daw.transport import Transport
from daw.util import DawError, canonical, now, read_json, write_json


def collect(ws, model, responses=None):
    nodes = model["nodes"]
    if not 1 <= len(nodes) <= 12 or any(not isinstance(n, str) or not n.isalnum() for n in nodes):
        raise DawError("invalid_benchmark_node_set")
    sealed = ws.put_json(model)
    if responses is None:
        if os.environ.get("DAW_LIVE") != "1":
            raise DawError("live_benchmark_disabled", "use recorded responses or set DAW_LIVE=1")
        responses = []
        http = Transport(ws)
        try:
            for dataset in ("omnipath", "tf_target"):
                url = "https://omnipathdb.org/interactions?" + urlencode({"targets": ",".join(nodes), "datasets": dataset,
                    "resources": "SIGNOR,TRRUST", "genesymbols": "yes", "fields": "sources,references,type", "organisms": "9606", "directed": "yes"})
                start, before = time.monotonic(), http.requests
                receipt = http.fetch(url, expected="tsv", limit=8 * 2**20)
                responses.append({"dataset": dataset, "url": url, "receipt": receipt, "created": now(),
                    "wall_seconds": time.monotonic() - start, "http_requests": http.requests - before})
        finally:
            http.close()
    if len(responses) != 2 or {r["dataset"] for r in responses} != {"omnipath", "tf_target"}:
        raise DawError("incomplete_recall_receipts", "both distinct dataset requests must be recorded, including failures")
    edges, failures = [], []
    for response in responses:
        receipt = response["receipt"]
        if receipt["outcome"] != "available_full":
            failures.append(receipt)
            continue
        raw = verify_object(ws, receipt["blob"]).read_text()
        rows = list(csv.DictReader(io.StringIO(raw), delimiter="\t"))
        if len(rows) > 5000:
            raise DawError("over_budget", "recall audit exceeds 5000 records; narrow the question")
        for line, row in enumerate(rows, 2):
            target = row["target_genesymbol"]
            if target not in nodes:
                raise DawError("unbounded_benchmark_response", target)
            positive, negative = row["is_stimulation"] == "True", row["is_inhibition"] == "True"
            effect = "mixed" if positive and negative else "stimulation" if positive else "inhibition" if negative else "unspecified"
            edges.append({"source": row["source_genesymbol"], "target": target, "species": "human", "effect": effect,
                "scope": "expression" if row["type"] == "transcriptional" else "activity",
                "source_identifier": row["source"], "target_identifier": row["target"], "resources": row["sources"],
                "references": row["references"], "evidence": {"blob": receipt["blob"], "snapshot": receipt["snapshot"], "locator": f"row:{line}"},
                "caution": "human identifier namespace is not proof of human primary experiments; aggregate signs may mix resource contexts"})
    return {"kind": "prior_recall", "nodes": nodes, "model": {"state": "complete", "edges": model["edges"], "sealed_blob": sealed,
            "cost": {"tool_calls": 0, "agent_seconds": None, "tokens": None, "usd": None}},
        "database": {"state": "partial" if failures else "complete", "edges": edges, "failures": failures,
            "cost": {"tool_calls": len(responses), "tool_seconds": sum(r["wall_seconds"] for r in responses)}},
        "reviews": [], "responses": responses,
        "limitations": model.get("limitations", []) + ["Bounded two-endpoint audit of selected nodes; no global mirroring",
            "SIGNOR/TRRUST-filtered OmniPath rows can retain other supporting resources and conflicting signs",
            "Endpoint overlap is not agreement about expression, activity, directness, context, or primary experimental species",
            "Unreviewed edges cannot justify a local prior subsystem"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--responses")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    ws = Workspace(args.workspace)
    try:
        with ws.writer():
            result = collect(ws, read_json(args.model), read_json(args.responses) if args.responses else None)
            write_json(args.output, result)
        print(canonical({"output": str(Path(args.output)), "kind": "prior_recall",
                         "database_state": result["database"]["state"]}).decode())
    finally:
        ws.close()


if __name__ == "__main__":
    main()
