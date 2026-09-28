# Choosing informative investigations

Use the existing notebook, network and investigation queue; this guide adds decision criteria, not a new platform schema. Preserve a short decision checkpoint before the work it motivates. Additional queue fields or a compact question-local table are sufficient.

State the checkpoint's actual stage: before acquisition, before computation, or after inspecting outcomes. If acquisition already happened, record that fact and the remaining decision. A later note cannot establish an earlier decision, and a retrospective checkpoint does not confer prospective credit.

## Match the analysis to the question

Specify the endpoint and biological context. Regulation of transcription, RNA persistence, protein abundance and protein function require different observations. Upstream activity can change without a change in the regulator's RNA. Shared-program regulation and target-specific regulation are both meaningful; decide which effect the analysis addresses. Adjusting for a program that mediates regulation can remove the effect of interest. Draw the proposed relationships before interpreting an adjusted association as specificity.

For broad questions, compare consequential unresolved branches before repeatedly deepening the most convenient assay. These can include upstream controls, regulatory elements, RNA processing, protein handling, temporal responses or interactions when relevant to the question and available data. Do not force every branch into every investigation or impose a candidate quota.

## Choose experiments for discriminatory value

For plausible sources, compare exact experiment/file identities, independent biological units, endpoint and units, perturbation, material and context, prior outcome exposure, eligibility limits, and the alternatives the comparison could separate. First use metadata where possible; do not inspect validation outcomes to choose a successful-looking source.

Trace each treatment to its appropriate controls before sealing a test. Check sample records, source filenames and methods for distinct control backgrounds, cohorts, batches and time points hidden by generic labels. Filenames can expose inconsistencies without proving biological identity. Unresolved compatibility cannot be repaired by pooling controls to increase sample count. Define eligible comparisons from source design, not from favorable target responses; preserve later subgroup analyses as exploratory. If eligibility inspection reveals outcomes, record that exposure. Passing documented quality flags excludes those flagged failures, not every possible measurement artifact.

Distinguish:

- Replication in a comparable context: does a finding recur in different biological samples?
- Transfer across contexts: does it hold when a declared factor such as state, species or assay changes?
- Mechanistic tests: does a relevant intervention or orthogonal endpoint discriminate the proposed process from alternatives?

Several simultaneous differences can make transfer failure hard to explain. Favor comparisons that isolate a consequential difference, or describe the remaining ambiguity. Distinct accessions and identical feature names do not establish either independence or comparability. Preserve within-study contrasts; do not pool independently normalized measurements merely to increase sample count.

Before a substantial fetch or computation, explain why it has a better chance of changing the answer than the feasible alternatives. State what different outcomes would imply and what prerequisite could make the test uninformative. Use qualitative judgments rather than invented numerical information-gain scores. A source-paper reanalysis may be valuable even without a new dataset if it answers a different, defensible question.

## Select leads without overstating discovery evidence

Inspect source quality/status and sample design before fitting. Keep exploratory searches broad enough to expose unfamiliar mechanisms: use annotations to interpret or prioritize, not as a universal gate excluding poorly annotated features. Candidate abundance, pathway activity, coordinated modules and distinct molecular endpoints are possible lenses, not interchangeable measurements.

Compare against a defensible simple baseline. When evaluating predictive performance after searching features or models, repeat selection within the training portion of each eligible held-out split; include transformations learned from outcomes. Prefer genuinely independent studies for replication where available. Inspect whether selected leads survive changes in samples, justified baseline choices and relevant negative controls. A permutation or other null comparison must respect exchangeability and biological grouping. With very few units, report instability and seek a better experiment instead of relying on asymptotic p-values or extensive model tuning.

Use matched negative targets or alternative endpoints when they can distinguish a target-specific effect from a generic state response. Do not assume that controlling for a state program estimates a total regulatory effect. Predeclare the confirmatory comparison and retain retrospective sensitivity analyses as such.

For a striking cross-context discrepancy, compare the shared assay/time/readout where possible, then ask whether the target departs from the broader measured response. Define the shared eligible feature universe and comparison targets using defensible design or baseline properties. Show how matching, normalization and reference-set choices affect the inference. Thousands of genes are reference measurements, not thousands of independent biological samples; ranks or resampling genes cannot repair absent biological replication. State exactly which alternative the comparison resolves and which jointly changing factors remain inseparable.

When comparing treatment responses, prefer primary reference membership defined by untreated measurements and source design. Requiring treated abundance to remain above a threshold can select on the response being studied; report that restriction as a sensitivity analysis. Genuine quantification failures remain ineligible. Distinguish failed or unmeasured values from valid low measurements, and state any floor or clipping convention explicitly. Lead with the primary rule's result rather than a more favorable sensitivity result.

## Follow a result into the next decision

After a consequential result, name the explanations it weakens and those still compatible. Select a feasible observation that separates the remaining explanations; examples include a matched assay, a different time point, an orthogonal molecular endpoint or a source-identity audit. If these are unavailable, preserve the blocker and move to another consequential feasible branch. Repeated sensitivity calculations that cannot distinguish the same unresolved alternatives have diminishing value.

Investigate the closest prior work early enough to avoid spending the whole budget rediscovering a source paper's headline. For a promising exact claim, complete an appropriately scoped novelty search, including synonyms and relevant citation trails; record truncated result sets and unread hits. A scoped absence is not global novelty. Register rejection and known-result reproduction honestly.

The final synthesis should show how the original answer changed: a supported mechanism, a narrowed context, a rejected explanation, or a specific measurement needed to decide. Preserve new analytical findings even when biological novelty remains unestablished. Continue meaningful feasible work within the budget; at stopping, identify remaining resources and the best unperformed analysis with its reason for deferral.
