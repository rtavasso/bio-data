# PMP22 regulatory system — new iteration

Question **q_277f20df4b6b47cc**. This report continues the supplied question. All work in `outputs/REPORT.md`, `outputs/specific/REPORT.md`, map revisions through r012, queue through r010 and discovery ledger through r002 is **inherited**, including the rejected Ppp6r1/Gtf2f1/Hck predictors. Nothing in those analyses receives new-work credit here.

**The new analysis strengthens an endpoint- and context-dependent account of PMP22 regulation; it does not establish a novel universal regulator.** Chronic stress can reduce Pmp22 RNA and its association with heavy polysomes, but a separate fibroblast footprint experiment shows the opposite response. Genetic-array evidence is sensitive to which control cultures are compared. A gene's membership in an ER-stress program cannot supply a universal regulatory sign or predict functional myelin protein.

## What existing evidence establishes

The inherited primary-source audit supports several distinct layers:

- **Dosage and cis architecture:** copy number, P1/P2 transcripts, distal/intronic enhancers, SOX10/EGR2 and TEAD/YAP/TAZ. Gene-level counts are not promoter output. Endogenous enhancer deletions and motif/perturbation experiments are stronger evidence than expression associations. See [enhancer work](https://pmc.ncbi.nlm.nih.gov/articles/PMC3298281/), [endogenous deletion](https://pmc.ncbi.nlm.nih.gov/articles/PMC7322568/) and [TEAD experiments](https://pmc.ncbi.nlm.nih.gov/articles/PMC5181599/).
- **Upstream signaling and timing:** cAMP/differentiation and NRG–ERK–YY1–Egr2-AS/chromatin routes. The inherited Egr2-AS RNA/protein discrepancy remains unresolved; RNA abundance does not measure regulator activity or nascent transcription. Human transfer and quantitative mediation remain unestablished.
- **Post-transcriptional regulation:** miR-29/3′UTR perturbations, Dicer/AGO involvement and context-specific G3BP1-associated changes. Binding does not itself establish altered decay. The [miR-29 primary source](https://pmc.ncbi.nlm.nih.gov/articles/PMC2713384/) supports a mechanism but does not quantify endogenous AGO loading across injury.
- **Protein disposition and reciprocal effects:** glycosylation, UGGT1/calnexin, retention, degradation and trafficking regulate processed protein. [Glycosylation experiments](https://pmc.ncbi.nlm.nih.gov/articles/PMC8191293/) separate interaction from functional necessity; [ABCA1 experiments](https://pmc.ncbi.nlm.nih.gov/articles/PMC6607759/) show reciprocal protein-processing effects without proving transcriptional feedback.

The present iteration adds measurements of stress-dependent RNA/polysome partitioning, genetic PERK/eIF2α perturbation, ribosome footprints, RNA-granule partitioning and a PTEN metabolic intervention. These are separate contexts, not pooled biological replication.

## Executed new analyses

**1. Matched RNA and heavy-polysome RNA, GSE90070.** The processed matrix has 20,234 genes and 32 libraries: four conditions, four labelled replicates, two fractions per sample. There are 10,760 genes with at least ten reads in every library. Pmp22's minimum count is 1,136. MEFs received 400 nM thapsigargin; heavy fractions contain more than four ribosomes. Separate donor identities are not established.

| Pmp22 contrast | Cytosolic RNA log2 change | Heavy-polysome RNA log2 change | Difference between fractions |
|---|---:|---:|---:|
| 1 h / untreated | −0.974 | −1.543 | −0.569 |
| 16 h / 1 h | −1.960 | −1.962 | −0.002 |
| 16 h / untreated | −2.934 | −3.505 | −0.571 |
| Last-4-h PERKi / 16-h stress | +2.740 | +3.272 | +0.532 |

Median-ratio and CPM normalization retain the directions; leave-one-replicate analyses do too. The PERKi relative-loading difference has a descriptive replicate-based 95% interval of +0.318 to +0.746 log2, conditional on the replicate model. Without external calibration this is **relative polysome association**, not absolute protein synthesis. Chronic/acute congruence reproduces a result already explicitly discussed for PMP22 in [Guan et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC5730339/). New effect-size estimation is not biological novelty.

**2. Frozen genetic test, GSE49598.** The prediction was sealed before target-specific validation outcomes were acquired: `prediction-r001.json`, SHA256 `ad886ca8e48a1d0db27ce28b1b189c59c1729d288602363b6149bc0524952947`. It required WT repression of at least 0.5 log2 and relief of at least 0.5 log2 in both PERK-KO and eIF2α-S51A cells, with concordant probe directions. General published ER-target findings had already been seen; this was not fully blinded.

The **original numerical rule fails**: the two Pmp22 probes give WT responses +0.014 and −0.655 log2, median −0.320. Positive pooled mutant interactions do not rescue that failure. Subsequent source inspection changes the interpretation further: the four nominal WT arrays combine two ATF4WT and two PERKWT filename groups, and one PERKKO untreated filename says Mock24h. Matched WT provenance for the eIF2α mutant is unclear.

All **48 target probe measurements across 24 native Agilent exports pass the conservative native quality-flag audit**. Thus failed quantification or background flags do not explain the discrepancy. In the post hoc PERKWT subset, both probes decline (−0.685/−1.062 log2); in the ATF4WT subset they give +0.712/−0.247. Alternative normalization retains the PERKWT declines. These subset calculations support a context-sensitive PERK hypothesis but are **not replacement confirmation** of the frozen test. They cannot separate line, batch, normalization and biological response. Probes are not assigned to P1/P2.

**3. Independent footprint contradiction, GSE118660.** Across 22,406 genes, 7,776 pass conservative abundance eligibility. Pmp22 has at least 107 expected counts and 66.11 TPM, avoiding the source's low-abundance floor. In MEF WT, Pmp22 footprint TPM increases at 1, 2, 5 and 8 hours; the 8-hour effect is **+1.238 log2**, versus the sealed prediction of repression. Median-ratio and CPM agree on direction. This contradicts the secondary prediction; it is not translation-efficiency validation because matched RNA is absent and each condition has one library.

The native [Gonen et al. supplement](https://pmc.ncbi.nlm.nih.gov/articles/PMC6416471/), Table S5A, reproduces those values and classifies Pmp22 in the late-induced cluster. In its NIH3T3 experiment, footprints instead decrease: 102.35 TPM untreated, 39.38 at 2 h and 33.34 at the late point. Dose differs too: MEF 1 µM, NIH3T3 200 nM. GEO/methods label the late NIH3T3 point 7 h; Table S5B labels it 8 h. No value was relabelled silently. Shared-label values match GEO across 22,381 genes; 25 date-like labels differ between Excel native dates and GEO strings and were not guessed into gene identities.

This follow-up weakens an explanation based only on polysome versus footprint assay: the same footprint study itself has opposing cell/dose contexts. It does **not** isolate which contextual difference causes the reversal, or establish a universal causal effect of PERK.

**4. Translation and RNA granules, GSE103667/GSE90869.** In [Namkoong et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC6359928/), Pmp22 deposited TE values decrease in both NIH3T3 replicates. Seven nearly repeated RefSeq rows are not seven independent observations. A linear-TE interpretation gives approximately −2.49 log2, but exact file-scale documentation is incomplete; the downward direction is robust to that ambiguity and the conditional magnitude is labelled accordingly. Pmp22 is around the 33rd percentile of the gene-level TE change, so it is not an exceptional target in this broad suppression program.

Three processed granule tables contain 34,739 source rows each. After retaining duplicate-label provenance and excluding one inconsistent annotation, the representative-gene analysis covers 24,171 genes. For Pmp22, median-centered ER-stress granule/cytoplasm changes are **−0.313, −0.291, +0.440 log2** across three biological replicates: no reproducible preferential enrichment. Heat/arsenite comparisons are also preserved. No named spike calibrators were supplied in these tables; failed supplement routes are recorded. Consequently, **absolute recruitment remains unidentified**. Lack of relative enrichment does not prove absence of sequestration. The 9,309-gene TE/granule comparison is exploratory and from the same study; the paper already established general decoupling between translation loss and granulation.

**5. PTEN/metabolic intervention.** Native [Figure 7 source data](https://pmc.ncbi.nlm.nih.gov/articles/PMC10940316/) show Pten reduction in Pmp22-transgenic nerves, but no convincing metabolic rescue distinct from differentiation. Double-mutant/CMT1A mean ratios are Pten **0.514**, Hmgcr **1.217**, Nrg1-I **1.006**, Ngfr **1.229**, Sox2 **1.098**, Pou3f1 **0.903**. Hmgcr's descriptive interval is broad and does not establish rescue. No PMP22 endpoint after PTEN intervention is present in this table, so reverse promoter feedback is untested.

Two source-quality findings constrain precision: Figure7A supplies four double-mutant values although its legend says five; Figure7B contains an identical six-gene vector in WT row6 and HNPP row8. The missing value was not imputed and the duplicated vector was not arbitrarily corrected. Removal of either occurrence is retained as sensitivity, not a claim about animal identity.

## What changed, novelty and next decisive test

The strongest new inference is a **restriction on the regulatory model**: neither chronic ER-stress program membership nor PERK perturbation alone determines a transferable sign for the PMP22 output being measured. The original RNA-only view now has explicit translation/partition endpoints and an executed genetic test, but context, control provenance and measurement scale remain consequential. This survives count-floor and simple normalization explanations in the footprint comparison, while failing to distinguish dose, cell lineage/state, batch and assay-dependent occupancy. The source papers already contain the central response directions; the scoped novelty audit does not justify a previously unknown biological mechanism.

The overturning experiment is a matched, adequately replicated Schwann-cell study with a fixed genetic background, PERK perturbation plus rescue, two stress doses and a timecourse, measuring calibrated nascent and mature PMP22 RNA, heavy-polysome RNA, footprints and protein synthesis/processing from matched cultures. That would separate RNA loss, translation initiation, ribosome occupancy and clearance. For the present source problems, obtain exact WT-line/control mapping and corrected Figure7 animal-level exports before tighter inference.

The broader question stays **open**. Human promoter-specific regulation, direct TEAD/EGR2 mediation, endogenous miRNA loading, matched human functional protein and hormonal regulation retain their inherited limitations. No novel mechanism was manufactured, and inherited rejected hypotheses remain rejected.

## Reproducibility and handoff

- Numerical authority: `isr-panel-effects.tsv`, `genetic-validation-summary.json` **together with** `array-quality-summary.json`, `footprint-pmp22-effects.tsv`, `followup-summary.json`, `pten-summary.json`.
- Figure: `PMP22-iteration-r002.png` / `PMP22-iteration-r002.pdf`.
- Decisions: `decision-r001.md` through `decision-r006.md`; frozen prediction: `prediction-r001.json`.
- Provenance: `registrations.json`, input-object manifests, native files under `inputs/iteration/`, and `inputs/iteration/transport.json`.
- Source/novelty review: `primary-passages.json`, `novelty-audit.json`, `web-searches.json`.
- Current notebook: `../../LABBOOK.md`; network/queue/discovery snapshots are preserved in the parent output directory.

Run ordinary scripts with `./bin/python`; no downloaded scripts, formulas, macros, pickle/R objects or raw sequencing were executed. Agilent inputs are already processed feature-extraction measurements. Repeated source labels, native blanks, numeric zeros, ineligible values and absent measurements remain distinct.
