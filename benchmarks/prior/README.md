# Biological-prior recall audit

Ask the same model for direct/near-direct upstream candidates for **EGR2, SOX10, TEAD1, YAP1, PMP22, STAT3** without tools. Save this list and the exact prompt, species/context hypotheses, model identification if available, and limitations before consulting databases. These are candidate hypotheses, not validated scientific edges.

Then use selected curated resources at runtime. The small collector requests only those target nodes from SIGNOR/TRRUST-filtered OmniPath interaction and transcriptional endpoints; it does not mirror the database or create a platform prior graph. It seals the model JSON in the immutable store before network access, preserves transport receipts and row locators, caps response sizes and rows, and supports offline replay:

```sh
# Explicit live use only; write a fresh model-only JSON first.
DAW_LIVE=1 uv run python -m benchmarks.prior.collect \
  --workspace workspaces/evaluation/workspace \
  --model workspaces/evaluation/model.json \
  --output workspaces/evaluation/prior-run.json

# Replay exact saved raw-response objects in that workspace.
uv run python -m benchmarks.prior.collect \
  --workspace workspaces/evaluation/workspace \
  --model workspaces/evaluation/model.json \
  --responses workspaces/evaluation/responses.json \
  --output workspaces/evaluation/replayed-run.json
uv run python -m benchmarks.evaluate workspaces/evaluation/prior-run.json \
  --output workspaces/evaluation/prior-report.json
```

`responses.json` is the `responses` array in the collected run. Keep both dataset request receipts, including failures. Replay reads and verifies immutable response bytes rather than trusting any edited parsed-row cache. A failed request is partial coverage; an empty successful response is different. Input model JSON contains `nodes`, `edges`, and optional `limitations`; every edge has `source`, `target`, `species`, and preferably `effect`, `scope`, `context`, and an explicit unverified status.

Comparison uses exact source/target/species keys. Preserve composite/unmapped source identifiers instead of inventing aliases. Expression, activity, and near-direct hypotheses remain separate records; endpoint overlap is not mechanism/sign agreement. The report retains differences in effect/scope and all underlying records. Human UniProt identifiers are a namespace, not proof of human experimental context; SIGNOR can map nonhuman work to human counterparts. Aggregate OmniPath annotations can include additional resources and conflicting signs even after resource filtering. Consult [OmniPath's service documentation](https://pypath.omnipathdb.org/webservice.html), [resource-filter semantics](https://r.omnipathdb.org/reference/import_omnipath_interactions.html), and [SIGNOR's guide](https://signor.uniroma2.it/user_guide/).

Add run-local `reviews` for database-only keys (computed by `benchmarks.evaluate.edge_key`): `{edge, reviewer, reason, evidence, importance}`. `importance` is `important`, `useful_but_minor`, or `irrelevant_or_context_inappropriate`. Importance is judged against the stated biological investigation, with primary-paper context. Missing reviews remain explicitly `unreviewed`; never silently classify uninspected edges as irrelevant. Report coverage and how review candidates were selected. Include time spent checking citations separately from endpoint request cost.

The [pilot](../../docs/V3_PILOT.md) freezes a 32-pair model list, reports the complete returned endpoint comparison, and performs a bounded 13-pair citation audit. It is an exploratory sample from the active agent, not a model leaderboard or exhaustive curation. Important missed mechanisms support selective runtime checks. One such audit does not establish that a maintained local graph beats federation.
