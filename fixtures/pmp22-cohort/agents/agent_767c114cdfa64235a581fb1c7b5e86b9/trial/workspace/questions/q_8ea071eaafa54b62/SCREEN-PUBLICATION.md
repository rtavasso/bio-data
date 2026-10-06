# Executed first-pass screen: binding is present, abundance nomination fails

Question q_8ea071eaafa54b62. I executed a processed-data screen covering all 223 source-defined high-quality ENCORE eCLIP contexts (150 RBPs) and their 203 matched RBP knockdown RNA-seq contrasts. All 426 native processed files were downloaded and checked against source MD5 and size. The 20 unmatched contexts remain explicit in the table; all paired DE files contain the same 20,474-gene background. GENCODE19 identifies PMP22 as ENSG00000109099.9 on minus-strand hg19 chr17:[15133094,15168643).

Five reproducible PMP22-binding contexts were found, all K562: IGF2BP2 (one CDS peak), SND1 (one CDS peak), TIA1 and QKI (one 3UTR peak each), and PUM2 (four peaks, all 3UTR in the two long coding transcripts; one also intersects CDS of an alternative transcript). This is binding evidence, not five validated abundance regulators. No HepG2 selected PMP22 peak was found; that is not proof of absent binding.

No joint candidate passes the stated criteria: source gene-wise FDR<=0.05, BH across all 203 planned PMP22 contrasts<=0.05, adequate target RNA depletion and reproducible binding. The broad failed prediction is preserved rather than rescuing it with a five-binder denominator. Median PMP22 baseMean is 8.25 in HepG2 and 41.28 in K562; 85/92 and 13/111 contrasts respectively fall below the exploratory low-coverage flag of20. No equivalence/no-effect claim follows.

PUM2 is the strongest site-based follow-up, not a confirmed RNA regulator here: K562 ENCSR661ICQ / ENCFF767LWE yields four PMP22 peaks, while PUM2 KD ENCSR118XYK / ENCFF217GTE gives PMP22 log2(KD/control)=+0.732, 95% Wald CI[-0.004,+1.467], raw p=.0514, gene FDR=.546, screen BH=.996. PUM2 target RNA itself falls only0.753 log2; current ENCODE metadata also warns of missing biosample characterization. IGF2BP2 and SND1 pass the conservative target-RNA depletion screen but have wide nonsignificant PMP22 intervals. Protein knockdown adequacy is not inferred from RNA alone.

The supplement's old DESeq file IDs were reconciled with current GC-bias-corrected Salmon/CQN files by experiment, cell and control, not by guessing replacement IDs. FUS/HepG2 has a retained control-map conflict and is not ranked. One failed producer run is preserved: GTF gene rows carry a transcript_id field and needed exclusion from the transcript grouping; corrected run r002 completed against the same frozen native inputs.

Registered products:
- Binding-by-perturbation TSV: artifact_6a0119b8ecd1d29ff44d122e74920f2097d6b1c9179ab9572f2237585effc047
- Summary: artifact_6301fefa2df5dd8e1add3b1061228298725067a539e9a42b289fb9d5d05e5360
- Peak sites with per-transcript annotation: artifact_5edca4e4c4bd89c62c6779dcb242b33a8bc3f88a42b60c9f4897653b3ee20b85
- Complete eligible backgrounds: artifact_72a872b3caad48de5465572d0403d38c82b906e6f9bd078777f18a91e9010b8b

Ongoing: batch-normalized sensitivity (not replication), independent PUM perturbations in other cell contexts, and source-specific novelty audit. A newly recovered primary paper PMC13234107 already explicitly studies QKI-dependent PMP22 isoform balance in human stem-cell-derived Schwann precursors; QKI cannot be labelled a newly discovered PMP22 connection. That paper's interpretation and isoform/first-exon mapping still need auditing. No novel decay mechanism or Schwann transfer is claimed.
