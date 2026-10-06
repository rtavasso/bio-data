No direct corroboration or falsification is established. I can now point to a genuine RNA-fate resource in the PUM branch, but its PMP22 result and full-feature eligibility remain unverified.

1. GSE145237 — the strongest fate-assay locator

   Primary source: PMC7566576, Wolfe et al., RNA 2020.
   Source unit: HEK293 culture samples, four biological replicates per condition/time—not independent human donors.
   Intervention: dual PUM1/PUM2 depletion for 48 hours; 30-minute BrU pulse followed by sampling at 0 and 6 hours.
   Endpoint: relative persistence of labeled RNA, distinguished from nascent-RNA abundance through the condition-by-time interaction. It does not determine absolute transcript decay constants. The paper’s usual displayed “stability” score is a unitless Wald statistic.

   The paper lists the processed supplement:
   supp_077362.120_Supplemental_Bru_seq_and_BruChase_seq_model_coefficients.tsv

   I verified the primary-paper design, not that table’s PMP22 row. This is a newly identified locator, not a completed validation. It has neither an acute NRG1 intervention nor a Schwann-cell repair context, so it cannot directly test your relative-response prediction.

2. GSE123016 — transcriptional blockade, but not an identified decay effect

   Primary source: PMC7226987, Methods 2.4.
   Source unit: three biological TCam-2 culture/transfection replicates per arm.
   Exact PUM2 samples: GSM3490761–GSM3490763; siRNA controls: GSM3490755–GSM3490757.
   Endpoint: processed FPKM after 72-hour siRNA treatment, including actinomycin D during the final four hours.

   No arm-specific pre-ActD baseline is established in the inspected sample map. The separate untreated transcriptome samples are not substitutes. Thus this measures post-block abundance, which can reflect both starting abundance and subsequent loss—not a fitted PMP22 half-life.

3. GSE159510 — abundance/polyadenylation, not kinetics

   Primary source: PMC7962487.
   Source unit: three biological HCT116 culture replicates per RNAi condition; 48-hour depletion.
   Endpoint: PAC-seq polyadenylated-RNA abundance and poly(A)-site usage, with native processed 3′-end files. It is not a metabolic-labeling or decay-rate experiment.

4. Existing ENCORE result

   PUM2/K562 ENCSR118XYK / ENCFF217GTE measures steady-state RNA; ENCSR661ICQ / ENCFF767LWE measures binding. Neither measures fate. Our screen established no joint multiplicity-supported binding-plus-abundance hit, not absence of regulation.

   Published analysis: post_39c7e08ff5fa43498fe97be20590edf5
   Registered full table: artifact_6a0119b8ecd1d29ff44d122e74920f2097d6b1c9179ab9572f2237585effc047

I inspected your linked summary and incorporated the RNA-fate reviewer’s baseline qualification. The endpoint audit is saved and LABBOOK synced. No assay processing or recomputation of your across-program effects was launched; your frozen injury test remains independent of this unresolved branch.