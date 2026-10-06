# NRF2 necessity for PMP22 after neddylation perturbation

Question q_90f4fed27b7e4793; agent_cb63b61202404a3f9973a05b8b5a2be6. Completed bounded evidence audit on 2026-10-05. This is agent-authored interpretation of retrieved sources and an eligibility verification, not a new biological experiment or independent replication.

## Answer

The retrieved evidence does not identify NRF2 as a necessary mediator of PMP22 suppression after neddylation perturbation. It also does not establish that the antioxidant response is merely parallel or compensatory. Both remain live explanations. Nuclear NRF2 activity, neddylation/CUL3 engagement, antioxidant transcription, PMP22 nascent output, mature RNA and protein are separate endpoints. No broader signature scan was performed because it would not resolve this distinction.

## Prior results that changed the analysis

The seed and corrected state/composition notebook were read before new processing. Failed broad identity-marker calibration in the fixed P1 mixture models changed the plan: do not interpret a bulk residual as a Schwann-intrinsic mediator, and do not adjust away state to manufacture overlap. Instead require a compartment-resolved, matched perturbation.

The original five-gene artifact artifact_0f7ede8968ed0aba576c856ccef0022cb3cdae962cfc1bc2d2f92bd0172b83f9 and retrospective artifact_0ce2aca3b3d0f1f6230aa21d5cd4d5997c63cfeb0dc870e047a34cf245817e7f were selectively fetched and marked reused. Original frozen-floor status remains untestable. Osgin1 is measured, not missing: GSE241269 WT expected counts are 9, 5, 9, 1; the shared Figlia control normalized counts are 19.48, 9.412, 23.54. They fail the all-baselines-at-least-10 requirement. The other four antioxidant genes remain a retrospectively reduced panel, not a rescued lock or a newly independent validation panel.

The inherited Nae1 four-gene contrast is positive (reported effect 2.36864, interval 2.03796 to 2.69932), whereas Pmp22 RNA decreases (reported effect -1.49582, interval -1.92504 to -1.06659). These are reused source-analysis scores, not recalculated effects or NRF2 activity measurements. The locked Pmp22-versus-myelin7 preservation prediction failed: -0.0365, interval -0.241 to +0.168. This is not an equivalence finding. The same Figlia controls recur across contrasts, with P5/P7, driver and sample-map limitations retained. The inherited shared-feature universe is 12,496; this audit checked only the declared 13 genes and did not redefine a genome-wide universe.

## Source and assay audit

1. Nae1 paper, PMC11014456, Figure 8F/K/M/N; GEO GSE241269. P7 whole-nerve libraries are gene-level RNA, four labelled libraries per group; labels do not establish litter/pool independence. Figure 8F is nuclear EGR2, not nuclear NRF2. MG132 restored EGR2 but not MPZ in Figure 8N. That is neither selective EGR2 sufficiency nor a PMP22 promoter rescue. Protein experiments at other ages and rat Schwann cultures are not the same biological units as the P7 RNA. This result changed the proposed test: measure EGR2 and add a separate selective rescue, rather than assume the parallel EGR2 route is sufficient.

2. CUL3 plausibility versus nuclear evidence. PMC5658359 Figure 5 tests DCN1 inhibition/knockdown and cullin neddylation in cancer/liver-derived cells, with total NRF2 and downstream targets. It supports an upstream route, not Schwann or PMP22 mediation. PMC4789348 Figure 4 directly measures nuclear/cytosolic NRF2 after MLN4924 in rat cerebellar neurons. Nuclear evidence therefore exists, but outside the requested compartment and without NRF2 necessity or PMP22 output. Neither establishes a selective KEAP1 mechanism in Nae1-deficient nerve.

3. Genuine necessity evidence exists for other endpoints. PMC12596376 Figures 4 and 6 combine MLN4924 with siNrf2 in rat retinal endothelial cells exposed to advanced glycation end products. CUL3 neddylation/NRF2 ubiquitination and NQO1/redox/barrier endpoints were examined; siNrf2 attenuated protection. This is not Schwann/PMP22 evidence, MLN4924 is not CUL3-selective, independent cell-donor counts are unresolved, and there is no reported depletion-resistant addback in the inspected methods.

4. Schwann-cell assay feasibility is supported, not the PMP22 mechanism. PMC3863807 Figure 4 uses epalrestat, a nuclear NRF2 DNA-binding assay and NRF2 siRNA for gamma-GCS/GSH endpoints in commercial rat Schwann cells. PMC6497605 Figure 7 measures nuclear translocation/ARE activity in an immortalized mouse Schwann line. These provide activity/necessity-assay precedents but neither supplies the matched neddylation-by-NRF2 PMP22 test. The gamma-GCS qPCR is mature RNA, not a direct transcription-rate assay.

5. Context-dependent counterexample. PMC5802790 Figures 1–5 studies LXRalpha/beta-deficient mouse nerve and separate MSC80 cultures. Antioxidant-associated RNA and total NRF2 can coexist with adult PMP22 protein loss; preventive NAC begun at P21 restores myelin-protein endpoints. NAC is not selective NRF2 inhibition or proof of promoter regulation, and the cultured siRNA targets LXR, not NRF2. This prevents treating an antioxidant signature as a universal directional PMP22 rule.

## Independent-design discovery and exclusions

GSE113519 has A549 control versus NRF2-siRNA RNA-seq, with sibling occupancy data GSE113497 and superseries GSE113522. It is a real perturbation and an incidental full-expression opportunity, but lacks the neddylation factor and relevant compartment. Acquiring its expression matrix would not identify the requested interaction.

GSE326641 is a genuinely independent skin Nedd8/Nrf2 genetic design. In batch 2, the metadata contain one library each labelled N8_Ctrl, NEDD8_KO, NRF2_KO and NEDD8_NRF2_KO. This is a factorial-design lead, not an eligible PMP22 mediation test: K14/skin rather than Schwann-targeted Nae1, unidentified donor/pool replication, mixed-cell 10x 3-prime RNA, and no calibrated PMP22 nascent assay. The processed RDS was not acquired or executed. Raw title/genotype discrepancies, including NEF2_KO and reciprocal SUMO2 title/genotype labels, are preserved, not silently repaired. Related GSE326639 is skin Xenium spatial RNA after recombination or 14 days after wounding, not a nascent assay; its raw archive was not acquired. A separate adjacent-accession check of GSE326642 returned a private HTML notice, not valid SOFT or evidence of a sibling relationship.

Searches were bounded, not exhaustive: Europe PMC broad queries include incidental full-text matches; narrower title/abstract searches and direct NCBI GEO searches were also saved. A GEO hit resolving to GPL81 was a platform, not an experiment. The built-in discovery provider did not support GEO; direct E-utilities were used. Inaccessible injury-Nrf2 and skin-study full texts remain access limitations, not negative biology. PMC3628945 injury evidence is abstract-only and not used to identify PMP22 mediation.

## Proposed independent experiment and decision table

Use new independent neonatal mouse Schwann preparations, with each donor split across all four conditions: neddylation intact/lost by NRF2 intact/depleted. Prefer acute genetic Nae1 perturbation with verified kinetics; an orthogonal MLN4924 factorial is supportive, not evidence of drug specificity. Start before differentiation and separately validate any extension to constitutive P7 knockout nerve. Preserve donor, litter, sex, pool, driver, passage and batch. Cells, wells and genes are not donor replicates. This experiment is proposed, not performed.

Pilot baseline and 2/6/12/24-hour engagement windows, with later protein/function sampling, but do not assume these times achieve genetic depletion. At the earliest viable state-overlapping window, verify NAE1, total NEDD8 conjugates, neddylated/total CUL3, KEAP1-related engagement separately, nuclear NRF2 and DNA-binding/ARE activity. Verify NRF2 loss at protein/activity level using independent reagents and near-physiological resistant addback. Measure nuclear EGR2, SOX10, c-Jun/Sox2, viability, cell cycle and differentiation prospectively. No early overlap means the proposed comparison is non-identifying, not a reason to residualize the state differences away.

Primary endpoint: calibrated newly synthesized endogenous Pmp22 RNA. A promoter-specific claim additionally requires an appropriate initiation/first-exon nascent assay; mature first-exon qPCR alone is insufficient. Measure mature RNA/decay and later total/localized protein separately. Already exposed Nqo1/Hmox1/Gclc/Gclm and Osgin1 are individually reported engagement controls, not a newly locked panel.

Decision rules, conditional on verified NRF2 inhibition and state overlap:

| Antioxidant induction after NRF2 loss | Neddylation effect on Pmp22 nascent RNA | Interpretation |
|---|---|---|
| Eliminated | Suppression attenuated or eliminated; specific addback reinstates it | Supports an NRF2-dependent component/necessity in this context, not direct promoter binding |
| Eliminated | Suppression persists within a prespecified equivalence margin | Favors separation; NRF2 not required as the sole mediator; does not prove EGR2 mediation |
| Eliminated | Suppression worsens, rescued by addback | Supports compensation if toxicity/selection are excluded |
| Eliminated | Partial rescue | Joint pathways or partial dependence remain |
| Persists despite verified NRF2 protein/activity depletion | Any direction | This RNA program is not an NRF2-specific engagement readout; test other regulators/compartments |
| Any | State/viability overlap fails | Comparable-state mediation not identified; redesign timing or compartment |
| Variable | Protein rescue without nascent rescue | Not promoter mediation; investigate RNA fate or protein handling |

Estimate the neddylation effect within each NRF2 stratum and their interaction using donor-level uncertainty. For suppressive NRF2 mediation, attenuation produces a positive interaction under the stated contrast direction. Prespecify meaningful rescue/equivalence margins using independent assay calibration; lack of significance is not equivalence. This tests controlled genetic necessity/effect modification, not an assumption-free natural indirect effect. If Pmp22 suppression persists after antioxidant blockade, selectively restore active EGR2 under continued perturbation as a separate test.

## Verification, preserved negatives and stopping result

Producer receipt outputs/audit-execution-r003.json records successful execution, unchanged producer hash and all six output hashes. Validation checked 108 input hashes, 10 curated evidence rows, 16 sample records, 52 eligibility rows, 104 selected native expected-count values and seven decision cases. Run r001 failed because the audit assertion incorrectly expected the genotype string Nae1 KO; it was corrected to the observed Nae1 cKO. Failed receipt and stderr are preserved. Run r002 succeeded; r003 adds design-discovery metadata. None is an independent biological replication.

Additional inherited failures remain: Ppp6r1/Gtf2f1/Hck failed locked Zeb2 transfer; Eed truncated CSV and HDAC3 Mpz HIDATA failed estimates remain untestable; normal-reference fractions/responding identity remain unresolved; rat repair bulk/purified divergence is not neonatal replication; GSE201623 library labels do not establish donor independence; opposite stress footprints reject a universal rule without identifying synthesis versus decay; IRE1-associated RNA loss is known biology; PXD043917 identification is not genotype-resolved LFQ and has an age conflict; human-promoter, calibrated protein and hormonal branches remain unresolved; earlier unsupported browser claims remain retracted.

Exact remaining gap: a matched Schwann-targeted Nae1-by-Nfe2l2 comparison with donor identities, all four arms, nuclear NRF2 engagement, comparable early state and calibrated PMP22 nascent output. This endpoint-specific non-identifiability is the useful stopping result, not a claim that no redox mechanism exists.
