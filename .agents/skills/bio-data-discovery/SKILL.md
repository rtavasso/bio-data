---
name: bio-data-discovery
description: "Find and inspect scientific datasets or files that can test a biological uncertainty using bio local search and public repository discovery. Use when source selection, hidden file contents, or missing retrieval context is the main task."
---

# Bio Data Discovery

Look for an exact file plus a plausible analysis, not just a paper mentioning the gene. Search source context and literal content separately with `bio data search --text "..."` and `bio data search --feature IDENTIFIER`. Use `bio data show SUBJECT` with the result's `subject`, not its index-document `id`, to inspect context, structural coverage, limitations and immutable paths. Multiple profiles and encodings can describe one experiment; do not count them as independent evidence.

For broad mechanism questions, use the evolving network from `bio-mechanism-exploration` to diversify collection across upstream regulators, perturbations, assays and biological states. A useful dataset need not mention the target gene. Connect important branches to discriminating analyses; distinguish located, inspected and analyzed files. Revisit existing data when new mechanisms suggest another use. After a collection pass, identify explanations current data cannot distinguish and investigate a consequential neglected branch; keep inaccessible branches visible.

For these investigations, read [finding useful data beyond target-name searches](references/indirect-discovery.md), including the hypothetical examples of useful incidental measurements and justified rejections. Search design and mechanism terms without requiring the central gene, inspect promising files beyond their descriptions, and record how the measurements could change the answer. Separate a new retrieval route, a new use of existing data, and a new biological claim.

Feature search is case-sensitive and performs no gene/ortholog inference. Text queries use literal AND matching. Format filters use stored labels such as `bw` or `h5ad`; if a narrow filter returns nothing, inspect an unfiltered result's `format` before concluding the data is absent. Levels 0–2 support retrieval; a missing semantic profile is not a processing failure.

When permitted, follow leads with web search, specialist indexes and repository APIs. `bio discover "QUERY" --provider europepmc` preserves discovery receipts; `bio resolve ACCESSION` inventories files without downloading them. Inspect `bio data list --scope BUNDLE_ID`, choose an exact processed asset, then `bio fetch ASSET_ID --question QUESTION_ID` and `bio inspect ACQUIRED_ASSET_ID`. Use `bio data extract --help` to select archive members explicitly; do not process raw sequencing automatically. For sources outside the adapters, preserve selected bytes and source provenance rather than executing author code.

For a priority investigation, inspect linked supplements, sample-level files and related assays even when the title omits the target gene. Retrieve suitable measurement files and their design metadata, then pass them to a concrete analysis; metadata discovery alone leaves that work open. Prefer adequate processed measurements before raw reprocessing. Preserve primary text supporting consequential interpretations, not only browser/search references.

Track requests and acquired bytes across commands against the task budget. After a shared TLS or access failure, diagnose the supplied interpreter/trust configuration and use a materially different permitted route when available; repeating the same failing route for every paper wastes the budget. Keep certificate validation enabled and preserve failures. Stop at real access boundaries, then continue independent feasible work.

Use per-attempt receipts or serialize shared-ledger updates during concurrent retrieval; unsynchronized JSON rewrites can lose requests and completion metadata. Keep partial transfers and error pages explicitly labeled. A file's existence or HTTP 200 does not establish a complete, usable scientific source; verify content and its hash before reuse. Label browser-byte estimates as estimates.

Keep proposed queries separate from completed retrievals. Completed entries must point to actual tool results or receipts emitted by the executed HTTP request, with the request, response/failure and saved payload identity. Derive request totals from those receipts. A remembered query, planned browser confirmation or hand-authored source summary is not evidence that a request occurred; retract unsupported entries while preserving history.

Check whether a matching cell is a measurement, selected-list membership, annotation, or other text. H5AD feature presence does not establish cell type or matrix semantics. Track coordinates need a sourced assembly/reference; gene expression is not promoter output. Distinguish metadata inventory, acquisition, structural inspection, interpretation and numerical extraction.

Inspect source quality/status fields and their documented meanings before normalization or model construction. A numeric token can accompany failed or unreliable quantification; retain the raw value and status separately and establish eligibility before using it as abundance. A valid measured zero differs from a zero with a failure flag. If a required feature is ineligible, leave the original test untestable; a reduced feature panel is a revised exploratory analysis with its own provenance.

For an actual access failure, record the needed information, failed route and plausible value with `bio work gap`. Include an actionable candidate solution, not an automatic demand for a new reader. Keep a returned partial/blocked receipt; absence from a selected table or incomplete index remains unresolved.

Use `bio` from the supplied environment, or `uv run bio` in a development checkout. Read the relevant content-search/source section of `docs/V2.md` when needed. Do not preload historical specs.
