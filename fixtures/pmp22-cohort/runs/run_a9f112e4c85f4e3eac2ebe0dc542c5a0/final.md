The exact processed annotation is now available in post_47e5f926b60a4536902d4550f10a184d. It was already registered locally but missing from the shared library; I published the unchanged output and verified its shared bytes. No screen was rerun.

1. Exact annotation derivation

  Source: gencode.v19.annotation.gtf.gz, preserved ENCODE copy.
  Native header: human GRCh37, GENCODE19, Ensembl74.
  Matching eCLIP coordinate label: hg19.
  Gene: PMP22, ENSG00000109099.9.
  Strand: minus.
  Gene span: chr17:[15133094,15168643), zero-based half-open.

Source GTF coordinates were converted from one-based inclusive to [start−1,end). Rows were selected by literal gene_name=PMP22, with a unique gene record asserted. Gene rows were excluded from transcript grouping despite carrying a transcript_id attribute.

  Native compressed-source SHA256:
  a942a06720c48d10b80582ec2aabc49c519eeede6241cdc10254ba1cd53908ab

  Processed annotation:
  artifact_c903ed3621d37947e5d497192aca7b331242a3b5ad89b4da201db12979046f25

  Processed-output SHA256:
  65f69c1d331ed092e0e6a8250226238e5ea187c24e632027ca9f6c5454aa73f4

The derivation preserves screen.py and its successful execution-screen-r002.json receipt. The JSON contains transcript/exon/CDS/UTR/codon features; the native GTF remains authoritative for full attribute syntax.

There are eight transcript annotations but seven distinct annotated terminal boundaries—not eight observed ends. Their terminal exons are:

  ENST00000395938.2   [15133094,15134397)
  ENST00000312280.3   [15133094,15134397)
  ENST00000494511.1   [15133832,15134397)
  ENST00000395936.1   [15134113,15134397)
  ENST00000580584.1   [15134383,15134397)
  ENST00000426385.3   [15142657,15142928)
  ENST00000580497.1   [15162053,15162510)  retained_intron
  ENST00000471150.2   [15163596,15164078)  retained_intron

All use the hg19/chr17/minus/half-open convention. The genomic lower boundary is the terminal side, not a promoter coordinate.

2. Measured binding whose interpretation depends on inclusion

All following sites are K562 reproducible/input-enriched selected eCLIP peaks, using the same coordinate convention.

  PUM2 — ENCSR661ICQ / ENCFF767LWE
    [15133169,15133238)
    [15133388,15133423)
    [15133966,15134024)
    [15134036,15134088)

All four overlap annotated 3′ UTR in ENST00000312280.3 and ENST00000395938.2. Only the latter two overlap ENST00000494511.1; the final interval overlaps both its UTR and CDS.

  TIA1 — ENCFF298ZAG
    [15133283,15133345), long-model 3′ UTR.

  QKI — ENCFF027CBV
    [15133459,15133540), long-model 3′ UTR.

  IGF2BP2 — ENCFF977MKB
    [15142787,15142860), CDS overlap.

  SND1 — ENCFF331VCF
    [15142804,15142894), CDS overlap.

Exact peak/per-transcript table:
artifact_5edca4e4c4bd89c62c6779dcb242b33a8bc3f88a42b60c9f4897653b3ee20b85

Important coordinate critique: my feature labels mean overlap, not whole-peak containment. Shared-sequence peaks also do not identify which first-exon-bearing molecule was bound.

3. What site availability changes—and what it does not

PUM2 is the most consequential site-availability lead, but not a validated abundance regulator. Its K562 perturbation gives PMP22 +0.732 log2, nominal 95% CI [−0.004,+1.467], gene-wise q=0.546, with incomplete target-RNA depletion. No binder passes the joint criteria.

I have incorporated your completed end analysis and inspected your mapped-site artifact:
artifact_1dc56cde62ec0f2c595bb2ccdb71d1259b3c4dec85cda82a2ec057ab5761b9b7

Your partial-versus-complete retention distinction materially sharpens the hypothesis:

  GRCh38 one-based cleavage representative 15230714 conditionally
  retains PUM2 [15230719,15230771), while losing the other three.

  Representative 15230826 conditionally removes all four.

Those are GRCh38 predictions, not coordinates interchangeable with the hg19 table above. Cluster microheterogeneity and full-length transcript linkage remain essential qualifications. No current conclusion requires loss of all four regions; their functional sufficiency or redundancy is unknown. Losing the miR-29 site therefore does not establish complete PUM2 escape.

Finally, selected-peak absence is not absent binding. HepG2’s lack of selected PMP22 peaks coincides with substantially poorer RNA coverage. Likewise, your IGF2BP2 one-base containment ambiguity is not loss of binding, and SND1 availability depends on the internal exon path. These remain structural constraints on a future mechanism—not demonstrated natural-APA mediation.