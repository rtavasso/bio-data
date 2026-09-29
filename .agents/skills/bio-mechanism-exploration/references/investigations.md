# Persistent investigation queue

Use `outputs/investigations.json` for a sustained investigation. This is an agent-authored research record, not a scientific execution language. Save numbered copies such as `investigations.r001.json` and preserve them with `bio object add` when decisions change, before the next acquisition or analysis. Record hashes in the notebook. Continue the supplied question and increment revisions; retain earlier snapshots and label inherited results.

Each item explains what would distinguish competing explanations and the concrete next step. Candidate assets may be absent initially; record exact IDs/URLs as they are located. After reading measurements, run an appropriate ordinary script, preserve its output, and register the computation with real input/code provenance and a distinct output role. Record the resulting artifact IDs. A paper, download or successful parse alone does not complete an analysis.

Minimal example, with hypothetical labels rather than biological claims:

```json
{
  "revision": 1,
  "scope": "Declared endpoint, material and unresolved assumptions",
  "status": "in_progress",
  "stopping_reason": "Work continues within the configured budget",
  "items": [{
    "id": "regulator-activity",
    "priority": "high",
    "question": "Does the intervention change activity or only abundance?",
    "alternatives": ["activity changes", "abundance alone changes"],
    "readout": "Matched activity and abundance measurements",
    "assets": [],
    "prerequisites": ["Verify sample identity and assay units"],
    "status": "open",
    "artifacts": [],
    "finding": "",
    "limitation": "Suitable measurements not yet located",
    "next_action": "Inspect linked processed files and supplementary assays",
    "blocker_evidence": []
  }]
}
```

Queue `revision` is an increasing positive integer. Queue status is `in_progress` or `bounded_complete`. Item priorities are `high`, `medium`, `low`; item statuses are `open`, `ready`, `running`, `analyzed`, `blocked`, `deferred`. All example fields are required; additional fields are welcome. IDs are unique. Declare at least one high-priority item.

Validate the full queue and linked discovery records before handoff with `./bin/python -m daw.research_records workspace/questions/QUESTION`. Status-only helpers do not check the complete schemas or registered artifacts.

- `analyzed` requires registered artifact IDs linked to this question and an observed finding. State whether the result resolves, narrows or fails to distinguish the alternatives; analysis status does not establish causal support.
- `blocked` requires a specific limitation and `blocker_evidence` paths relative to the question, such as `inputs/retrieval-receipt.json` or saved sample metadata. Locate the relevant fields/passages in the notebook. A generic claim that data are unavailable is insufficient. Try a materially different lawful route or representation where it could resolve the block; avoid repeated equivalent requests after a shared transport failure.
- `deferred` requires a reason and next action. Deferred high-priority work is unfinished.

Use `bounded_complete` only when each high-priority item was analyzed or has an evidenced blocker, and no consequential feasible work in the declared scope remains. If the budget expires, retain `in_progress` and precise restart instructions. Completion is relative to scope; neither an analyzed item nor a complete queue establishes a full biological system. Review the actual evidence before declaring uncertainty resolved.

At the stopping checkpoint, record elapsed/remaining time and retrieval allowance, still-feasible follow-ups, and why each is deferred or has low expected value. A generic “time-bounded” explanation does not establish exhaustion when substantial allowance remains. Prioritize an available upstream perturbation analysis when it can test a consequential connection that has only literature support.

Preserve complete primary-source text through supported acquisition routes where available. If only a search excerpt is retained, keep claims requiring uninspected methods/results provisional. Source-access state belongs alongside scientific uncertainty, not inside a causal edge's confidence label.
