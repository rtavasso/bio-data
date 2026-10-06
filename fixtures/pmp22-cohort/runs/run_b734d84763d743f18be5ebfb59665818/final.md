The audit supports neddylation-sensitive EGR2 protein persistence, but does not establish that it chiefly mediates PMP22 regulation. I revised the EGR2-first starting preference toward a multibranch working model, while leaving the PMP22-mediated fraction unidentified. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11014456/?utm_source=openai))

What changed the interpretation

1. Persistence is supported: PMC11014456 Figure 8K–L reports faster EGR2 loss during a cycloheximide chase with MLN4924 after 48 hours of differentiation. ZEB2 did not show the same effect. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11014456/?utm_source=openai))

2. Abundance rescue is insufficient evidence: Figure 8N reports that MG132 restored EGR2 abundance without restoring MPZ. This is not selective EGR2 restoration, verified EGR2 activity, or a PMP22 initiation assay. It weakens an abundance-only sufficiency model without excluding active-EGR2 mediation. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11014456/?utm_source=openai))

3. Parallel branches remain plausible: the reported individual mTOR, Hippo/YAP, c-Jun and Sox2 interventions also failed to rescue the tested myelination endpoints. These failures do not establish which branch dominates PMP22 regulation. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11014456/?utm_source=openai))

Executed counterexample

The source-verified GSE201623 calculation retained 17,949 numeric features after explicitly identifying and excluding one embedded header—not a failed gene measurement. Descriptive median-ratio log2 effects, LentiAS versus LentiGFP, were:

    Egr2   +0.331
    Pmp22  −0.176
    Jun    −0.286

Directions agreed across raw-count, CPM and median-ratio summaries. These are descriptive results; two labelled libraries per arm do not establish independent donors.

The Egr2 increase contrasts with reduced nascent Egr2 transcription reported in the separate nuclear-run-on experiment. The experiments are not sample/time matched, so the discrepancy does not identify RNA decay or protein turnover. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC5800313/?utm_source=openai)) Separately, EGR2-specific siRNA did not reproduce AS-induced C-JUN activity, cautioning against treating Egr2-AS manipulation as EGR2-specific. ([pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11592338/?utm_source=openai))

Useful stopping result and falsifiable test

The intervention table contains 13 contexts and zero qualifying selective active-EGR2/endogenous-Pmp22-initiation rescue contrasts. Numerical half-life and mediated fraction remain unestimated, not zero. Native quantitative protein prerequisites and independently inspected Nae1 supplementary panels remain missing.

The proposed—not performed—test uses donor-labelled sister cultures with vehicle, upstream inhibition, selective EGR2 restoration, and their combination. It requires continuing upstream target engagement, restored nuclear EGR2 binding/transactivation, and promoter-specific nascent Pmp22 measurements before state divergence.

    Initiation recovery supports EGR2 sufficiency in that window.
    Persistent suppression despite verified activity restoration supports a parallel contribution.
    Failure to restore EGR2 activity makes the contrast uninformative.

Prior results changed concrete decisions: identification-only proteomics prevented invented abundance/half-life estimates; missing donor provenance prevented inferential RNA testing; failed mixture calibration prevented causal state adjustment. All inherited failed and untestable predictions remain retained.

Saved and published

Completed, synced notebook: q_59708481fed741af

Corrected analysis:
post_8361a97308264d1892df187d5132826d

Corrected bundle containing the report, intervention table, assay eligibility, source locators, scripts, receipts and rescue design:
artifact_13cc1c9191396833d1c76cb016bdf9702f312f5a8e285c852a8ac3a5c442b42c

RNA audit:
artifact_c2f6362168a0124b57c1e807a598b73005ed36f8c4f609b5be6743047d88faec

Producer receipts, archive hashes and publication readbacks were verified; scripts passed Ruff. I retracted unsupported browser-check claims and superseded the earlier publication/archive provenance; scientific output bytes were unchanged. The cis-promoter handoff remains pending, with no agent dispatched and no peer agreement claimed.