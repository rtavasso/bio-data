# PMP22 mechanism-exploration audit

The agent went beyond first-order regulators and used the expanded network to change its analysis. It revisited existing RNA measurements, investigated controls on EGR2, acquired additional chromatin measurements, and retained a result that complicated its initial explanation. This is evidence of useful exploration in one bounded run. It does not establish a complete regulatory system or prove that the new skill caused an improvement over a baseline.

The exact question was **“What is the full regulatory system for PMP22?”** The subject received the research, mechanism-exploration, discovery and artifact-reuse skills, without a supplied regulator list or preferred biological answer. The new skill requires an early hypothesis map, upstream investigation, competing explanations, concrete file-plus-analysis opportunities, evidence-driven revision and a prioritized unresolved frontier. The evaluator assesses those behaviors separately; node counts and a valid graph do not earn a scientific pass.

## Recorded experiment

The completed run is `workspaces/agent-evals/20260927T172147-ad8067db`, question `q_277f20df4b6b47cc`. It used stock `codex-cli 0.157.1`, its unpinned default model, a 900-second subject budget, public retrieval and an isolated copy of `workspaces/v2-pilot`. The seed provided existing source files and artifacts, so this tests finding new uses for available evidence as well as new acquisition. Its original workspace was not supplied as the subject's writable catalog.

The subject finished in **780.091 seconds**. All 11 mechanical checks passed; scientific validity remains `unknown` in those checks. The recorded subject usage was 2,402,209 input tokens, including 2,285,184 cached input tokens, and 19,609 output tokens. These are cumulative CLI usage figures, not context length. Dollar cost was unavailable. A separate read-only reviewer inspected the frozen report, transcript and outputs without fetching new evidence.

The reviewer completed in 188.719 seconds and returned the following evidence-cited judgments. Its citations were validated against the recorded files; this is an independent session, not independent expert consensus.

| Criterion | Reviewer verdict | Reason |
| --- | --- | --- |
| Recursive exploration | Partial | Upstream investigation changed collection, but retained source text does not verify every consequential connection. |
| Breadth | Demonstrated | Searches and analysis considered transcription, RNA regulation, protein handling, cell state and lipid consequences. |
| Discovery value | Demonstrated | Existing RNA data gained a new analysis, and a discrepancy motivated an executed ATAC follow-up. |
| Discrimination | Demonstrated | The agent retained contradictory measurements and distinguished assays and competing mechanisms. |
| Revision | Partial | Initial timing and adaptive behavior are visible; later numbered snapshots were written together. |
| Calibration | Partial | Measurement conclusions were carefully bounded, while several literature and coverage claims exceeded the preserved support. |

Open the [local evaluation report](../workspaces/agent-evals/20260927T172147-ad8067db/report.html), [research report](../workspaces/agent-evals/20260927T172147-ad8067db/cases/pmp22-regulatory-system/trial/workspace/questions/q_277f20df4b6b47cc/outputs/REPORT.md), or [readable transcript](../workspaces/agent-evals/20260927T172147-ad8067db/cases/pmp22-regulatory-system/transcript.md). These ignored local files include the full evidence; the committed [compact receipt](v3/receipts/pmp22-mechanism-evaluation.json) records hashes and outcomes. The seed, downloaded measurements and full transcripts are not committed.

An earlier attempt, `20260927T134619-143f8f8c`, was interrupted after a host-time gap. Its timestamps span 23,572.975 seconds although the old timer reported 780.042 seconds under `wall_seconds`. That field measured monotonic time, which did not include the gap on this host. The partial run and its failure state remain preserved; it is not counted as a completed scientific trial. The rerun used a corrected timeout that checks both clocks.

## What the agent actually did

Evidence references below are physical lines in the completed run's `cases/pmp22-regulatory-system/events.jsonl`.

| Evidence | Observed behavior | Why it matters |
| --- | --- | --- |
| Line 17, before the first web search at line 22 | Saved and preserved the initial map after local inventory; its edges were explicitly unverified hypotheses. | The initial network was not reconstructed after external research. |
| Lines 22, 26, 39 | Searched beyond transcription factors into RNA regulation, protein handling, and Egr2 antisense/chromatin mechanisms. | The investigation used multiple biological endpoints. Source visibility is limited as discussed below. |
| Lines 41, 55, 76 | Reused the source-preserving RNA artifact, analyzed a new 28-gene panel and verified its cells and row locators against the original source. | Existing measurements gained an additional use; this was more than a dataset citation. |
| Lines 55–60 | Identified discordant Egr2/Jun RNA directions and then fetched three additional processed ATAC files. | A discrepancy visibly changed collection. |
| Lines 64, 67 | Analyzed four peak files against rn6 reference windows, keeping rn5 promoter-associated RNA coordinates separate. | The agent investigated a chromatin alternative without claiming that called peaks establish differential accessibility. |
| Lines 69, 74 | Wrote later maps, coverage, notebook explanation and preservation records. | These outputs make the result reviewable, but the later map timing limits the revision claim. |
| Line 78 | Corrected nonstandard JSON `NaN` values to null, registered the corrected output and retained the earlier immutable version. | This was a self-corrected serialization issue, not an unresolved final-output failure. |

The strongest concrete result was the RNA discrepancy. Independent recomputation directly from the immutable source TSV reproduced the agent's descriptive AS/control ratios: **Pmp22 0.885, Egr2 1.258, Jun 0.820**. The calculation excluded the embedded header at source row 1472 and used 13,610 rows positive in all four libraries for median-ratio size factors. This checks arithmetic and source extraction, not a causal mechanism, donor independence or statistical significance. The agent appropriately withheld those claims. Two reported TSS contrasts also match their original source rows.

The upstream branch was substantive: the agent connected extracellular signaling, YY1, Egr2 antisense RNA and chromatin regulation, then considered how this could relate to PMP22. An independent spot-check of the [primary Egr2-AS paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC11592338/) confirmed evidence concerning ERBB-dependent YY1 phosphorylation and RNA binding (Results 3.1, Figure 1C–D). The paper also separates C-JUN regulation from simple EGR2 inhibition (Results 3.3, Figure S1B). These findings support investigating separate branches; they do not establish the entire mediated path to human PMP22. This was one primary-paper spot-check, not validation of every cited mechanism.

## Limitations and changes prompted by the audit

**Source support was stronger for the measured-data branches than for the full literature network.** Seven direct XML requests failed certificate verification, and several web opens returned CAPTCHA pages. Search events retained URLs and short excerpts; the successful paper-open event retained a title and line count rather than its full text. Several edges nevertheless received `supported` status from indexed excerpts. The final prose also stated some of those mechanisms more firmly than its coverage table. Their detailed source support cannot be established from the recorded subject evidence alone. The independent source spot-check was kept outside the run and was not supplied to the reviewer or retroactively credited to the subject.

**Intermediate revision was retrospective.** Initial-map timing is sound, and the transcript shows a changed investigation. However, revision 2 and revision 3 were both written by the same command at line 69, after the ATAC analysis. Revision 2 already contained the expanded network. Its label does not establish a saved first-pass checkpoint. The refined skill now explicitly asks for the revised map before the next collection or analysis it motivates, and requires retrospective reconstruction to be labeled as such.

**Distinct computational products shared an output role.** The preservation ledger records five ambiguity warnings among ten registration receipts. Different products from the same script used the default `result` role; different titles do not distinguish them for reuse. The artifact-reuse skill now explains `--output-role` with concrete examples. Existing output bytes and warning history were preserved.

**Analyzing a related file did not test every linked edge.** The reviewer correctly flagged coverage rows that associate promoter peaks with signaling/recruitment edges, and Abca1 expression with lipid feedback. Their caveats avoid a causal conclusion, but the shared `analyzed` label can still overstate edge-specific coverage. The artifact conventions now explicitly separate file-analysis status from causal support and require contextual/non-discriminating measurements to be labeled. This clarification has not yet been tested in another live trial.

**Setup friction consumed research time.** Restored seed workspaces omitted disposable `staging` and `runs` directories. The subject recovered by creating them; the failed first creation left an additional question record without a completed notebook. The evaluator now recreates those directories through the existing workspace initializer after copying a seed; a regression test verifies that new work succeeds and the original source remains unchanged. This repair was made after the completed trial was prepared, so its benefit is tested offline, not demonstrated by this live run.

The login shell also selected a pyenv Python without the scientific dependencies; the subject recovered by explicitly using `bin/python`. Interpreter resolution under login shells and certificate trust remain environment issues to address in the next controlled run. This audit does not claim those host-dependent problems are fixed.

The post-audit skill refinements also keep excerpt-only mechanisms provisional and require strict JSON before registration. These refinements were not supplied to the recorded subject. The run's source and driver snapshots pin what it actually tested; the audit does not relabel that trial as validation of later changes.

## Next evaluation

Run a pinned-model, repeated comparison before attributing behavioral gains to the skill. Alternate skills-on and skills-off runs with the same seed and budgets. Judge concrete analysis choices, upstream evidence, contradictions and revision timing; retain failures instead of rewarding a larger graph or longer answer.

The new offline `mechanism-challenges` fixture complements the public question: one intervention changes regulator activity without changing abundance, another changes RNA lifetime without changing nascent RNA, and a third belongs to a different cell context. Its raw synthetic measurements are available to the subject; expected interpretations remain outside the trial. Fixture preparation and its acceptance tests ran offline; a model was not run on that synthetic case in this audit.

Validation: **152 tests passed, 3 opt-in live tests skipped** with scientific extras installed; Ruff passed for `src tests scripts benchmarks`, and the distribution built successfully. The first full-suite attempt hit an existing 0.3-second subprocess-startup race; its receipt was retained. The timeout fixture now allows 2 seconds while retaining the same expected timeout, partial-output and termination assertions. No scientific acceptance criterion was weakened.
