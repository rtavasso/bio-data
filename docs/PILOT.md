# Completed pilot and implementation handoff

Start with the [offline report index](../workspaces/pilot/reports/index.html). It links every saved query, its complete Parquet package, coverage ledger, and native-reference IGV sessions. The data are already present in this checkout; the ignored workspace is not part of a Git clone.

The application is a working local CLI, not a study-summary generator. Its implemented operators recover literal table values, published contrasts, interval overlaps, exact covered-base bigWig statistics, expression slices, documented descriptive pseudobulk counts, and Cooler region pixels. Each query freezes its candidate set and retains unacquired, unsupported, incompatible, and unresolved candidates.

## What the real data yielded

| Evidence | Recovered result | Interpretation boundary |
|---|---|---|
| GSE139321 and versioned PMC7430845 supplements | 424 Pmp22 source-cell records (326 numeric, 98 blank), 24 numeric Sox10 records; 156 published Pmp22 contrast entries (104 numeric, 52 blank) | Selected rat TSSs and repeated source representations; these are not independent experiments, total-gene effects, or P1/P2 assignments |
| Auxiliary MOESM3 workbook | Four PMP22 list-membership records across independently curated columns | Source-selected isoform lists linking rat experiments to human RefSeq annotations; no cross-species activity equivalence |
| ChIP-Atlas SRX24150189, found by a Schwann repository search without PMP22 | Exact hg38 H3K27ac signal over PMP22 and SOX10 annotated gene spans | Engineered immortalized human Schwann cells, NF1 proficient/SUZ12 deficient; source antibody attributes preserved |
| GSE201627, GSM6068778 | Four source-called ATAC intervals overlap the rn6 Pmp22 gene span; one overlaps Sox10 | Accessibility calls in the native rat reference; no inference of TF binding or causal regulation |
| Zenodo record version 21324866 | 71 literal PMP22 values and 71 SOX10 values, each checked against the deposited row | Tumor bulk mixture; filename says FPKM, but transformations and donor relationships were not established, so normalized/count inference stays unavailable |
| Held-out PBMC3k human H5AD | 2,700 MS4A1 values, including 2,277 measured zeros; full vector and cell order independently verified | Human blood validation dataset, not Schwann evidence. Missing feature is `not_measurable`; donor pseudobulk is blocked |

For example, the source workbook's `TSS- Primary SC cAMP Increased`, cell T51, contains a published Pmp22 SOX10-loss log2 fold change of −9.34466243284964. Its denominator, selection, cell, exact bytes, and curation are retained. This selected TSS result does not become a gene-wide or promoter-specific effect.

The human PMP22 H3K27ac gene-span query covers hg38 `chr17:15229776–15265326` in internal zero-based half-open coordinates. Its mean is 0.05732915592145845 native RPM **over 19,719 covered bases**, out of 35,550 requested bases. Uncovered bases are not silently replaced with zero. The independently checked SOX10 result uses the same imported experiment. These annotated spans are explicitly provisional inspection regions, not established regulatory domains.

All 604 source-cell records across the main table lookups and published-contrast query were checked against original source cells, including preserved blank values. Four genomic queries were independently checked using native exact bigWig statistics or direct interval arithmetic. These checks validate extraction, not the authors' upstream processing or biological causality. See [numerical checks](receipts/numerical-crosschecks.json), [held-out validation](receipts/heldout-validation.json), and [repository-row checks](receipts/repository-table-results.json).

## Empirical source support

| Provider | Actual live outcome |
|---|---|
| Europe PMC | Article/JATS retrieval and bounded search; final-page cursor omission resolved against reported totals and regression-tested |
| PMC Open Data | Version/object enumeration, direct cloud media, JATS, XLSX supplements, and ZIP acquisition; preserves object identity and provider checksums |
| GEO / GEOfetch / PEP | Three seed/subseries inventories, source SOFT, pinned GEOfetch 0.12.11 output, resolved PEP, and sample/relationship frontiers |
| ENA | `read_run` field handshake and 32 raw-file references for PRJNA579292; raw processing disabled |
| ChIP-Atlas | Experiment-list discovery, genome/detail handshake, original antibody/sample metadata, exact documented track URLs, and downloaded hg38 signal/peaks |
| Zenodo | Published version resolution, bounded search, multiple-modality inventory, checksum-verified numeric file; 852,515,826-byte matrix recorded over budget before download |
| Figshare | Public index and explicit version-1 article 34004685 enumeration, 24 file references; file acquisition from that handshake was not needed or tested |
| BioStudies | E-MTAB-10553 and differently structured S-EPMC9722693 inventories, including source location metadata |
| ENCODE | ENCSR000AKO exhausted three bounded attempts with `ReadTimeout`. Offline contract tests pass; live acquisition is **not certified** |

ChIP-Atlas's processing documentation and agent guide disagreed on threshold wording. File-level validation confirmed the acquired per-experiment files are ten-column narrowPeak: the ninth column is −log10(Q). The 05 file has 3,329 peaks and the 20 file has 26; all 26 strict intervals lie within loose intervals, but their boundaries differ, so exact row-set inclusion is false. This resolves these exact file hashes; it is not a blanket interpretation of every ChIP-Atlas BED layout. [Threshold receipt](receipts/chipatlas-threshold-check.json).

Actual endpoint URLs, UTC timestamps, outcomes, source snapshots, byte hashes, and enumeration receipts are in [the snapshot index](receipts/source-snapshot-index.json), [initial handshakes](receipts/provider-probes.json), [schema refinements](receipts/provider-refinements.json), [final handshakes](receipts/final-handshakes.json), [repository acquisitions](receipts/repository-acquisition.json), and [the final Europe PMC check](receipts/europepmc-final-page.json). Earlier failed attempts remain in the history.

## Coverage and unresolved work

[The coverage audit](receipts/coverage-audit.json) lists every current catalog asset. [The pilot summary](receipts/pilot-summary.json) records per-bundle denominators, acquired/query-ready counts, accepted selector count, assertion count, immutable storage, source response outcomes, recipe timings, and exact retry reuse. Discovery pages are bounded; pending frontiers prevent any claim that all public evidence was exhausted.

The audited GEO source inventories contain 1, 13, and 1 deposited-file entries for GSE139321, GSE201627, and GSE201623 respectively. Archive members and alternate source routes add separate candidates with ancestry; they do not add biological replication. GEO and ENA source experiment links share the INSDC experiment namespace. ChIP-Atlas hg19 and hg38 representations likewise retain one experiment identity.

GSE201627's RNA, ATAC, and Hi-C modalities remain inventoried together. Native RNA counts and one ATAC representation are queryable; unacquired `.bed`/`.matrix` contact files and the raw archive remain visible. Cooler numerical behavior is tested with controlled fixtures, but this pilot does not claim a real Hi-C extraction. The PMC11592338 supplement ZIP contains two PDFs, which are inventoried and explicitly unsupported by the current readers.

Promoter/P1/P2 inference, cross-species pooling, automatic liftover, new differential-expression fitting, raw-sequencing workflows, R object loading, PDF/OCR extraction, and long-tail compendia are not activated. Gene spans are not full regulatory domains. See [the complete supported scope](LIMITATIONS.md).

No paid service, credentials, author-code execution, access-challenge bypass, or raw analysis was used. Acquisitions used public provider APIs, PMC's cloud distribution, documented public track locations, and maintained reference/example-data hosts. Public availability does not establish redistribution rights: original dataset license fields, including `unknown`, are preserved. [License inventory](receipts/licenses.json) records installed distribution declarations and asset licenses; bundled-library metadata is not independently certified.

Source-backed recipes and their exact assertions are reviewable. Human review time, global semantic-error rate, and global discovery recall were not measured. Tests check identity separation and reject unsupported semantics; they do not justify a universal zero-error claim.

## Validation and recovery

The final run passed **77 offline tests**, with the two explicitly gated network tests skipped. Both network tests also passed separately. Status is recorded in [offline test results](receipts/offline-tests.xml) and [live test results](receipts/live-tests.xml). Ruff checks cover `src`, `tests`, `scripts`, and `recipes`; wheel and source-distribution builds also succeeded. The duplicate-symbol fixture intentionally triggers AnnData warnings; Cooler and SciPy emit upstream deprecation warnings.

[Backup/restore receipt](receipts/backup-restore.json) records a full SQLite API backup and copied immutable blobs, restored into an independent temporary workspace, with catalog integrity, foreign keys, manifest reconciliation, and every blob hash checked. Repeated query attempts have different attempt IDs and identical cached artifact hashes. Historical results remain recoverable after corrected interpretations.

IGV packages use copied native tracks, the pinned assembly name, converted one-based display locus, and a provenance manifest. XML/coordinates/copy isolation are tested; the IGV GUI was not run. HTML escaping and artifact generation are tested; a browser visual regression test was not run. The [IGV format documentation](https://igv.org/doc/desktop/UserGuide/sessions/) guided session export.

This machine uses Python 3.12.8 and SQLite 3.45.3 in DELETE journal mode. Native scientific extras are installed separately from the base dependency set; GEOfetch has its own locked environment. Parser subprocesses have CPU/wall limits. On macOS, memory protection uses allocation estimates rather than a hard address-space cap; this is a private local tool, not a hostile multi-tenant sandbox.

## Reproduce

From this populated checkout:

```sh
uv sync --locked --all-extras
uv run python scripts/pilot_finalize.py
uv run daw -w workspaces/pilot doctor
uv run daw -w workspaces/pilot audit coverage
uv run pytest -q
DAW_LIVE=1 uv run pytest tests/integration -q
```

`pilot_finalize.py` reruns the four reviewed recipes, independently checks numerical outputs, verifies cache reuse, exports IGV sessions, writes the report index, and makes/tests a new backup. It includes one small live Europe PMC check. Individual recipes can run offline against the saved workspace. They reject changed pinned data where their mapping depends on exact bytes.

To reconstruct acquisition into a new workspace, run `scripts/pilot_probe.py`, `scripts/pilot_refine.py`, `scripts/pilot_acquire.py`, `scripts/pilot_sources.py`, `scripts/pilot_repository.py`, and `scripts/pilot_final_handshakes.py`, then finalize. These are explicit bounded public-network jobs; changed upstream contents can require renewed review. The verified backup is the exact historical reproduction path. General CLI workflows are in [examples](../examples/README.md); [backup instructions](BACKUP.md) cover restoration into a fresh directory.
