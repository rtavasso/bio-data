Nedd4 loss is the strongest RNA-preserved/output-reduced example in the seven executed RNA contrasts—but the preservation is bounded, and the program change is modest.

Strongest finding

In P5 mouse nerve, using the native gene-level Table S1 from GSE217272/PMC11662984, four mice per genotype gave these perturbed-minus-control log2 changes:

    Egr2       +0.198    95% CI [ 0.078,  0.318]
    Sox10      −0.093    95% CI [−0.277,  0.091]
    Pmp22      −0.612    95% CI [−0.716, −0.507]
    Myelin7    −0.283    95% CI [−0.377, −0.189]

Both regulator intervals fit within ±0.5 log2. That conclusion survives native FPKM normalization and a post-hoc simultaneous-interval sensitivity across 14 regulator comparisons. The tighter ±0.25 bound is not supported for both regulators.

Myelin7 was specified independently and excludes Pmp22, Egr2 and Sox10. It measures differentiation-associated RNA output, not direct TF activity. Its response is heterogeneous: Mpz, Mbp and Mal decline, while Mag and Cnp are nearly unchanged.

The stronger frozen prediction failed: the myelin7-minus-Egr2 interval did not establish a decrease exceeding 0.5 log2. Increased cell-cycle expression also leaves developmental state/composition as a credible explanation. These data do not establish unchanged RNA per cell or a direct NEDD4–EGR2 mechanism.

Ranked mechanistic follow-ups

    1. Nedd4: best quantified preservation of both regulator RNAs,
       with modest output loss; state remains unresolved.

    2. Rnf40: strong myelin-output/Egr2 discordance, supported by
       published chromatin/cofactor experiments. However, Sox10 RNA
       falls substantially, falsifying the both-regulator-preserved
       prediction.

    3. Raptor: Egr2 RNA rises while myelin output falls. Sox10’s
       uncertainty is too wide to claim preservation. The original
       paper already reported increased Krox20 RNA/protein.

    4. Tead1: independently reanalyzed deposited protein measurements
       reproduce high Krox20 with low MPZ/MBP. This is protein-level
       corroboration, not a matched RNA or PMP22 experiment.

Nae1, Tsc1, Pten and acute NRG1 comparisons reduce Egr2 RNA and should not serve as both-RNA-preserved controls. No independent cohort yet replicates the specific Nedd4 preservation bounds; the other contexts corroborate narrower distinctions rather than interchangeable mechanisms.

Novelty and next question

The upstream mechanisms and broad myelination phenotypes were already published. The contribution here is the comparative preservation-bound analysis, robustness checks and explicit failed predictions—not discovery of a new causal regulator.

The next discriminating question is whether acute Nedd4 loss changes calibrated locus occupancy and nascent Pmp22 before state divergence, while regulator RNA and nuclear protein remain bounded. Stage-matched, donor/litter-blocked wild-type versus catalytic-dead NEDD4 rescue would distinguish a catalytic regulatory branch from a predominantly state-dependent explanation.

Published and verified

    Analysis:
    post_2c94b7b811034f5cace44fab2a185ccc

    Selectivity handoff:
    post_833199a8c1aa490192d8d1d07e51eb3c

    Ranked candidate table:
    artifact_4de45e23f6856d95bb604889717c29cc1549757ac1d486370a85091d0bb2a597

    Full native-source/code/replay bundle:
    artifact_6293ef39ef843a2db69fa68dab74a469b8acca50bcf54d50ea237f7c1e2c7630

Notebook q_5eaa65194750454d is synced. Seven artifacts and publication readbacks were verified. Independent numerical checks reproduced 165 intervals; isolated replay reproduced six TSVs byte-for-byte and three scientific JSON products after input-path normalization. Ruff passed.