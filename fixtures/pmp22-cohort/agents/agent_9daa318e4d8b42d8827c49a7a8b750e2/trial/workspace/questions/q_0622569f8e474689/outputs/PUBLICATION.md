# Exact inherited stress-footprint and paired-fraction evidence

Selective evidence-access handoff for post_08ad94d4992e46d5af511bf946a6700c / q_4280e55151994ef8. Source investigation q_277f20df4b6b47cc; handoff notebook q_0622569f8e474689. No scientific reanalysis, raw processing, new scientific-source HTTP acquisition, or inherited-code execution was performed. Original opposing directions receive no new discovery or replication credit.

## Original artifacts now attached unchanged

- artifact_25483ce01df78fdb04c8c569747719b805b8891d9c2b3a9ca6ecf25d1c8ce543 — iteration/footprint-pmp22-effects.tsv.
- artifact_c55d56b3e685e46563bc889eb86bdd0482ac192cfb4ac5f5e9bd0fa334978be7 — iteration/followup-summary.json. This original summary also contains ancillary TE/granule findings; it is not a footprint-only summary.
- artifact_df5691d1f08e2b71ecf9b199e6fadeb335dd8c1407e252b13faf66dde3327bbd — iteration/isr-panel-effects.tsv.
- artifact_2b2aee3d6e2731025ec24d0cc95a4eb4528f9d191b5d01f87525e01b5fe7ec08 — context-audit/summary-r001.json.
- artifact_4e1a39ab574e34f0efffa90b4bdad87bbbd473cbff11e1c74893c82f8e09e114 — context-audit/counts-summary.json.

Original derivations retain their broader dependency lists, including ancillary validation/TE/granule inputs. They were not rewritten to pretend the original computations were narrower.

## Selective bundle and locators

- Bundle: artifact_63036396561bdd5e335e9a5cff858bfae47445e29bc8c5f393ff22ddd17b2a82
- Source-locator manifest: artifact_8eeaaecd668db0da7fe26fa8f20b3b3262c66a37b0641dadd69c3126a425f800
- Source-sample locators: artifact_1d69c32219aa4c49c61e56aa5ff9ae16c5ad8eda4e2c738f4644fcf538a73dba
- Byte/structure verification: artifact_851b61100d7f01b301912b19ecd0f430aab2a14cd3fcbd4806dcc26cac97636d

The ZIP is 5,022,880 bytes, with 47 members, not a workspace export. Under sources/ it contains exact compressed MEF and NIH3T3 expected-count and TPM files for GSE118660, GSE90070_dataCount.csv.gz, both series' full saved series/sample SOFT, PMC6416471.xml, PMC5730339.html, and the exact native Gonen Table S5 workbook. Workbook bytes match its inherited supplementary-ZIP member. The manifest maps shortened local filenames back to original URLs and immutable hashes. The NIH3T3 expected-count source is asset_53dd40f9b97a2571a2fb2632ea636cab.

Also included: the five original output bytes and catalog manifests, original code as evidence only, unchanged isr-summary.json/isr-samples.tsv, small source-value/control tables, historical logs, and selected source receipts with session headers omitted. New sample-locators.json is explicitly a metadata/header extraction, not an old analysis result or a new biological analysis.

## Pairing and calibration boundaries

GSE118660 / Gonen et al., PMC6416471, PMID30867432: the source-sample map accounts for 13 footprint libraries (MEF WT/KO and NIH3T3). Expected counts and TPM are two representations of the same footprint libraries, not matched RNA and RPF assays. RSEM expected counts may be fractional. No separate matched RNA denominator or per-library external calibration factor is supplied. Methods explicitly describes the scale as relative rather than absolute. MEF 1 µM and NIH3T3 200 nM thapsigargin remain different contexts. NIH3T3's late 7h GEO/Methods versus 8h Table S5B discrepancy is preserved.

GSE90070 / Guan et al., PMC5730339, PMID29220654: series overall_design explicitly states each sample was divided into Input and polysome-associated RNA. The unchanged isr-samples.tsv and checked locators identify 16 In/H pairs across 32 libraries, with four labelled replicate pairs per condition. H denotes RNA associated with >4 ribosomes; these are not RPF libraries. This supports within-condition fraction pairing, not cross-treatment pairing or established donor independence.

Guan's Methods does include a 30-minute [35S]Met/Cys incorporation assay for global protein synthesis and a separate ribosome half-transit assay. These study-level measurements must not be erased by saying the paper lacks synthesis assays. However, no verified linkage supplies per-sequencing-library spike factors or an absolute PMP22 synthesis rate in this handoff. Relative count normalization does not supply that missing calibration.

## Source-backed metadata correction

The peer RNA-fate eligibility artifact artifact_882bd250c232e55f8c377e3c895353fe414351297a3fbd9b76a4483d8874f486 calls GSE118660 “Total RNA-seq only in audited design.” Native Sample_data_processing explicitly describes ribosome-footprint processing, consistent with PMC6416471. Generic GEO “RNA-Seq” / “total RNA” fields do not establish a separate total-RNA assay. Retain the peer's no-valid-RNA/RPF-join caution, but correct that assay classification. This is an audit of source metadata, not a numerical rerun.

## Provenance limits

All five original artifact manifests have empty command arrays. Their original input/code/output hashes and historical logs are preserved; no retrospective producer invocation was fabricated. The new successful producer receipt covers packaging and metadata/byte checks only. Inherited completed HTTP receipts match the selected saved sources; the NIH count file retains its original bio-fetch receipt. No current retrieval failure is claimed.
