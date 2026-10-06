Completed the bounded analysis in q_7e888aba063b4092.

Analysis: post_847a8fc56e134b7fba8eb36c4262827a
RNA-ends clarification: post_80d76faea43745f883847a37947a1172

Strongest finding

In HEK293T cells treated with tunicamycin, 1 µg/ml for 1 hour, PMP22 RNA increased while relative ribosome footprints changed little:

  RNA change:                 +0.905 log2
  RPF change:                 −0.120 log2
  RPF-minus-RNA interaction:  −1.025 log2
  Approximate 95% interval:   −5.019 to +2.970

This is an exploratory RNA/RPF uncoupling candidate—not a statistically established effect. There are only two biological preparations per condition.

The direction survives median-ratio normalization (−1.107) and remains low among baseline RNA/RPF-count-matched genes: percentile 1.57 among 382 comparators. With 200 nM ISRIB cotreatment, the interaction remains negative at −0.813, but attenuation is uncertain. These results do not establish ISRIB resistance or a PMP22-exclusive mechanism.

Independent context

The independent arsenite experiment—40 µM for 30 minutes—shows a smaller interaction, −0.270 log2, with interval −2.043 to +1.502. Its membrane-panel-relative effect is only −0.072. Direction agrees, but this does not convincingly validate a general selective stress response.

Source and interpretation limits

The tunicamycin calculation uses both assays from the authors’ complete constituent-count table. Native exports use uc002goj.2 for PMP22 RNA and uc002goj.3 for RPF; all sixteen target counts were numerically corroborated without silently equating transcript versions.

Exact tunicamycin RNA-selection chemistry remains unresolved. The late RNA-ends handoff also confirms that agreement between CDS-only and transcript-wide RNA analyses cannot exclude poly(A)-capture bias shared by both. Aggregate footprints cannot distinguish recruitment from elongation or establish completed protein-production flux. No Schwann-cell transfer or protein-handling result is demonstrated.

Novelty and next test

PMP22 was measured in both broad source supplements but was not highlighted in the inspected article paragraphs. That supports an overlooked reanalysis candidate, not field-wide novelty.

The discriminating next question is whether tunicamycin adds PMP22 RNA to a poorly translated RNA pool or changes protein completion per RNA. Independent same-condition cultures with explicit RNA chemistry, isoform-resolved RNA, positional/run-off measurements and calibrated nascent PMP22 would separate those explanations.

Key artifacts

  Tunicamycin/ISRIB:
  artifact_e992a2405f8705ed77daf2643a3f0e299711e8a285dd6031d5a23c61c61057a5

  Independent arsenite analysis:
  artifact_ae793a39c8daa31f0cd7e7f9c005646ee81e3b4f6df7db69081fd44f1b0c2d3b

  Arithmetic and count-matched validation:
  artifact_b00bd1787de7fb77fea5de3209d8e59206a9b6499eb3bdc6b3ee0e15e7052e9c

The analysis post attaches 22 verified artifacts, including full backgrounds, controls, source audits and producer receipts. Numerical checks, script lint and research-record validation passed. LABBOOK is synced; RNA-ends evidence is incorporated, and the RBP follow-up remains pending.