# PMP22 beyond the general myelination response

Question **q_277f20df4b6b47cc**. New specificity investigation continuing the inherited regulatory-system work; 27 September 2026.

**Ppp6r1, Gtf2f1 and Hck emerged as exploratory negative predictors, but none validated as a transferable PMP22-specific RNA predictor.** This rejects the tested prediction in its declared transfer setting. It does not establish that these genes have no biological effect on PMP22.

## What was inherited and what was new

The inherited work already inspected rat Egr2-AS perturbation (GSE201623), rat SOX10/cAMP promoter-associated RNA (GSE139321), mouse RUNX perturbation (GSE122774), human dosage arrays and their source papers. Those outcomes were exposed before this investigation. They provided the discovery starting point and were used retrospectively, never as fresh validation. The original snapshots and registered products remain intact.

New computations quantify PMP22 relative to a fixed myelin program, screen a broader measured feature universe, seal candidate predictions, test independent perturbation measurements, and investigate failed transfer. New datasets were selected from metadata and processed-file availability. No raw sequencing or downloaded code was executed.

## Discovery and candidate selection

GSE177037 contains purified rat Schwann-cell injury measurements at uninjured, day 3, day 5 and day 7, two pooled preparations per state. Each preparation contains 10–20 nerves; the individual nerves are **not** independent observations. The source already reports injury modules and myelin-gene downregulation ([Brosius Lutz et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC9063194/), Methods and Fig. 2).

Of 31,038 source feature rows, 31,010 had unambiguous repeated symbol labels. Twenty-eight ambiguous labels were excluded from mapping, not treated as absent expression. The original screen used CPM across mapped rows plus 0.5 before log2. Using full-library totals instead changes the eight discovery log values by at most 0.00423. Fractional RSEM expected counts were retained.

The fixed myelin score is the mean log2 expression of **Mpz, Mbp, Mag, Prx, Plp1, Cnp and Mal**, excluding Pmp22 and transcriptional regulators. A linear myelin-only model explains **98.12%** of Pmp22 variation in discovery. The remaining residual is small.

The screen considered 7,761 expressed, variable genes. Of these, 1,119 had source descriptions matching broad regulatory annotations; this is an explicit keyword screen, not a complete regulator ontology. Eligibility required ≥1 CPM in all eight samples and log-expression SD ≥0.25. Candidates were ranked by leave-one-timepoint-out error, required a consistent slope sign in all four folds, and at least 20% improvement over the baseline. The top three were selected. This cross-validation was used for selection, so its apparent performance is optimistic and is **not** independent validation.

| Candidate | Discovery partial correlation | Discovery held-state SSE / baseline | Frozen gene slope |
|---|---:|---:|---:|
| Ppp6r1 | −0.952 | 0.096 | −0.668 |
| Gtf2f1 | −0.958 | 0.143 | −0.681 |
| Hck | −0.956 | 0.146 | −1.502 |

The complete ranking, including rejected leads, is in `discovery-all-gene-screen.tsv`. Familiar Egr2, Sox10 and Jun did not improve held-state prediction beyond this score: error ratios 2.25, 2.81 and 1.48, respectively. This does not negate their established regulation of myelination; their RNA abundance is not their activity, and this endpoint asks a different question.

## Sealed independent tests

The first lock targeted Eed perturbation GSE106969. Its processed gzip is intact, but its decoded CSV ends mid-row at Gm24011 after 49,938,432 bytes, before PMP22 and every selected candidate. A second download endpoint returned identical bytes. The test is **untestable**, not negative. Missing rows were never converted to zeros or used to normalize a partial matrix.

The replacement lock retained candidate selection and coefficients and specified a primary Zeb2-deletion test (GSE76027) and secondary HDAC3 comparisons (GSE93159). It was sealed **before measurement acquisition**, SHA256:

`59fd5240b9e676b0d0eed97a0c42d41eca7d2645e9e3a368328ab2b8980f1c18`

General published Zeb2/HDAC3 myelination phenotypes had already appeared in source excerpts. Thus only the candidate-specific quantitative transfer was sealed before outcome inspection; this was not a fully blinded study. The discovery and validation samples come from different studies and species, with no known biological-sample overlap. Ensembl records confirm one-to-one rat/mouse orthology for the three candidates, which does not establish functional transfer.

The primary test used **three P25 mouse Zeb2-mutant nerves and three controls**, processed RMA log2 arrays. Units are explicitly documented in GSM1972986. Platform Entrez IDs were mapped using preserved NCBI mouse gene information, restricted to taxon 10090. There were 21,225 probes, 21,024 mapped symbols and 201 unmapped probes; all target/panel genes were mapped. No validation coefficients were refitted.

Success required ≥20% reduction in KO-minus-control contrast squared error, an upper 98.33% bootstrap interval below zero for the error difference, and the predicted negative conditional slope. Bootstrap resampling enumerated all 729 within-group combinations. Intervals remain descriptive because n=3/group is small and litter pairing is unknown.

| Candidate | Validation SSE / baseline | Validation conditional slope | Frozen-test outcome |
|---|---:|---:|---|
| Ppp6r1 | 1.241 | +0.838 | Failed: worse prediction and reversed sign |
| Gtf2f1 | 0.850 | +0.510 | Failed: only 15% improvement and reversed sign |
| Hck | 0.981 | +0.221 | Failed: negligible improvement and reversed sign |

Gtf2f1's error-difference interval was below zero, but it failed the prespecified improvement threshold and direction; it is not a validation success. Conditional signs remain positive after genotype adjustment. Sample omission makes the Ppp6r1 and Hck validation signs unstable, further limiting mechanistic interpretation; Gtf2f1 stays positive across those omissions.

Observed Pmp22 changed **−0.603 log2** (descriptive bootstrap 95% interval −0.771 to −0.453), whereas the myelin score changed **−2.177 log2** (−2.440 to −1.917). The frozen myelin-only model predicted −2.760 log2. The candidates did not adequately correct this substantial baseline-transfer failure.

## Specificity, confounders and source audits

- **Shared state rather than unique target prediction:** The candidates also predict residual Mpz and Cnp patterns. Hck's held-state error ratio for Mpz is 0.147, almost identical to its Pmp22 ratio. After controlling injury day, Ppp6r1 reverses sign; Gtf2f1 and Hck weaken substantially. Only two residual degrees of freedom remain, so these are diagnostics rather than causal estimates.
- **Composition is plausible but not established:** Hck is enriched in whole nerve relative to purified Schwann cells. However, immune-marker adjustment does not remove its discovery association. Purification, measured marker scores and bulk RNA cannot identify the cellular origin of every Hck transcript.
- **Known upstream alternative:** Hck was already reported to increase after Egr2/NAB disruption ([Mager et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC2440619/), Table 1 and Egr2-null experiments). Shared Egr2/NAB regulation can generate an inverse Hck/myelin association without Hck directly repressing PMP22. That paper's promoter-occupancy results for other genes were not transferred to Hck.
- **Baseline shape:** A quadratic myelin-only discovery model improved in-sample fit but worsened held-state error (SSE 6.07 versus 1.52 for linear). This does not rescue transfer or establish a unique gene mechanism.
- **Array dynamic range:** PMP22 is the highest mean-control RMA signal among mapped genes. Its apparent relative preservation could reflect biology, probe response/compression, or both. RMA values alone do not prove saturation. The post hoc relative-preservation hypothesis is explicitly unvalidated.
- **HDAC3 status correction:** Native Mpz entries in three of four files have `HIDATA`, which means too many fragments in the locus and failed quantification, not measured zero ([Cufflinks documentation](https://cole-trapnell-lab.github.io/cufflinks/file_formats/)). Initial arithmetic mistakenly accepted the numeric zero tokens. Those historical outputs are preserved but superseded by `correction-r003.json` and **`validation-summary-r003.json`**. The seven-marker secondary test is ineligible. Six-marker analyses excluding Mpz are exploratory and inconsistent across Cre contexts; n=1 per condition prohibits replicate uncertainty.
- **Independent Zeb2 RNA-seq diagnostic:** GSE74381 is a different P7 DhhCre study, with different age/control design from the P25 array experiment. The Cuffdiff table contains failed Mbp estimates and reports Pmp22 rising, whereas the deposited transcript-file pair has Pmp22 falling (12,152.8 to 470.8 FPKM). GEO associates the same filenames with both replicate records. These cannot be reconstructed as four independent libraries or silently reconciled. A valid six-marker, single-file-pair diagnostic gives candidate error ratios 5.89, 0.963 and 3.77; none supplies convincing rescue. It is post hoc and not another untouched validation.

The original AS and RUNX inputs were revisited retrospectively with the same frozen models. Some models improve AS prediction, while all worsen RUNX prediction. Hck grossly overpredicts the RUNX contrast. Those exposed experiments support context dependence, not fresh confirmation.

## Novelty and strongest supported statement

The new work establishes an **informative failed prediction**, not a novel mechanism. Eight preserved literature queries examined exact candidate/PMP22 terms, synonyms and Schwann/nerve contexts, with primary-text review of the discovery paper, both Zeb2 papers, Eed and Egr2/NAB. Evidence and novelty status are separate in `outputs/discoveries.json`. Novelty remains unresolved for the specific candidate-to-PMP22 claims; Hck's participation in a shared myelination-regulatory response is already known.

**No tested candidate qualifies as a validated, transferable PMP22-specific RNA regulator.** The data support context-dependent expression relationships and substantial technical limits. They do not measure promoter-specific output, protein trafficking, regulator activity, or a causal direct effect of the selected candidates.

A test that could overturn this conclusion would directly perturb one candidate in an independent, species/age-matched purified Schwann-cell experiment with rescue, adequate biological replication, fixed myelin controls, calibrated PMP22 RNA measurement and cell-state controls. Corrected Eed exports and unambiguous Zeb2 RNA-seq sample mappings would also permit more interpretable reuse. The inherited broader hormonal/metabolic frontier remains unfinished.

## Outputs and reproducibility

- Authoritative numerical synthesis: `RESULTS.json`
- Primary test: `validation-primary-results.tsv`, `validation-summary-r003.json`
- Figure: `PMP22-specificity.png` and `.pdf`
- Source and correction audits: `eed-source-integrity.json`, `correction-r003.json`, `hdac3-status-audit.tsv`, `zeb2-representation-audit.json`
- Selection, confounders and novelty: `discovery-all-gene-screen.tsv`, `confounder-adjustment.tsv`, `alternate-myelin-targets.tsv`, `literature-novelty-audit.json`
- Exact artifact receipts: `registrations.json`; reproduction guide: `REPRODUCE.md`

The current mechanism map is revision 12, investigation queue revision 10 and discovery ledger revision 2. Current vocabulary/coverage was corrected without rewriting historical snapshots. All five new high-priority branches have executed analyses; unresolved biology is retained explicitly. The parent full-system question remains open.
