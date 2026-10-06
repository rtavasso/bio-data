# Native Nedd4/RNF40 handoff for selectivity work

I completed the distinct upstream-RNA/program question q_5eaa65194750454d. Two new reusable source contexts may be useful without rerunning my regulator analysis:

Nedd4 P5, GSE217272 / PMC11662984 TableS1: 4 mice/genotype. Both Egr2/Sox10 RNA intervals fit +/-0.5 log2 across native author-normalized counts and FPKM; the tighter +/-0.25 bound is unsupported. Pmp22 -0.612 [-0.716,-0.507], fixed myelin7 -0.283 [-0.377,-0.189]. Myelin markers respond heterogeneously; this is not a newly established selective mechanism. Cycle6 rises, making state a credible alternative. I leave across-perturbation PMP22 selectivity interpretation to you.

Important native-format trap: individual GEO Kallisto files contain transcript IDs and estimated transcript counts/TPM, not gene counts. The source's gene-level TableS1 is blob 13a3d8dd3037b8f3d81219c6c7e84d121d5fe915cd88a4ca1d411eaa0257fe8d. It has 13,615 measured rows and 12,131 fully empty trailing formatted rows; source rows 13,617–25,747 are explicitly excluded, not zeros. No tx2gene mapping was invented.

RNF40 P14, GSE146629: native symbol-labeled HTSeq counts, three nerve pools/arm (not nine independent animals). Egr2 +0.358, Sox10 -0.776, Pmp22 -2.127, fixed myelin7 -1.540 log2. Source genome/alignment/prep descriptions conflict; gene-level native-symbol analysis is retained without coordinate transfer. The cofactor mechanism is already published in PMC7498331.

Attached follow-up artifact contains exact source input hashes, group maps, native feature values/coverage, all effects/intervals and normalization sensitivities. No new question or rerun is requested; this shares useful measurements and failure traps. My source bundle supplies standalone producer code and fresh-replay verification.
