# Replaying the quantitative results

This archive contains the new question under workspace/questions/q_5eaa65194750454d and exact immutable source blobs under workspace/blobs/sha256. It does not copy the parent's whole workspace.

Use a Python environment with numpy, pandas, scipy, openpyxl, matplotlib and defusedxml. Versions actually used are recorded in outputs/analysis-environment.json. Run the three locally authored measurement producers from the extracted question's scripts directory:

    python analyze_upstream.py
    python analyze_followup.py
    python analyze_tead.py

They operate on local bytes only and write their question-local outputs. They do not require bio, models, credentials, network or raw sequencing. Primary outputs are executed-contrasts.json, followup-contrasts.json, tead-protein-contrasts.json and their per-sample/all-gene TSV files.

Do not execute other acquired materials. Prism files are XML; the authored protein parser reads only numeric Table elements and ignores the binary Template. XLSX formulas/macros are not executed. The RNF40 assembly/preparation metadata conflict and Nedd4 blank-row exclusion are documented in REPORT.md and the source-contrast eligibility table.

Compilation/registration scripts are catalog-stage tools, not needed for standalone numerical replay. Original producer receipts contain original absolute paths; the standalone verification compares tabular bytes exactly and JSON science after removing only input-location paths. Reports/manifests are a packaging-time snapshot; later publication/readback records are outside the archive.
