Use the supplied interpreter from this checkout. No installation is required.

All analyses use preserved processed data. The source-preserving Egr2-AS Parquet is reused through the recorded manifest in inputs/continued-reuse.json. Native sources, exact hashes and receipts are listed in outputs/continuation-preservation.json and inputs/continuation/transport.json. Computational code, environment and input hashes are captured by the 44 registrations in outputs/continuation-registration.json. Existing registered outputs should be copied aside before any intentional rerun.

Run question-local scripts with ./bin/python workspace/questions/q_277f20df4b6b47cc/scripts/SCRIPT.py. The scientific execution order is:

1. audit_rna_continued.py, then analyze_globin_specific.py.
2. analyze_protein_interactors.py.
3. analyze_human_dosage.py, then audit_human_channels.py.
4. analyze_runx_accessibility.py, then analyze_runx_locus.py. Both use read_tdf.py on unzoomed processed tracks, not raw sequencing.
5. analyze_runx_rna.py. Its six native gzip inputs were copied byte-for-byte from GSE122774-processed.tar, preserving the exact member names. Do not execute archive members. The archive and extracted files are all preserved; filename/header and GEO-title mismatches are explicitly audited.
6. analyze_g3bp_endpoints.py uses the inspected supplemental table and main XML. PDF text was extracted with the locally authored read_pdf.swift and native PDFKit, not a downloaded executable.
7. analyze_lipid_summary.py extracts published summary means from preserved primary HTML. Its derived index is illustrative, not a paired measurement or a new significance test.
8. validate_continuation.py verifies all registered output hashes, finite TSV numeric values, network references and investigation conventions.

extract_claim_evidence.py preserves exact selected primary paragraphs. assay-endpoint-audit.tsv is an authored audit, not a newly measured matrix. checkpoint/finalize scripts are one-time interpretation revision writers with assertions that prevent overwriting numbered snapshots; do not blindly rerun them. No repository application code or external author code was executed as part of scientific analysis.

The highest-value next input is a sample-linked Egr2-AS nascent/mature RNA and protein timecourse, plus the processed ATAC promoter matrix. See investigations.json for source-specific blockers and unfinished branches. The supplied question remains q_277f20df4b6b47cc.
