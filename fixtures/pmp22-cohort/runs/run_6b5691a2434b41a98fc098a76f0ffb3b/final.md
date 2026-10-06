No GRCh38/hg19 intervals in my existing audit meet your full assembly/strand/base-convention requirement. I do have source-verified human hg18 reporter-fragment coordinates—not rat lifts—that provide useful starting locators.

All ranges below are human chr17, hg18, March 2006 UCSC assembly. They are literal printed ranges. The cited methods do not explicitly declare interval strand or endpoint/base convention; I have not certified them as BED or one-based closed intervals.

1. P2-containing and intronic constructs — PMC3100536

   Methods, “Transfection Assays,” BioC passage 15:
     P2-containing −2 kb construct: 15,106,498–15,106,933
     Intronic +11 kb reporter:      15,091,959–15,092,201

   Methods, “Transgenic mice,” BioC passage 22:
     Larger intronic fragment:     15,090,965–15,092,611

   The P2 construct contains the native P2 promoter; its boundaries are not an exon1B or TSS annotation. The larger intronic fragment was tested with an Hsp68 promoter and is distinct from the short +11 kb reporter.

2. Distal enhancer reporter fragments — PMC3298281

   Methods, “Transfection assays”:
     A / −120 kb: chr17:15,253,855–15,254,150
     B / −115 kb: chr17:15,250,013–15,250,409
     C / −91 kb:  chr17:15,221,688–15,222,096

   PMC5181599, Methods, “Luciferase assays,” repeats the B, C and short +11 kb coordinates.

Critical mapping pitfalls

   The distance labels refer to the translation start, not the P1 TSS. PMC3298281 Figure 1 occupancy coordinates are rat rn4, whereas its Methods reporter coordinates are human hg18.

   The NCBI build 36 interval chr17:15,143,663–15,311,619 in PMC3298281’s Introduction is the overlap of patient duplications—not one precisely delimited enhancer. The thesis’s corresponding literal “hg36” token should not be silently normalized.

   I have no equivalently verified P1/exon1A interval. PMC7145652 Figure 1B–D supplies a human P1 TATA-target locator, but my audit did not anchor it to an assembly-specific exon interval.

Reusable evidence

   Exact PMC3298281/PMC5181599 HTML is in artifact_306fb5726176ef0cce72cbb8e050d575baedd023b6014e8fe674336b16a4c606, published at post_c344fef84f344beca27925ec3f9ce940.

   PMC3100536 BioC XML is preserved as input blob 0cbe637cb10bd02d5085dca80c7841012ee4269ce116bcc0b1db856bf8733b6e in my original bundle’s provenance.

A harmonized overlap would establish overlap with a tested human sequence, not endogenous-human enhancer necessity or causal QTL mediation. I verified the preserved source hashes and synced this handoff to LABBOOK; no new primary collection, liftOver or QTL analysis was performed.