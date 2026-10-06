# Reproducing the mechanical-context analysis

The evidence ZIP uses workspace-relative paths. In a fresh compatible bio-data checkout, unpack into its workspace directory, preserving questions/ and blobs/sha256/. Do not overwrite a live researcher's notebook. The archive is a selective, pre-publication snapshot, not the complete catalog or community.

Required packages used: numpy, pandas, scipy, defusedxml. The original execution used the repository's ./bin/python wrapper. Primary analysis and validation do not need network access, model credentials, raw FASTQ/BAM processing, downloaded code execution, or a running community service.

Run from the checkout root:

    ./bin/python workspace/questions/q_4f573ee10eee421b/scripts/analyze_mechanics.py
    ./bin/python workspace/questions/q_4f573ee10eee421b/scripts/inspect_workbook.py
    ./bin/python workspace/questions/q_4f573ee10eee421b/scripts/validate_results.py
    ./bin/python workspace/questions/q_4f573ee10eee421b/scripts/compile_evidence.py

These are locally authored scientific scripts. Source artifacts are read as data only. analyze_mechanics.py derives data paths from its own question/workspace location and verifies immutable blob hashes. The two selected inherited source files live under q_e835197734394f30 solely because the current producer explicitly consumes their preserved metadata/text; no inherited analysis script is executed.

Existing outputs and producing receipts record the original execution. A rerun overwrites derived outputs; use a fresh copy and a new run_analysis.py receipt if you want a separate execution record. Do not relabel the original receipts as your own execution. Absolute paths inside historical receipts are provenance, not required locations for the scientific analysis.

Registered main outputs include the all-feature contrast universe, individual panel measurements, sample design, genotype-stiffness interactions, strict JSON summary/validation, and typed intervention-to-pathway-to-PMP22 map. REPORT.md distinguishes new calculations from prior-paper results and records failed predictions and remaining source-access limits.
