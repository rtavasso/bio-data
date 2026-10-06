# Independent evidence and novelty audit

Question q_488429beed204371; this is source adjudication, not a new biological experiment.

GSE139321 / PMC7430845 is the discovery/quantitative-extension source. The parent audit already exposed source fitted changes for 5439 and 5446; the present calculations add library variance, zero-sensitive ratio diagnostics, positional neighborhoods and comparator context. Neither extracting the native file nor agreeing with its source edgeR directions is independent replication. Source differential-expression FDRs cannot test the difference between P1/P2 responses.

PMC7322568, final published mouse enhancer experiment, Figure 2A-C; Results paragraphs beginning “Upon identification of the desired deletion” and “Because our in vitro model”; Methods “Experimental animals”, “Reverse transcription-quantitative polymerase chain reaction”, Table 1.

  Species/tissue: C57BL/6-derived mouse whole sciatic nerve.
  Perturbation: germline 40.5-kb Pmp22 super-enhancer deletion; WT/heterozygous/homozygous littermates from a single founder followed by backcrossing. This changes enhancer dosage, not the Pmp22 coding locus by design; it is not evidence of independent edited founder lines.
  Time: P0, P10 and P56, not an acute cAMP or SOX10 time course.
  Figure n, WT/Het/Hom: P0 3/6/4; P10 5/5/3; P56 9/7/4. These are reported age/genotype sample numbers; litter-level allocation is not reconstructed here.
  Endpoint: first-exon-specific P1/P2 RT-qPCR with primers in Table 1, plus total RNA and other-gene controls; not nascent initiation.
  Observation: P1 is reduced in P0 homozygotes even though total RNA difference is nonsignificant. Both heterozygotes and homozygotes show P1 reduction at P10/P56. P2 reduction reaches source significance in P10 homozygotes and both deletion genotypes at P56; P2 is not invariant. Mag and Mpz show no detected RNA difference at these ages, supporting a more gene-selective perturbation in this distinct context. Nonsignificance is not equivalence, and differing significance across promoters is not itself a formal promoter-by-genotype interaction.
  Interpretation: independent in-vivo evidence that P1/P2-associated mature RNA can respond differently to a cis perturbation. This is NOT independent validation of the size of the rat cAMP or SOX10 response, nor proof that those interventions act through this enhancer. The thesis Chapter 3 and final article are the same experiment lineage and count once. We did not digitize plotted means, invent raw replicate values, or compute a cross-species pooled estimate.
  Source identity: saved native HTML SHA256 72fe05dae929f3ac87e20d85bc7340f3a33fc604e41076c989af11734d08e7ac, from producer post_c344fef84f344beca27925ec3f9ce940. Original transport receipt incomplete/reconciled; current byte verification does not reconstruct it. Readable extraction sources/PMC7322568.txt lines 203-236 and 376-419.

PMC3100536, separate rat S16 siRNA experiment, Figure 4A-B and BioC passages 17, 38-40, 51.

  Perturbation/time: Sox10 siRNA versus negative-control siRNA; RNA harvested 48 hours after transfection. Same S16 cell-line lineage, not donor replication or an in-vivo model.
  Endpoint: exon1a/exon1b RT-qPCR; qPCR performed in duplicate according to Methods (technical duplicates, not inferred donor n). Both transcript forms decline. The paper states similar results for two independent siRNAs without showing those data; that statement is not an independently reanalyzed replicate here.
  Egr2 also decreases; separate occupancy and motif-mutant reporters support regulatory involvement but do not isolate direct SOX10-to-Pmp22 mediation or nascent initiation.
  Support: independent perturbation experiment/assay supporting co-decrease of both Pmp22 first-exon RNAs. The recovered text does not supply sample-level P1/P2 response ratios for independent numerical confirmation of the large differential magnitude.
  Correct source: inherited PMC3100536-bioc.xml / PMC3100536-bioc.txt and matching preserved HTTP receipt. The simpler inherited PMC3100536.txt is a browser challenge and is expressly excluded, not silently substituted.

Novelty tiers

  Established: alternative first-exon regulation, SOX10-related Pmp22 RNA loss, and preferential P1 enhancer sensitivity already occur in primary studies.
  New executed extension of an exposed source: strong SOX10-loss relative P1 suppression across libraries/specifications; weak cAMP preference that becomes non-robust under combined low-signal and library sensitivity; both signals move together in RPM while relative composition changes. The failure of robust cAMP-selectivity is informative, not a reason to discard the source.
  Context observation, not replication: cAMP-cultured primary cells remain P2-dominant in this assay, unlike the two adult nerve libraries. Species is shared but cell composition, maturation and sequencer platform differ; this cannot establish failure of differentiation or causal promoter switching.
  Not claimed: new biology across all literature, direct cis mediation, acute SOX10 action, donor-general effects, promoter initiation, whole-transcriptome specificity or therapeutic selectivity.

The next discriminating experiment is donor/lot-labelled primary Schwann populations split to vehicle and cAMP, with promoter-resolved first-exon RNA and independently calibrated nascent output/survival measured on the same units. A true cAMP-by-SOX10 question requires crossed treatment arms within one system, not a subtraction between primary-culture and stable-clone effects.

Live discovery scope: a current Europe PMC general query returned 25 inspected metadata records and a page-budget warning; many were full-text keyword/review hits rather than promoter-resolved experiments. PMC7430845 is the same analysis source, not validation. PMID41296728/PMC12685092 supplies a myeloid GPSM1/cAMP/PMP22 lead, not Schwann-cell P1/P2 validation in the inspected abstract. Review articles and gene-level/protein endpoints were not promoted to promoter-resolved replication. A more focused TITLE_ABS query returned a preserved HTTP 503 warning, not evidence of literature absence. No claim of exhaustive independent cAMP-promoter evidence coverage is made.

The retry removing the promoter restriction succeeded, returned nine inspected metadata records, and reported exhausted=true for that query. It adds two consequential distinctions:

- PMID10806367 (2000), “Molecular dissection of the Schwann cell specific promoter of the PMP22 gene”: the primary abstract describes beta-galactosidase reporter constructs and a cAMP-sensitive silencer region. This is independent reporter-based support for cAMP-responsive PMP22 cis regulation, NOT an endogenous P1-versus-P2 RNA comparison, nascent initiation, or independent replication of the modest relative effect computed here. Full methods were not retrieved in this task. The existence of this study further limits any broad novelty claim about cAMP-responsive PMP22 promoters.
- PMID39823724 (2025), “Phosphodiesterase 4D inhibition improves the functional and molecular outcome in a mouse and human model of Charcot Marie Tooth disease 1 A”: the primary abstract reports Gebr32a-associated increases in several myelin genes while human PMP22 decreases in mouse transgene and patient-derived contexts. This is a useful gene-selectivity lead for the selective-perturbations peer, not P1/P2-resolved validation or an effect already reanalyzed here. Pharmacological PDE4D inhibition is not interchangeable with rat CPT-cAMP exposure. This warns against transferring the direction of gene-level response across interventions and disease/model contexts.

Source records and discovery response are preserved in independent-promoter-focused-retry.json, independent-promoter-retry-details.json and independent-promoter-retry-review.txt. The older 503 remains history. The targeted query's exhaustion is not exhaustive coverage of all promoter literature.
