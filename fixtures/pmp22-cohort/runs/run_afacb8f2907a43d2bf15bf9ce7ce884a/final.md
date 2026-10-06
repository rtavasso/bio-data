SOX10 knockout shows a robust relative loss of P1-associated RNA. cAMP co-induces both signals, but preferential P1 induction is fragile rather than uniformly supported.

Executed results

Focal clusters: P1-associated 5439 and P2-associated 5446. Values are native RPM, mean ± sample SD:

Condition                 P1-associated        P2-associated
Vehicle, 3 cultures       1.287 ± 1.120         411.77 ± 33.88
cAMP, 3 cultures          19.521 ± 4.731        3492.62 ± 436.01
S16 parental, 2 samples  523.801 ± 13.893       5855.00 ± 21.21
SOX10 KO, 4 clones         0.743 ± 0.991         194.91 ± 104.41

SOX10 loss:
  P1 and P2 change by log2 −9.460 and −4.909, respectively—a response difference of −4.552.
  All eight clone-to-parental cross-library ratio comparisons are negative.
  All 168 combined cluster-window, low-signal and leave-one-library checks retain the negative difference.
  Mean within-library P1/(P1+P2) falls from 8.211% to 0.301%.

This is relative P1 depletion, not absolute P2 compensation: P2 also falls strongly.

cAMP:
  P1 rises 15.172-fold and P2 8.482-fold; the nominal log2 response difference is +0.839.
  However, one vehicle library has zero focal P1 signal. Its unadjusted log ratio is undefined, not silently imputed or discarded.
  Combined sensitivity checks span −0.343 to +1.433 for the response difference. Removing that zero-P1 control and adding 1 RPM reverses the apparent preference.
  Mean P1/(P1+P2) increases only from 0.3265% to 0.5539%; P2 remains overwhelmingly dominant.

Thus co-induction is well supported in these libraries, but a robust preferential cAMP response is not.

What the design permits

The primary comparison comprises three independent culture populations per arm, with donor/lot matching undocumented. The SOX10 comparison comprises four established edited clones versus two parental RNA preparations—not six donors or matched control clones. The parent researcher’s critique confirmed those limits.

There is no cAMP-by-SOX10 factorial experiment. Within-library P1/P2 comparisons are valid descriptive contrasts, but cannot establish a treatment interaction across these different models. Reported sensitivity ranges are not confidence intervals.

Measured comparator signals also change substantially: Mpz and Mbp rise with cAMP and fall after SOX10 loss. Consequently, the supported selectivity is within PMP22, not a PMP22-only perturbation. P2 is not an invariant control. The 4,993-cluster SOX10/H3K4me3-selected universe is neither the whole transcriptome nor all PMP22 transcripts.

Independent evidence and novelty

PMC3100536’s separate 48-hour SOX10-siRNA experiment supports decreased first-exon RNA from both promoters. Final mouse study PMC7322568, Figure 2, supports differential, age-dependent first-exon responses to enhancer deletion. Neither independently validates these rat response magnitudes; the mouse thesis and final paper count as one experiment lineage.

The contribution here is the executed per-library variability and robustness analysis—particularly the failure of a strong cAMP-selectivity claim—not discovery of previously unknown SOX10 or cAMP regulation. These total-RNA start signals do not establish nascent initiation or direct cis mediation.

Published and verified

Main analysis:
post_d796b8a816a54b3a80d5662043ac90c9

Complete sources, code, tables, figures and assumptions:
artifact_47ffe12f2c56f91300e2658703d42cf66ba4edae2cb34d0847d6f7f11c5e245d

Per-library table:
artifact_c5b306cc4cf73b8d43a58cc0f75679b5250ef975ebb1cbbd60d5957cc3241c71

Contrasts and sensitivities:
artifact_359615391bfc799b2d716ec77ad9267b7b1ca9ed6bb1db225273108feb626ace

Shared with selective-perturbations:
post_7ecc0aec99444ae58621efc0514ad8ef

Independent computational validation passed 129 checks; scripts pass ruff. Publications and registered bytes were read back, and q_488429beed204371 is completed and synced.

Next discriminating question: does modest cAMP-associated P1 enrichment persist in donor/lot-split cultures above the P1 low-signal range, and does it reflect altered initiation rather than RNA survival?