# Worked workflows

```sh
uv sync --locked
uv run daw init workspace
uv run daw demo
uv run daw audit coverage
uv run daw doctor
```

The demo is **synthetic**, with a hidden auxiliary sheet, leading empty rows, literal `NA`, an uncached formula, and a selected-only universe. It produces a feature lookup, an omission refusal, and an offline HTML report.

Separate enumeration from acquisition:

```sh
uv run daw bundle add --reference PMC11592338
uv run daw bundle inventory BUNDLE_ID
uv run daw run --plan acquisition.json
uv run daw bundle inspect BUNDLE_ID
uv run daw curate packet BUNDLE_ID --output workspace/proposals/review
```

An acquisition plan is `{"action":"acquire","assets":["ASSET_REVISION"]}`. To extract selected archive members use `{"action":"extract","assets":["CONTAINER_REVISION"],"members":["table.xlsx"]}`. Nested selectors and parent hashes are retained.

Register original evidence with `daw bundle import metadata.json --name study-name`. An assertion cites original bytes:

```json
{"subject":"ASSET_RESOURCE_ID","field":"namespace","raw_value":"Gene symbol","value":"literal_source_gene_symbol","evidence":{"blob":"SOURCE_SHA256","locator":"/feature_header","method":"literal header mapping"}}
```

`daw curate assert --assertion assertion.json` returns an assertion ID. A table curation can then be:

```json
{
  "asset_revision":"ASSET_REVISION_ID",
  "kind":"table",
  "selector":{"sheet":"Table 2","start_row":4,"end_row":80},
  "settings":{"feature_column":1,"columns":{"reported_effect":3},"namespace":"literal_source_gene_symbol"},
  "assertions":{"namespace":"ASSERTION_ID"}
}
```

Row/column positions are **one-based original source coordinates**. A TSV can omit `sheet` and `end_row`. Multiple regions may have independent interpretations. Missing formula caches remain unresolved.

```sh
uv run daw curate validate --proposal curation.json
uv run daw curate accept --proposal curation.json
uv run daw query --request examples/literal-query.json --plan-only
uv run daw query --request examples/literal-query.json
```

Add bundle IDs or immutable asset revision IDs to `scope` to restrict a query. Replacement curations must name the current digest in `supersedes`. Conflicting semantic changes require an explicit named operator review via `daw curate review --decision decision.json`.

Genomic readers use the `genomics` extra; matrices/contacts use `matrix`. GEO's tool remains isolated:

```sh
uv sync --extra geo
uv sync --project tools/geofetch --locked
uv run daw bundle add --reference GSE139321
```

Register native references with `daw reference add --manifest reference.json` and independent regulatory domains with `daw reference domain --manifest domain.json`. The application never invents promoter definitions or silently lifts coordinates.
