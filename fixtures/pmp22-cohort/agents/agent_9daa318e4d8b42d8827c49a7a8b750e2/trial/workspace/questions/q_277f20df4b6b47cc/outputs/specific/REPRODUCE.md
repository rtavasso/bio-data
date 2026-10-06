# Reproduce the specificity continuation

Run from this isolated checkout with `./bin/python`; no installation or raw processing is needed. All scripts are in `workspace/questions/q_277f20df4b6b47cc/scripts/`. Input identities and exact code hashes are in `registrations.json`. Source bytes are either immutable workspace blobs or preserved question-local files with object receipts.

The executed scientific order was:

1. `discover_specific.py`: GSE177037 broad screen and fixed seven-marker model. Uses inherited source-preserving Parquet **only for gene descriptions**.
2. Prediction locks were generated with the skill sealing helper before measurement acquisition. Do **not** rerun the sealer onto existing locks. r001 targets Eed and is untestable; r002 is the actual primary Zeb2 test. `seal_specific.py` produced the initial structured draft; required text fields were converted to JSON text before successful sealing. The exact successful sealed bytes, not regenerated drafts, are authoritative.
3. `validate_specific.py`: primary Zeb2 array calculation and preliminary HDAC3 arithmetic. The latter is superseded by step 5 because source statuses were initially not gated. Initial taxon assertion failed because the NCBI file includes other mouse taxa; the successful script explicitly filters taxon 10090.
4. `check_specific_alternatives.py`: fixed-panel and alternate-panel diagnostics. Preserve source numeric tokens, but do not interpret its full-panel HDAC3 arithmetic biologically.
5. **`audit_specific_status.py`**: authoritative correction and status gating; generates `validation-summary-r003.json`, `hdac3-eligible-FPKM.tsv` and `correction-r003.json`. These supersede preliminary HDAC3 results. Keep source `HIDATA` and raw numeric tokens separate from eligible abundance.
6. `diagnose_specific_models.py`: nonlinear baseline and explicitly retrospective inherited contrasts.
7. `diagnose_zeb2_rnaseq.py`, then `audit_zeb2_representations.py`: post hoc source/assay diagnostic, including conflicting source representations; no reconstructed replicates.
8. `audit_specific_robustness.py`, `audit_specific_literature.py`, `plot_specific.py`: sample leverage, uncertainty, primary-text locators, scoped novelty records and figure.
9. `finalize_specific.py`: final question-local maps/ledger and numerical synthesis. This records an agent-authored interpretation, not platform biological truth. Historical snapshots must not be overwritten during a future continuation; increment revisions instead.

Analysis scripts that write outputs should be copied/adapted to new revision names for future changes. Original registration manifests preserve the executed code and output bytes. Registered old products remain immutable even when a later correction supersedes their interpretation.

The wrappers' verified TLS configuration was used throughout. `acquire_specific.py` enforces per-file/cumulative caps and now serializes transport-ledger writes with a lock. An early possible concurrency collision is conservatively over-accounted in the ledger. External CLI/browser operations carry explicit conservative request/byte reserves. No author scripts, macros, formulas, pickle or R objects were executed.
