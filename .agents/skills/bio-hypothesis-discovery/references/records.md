# Discovery records

These are question-local research notes with machine-checkable references, not a scientific acceptance engine. Additional fields are welcome. Use strict finite JSON and question-relative file paths. Keep revisions rather than replacing the history; preserve snapshots with `bio object add` and notebook hashes.

## Prediction before validation

Write a draft JSON object with these required fields (text unless indicated):

- `candidate_id`, `claim`, `context`, `baseline_model`.
- `discovery_sources`: nonempty list of exact experiment/asset identifiers.
- `validation_sources`: nonempty list of intended validation experiment/asset identifiers. Identify these using design metadata where possible. If suitable data have not been located, retain a proposed test in the ledger rather than sealing an unspecified test.
- `prior_exposure`: what source outcomes, papers, inherited analyses or related samples were already inspected; state whether prospective testing remains possible. Never assert the model has no prior knowledge.
- `prediction`: endpoint, contrast and expected direction or magnitude.
- `analysis_plan`: units, independent biological unit, eligibility, feature selection, normalization, comparison and uncertainty estimation as appropriate.
- `success_rule`, `failure_rule`: criteria fixed before inspecting validation outcomes; inconclusive results are allowed.
- `confounder_checks`: nonempty list of technical/biological alternatives and relevant controls.
- `selection_and_multiplicity`: how candidates were selected, the tested family, and correction or descriptive-only boundary.

For one claim, `candidate_id` must equal the eventual ledger `id`. For a multi-claim prediction, use a stable panel ID as `candidate_id` and include `candidate_ids`, a nonempty list of unique ledger IDs (lowercase slugs, at most 64 characters, starting with a letter). Each member's hypothesis and test must be specified in the sealed plan. Declare membership before validation, not after seeing which claims look promising. Additional structured fields can retain models and coefficients without encoding them into the required text fields.

Seal with the supplied interpreter, using a new destination each time:

```sh
./bin/python .agents/skills/bio-hypothesis-discovery/scripts/seal_prediction.py \
  workspace/questions/QUESTION/outputs/prediction-draft.json \
  workspace/questions/QUESTION/outputs/predictions/candidate-r001.json
```

The helper validates the required fields, creates the destination exclusively, and prints an `event: prediction_sealed` receipt with its SHA-256. It will not overwrite an existing file. Record the hash and preserve the output object before validation. It does not certify scientific validity, independence, or absence of prior exposure. Review must locate the successful helper invocation before the first outcome inspection and compare the recorded hash with the surviving bytes. A later result derived from an earlier inspection is retrospective even if its script runs after sealing.

## Ledger

Save `outputs/discoveries.json`. Required top-level fields:

- `revision`: positive integer, incremented across snapshots.
- `scope`, `known_baseline`, `budget_allocation`, `stopping_reason`: nonempty text. Cite source paths/locators for the baseline and record remaining resources and feasible next work at stopping.
- `candidates`: list of records below; it may be empty.
- `no_candidates_reason`: text; required to be nonempty when no candidates are reported. Explain the actual exploration and its limits.

Each candidate has all these fields:

```json
{
  "id": "hypothesis-one",
  "claim": "Hypothetical context-specific biological claim",
  "context": "Declared material, assay and endpoint",
  "kind": "biological",
  "status": "candidate",
  "alternatives": ["Proposed mechanism", "Generic state response", "Technical explanation"],
  "discovery_artifacts": ["artifact_ID"],
  "prediction_lock": null,
  "prediction_sha256": null,
  "validation_mode": "not_tested",
  "validation_artifacts": [],
  "validation_result": "No independent test yet",
  "independence_assessment": "Source/sample overlap and prior outcome exposure remain to be checked",
  "novelty": {
    "status": "unresolved",
    "closest_prior_work": [],
    "searches": [],
    "limitation": "Literature coverage not established"
  },
  "limitations": "What the measurements cannot establish",
  "next_test": "A concrete observation that could reject this claim"
}
```

`kind` is `biological` or `analytical`. Evidence `status` is `candidate`, `supported_in_scope`, `contradicted`, `unresolved`, or `reproduced_known`. None means field novelty or causal proof. `supported_in_scope` and `contradicted` need registered validation artifacts and an observed result; state the scope of that test. A hypothesis can have strong retrospective support while remaining prospectively untested.

`validation_mode` is `prospective`, `retrospective`, or `not_tested`. Prospective records require a question-relative `prediction_lock` path and its `prediction_sha256`, as well as validation artifacts. Untested locks are allowed with `not_tested`. A sealed file for a retrospective test records transparency, not prospective credit. Artifact IDs must be registered and linked to this question; discovery artifacts can include correctly attributed inherited work. Keep complete input/code provenance.

An optional ledger `prediction_id` explicitly references a sealed panel's `candidate_id`; otherwise the evaluator expects the ledger `id`. For a panel reference, the ledger `id` must also appear in the sealed `candidate_ids`. Every member records the same exact file/hash and panel ID, with its own outcome. This checks identity and predeclared membership, not scientific correspondence between prose claims. An unrelated claim cannot borrow a panel's seal. Verify these relationships before handoff. Preserve an older lock lacking membership; report the limitation or use one ledger record for the original panel rather than retroactively changing or resealing its bytes.

Check all current entries at continuation intake, including inherited ones, and again before handoff:

```sh
./bin/python .agents/skills/bio-hypothesis-discovery/scripts/check_prediction_links.py \
  workspace/questions/QUESTION
```

This read-only helper reports identity/path/hash errors as JSON and exits nonzero on failure. It does not check the full ledger schema, artifact registrations, biological eligibility or prediction timing. When representing an older panel as one current record, retain the original panel ID and exact sealed bytes, preserve every member's outcome in that record, and archive the earlier ledger and its failure. This is a record correction, not a new validation or a repaired historical seal. Do not omit negative findings to obtain a passing check.

Novelty `status` is `known`, `not_found_in_scoped_search`, or `unresolved`. `closest_prior_work` entries have `source` (citation/URL), `locator` (precise passage/table), and `relationship` (what was already known and the exact proposed difference). `searches` entries have `query`, `date` (ISO date), and `evidence` (question-relative saved receipt/results path). `limitation` always describes the search boundary. `known` needs closest prior work; `not_found_in_scoped_search` needs saved searches and closest prior work. No matches alone cannot establish global novelty. Evidence status and novelty status must be reported independently.

The evaluator checks file references, registered artifact links, hashes and records of sealing. It leaves prediction timing, sample independence, analysis validity, claim support and novelty to evidence-cited review. It does not reward a populated ledger or positive outcome as scientific success.
