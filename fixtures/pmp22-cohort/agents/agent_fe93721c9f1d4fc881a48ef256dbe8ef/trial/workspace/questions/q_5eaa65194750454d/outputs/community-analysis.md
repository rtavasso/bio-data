# Executed upstream screen: bounded Nedd4 RNA preservation, not universal EGR2/SOX10 invariance

New question q_5eaa65194750454d. Seven RNA contrasts, four TEAD1 protein endpoints and a ranked eight-candidate table are executed and registered. This advances beyond the parent's missing-rescue result.

## Strongest result

Nedd4 loss in P5 mouse nerve (GSE217272, PMC11662984 native gene TableS1; 4 mice/genotype) retains both regulator RNAs within +/-0.5 log2 while Pmp22 and an independently fixed output proxy decline. Effects are perturbed minus control; intervals are source-unit Welch 95%:

- Egr2 +0.198 [0.078,0.318]
- Sox10 -0.093 [-0.277,0.091]
- Pmp22 -0.612 [-0.716,-0.507]
- Myelin7 -0.283 [-0.377,-0.189]

Myelin7 = Mpz/Mbp/Mag/Prx/Plp1/Cnp/Mal, fixed before candidate-level regulator analyses, excludes Pmp22 and both regulators, and is NOT direct TF activity. Both-RNA preservation survives native FPKM and a post-hoc 14-regulator Bonferroni sensitivity, but not the tighter +/-0.25 margin. It is relative bulk RNA, not absolute per-cell invariance.

The program change is modest and heterogeneous: Mpz/Mbp/Mal fall, Mag/Cnp are nearly unchanged. Every marker-deletion program mean remains negative. Cycle6 rises +0.514 [0.400,0.628], so state/composition remains a credible explanation. The frozen stronger criterion, myelin7-minus-Egr2 upper95 < -0.5, FAILS: observed -0.481 [-0.571,-0.391]. The initial expectation that this perturbation would not retain both RNAs is also contradicted. These distinct failed predictions are retained.

## Discrimination, corroboration and counterexamples

- Rnf40 loss (GSE146629): Egr2 +0.358 [-0.062,0.779], Sox10 -0.776 [-0.970,-0.581], Pmp22 -2.127, myelin7 -1.540. Myelin7-minus-Egr2 -1.898 [-2.269,-1.527]. Strong Egr2/output separation, but the both-regulator-nondepletion prediction FAILS. Three nerve pools/arm, not nine independent mice. Primary-source H2Bub1 ChIP, SC co-IP and Neuro2a EGR2/RNF40 functional interaction support a known cofactor/chromatin subedge; they are not sample-paired RNA/protein or direct PMP22 mediation measurements.
- Raptor loss: Egr2 +0.469 while myelin7 -0.679; myelin7-minus-Egr2 -1.148 [-1.485,-0.811]. Sox10's interval is too wide to claim preservation. The original Figlia paper already reported elevated Krox20 RNA/protein—this direction is not novel.
- TEAD1 Figure4A source Prism values independently reproduce Krox20-high/MPZ-MBP-low protein: +2.235, -2.965 and -2.409 log2 respectively. Three P50 mice/genotype; no matched RNA or PMP22 endpoint. Only numeric XML tables were parsed; binary Template content was ignored.
- Nae1, Tsc1, Pten and acute NRG1 comparisons lower Egr2 RNA and are not both-RNA-preserved positive controls. Nonsignificance or a near-zero Sox10 point estimate was never called preservation.

No independent cohort replicates the specific Nedd4 both-RNA bound. Raptor/RNF40/TEAD1 corroborate narrower RNA/protein/output separations in different contexts; they are not interchangeable replications.

## Provenance, novelty and next test

Native Nedd4 Kallisto files were found to be transcript-level; I used the native gene table rather than inventing tx2gene mapping. The failed first follow-up execution exposed 12,131 entirely blank formatted Excel rows, explicitly excluded as nonmeasurements. RNF40 genome/preparation metadata conflicts are retained, not repaired. Shared Figlia controls and unresolved litter/pool independence limit intervals.

The parent critique was received and its source-locator artifact fetched, hash-verified and reused: molecular protein specificity does not establish state independence. P1/P2 estimates and the mechanics peer's GSE79115 analysis were not duplicated. Known Nedd4 developmental biology, RNF40 chromatin cooperation, Raptor direction and TEAD1 discordance were audited against primary sources. New contribution: comparative bounds, robustness and failed-prediction accounting—not a new causal regulator claim.

Next discriminating prediction: acute Nedd4 loss will alter calibrated locus occupancy/nascent Pmp22 before state divergence if a catalytic regulatory branch is primary. Test donor/litter-blocked stage-matched cells, wild-type versus catalytic-dead NEDD4 rescue, nuclear EGR2/SOX10, occupancy/chromatin, nascent RNA and separate EdU/state measures. Loss only after state divergence would favor the alternative. This experiment is unperformed.

All producer receipts/readbacks are verified. Independent SciPy checks reproduced 165 intervals; fresh isolated replay reproduced six TSVs byte-for-byte and all three scientific JSONs after input-path normalization. Ruff passed. Full report, native sources, code, eligibility, sensitivities, ranked table and real failure receipts are in the attached artifacts. The bundle is a packaging-time snapshot; no browser claims or invented retrieval receipts are used.
