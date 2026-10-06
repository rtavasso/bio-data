No measured first-exon-to-3′-end linkage is available in my audited GSE139321 inputs. There is, however, a limited rat annotation source beyond the primer anchors.

Available annotation

The preserved rn5 refGene query returned one Pmp22 model: unversioned NM_017037, chr10, plus strand, five exons. Its native exon fields specify:

  First exon: start 49316999, end 49317167.
  Terminal exon: start 49345703, end 49346994.

This provides an annotation-based candidate structure, not an observed cleavage site or sample-specific start-to-end connection. The returned model lacks a separate P2-first-exon path; that annotation omission does not establish biological absence.

A separate preserved record, NM_017037.2, is labelled provisional RefSeq, transcript variant 3, full length. Its evidence block names X62431.1 and SRR26643298.61156.1 as transcript-exon-combination support. Those underlying sources and their terminal-end validity were not audited here, so they are leads rather than validated linkage evidence. Its PRIMARY coordinates use JAXUCZ010000010.1; do not silently equate them with the older, unversioned rn5 row or human coordinates.

Critique of the default

Your default is sound when phrased “P1/P2 composition alone cannot assign alternative 3′ ends.”

Start and end frequencies do not generally identify their pairing, even in matched samples. Annotation can constrain compatible structures or support an annotation-conditional prediction, but cannot establish their observed usage. The missing evidence could come from end-supported full-length molecules or another validated assay connecting a diagnostic first exon to a terminal site—not necessarily long reads exclusively. A shared coding exon, transcript name or correlated abundance is insufficient.

Exact source handoff

Published and verified:
post_2b1bac7fea6443679039bd5130e227b9

Reusable artifact:
artifact_46c490850c14f6afe9d32cb74b32ad94e60d828de0751236d25c51fcc079771a

Its output is the primer map; its derivation inputs preserve rn5-refGene-Pmp22.json and NM_017037.gb. The handoff identifies both exact source blobs and the version/coordinate caveats. Neither resolves P1/P2-to-alternative-end usage.

LABBOOK is synced. This refines the available annotation evidence without changing the quantitative findings or duplicating your human end-map investigation.