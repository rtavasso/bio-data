# Finding useful data beyond target-name searches

Use this guide for broad mechanism investigations and discovery questions. The aim is to find measurements that can change the answer, including studies collected for another purpose. A remote topic is useful only when its design can address a consequential uncertainty; familiarity is neither a requirement nor a reason to reject a source.

## Search from the uncertainty as well as the target

Target-name and synonym searches establish reported knowledge. They preferentially retrieve connections somebody has already described. Also construct queries from the unresolved mechanism, upstream perturbation, assay, material and endpoint, omitting the central gene. For example, a discrepancy between RNA and protein can motivate searches for RNA turnover, ribosome loading or protein trafficking experiments. Choose mechanisms from the question and observed evidence rather than following a fixed biological checklist. Verify organism and identifier mappings when aliases collide.

Use two routes: follow the provisional mechanism map, and independently ask which experiments might have measured the relevant cells, locus or process. Measurement coverage can justify inspection before a causal connection is known. Let inspected data add or revise branches; collecting a dataset for every known factor is not the objective.

Use source papers to locate accessions, supplements and related assays. Then look beyond that bibliography when it keeps returning the same experiments or explanations. Follow a consequential upstream control or competing process into its own experimental literature and repository metadata. Different papers, accessions, formats and citations may still describe the same samples or reuse the same dataset.

Make a bounded pass over a neglected branch before spending the remaining budget refining the easiest dataset. Allocate effort according to expected discrimination and feasibility; no fixed number of queries, datasets or positive discoveries is required. Keep source discovery separate from the later search for precedent for an exact result.

## Explain the connection, then inspect it

For a promising indirect source, add a compact note to the existing notebook or investigation queue:

- The query or citation route, study identity and exact candidate file; whether it is newly located or inherited.
- Its original experimental purpose and the proposed connection to the central question. Label each necessary link supported, hypothesized or unresolved.
- The measured endpoint or upstream process, intervention and controls that could distinguish competing explanations; state what different outcomes would imply.
- The prerequisite to inspect next, such as feature coverage, regulatory-element coordinates, sample matching, assay units, quality flags or a processed supplement.
- The eventual disposition: inspected, analyzed, rejected on evidence, blocked or deferred; link the output or reason and explain any change to the answer.

Use existing queue statuses when recording the disposition. These notes are question-local judgments, not a platform relevance score. A hypothesis can justify inspection without already being proven. If the central target is unmeasured but an upstream process is measured, explain which link can be tested and which remains untested. Do not turn an indirect association into a complete causal chain.

Screen metadata cheaply, then inspect suitable processed matrices, feature annotations, source tables and sample records within budget. A target absent from a title, abstract, selected hit list or incomplete index may still be measured. A target absent from the assay cannot be reconstructed by assuming a zero. A well-designed perturbation with assay-wide measurements may be more informative than a target-specific paper with no usable contrast. If a source is rejected, retain the concrete design or measurement reason.

## Examples of finding and rejecting opportunities

These are hypothetical reasoning examples, not claims about particular studies or a checklist to complete. Adapt the search terms to the question. Each connects a reason to inspect with a possible comparison and a limit on what it could establish.

- **Different research focus, useful perturbation.** For a question about a differentiation program, a migration study might have measured the transcriptome after a signaling perturbation. Try queries such as `"[cell type] migration perturbation RNA-seq"`, without the target gene. Inspect the complete matrix, treatment timing, controls and biological replicates. A usable design could compare the target response with the wider differentiation program; a selected migration-gene list cannot establish the target's absence or response. Redirect if the relevant measurements cannot be obtained.
- **Relevant cells inside a broader atlas.** A question about a rare stromal population might benefit from an organ atlas advertised for a different cell type. Search `"[organ] single cell atlas metadata"` or `"[organ] multiome"`. Inspect cell annotations, donor identities, representation and assay coverage before extracting a subset. Adequate data could test whether a pattern persists within the population rather than reflecting composition. Sparse cells or missing donor labels limit the comparison; RNA and chromatin assays do not imply matched cells or establish regulation.
- **A secondary assay hidden behind the headline.** A paper focused on protein localization might include a companion transcriptional time course. Search `"[process] perturbation time course"`, then inspect methods, supplements and related accessions for measured endpoints beyond the main figure. Verify that RNA samples share the relevant intervention, controls and timing. A suitable comparison could distinguish an early RNA response from a later protein change; unmatched experiments leave that ordering unresolved. Move on if only images or selected markers are available for a question requiring broader measurements.
- **An observation opens a new search branch.** Suppose an acquired dataset shows increased protein with little RNA change. Search `"[cell context] ribosome profiling perturbation"`, `"[cell context] RNA half life"` or `"[cell context] protein turnover"` according to the competing explanations. Inspect matched input measurements, assay units and feature eligibility. A suitable assay could distinguish altered synthesis from degradation; RNA abundance alone cannot. Evidence from another context may test a process there while leaving the original discrepancy unresolved.
- **An attractive source fails the needed comparison.** A large expression matrix contains the target, but the proposed treatment effect requires controls and cell identities that are missing. Inspect sample records and linked metadata before rejecting it. If the gap remains, retain its limited value for feature coverage, record why it cannot test the treatment hypothesis, and redirect toward a smaller matched experiment. Target presence and file size do not compensate for an unusable design.

## Turn an opportunity into a test

For the most informative feasible lead, extract actual measurements and run the analysis. Inspect broader responses or suitable negative controls when they can challenge the proposed link. Retain context, endpoint and independence limits when comparing experiments; observations in another tissue can test a process there without establishing transfer to the central context.

After a new mechanism or anomaly appears, reconsider both previously acquired files and new sources. Preserve an informative negative finding: it may eliminate a plausible connection or reveal the measurement needed next. If a promising source cannot be analyzed, record the unresolved prerequisite rather than claiming that locating it closed the branch.

Report original study purpose, whether its authors already discussed the target/result, and the exact additional analysis separately. A known mechanism recovered from a general paper is a repaired blind spot. An unadvertised gene row or a previously unused comparison can support a new analytical use. Neither establishes that nobody has used the data for that purpose; that requires a scoped precedent search and appropriately qualified claims.
