# Experimental-index value benchmark

This directory defines an evaluation, not a research agent harness. Use the same stock agent/model and ordinary tools in both conditions. Save authored observations and reviews as JSON in an ignored workspace, then run:

```sh
uv run python -m benchmarks.evaluate workspaces/evaluation/retrieval-run.json \
  --output workspaces/evaluation/retrieval-report.json
```

## Protocol

1. Choose several difficult biological questions and unresolved competing explanations. Fix the question, model, time/request/download budgets, stopping rule, and review criteria before collecting results. Record inaccessible sources and incomplete runs.
2. Runtime condition: biological reasoning, primary literature, web search, GEO/other repository APIs, specialist indexes (for example ChIP-Atlas or cellxgene), and direct inspection of selected public processed files. Follow meaningful leads. A few generic keyword queries are not an adequate baseline.
3. Assisted condition: identical capabilities and budgets plus the local deep-content index, source profiles, and reusable artifacts. For an independent paired experiment use fresh isolated sessions with the same starting information, randomize order, and preserve transcripts. Never let results from the other arm leak silently.
4. Record a candidate as an exact dataset/file and **specific analysis**. Preserve accession, file URL/blob, selector if relevant, source receipts, and how it was found. A paper or gene-name match alone is not a useful opportunity. Assign the same stable opportunity ID to the same file/analysis in both arms. Assign one `information_group` to different files/assemblies/encodings of the same information. Do not equate file count with biological replication.
5. Review relevance, independent information, ability to test a stated uncertainty, and whether a competent researcher would analyze it. Use `true`, `false`, or `null` for unknown; cite the source and explain each decision. Independence is evidence independence for this comparison, never a claim of independent donors. Reviews are attributed run-local judgments, not platform eligibility or truth scores.
6. Report common/runtime-only/index-only/valuable-index-only sets, false positives and unreviewed candidates, measured agent/tool/time/token/monetary costs, and missing measurements. Measure indexing setup/storage separately from marginal retrieval. No scaling decision follows automatically from counts.

The [v3 pilot](../../docs/V3_PILOT.md) is explicitly exploratory and incremental: the assisted arm starts from the recorded runtime findings, then measures additional local opportunities. Shared prior project context and incomplete agent telemetry prevent a blinded causal speedup claim. The evaluator also supports fully independent arms for subsequent evaluations. Do not relabel the incremental pilot as a randomized benchmark.

## Input shape

```json
{
  "kind": "retrieval",
  "questions": ["question-key"],
  "conditions": [{
    "question": "question-key", "arm": "runtime", "state": "complete",
    "cost": {"tool_calls": 3, "tool_seconds": 4.2, "agent_seconds": null, "tokens": null, "usd": null},
    "unmeasured_cost_fields": ["tool_seconds"],
    "discoveries": [{
      "id": "stable-opportunity", "dataset": "source accession",
      "file": "exact source URL or immutable blob",
      "analysis": "a specific analysis that could distinguish the alternatives",
      "information_group": "one experiment/measurement family",
      "evidence": [{"snapshot": "actual receipt", "locator": "source field or row"}]
    }]
  }],
  "reviews": [{
    "opportunity": "stable-opportunity", "reviewer": "identified reviewer",
    "reason": "source-backed explanation", "evidence": ["source receipt or primary citation"],
    "verdict": "useful", "relevant": true, "independent_information": null,
    "tests_uncertainty": true, "would_analyze": true
  }],
  "limitations": ["Record actual limitations here"]
}
```

Add a second condition with `arm: substrate` for each question. States are `complete`, `partial`, `not_run`; completion means the recorded bounded search was run, not scientific resolution. Verdicts are `useful`, `false_positive`, `unresolved`. The example intentionally has an unknown independence criterion and cannot count as a valuable unique opportunity. Partial/missing arms cannot establish incremental value. Repeated identical IDs count once; conflicting identities are rejected. Multiple representations of information already found cannot inflate the valuable count.

Costs are nullable. `known_total` is a measured subtotal; `complete` and `unmeasured_runs` expose missing coverage. List a field in `unmeasured_cost_fields` when a known number omits part of the work. Tool calls need an explicit counting convention in the run; never infer agent tokens or cost from elapsed wall time. Keep full runs, reports, and source payloads outside git.
