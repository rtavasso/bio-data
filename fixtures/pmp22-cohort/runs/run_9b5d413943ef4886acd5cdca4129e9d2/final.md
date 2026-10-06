No verified result in my end/isoform work establishes a PMP22-specific defect in the acute-arsenite RNA denominator. That remains unmeasured—not demonstrated unreliable, but not validated safe either.

Exact available evidence

1. Basal HEK293 cleavage measurements

   PolyASite2/GSE66092 PAPERCLIP:
   GSM1614165: primary terminal TPM 61.594916; site-retaining fraction 1.0.
   GSM1614166: primary terminal TPM 28.036445; site-retaining fraction 1.0.

   These native rows specify HEK293 cells, treatment “none.” They are not arsenite-treated HEK293T or matched capture chemistry. They measure terminal-site usage, not poly(A)-tail length or selection efficiency.

   Source: polyasite-usage.tsv, rows GSM1614165/GSM1614166.
   artifact_cab9bfda14010251628ff7b8d893fb0eb8ad87d192ee525239ac3401f4b407dd

2. Shared ends do not guarantee identical coding composition

   In the GTEx v9 filtered FLAIR table, ENST00000395938.6 and ENST00000312280.7 share a terminal exon but have different first exons. ENST00000494511.5 shares that terminal exon while omitting canonical coding segments from its internal path.

   This supports keeping CDS containment separate from end retention. It does not establish stress-induced isoform changes, productive ORFs, full-length coverage of every assigned read, or correspondence to your three RefSeq rows.

   Source: transcript-site-map.tsv, those exact transcript IDs.
   artifact_38b1b6bfb32140728b409c513a3b57633ebcca91bae62e99c65f5a795bec1c7c

Consequence for your sensitivity analysis

Given your stated preparation, CDS-only and transcript-wide RNA counts both come from the same poly(A)-selected material. Agreement can establish robustness to the counted region, but cannot by itself exclude selection bias shared by both denominators. Disagreement establishes denominator dependence—not APA, tail shortening, degradation, or isoform switching as its cause.

Keep the repeated CDS RPF vector as shared evidence, not independent isoform observations. GSE65778 can test a separate stress response but cannot validate the acute-arsenite denominator.

Both reused output hashes matched their registrations. The existing handoff, post_13a1b621cd7e4c3484ee34e53311dca6, remains applicable; LABBOOK is updated and synced. No new experiment or screen was run.