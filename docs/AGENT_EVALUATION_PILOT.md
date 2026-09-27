# Agent evaluation pilot — 2026-09-27

The evaluator ran three synthetic research questions through stock Codex, retained the complete JSONL transcripts and native outputs, and obtained a separate evidence-linked review. All three completed and passed their observable workflow checks. The reviewer found no concrete scientific reasoning failure in these cases; this is an attributed assessment of small fixtures, not validation on real studies.

## Observed runs

| Run | Case | Limit | Elapsed | Result |
| --- | --- | ---: | ---: | --- |
| Initial prototype | zero-vs-missing | 180 s | 180.06 s | Timed out; partial artifacts retained, final answer and notebook sync unfinished |
| Three-case suite | zero-vs-missing | 300 s | 204.55 s | Complete; 10 observable checks passed |
| Three-case suite | artifact-reuse | 300 s | 165.32 s | Complete; 11 observable checks passed |
| Three-case suite | limited-context | 300 s | 232.67 s | Complete; 9 observable checks passed |
| Registration follow-up | zero-vs-missing | 300 s | 184.49 s | Complete; 10 observable checks passed |

The recorded CLI version was `codex-cli 0.157.1`. These runs used its default model without an explicit model pin. Token usage is captured from actual completion events; dollar cost is unknown. Scientific data access was offline, while model inference used the authenticated CLI. No public dataset was acquired for this pilot.

The three-case review verified that PMP22's literal `0`/`5` values stayed distinct from MPZ's omission; SOX10's `7`/`11` values came from the reused representation; and the limited-context investigation did not infer promoter activity or independent donors. The last case saved three specific retrieval gaps. Reviewers inspected recorded execution, source bytes, native outputs and provenance; they did not rerun the scientific scripts.

## Changes supported by the evidence

The initial trace tried to register prose without code provenance. Skills and CLI help now distinguish computed outputs requiring input/code provenance from narrative notes preserved by notebook sync. The default wall limit is five minutes, reflecting the observed time needed to finish these small investigations.

The three-case reviewer identified a second concrete problem: `bio register --input` exposed only a string argument and returned an empty `invalid_blob_hash` detail for a local context path. The subject recovered but made an intermediate incomplete registration. Help now names the accepted identifiers; the error identifies the argument and explains `bio object add PATH` followed by the returned blob hash. The artifact skill says to preserve each file dependency. A regression test checks rejection, the recovery step and the resulting registered dependency.

In the follow-up, the subject preserved both source and context inputs and registered them together without the earlier argument error. One different failed command remained: it passed a search document's `data:` ID to `bio data show`, then recovered using the asset `subject`. The fresh reviewer proposes an explicit show command in search results. This is recorded as the next candidate improvement; no search contract was changed in this task.

These are descriptive observations, not a controlled causal estimate. The initial rerun changed both guidance and time budget. The registration follow-up kept the 300-second limit but has only one repetition, with an unpinned model. The 20-second difference does not establish a speedup.

## Evidence and validation

The [compact receipt](v3/receipts/agent-evaluation.json) records actual statuses, checks, usage, findings and SHA256 fingerprints. Full local evidence remains in ignored workspaces:

- Initial prototype: `workspaces/agent-evals/20260927T125527-1571f261/`
- Three questions plus reviewer: `workspaces/agent-evals/20260927T130332-8f3ac4c7/`
- Registration follow-up plus reviewer: `workspaces/agent-evals/20260927T131842-bb2e0d3b/`

Open each `report.html` for the investigation, native file links, failed commands, raw/readable transcripts and reviewer findings. The final runner also snapshots its Python sources and freezes the pre-review report; the earlier prototype runs predate those additions and are not retroactively claimed to contain them.

Validation: Ruff passed; the full offline suite passed **145 tests**, with three opt-in provider tests skipped and four existing scientific-library warnings. Focused evaluator tests passed after the final reporting changes. Wheel and source builds succeeded. Report links and maintained Markdown links resolve locally. Downloaded data, credentials and full run directories remain outside Git.

Next experiments should add ambiguous or unsuitable artifacts, explicit missing-value tokens, and technical-replicate metadata, then compare repeated runs with the same model and budget. The public-data suite is available but was not run in this pilot. See [the evaluation guide](EVALUATION.md) for commands and limitations.
