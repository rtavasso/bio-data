# Supported scope and explicit limitations

Implemented: table lookup, published contrast lookup, interval overlap, exact bigWig covered-base summaries, annotated matrix values, documented per-feature pseudobulk counts, and Cooler region extraction. Results are measurements with qualified outcomes, not mechanistic conclusions.

- Promoter summaries require an independently reviewed dedicated recipe and remain blocked. Total-gene expression is never a P1/P2 proxy.
- Native-reference queries only. No automatic liftover, cross-species pooling, cross-study normalization, causal inference, or new differential-expression engine.
- bigWig queries use verified full downloads and exact covered-base means. Remote ranges and zero-fill summaries are not enabled. Downloads restart; partial bytes are never appended optimistically.
- AnnData and explicitly paired Matrix Market are supported. Expanded layer/metadata allocation is bounded before loading. Feature presence is required to interpret zeros; missing presence remains unresolved. Pseudobulk returns descriptive sums by documented study/donor/sample, not significance tests.
- Cooler returns region pixels, bins, resolution, explicit normalization, invalid-bin context, and symmetric duplicate removal. It does not call loops.
- IGV export copies accepted native tracks with a pinned reference and provenance manifest. XML, coordinate conversion, and copy isolation are tested; the Desktop GUI was not exercised.
- Workbooks preserve hidden sheets, types, formulas, and caches. Legacy spreadsheets, R objects, PDFs/OCR, proprietary contacts, BigBed extraction, and downloaded code remain unsupported until specialized readers are justified.
- Archives are inventoried and extracted by selected member with path/type/duplication/expansion/depth limits.
- Workers have wall-clock/CPU limits. Linux also applies an address-space limit. On macOS, memory bounds are allocation estimates, **not a hard OS cap**. Subprocesses are a robustness boundary, not a security sandbox.
- Public HTTP(S), bounded redirects, and private-destination checks only. No credentials, restricted data, paid compute, author-code execution, or raw-sequencing processing. This is not a hostile multi-tenant sandbox.
- GEO preserves SOFT, GEOfetch output, and resolved PEP. Relationship expansion is explicit and bounded; unvisited descendants remain a frontier.
- Provider availability is empirical. Live receipts distinguish source failures from passing offline contracts.
- ChIP-Atlas threshold interpretation remains blocked while its agent guide and processing documentation disagree, unless an exact file-level recipe resolves the conflict.
- Census, compendia, GEOmetadb, ffq/BioMCP, R/PDF workflows, nf-core, DuckDB optimization, and a review UI are conditional expansion choices, not advertised implemented capabilities.
- One writer on local disk; rollback journaling, no WAL. Accepted evidence is never treated as disposable cache.

Unsupported, blocked, and unexamined candidates remain visible to scoped queries and later recipes.
