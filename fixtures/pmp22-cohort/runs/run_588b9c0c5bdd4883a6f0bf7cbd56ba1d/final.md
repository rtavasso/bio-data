No—my interpretation does not require loss of all four PUM2-associated regions. A miR-29-lacking molecule could remain PUM-responsive through the retained proximal interval, provided that interval is actually occupied and functional in the relevant transcript and cell context. Neither its sufficiency nor redundancy with the other regions is established.

Your distinction should remain explicit:

  GRCh38 cleavage representative 15230714:
  conditional partial retention, including PUM2 [15230719,15230771).

  Representative 15230826:
  conditional loss of all four mapped regions.

These are different site-availability hypotheses, not demonstrated differences in regulation. Peak counts cannot be translated into regulatory strength. Cluster microheterogeneity also prevents treating the retained peak boundary as an experimentally defined functional motif. Even loss of all four mapped regions would not establish absence of every possible PUM-dependent or indirect effect.

The PAC-seq follow-up is now completed, but does not resolve those exact ends.

GSE159510, HCT116, hg38/GENCODE32, Supplemental Table S2 supplies gene/exon aggregate measurements. Its PMP22 exon identifier is:

  PMP22_exon_chr17:15231080

That token is not an established cleavage coordinate. I cannot assign its aggregate values to your 15230714 versus 15230826 molecules or establish their full-length coding-path linkage.

All five inspected contrasts report Splicing APA=No and Tandem APA=No. These are thresholded source calls—the analysis uses a 20-percentage-point distal-use-change threshold—not evidence that rare ends are absent or usage is equivalent. Single- and dual-PUM abundance responses also remain unsupported after source FDR; they do not establish mediation through the retained interval.

Exact completed outputs:

  PMP22 endpoints:
  artifact_846caefc1fb2760cf47e458fe0745e309566d4a1845b78cf4a4d512f4704e0f2

  Full audit:
  artifact_779f4542f3154e93b42e157e59949383da2b50a7704a66aa4966704979b3a532

I already incorporated your map and IGF2BP2 boundary ambiguity in LABBOOK and post_1698da9b00254105913582883fecd721. Dominant-end retention constrains interpretation within your measured contexts; it is not assumed HCT116 or Schwann-cell evidence.

The older annotation-access request is also resolved in post_47e5f926b60a4536902d4550f10a184d, with the unchanged processed GENCODE19 annotation and peak artifacts available in the shared library. No new experiment, re-screen or raw processing was performed for this reply.