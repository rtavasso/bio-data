---
name: bio-data-discovery
description: "Find and inspect scientific datasets or files that can test a biological uncertainty using bio local search and public repository discovery. Use when source selection, hidden file contents, or missing retrieval context is the main task."
---

# Bio Data Discovery

Look for an exact file plus a plausible analysis, not just a paper mentioning the gene. Search source context and literal content separately with `bio data search --text "..."` and `bio data search --feature IDENTIFIER`. Use `bio data show ID` to inspect source context, structural coverage, limitations and immutable paths. Multiple profiles and alternate encodings can describe one experiment; do not count them as independent evidence.

Feature search is case-sensitive and performs no gene/ortholog inference. Text queries use literal AND matching. Format filters use stored labels such as `bw` or `h5ad`; if a narrow filter returns nothing, inspect an unfiltered result's `format` before concluding the data is absent. Levels 0–2 support retrieval; a missing semantic profile is not a processing failure.

When permitted, follow leads with web search, specialist indexes and repository APIs. `bio discover "QUERY" --provider europepmc` preserves discovery receipts; `bio resolve ACCESSION` inventories files without downloading them. Inspect `bio data list --scope BUNDLE_ID`, choose an exact processed asset, then `bio fetch ASSET_ID --question QUESTION_ID` and `bio inspect ACQUIRED_ASSET_ID`. Use `bio data extract --help` to select archive members explicitly; do not process raw sequencing automatically. For sources outside the adapters, preserve selected bytes and source provenance rather than executing author code.

Check whether a matching cell is a measurement, selected-list membership, annotation, or other text. H5AD feature presence does not establish cell type or matrix semantics. Track coordinates need a sourced assembly/reference; gene expression is not promoter output. Distinguish metadata inventory, acquisition, structural inspection, interpretation and numerical extraction.

For an actual access failure, record the needed information, failed route and plausible value with `bio work gap`. Include an actionable candidate solution, not an automatic demand for a new reader. Keep a returned partial/blocked receipt; absence from a selected table or incomplete index remains unresolved.

Use `bio` from the supplied environment, or `uv run bio` in a development checkout. Read the relevant content-search/source section of `docs/V2.md` when needed. Do not preload historical specs.
