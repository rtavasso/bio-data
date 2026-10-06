# PMP22: a bounded map of a multilevel regulatory system

Question **q_277f20df4b6b47cc**, agent-authored investigation, 27 September 2026. The best-supported system combines gene dosage and cis elements, Schwann-cell differentiation signals, transcription-factor cooperation, RNA repression, and protein quality control. It is not a complete or universally transferable wiring diagram. Human Schwann cells are the intended biological endpoint, but most mechanistic perturbations and all newly analyzed expression measurements here are rat experiments.

## Regulatory architecture

1. **Dosage and cis architecture.** PMP22 dosage is clinically consequential: increased and reduced dosage produce different neuropathies. Its two commonly described promoters, P1 and P2, use alternative first exons; promoter choice must be measured separately from total gene RNA. The distal enhancer cluster and intronic elements extend control beyond proximal promoters. Primary enhancer studies support SOX10/EGR2-responsive elements and an endogenous role for the distal super-enhancer. Mouse super-enhancer deletion produces neuropathy, making enhancer integrity biologically consequential, rather than merely a chromatin annotation. See [distal enhancer experiments](https://pmc.ncbi.nlm.nih.gov/articles/PMC3298281/), [endogenous enhancer deletion](https://academic.oup.com/hmg/article/27/16/2830/4996744), and [mouse deletion phenotype](https://pmc.ncbi.nlm.nih.gov/articles/PMC7322568/). These sources were audited through indexed primary-paper excerpts; full text retrieval was blocked for some.

2. **The transcriptional core is cooperative and state dependent.** SOX10, EGR2/KROX20 and TEAD1 with YAP/TAZ regulate the myelination program. TEAD1 has both a route through EGR2 and evidence for direct PMP22 enhancer regulation (binding, perturbation and motif mutation), so an EGR2-only model is insufficient. Upstream candidates include axonal neuregulin–ERBB2/3 signaling, cAMP-dependent differentiation and POU3F1/OCT6; MAPK/YY1 and calcineurin/NFAT help connect extracellular signals to EGR2 regulation. Mechanical/Hippo control of YAP/TAZ activity remains an upstream branch requiring its own context-specific test. YAP/TAZ RNA abundance does not measure nuclear activity. [TEAD1 primary study](https://pmc.ncbi.nlm.nih.gov/articles/PMC5181599/).

3. **Chromatin and repair-state control add a second route upstream of EGR2.** A consequential finding from this investigation is that the Egr2 antisense RNA is itself controlled by neuregulin–ERBB2/3–YY1 signaling and is reported to recruit EZH2/WDR5-associated chromatin regulation at Egr2 and C-JUN. This opens a testable route from signal state through antisense RNA and chromatin to the myelination/repair transition. The published work also examines AP-1-associated accessibility and mTOR contacts. Neither those contacts nor a path through EGR2 prove direct regulation of PMP22 by the antisense RNA. [Primary study, Results and Methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC11592338/).

4. **RNA regulation can change PMP22 without changing promoter output.** miR-29a regulates the PMP22 3′ UTR and lowers RNA and protein in cultured Schwann-cell experiments. Human patient-derived fibroblast experiments support transfer to human PMP22 sequence, but do not establish the same magnitude in human myelinating Schwann cells. In that human model, reported RNA and protein reductions differ, illustrating why the endpoints cannot be substituted. Upstream control of miR-29 abundance, processing and loading remains unresolved here. [Schwann-cell study](https://pmc.ncbi.nlm.nih.gov/articles/PMC2713384/), [human cellular models](https://pmc.ncbi.nlm.nih.gov/articles/PMC6920087/).

5. **Protein folding, retention, trafficking and clearance determine functional dosage.** Calnexin and RER1-dependent retention, ER-associated degradation/proteasomes, chaperones and autophagy affect PMP22 handling. Mutation-specific findings, such as L16P retention, cannot automatically be applied to wild-type duplication. Total protein is also distinct from correctly folded myelin-localized protein. [RER1/calnexin experiments](https://pmc.ncbi.nlm.nih.gov/articles/PMC4227013/), [HSP70 experiments](https://pmc.ncbi.nlm.nih.gov/articles/PMC4342366/). PMP22 also affects cholesterol trafficking and ABCA1-mediated efflux; that is evidence for a downstream lipid consequence, not proof of a closed feedback loop onto PMP22 transcription. [PMP22–ABCA1 primary study](https://pmc.ncbi.nlm.nih.gov/articles/PMC6607759/).

## Actual measurements analyzed

**GSE139321 / PMC7430845: Tn5Prime promoter-associated RNA.** The processed table contains 4,993 selected SOX10/H3K4me3-associated TSS clusters, including 22 assigned to Pmp22. These are a selected feature universe, not every possible PMP22 promoter. Coordinates are rat **rn5**, sourced from paper Methods. Source-reported edgeR effects were extracted, not refit.

| Pmp22 TSS ID | rn5 cluster | cAMP/control log2FC; FDR | ΔSOX10/parental log2FC; FDR |
|---|---|---|---|
| 5439 | chr10:49316968–49317054 | +3.923; 0.00582 | −9.345; 1.59×10⁻⁴⁰ |
| 5446 | chr10:49319494–49319573 | +3.086; 3.48×10⁻¹²⁷ | −4.786; 1.82×10⁻⁴⁷ |

The primary-cell cAMP comparison and S16 SOX10-loss comparison are different experimental contexts. The sciatic nerve measurements are tissue-level. The paper and GEO descriptions of clonal replication are not perfectly aligned; no independent-donor sample size is inferred. Tn5Prime measures 5′ transcript abundance as a promoter-use proxy, not nascent transcription alone. No P1/P2 labels were imposed on these coordinate clusters. Binding proximity plus loss-of-function supports SOX10 dependence but does not eliminate indirect differentiation effects. Supplementary workbooks encode the same experiment and were checked as alternate representations, not independent replication. Human uppercase PMP22 in the isoform workbook is list membership/annotation, not a human expression measurement. [Study](https://pmc.ncbi.nlm.nih.gov/articles/PMC7430845/).

**GSE201623: Egr2-AS overexpression, primary rat Schwann cells.** The existing source-preserving Parquet and Pmp22 extraction artifacts fit this question's exact source identity and were attached for reuse. A new 28-gene panel was analyzed. Raw Pmp22 counts were AS: 220,643 / 201,051; GFP: 267,997 / 282,624. Median-ratio normalization across 13,610 genes positive in all samples gave these descriptive AS/GFP ratios:

| Gene | Ratio |
|---|---:|
| Pmp22 | 0.885 |
| Egr2 | 1.258 |
| Jun | 0.820 |
| Sox10 | 1.494 |
| Mpz | 1.530 |
| Mtor | 1.275 |
| Abca1 | 1.349 |

These are not differential-expression significance claims. There are two source-labelled libraries per condition; donor independence is not established. Sox10 and Mpz also show substantial within-condition variability. A repeated embedded header at source row 1472 was explicitly excluded; it was not treated as missing biological measurement. All original source bytes and strings remain intact.

**Contradiction retained:** these counts do not reproduce a simple Egr2-down/Jun-up repair-state signature. Pmp22's modest decrease cannot be attributed specifically to EGR2 repression. Compare nascent Egr2 transcription, EGR2 protein/activity, time course, and RNA-seq sample mapping before making a causal claim. GEO reports GSNAP alignment whereas the later paper describes HISAT2; that provenance discrepancy is documented, not silently reconciled.

**GSE201627 ATAC-seq:** processed peak files were selected to test whether promoter accessibility could distinguish direct chromatin change from an indirect state effect. See the separate promoter overlap outputs and method file. Called peaks alone cannot establish differential accessibility; peak absence is selected-out, not measured-zero. No rn5 TSS coordinates were intersected with rn6 peaks.

## Remaining frontier, in priority order

- Resolve the Egr2-AS discrepancy with verified sample mapping and matched nascent RNA, promoter-resolved PMP22 RNA, EGR2 protein, and quantitative ATAC counts. Existing peak calls provide candidate loci but cannot settle mechanism.
- Test TEAD/YAP/TAZ activity and localization alongside EGR2 rescue and PMP22 enhancer perturbation to distinguish direct and mediated routes.
- Validate promoter and enhancer effects in human Schwann cells with allele/copy-number-aware assays; do not transfer rat coordinate labels.
- Pair RNA with pulse-chase, surface/myelin localization and protein clearance measurements to separate synthesis from turnover.
- Audit miR-29 upstream regulation and additional RNA-binding/translation mechanisms; assess whether lipid changes feed back on PMP22 rather than merely result from its perturbation.
- Broaden beyond the present developmental/culture contexts to injury time courses, nonmyelinating cells, aging and other tissues. Hormonal, metabolic and pharmacological regulation, additional chromatin cofactors, cis variants and other miRNAs remain incompletely audited.

The available data favor a multilevel model, but do not identify a complete set of regulators or a single universal direction for extracellular signals. The question-local network retains hypotheses and discrepancies explicitly.

ATAC result detail: the selected rn6 RefSeq Pmp22 transcript NM_017037 window (chr10:49537087–49539087) has zero overlapping *called peaks* in all four files, despite abundant Pmp22 RNA. Egr2 has 3/1/1/1 overlapping peaks in GFP1/GFP2/AS1/AS2; Jun has one in each. This illustrates annotation/selection and endpoint mismatch, not loss of expression. Peak counts are not an effect size. The reference was retrieved in 2026 and is not proven identical to the authors' original reference.
