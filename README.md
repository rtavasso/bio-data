# Data Archaeology Workbench

Recover public biological experiments and their measurements—including supplementary tables and auxiliary assays—with exact provenance and a ledger of what remains unexamined. A local Python CLI, one SQLite catalog, immutable files, and offline reports. No server or model required.

```sh
uv sync --locked
uv run daw init workspace
uv run daw demo
```

The demo returns an offline report path. It recovers a hidden workbook sheet, traces values to source cells, preserves an uncached formula as unresolved, and demonstrates why a selected-only table cannot establish a null effect. Its data are explicitly synthetic.

The completed real-data pilot is available at [workspaces/pilot/reports/index.html](workspaces/pilot/reports/index.html) in this checkout. It includes source-linked Schwann-cell tables, human H3K27ac and rat ATAC locus queries, a version-pinned tumor expression table, and independent validation of all 2,700 values in a held-out human matrix query. See [the pilot handoff](docs/PILOT.md) for receipts and limitations. Downloaded workspaces are intentionally excluded from Git.

For the complete tested scientific environment:

```sh
uv sync --locked --all-extras
uv sync --project tools/geofetch --locked
uv run pytest -q
uv run daw doctor
```

Use `daw -w /path/to/workspace …` or `DAW_WORKSPACE` to separate data from code. All command results are JSON. See [worked workflows](examples/README.md), [runtime contracts](contracts/README.md), [scope and limitations](docs/LIMITATIONS.md), and [backup/restore](docs/BACKUP.md).

```sh
uv run daw discover --request examples/discovery.json
uv run daw bundle add --reference GSE139321
uv run daw bundle inventory BUNDLE_ID
uv run daw run --plan acquisition.json
uv run daw bundle inspect BUNDLE_ID
uv run daw curate packet BUNDLE_ID --output workspace/proposals/study
uv run daw curate validate --proposal curation.json
uv run daw curate accept --proposal curation.json
uv run daw query --request examples/literal-query.json
uv run daw audit coverage
uv run daw export-igv --request locus-query.json --destination workspace/reports/native-tracks
```

Numerical operators cover tables, published contrasts, interval overlaps, exact bigWig summaries, annotated expression values, documented pseudobulk counts, and Cooler region extraction. Scientific eligibility is separate from successful parsing. Gene-level expression does not authorize promoter claims; unknown references, donors, layers, and feature presence remain unknown.

Adapters preserve raw responses, identities and pagination. The [pilot handoff](docs/PILOT.md) and `docs/receipts/` distinguish real provider behavior from offline contracts. Workspaces and downloaded datasets are intentionally excluded from Git.

The original [specification](BUILD_SPEC.md) and [execution brief](AGENT_START.md) remain unchanged. The implementation adds their previously absent contracts and adversarial fixtures without treating synthetic examples as biological evidence.
