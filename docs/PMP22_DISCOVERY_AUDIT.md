# PMP22 hypothesis-discovery audit

**Three exploratory predictors were selected from measurements; none passed the frozen independent transfer test. No new PMP22 mechanism was established.** This attempt demonstrates candidate generation, predeclared testing, informative rejection and source-quality correction. It does not demonstrate field novelty or a causal role for the selected genes.

The question was **“Which candidate regulators predict PMP22 changes beyond the general Schwann-cell myelination response, and do those predictions hold in an independent perturbation dataset?”** The agent continued `q_277f20df4b6b47cc` from the [sustained investigation](PMP22_DEEP_AUDIT.md), in a separate workspace copy with earlier results visible. This was guided public-data research, not a blinded discovery benchmark or a controlled comparison of skills.

## Recorded experiment

Run: `workspaces/agent-evals/20260927T203815-97e5dd48`. The subject used stock `codex-cli 0.157.1` with its default model unpinned. The deep profile allowed 3,600 seconds, 150 research requests, 512 MiB per file and 1 GiB total. It completed in **2,590.783 seconds**, about 43 minutes, with 53 newly registered outputs. Source, skill, prompt, evaluator and inherited-workspace hashes pin the actual tested bytes, including intentional uncommitted implementation changes at preparation.

Twelve mechanical checks passed, the discovery-ledger identity check failed, and scientific validity remained `unknown`. The exact failure was `prediction belongs to another candidate`: three per-gene ledger IDs referred to one sealed prediction-family ID without an explicit identity binding. The original failure and artifacts are preserved. It does not alter the independently reproduced numerical results.

The subject CLI recorded 12,986,461 input tokens, including 12,701,312 cached input tokens, and 67,168 output tokens. These are cumulative usage figures, not context length or a dollar-cost estimate. Cost is unavailable.

The separate read-only reviewer completed in **242.696 seconds**, with validated evidence locations. Its verdicts describe this recorded workflow, not independent expert consensus or positive biological validation.

| Criterion | Verdict | Boundary |
| --- | --- | --- |
| Baseline and selection | Demonstrated | Broad executed screen; selection optimism and annotation filtering disclosed. |
| Prediction timing | Demonstrated | Exact candidate-specific predictions precede measurement acquisition; general published effects were already exposed. |
| Independent validation | Demonstrated | A distinct experiment gave an informative rejection, without positive confirmation or a causal null. |
| Confounder discrimination | Partial | Multiple controls were executed; species, age, tissue composition and assay effects remain inseparable. |
| Novelty audit | Demonstrated | Scoped searches and primary passages retained; exact mechanism novelty remains unresolved. |
| Claim calibration | Demonstrated | Negative results and corrections retained; no novel causal claim made. |

The reviewer identified the same two concrete defects as the parent audit: failed quantification entered initial arithmetic, and the sealed panel lacked an explicit link to individual ledger IDs. It also found that a broad novelty query retrieved only 100 of 210 hits. Further literature inspection remained feasible; the record does not establish that another eligible, untouched validation dataset was available.

Open the [evaluation report](../workspaces/agent-evals/20260927T203815-97e5dd48/report.html), [scientific report](../workspaces/agent-evals/20260927T203815-97e5dd48/cases/pmp22-specific-regulation/trial/workspace/questions/q_277f20df4b6b47cc/outputs/specific/REPORT.md), [figure](../workspaces/agent-evals/20260927T203815-97e5dd48/cases/pmp22-specific-regulation/trial/workspace/questions/q_277f20df4b6b47cc/outputs/specific/PMP22-specificity.png), or [transcript](../workspaces/agent-evals/20260927T203815-97e5dd48/cases/pmp22-specific-regulation/transcript.md). Data and full transcripts remain in ignored local workspaces; the [compact receipt](v3/receipts/pmp22-discovery-evaluation.json) preserves outcomes and hashes for the repository.

## What was actually computed

Discovery used GSE177037: eight purified rat Schwann-cell preparations across four injury states. There were two pooled preparations per state; the constituent nerves are not independent replicates. The deposited matrix contained 31,038 feature rows; 31,010 unambiguous gene-symbol rows were retained. Fractional RSEM expected counts were preserved, normalized to CPM, and transformed with a 0.5 pseudocount.

A fixed seven-gene myelination score (`Mpz`, `Mbp`, `Mag`, `Prx`, `Plp1`, `Cnp`, `Mal`) explained 98.1% of Pmp22 variation in these samples. The agent screened 7,761 expressed, variable genes, including 1,119 with regulatory annotations. It selected the top three qualifying annotated genes by leave-one-timepoint-out squared error and stable negative slope. The cross-validation was used for selection and is explicitly optimistic, not independent confirmation. This broad screen was still constrained by an annotation filter and a small four-state experiment.

Primary validation used GSE76027: Zeb2/Sip1 deletion in P25 mouse sciatic nerve, three source-reported biological mice per group. Candidate coefficients and success criteria were frozen before numerical inspection. The test transferred contrasts between RNA-seq in injured purified rat cells and log2 arrays in developing whole mouse nerve. It is an independent experiment but a substantial context and assay transfer, not direct perturbation of the three candidates.

| Candidate | Discovery partial correlation | Validation squared error / baseline | Validation conditional slope | Frozen result |
| --- | ---: | ---: | ---: | --- |
| Ppp6r1 | −0.952 | 1.241 | +0.838 | Contradicted in this test |
| Gtf2f1 | −0.958 | 0.850 | +0.510 | Contradicted in this test |
| Hck | −0.956 | 0.981 | +0.221 | Contradicted in this test |

Success required at least 20% error reduction, a negative conditional slope, and a negative upper bound for the prespecified bootstrap error-difference interval. No candidate passed. Gtf2f1 reduced error by about 15% but failed the threshold and direction. All three full-data conditional slopes reversed sign. The exact 729 within-group bootstrap combinations quantify this tiny sample's behavior; they do not establish broad inferential coverage or remove unknown litter dependence.

Observed Pmp22 changed by −0.603 log2 units, whereas the frozen myelin-only model predicted −2.760. This mismatch is a potential analytical lead: Pmp22 responds less than the chosen marker program in this dataset. It is not yet a new regulatory mechanism. High array abundance raises a dynamic-range alternative; the processed values alone do not establish saturation. Additional controls showed that the candidates could predict other myelin genes' residuals, and injury-day adjustment weakened specificity. The agent retained the negative result instead of redefining success around a favorable post hoc analysis.

## Prediction timing and source eligibility

The following numbers are physical lines in the subject's `events.jsonl`.

- **57:** successfully sealed prediction r001 before fetching the intended Eed-deletion validation matrix. First numerical inspection followed at 60. The source gzip passed integrity checks but decompressed to a CSV ending inside a quoted row. Required target/candidate rows were absent. A second GEO endpoint returned identical bytes. The agent kept the test untestable and did not infer zeros from omission.
- **93:** sealed replacement prediction r002 for Zeb2/HDAC3 validation. Downloads followed at 95 and reported numerical inspection at 99. Candidate identities and fitted coefficients were unchanged. General published Zeb2/HDAC3 myelination effects had already been seen and were disclosed. This supports candidate-specific numerical predeclaration, not a claim of global blinding or no model prior knowledge.
- **137:** corrected the HDAC3 secondary analysis after finding that three numeric `Mpz` zeros had `HIDATA` status. Earlier calculations had incorrectly used those values as abundance. The agent preserved superseded results and wrote a separate correction and r003 summary. The frozen seven-marker secondary test became untestable; a six-marker analysis remained exploratory. The [source format documentation](https://cole-trapnell-lab.github.io/cufflinks/file_formats/) distinguishes quantification status from the numeric FPKM field.
- **174, 185:** the supplied status helper caught an inherited malformed coverage table; the agent repaired the continued copy and obtained a valid handoff while retaining earlier snapshots. The original historical evaluation remains unchanged.

Additional Zeb2 RNA-seq follow-up (GSE74381) exposed conflicting gene/transcript representations and duplicate associations between files and sample records. The agent did not manufacture four independent libraries or treat an alternative representation as a new replicate. Inherited Egr2-AS and RUNX computations were explicitly retrospective; neither rescued the primary prediction.

## Novelty and independent audit

The agent preserved eight novelty queries, inspected primary passages and distinguished shared upstream regulation from candidate-to-PMP22 causality. The source injury study already reported myelination modules. [Prior Egr2/NAB work](https://pmc.ncbi.nlm.nih.gov/articles/PMC2440619/) already included Hck responsiveness (Table 1 and the Egr2-null results), so the Hck signal cannot itself be presented as a newly discovered regulatory program. The exact candidate-to-PMP22 mechanisms remain unresolved; an unsuccessful scoped search does not establish that nobody reported them. No candidate obtained both independent predictive support and evidence for novelty.

The parent audit wrote separate scripts in `workspaces/discovery-audit/`; their results were not supplied to the subject or reviewer. They independently reproduced:

- Selected discovery fits and leave-one-timepoint-out errors directly from the native count matrix, using a separate least-squares implementation.
- Eed matrix truncation, row/column counts, missing required rows and byte identity across the two download endpoints.
- Both sealed prediction hashes against early transcript receipts and preserved objects, with unchanged selected coefficients across the replacement plan.
- Primary validation probe mapping and source genotype order, all frozen predictions, conditional slopes, and all 729 bootstrap combinations from the native array/platform/gene-mapping files.
- The three HDAC3 `Mpz` numeric zeros and their disqualifying `HIDATA` flags directly from the deposited files.

These checks support extraction and arithmetic. They do not independently establish causality, complete candidate-selection optimality, field novelty, or every supplementary diagnostic. The transcript shows successful sealing before the recorded candidate-specific numeric inspections; unrecorded browser response bodies and model prior knowledge limit stronger exposure claims.

## Workflow changes

The new `bio-hypothesis-discovery` skill and `discovery` evaluation suite ask for a known baseline, broad candidate exploration, frozen predictions, independent validation, confounder tests and a separate novelty audit. An informative rejection is a valid result. The evaluator checks linked artifacts and exact prediction bytes, then leaves scientific judgments to evidence-cited review. It produces no automated novelty score and imposes no positive-discovery quota.

Prediction files are created exclusively, preserving exact input bytes and printing a hash receipt; existing predictions cannot be silently overwritten by the helper. Review considers earlier exposure as well as the receipt. Artifact inventory now caps previews separately from file metadata, so a large inherited notebook cannot hide later analysis scripts from provenance inspection.

Two narrow changes followed the completed evaluation:

- **Prediction-family identity:** the record guide now explicitly requires either one matching claim/panel ID or an individual claim's `prediction_id` plus membership in the sealed `candidate_ids`. The sealing helper validates declared IDs; the evaluator rejects missing/wrong bindings and unrelated members. Regression cases cover one claim, a three-member panel, an unrelated claim and an older lock lacking membership. The original run still fails, including under the revised inspector. Adding only an identity binding to a temporary copy also fails because it cannot retroactively declare membership. No original prediction or ledger was edited.
- **Source-status eligibility:** discovery instructions now require checking documented quality/status fields before normalization and fitting, retaining raw tokens separately. An invalid required feature blocks the frozen panel; a reduced panel is explicitly exploratory. This is guidance for ordinary analysis scripts, not a new automatic expression-processing engine. Its behavioral effect needs a fresh agent evaluation, ideally including both a valid measured zero and an invalid zero token.

These post-run changes have offline validation and were not tested by this live subject. The compact receipt distinguishes tested snapshot hashes from later implementation hashes. The useful self-correction in this transcript occurred under the earlier instructions.

Validation: **164 tests passed, 3 opt-in live tests skipped**, with scientific extras installed and four existing warnings. Ruff passed for `src tests scripts benchmarks` and the prediction helper; all five modified/new skills passed validation. Tests cover immutable sealing, invalid/missing records, explicit panel membership, artifact/search references, prediction hash changes, mixed scientific rubrics, and continued-work provenance beyond the preview cap.

The remaining frontier is concrete: fresh direct candidate perturbations with rescue in purified Schwann cells; source-matched assay calibration; corrected Eed/Zeb2 exports; and the inherited hormonal/metabolic branch. About 1,009 seconds of subject wall allowance remained. The chosen prediction family received a bounded test and follow-up, but this does not demonstrate exhaustion of all feasible research or completion of the full PMP22 regulatory system.
