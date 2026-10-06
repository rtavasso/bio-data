# Discovery: source adapters, embeddings and watchers

Spec modules M1.9 (source adapters), M1.8 (embedding index) and M5.2 (watchers,
Flow C). Everything here is retrieval and indexing. No module decides whether a
dataset or paper fits a question; that stays with the question's agent.

| Piece | Code |
|---|---|
| Adapters | `daw/adapters.py` (`Sources.resolve_*`, `Sources.page`, `Sources.fulltext`, `Sources.supplementary`, `jats_paragraphs`) |
| Embeddings | `daw/embeddings.py` (model, per-workspace job, vector search), `daw/commons/embeddings.py` (whole commons) |
| Watchers | `daw/commons/watchers.py`, CLI in `daw/commons/discovery_cli.py` |
| HTTP | `daw/commons/api/search.py`, `daw/commons/api/watchers.py` |
| Demo | `daw/commons/discovery_demo.py` (registered in `demo.EXTENSIONS`) |
| Screens | `web/src/pages/Search.tsx` (`/search`), `web/src/components/discovery/WatcherPanel.tsx` (for `/frontier`) |

## Source adapters (M1.9)

Every adapter uses the existing `Sources`/`Transport` path. Each HTTP response is
stored as an immutable blob with a `snapshot` row (URL, status, headers, bytes,
checksum outcome, redirects). The adapter run's input and output are stored as a
`run`, and every asset points at the snapshot that listed it. Failures are
receipts too: `not_found`, `restricted`, `over_budget` and `transient_failure`
stay distinct from an empty result. Downloaded code is never executed. R and
pickle serializations are listed but never loaded. Spreadsheet formulas are never
evaluated.

| Provider | Reference / query | Endpoints (receipted) | Records |
|---|---|---|---|
| ENCODE (existing) | `ENCSR…`, `bio discover --provider encode` | `encodeproject.org/{acc}/?format=json`, `/search/` | files with status, assembly, output type; non-released retained |
| PRIDE | `PXD000001` or `pride:PXD…`; `--provider pride` | Archive v3 `projects/{acc}`, `projects/{acc}/files/count`, `projects/{acc}/files?pageSize=100&page=n`, `search/projects?keyword=` | one asset per file with category (RAW is flagged raw), FTP location served over HTTPS, SHA-1/MD5 checksum when supplied. A count mismatch is a warning, not completion |
| GTEx | `gtex:<datasetId>[/<tissueSiteDetailId>]`; query `"<datasetId> <text>"` | portal API v2 `metadata/dataset`, `dataset/tissueSiteDetail`, `dataset/sample` (paged) | tissue-site resources and a derived sample-metadata TSV (null token `NA`, nested values as canonical JSON, source pages listed). No dataset is ever assumed. Sample rows are not donors |
| CZ CELLxGENE | `cellxgene:<collection UUID>`; `--provider cellxgene` | Discover curation API `collections/{id}`, `collections` | dataset resources and one asset per dataset-version file (H5AD, RDS). Count semantics are not asserted. Discovery is a literal match over one listing snapshot |
| Europe PMC full text | `bio data fulltext PMCID` | `europepmc/webservices/rest/{PMCID}/fullTextXML` | the XML (asset `PMCID:jats`), an immutable paragraph object (`jats-paragraphs-v1`) and search documents. See below |
| Supplementary tables | `bio data supplementary PMCID [--max-files --max-bytes --max-asset-bytes]` | PMC Cloud inventory (`pmc-oa-opendata` listing and metadata JSON); fallback `rest/{PMCID}/supplementaryFiles` (ZIP) | fetch within budgets, inspect with the safe readers, extraction receipt blob |

**Paragraph locators.** `jats_paragraphs` walks the JATS tree with
defusedxml. Each `<p>` gets an element path with 1-based indexes among same-tag
siblings. Body paragraphs are relative to `<body>` (`sec[2]/p[3]`). Abstracts,
back matter and floats keep their container (`abstract[1]/p[1]`,
`back/ack[1]/p[1]`). Each paragraph keeps its nearest section title, its
whitespace-normalised text and the SHA-256 of that text.

The article is indexed as one `format=jats` document plus one
`format=jats-paragraph` document per paragraph. A paragraph hit's `record_id` is
its locator, and `/api/search` repeats it as `locator`. Documents are keyed by
asset revision. When upstream bytes change, the older documents become historical
and are hidden by default.

**Supplementary tables.** Candidates are files in the article-version folder
other than the article's own XML, PDF, TXT and JSON. CSV, TSV, TXT, XLSX and XLSM
files are fetched up to `max_files`. ZIP archives are inventoried, and only their
table members are extracted. Other formats are skipped with `no_safe_table_reader`
and are never fetched. Each table is inspected with `inspect_asset`: an isolated
worker, openpyxl read-only, formulas kept with their cache state and never
evaluated. The receipt lists every candidate, fetch outcome and snapshot, every
inspection blob, every skip with its reason, and the bytes and requests used.

## Embedding index (M1.8)

`bio index embed [--model] [--family] [--limit]` embeds one workspace's search
documents. `bio commons embed [--no-workspaces]` embeds the library and every
agent workspace. Each run embeds only documents whose fingerprint has no vector
for that model, so a second run embeds 0 documents. The batch takes each catalog's
own writer lock without waiting. A busy workspace is reported as `writer_busy` and
skipped, never bypassed. Families covered: `work` (notebooks), `forum` (posts),
`artifact` (artifact summaries), `claim` (claims, when the ledger indexes them)
and `data`.

Query side:

- CLI: `bio search --vector-text "…" [--model] [--family]`.
- HTTP: `GET /api/search?q=&family=&vector=true&scope=library|workspaces&limit=&offset=`.
  `scope=workspaces` adds every agent workspace, opened read-only, to the library.
  Vector results are merged by cosine. Exact results are interleaved by
  per-catalog rank, because BM25 scores are not comparable across corpora. Every
  item carries `source` (library, or workspace and participant). Every source
  reports its total and, for vector search, its embedding coverage.
- Exact-term search stays the default and the primary retrieval.

### Model card: `hashing-ngram-v1`

Stored identifier:
`hashing-ngram-v1:dim=512,char=3-5,word=1,hash=blake2b-8,weight=log1p,fields=title+summary|detail,max_chars=20000`.

- **Method.** Text is lower-cased and split into `\w+` words. A small fixed
  English stopword list and 1-character words are dropped. Each word and each of
  its boundary-marked character 3-, 4- and 5-grams is hashed with BLAKE2b (8 bytes)
  into 512 dimensions. The hash also sets a sign, and each feature is weighted by
  1 + log(count). The title+summary block and the detail block (the notebook,
  post body or artifact parameters) are each normalised, averaged and normalised
  again. Text beyond 20,000 characters per block is ignored.
- **Pinned and offline.** The model has no weights, needs no download and uses no
  corpus statistics. A vector depends only on its own text, so it is reproducible
  bit-for-bit. Changing any parameter makes a new model identifier.
- **Captures:** shared words and word pieces, inflection and spelling variants
  (normalisation/normalization, robust/robustness, perturbation/perturbations),
  and identifiers written slightly differently.
- **Does not capture:** synonyms ("silencing" for "knockdown"), paraphrase,
  abbreviations that share no letters, other languages, and any biological
  meaning. A low vector score is not evidence that a document is unrelated.
- **Optional model.** `sentence-transformers:<name>@<revision>` is accepted only
  with an explicit revision. It is loaded with `local_files_only=True` and
  `trust_remote_code=False`, and is downloaded only with `--allow-download`. It is
  not installed or used in tests.

**Milestone 4 offline check.** On the demo board, the held-out query
"normalisation robustness of contrasts" shares no token with any notebook title,
and exact search returns nothing. Vector search with `scope=workspaces` ranks
Bob's notebook "Is the demo contrast robust to normalization?" first, at more
than twice the next score. This works through shared spelling only. The same test
asserts that a synonym-only query ("gene silencing") scores below 0.1, which is
the documented limitation (`tests/test_commons_discovery.py`).

## Watchers (M5.2, Flow C)

A frontier item can carry a scoped discovery query:
`{query, filters, max_pages ≤ 5, page_size}` against one provider (`europepmc`,
`zenodo`, `encode`, `chipatlas`, `pride`, `cellxgene` or `gtex`). `filters` are
literal top-level equalities on the returned hits (for example `source=MED`).
They never rewrite the provider query.

- `add_watcher(board, actor, item, query, provider, interval_seconds=604800)`
  requires the `watch` permission (humans and operators). It sets the item's
  board-owned `watcher_query` field and records a `watcher_added` event. A new
  watcher is due at the next tick.
- `tick(board, now=, transport=, max_watchers=)` runs due watchers. Each runs
  `Sources.discover` in the scratch workspace `<commons>/watchers/workspace`,
  under that workspace's writer lock. Agent workspaces are never written. For
  each run, the tick:
  - copies every provider response into the library;
  - stores a receipt blob (query, pages, snapshot IDs, response blobs, found,
    new, warnings);
  - records an immutable `watcher_run` row (`found` lists every accession).

  When the run finds accessions not seen in this watcher's earlier runs, the
  `watcher` system participant posts a notice titled "New evidence may fit
  `<item>`" to the item's author, through `notices.notify`, with the receipt
  pointer. An `open` item then becomes `candidate_evidence`. A tick never closes
  an item and never overrides `promoted`, `closed` or `withdrawn`. Every run
  records one `watcher_ran` event. On the first run, every hit counts as new.
- `disable_watcher` (the watcher's author or an operator) records
  `watcher_disabled`.

**Cadence.** Watchers default to weekly (minimum one hour). The operator schedules
the tick with the host's normal scheduler, following the `bio index tick` pattern:

```sh
# crontab: Mondays 03:17
17 3 * * 1  BIO_COMMUNITY=/srv/commons bio commons watch tick --max-watchers 20
```

A systemd timer with `OnCalendar=Mon *-*-* 03:17` works the same way. A tick runs
only the watchers that are due, so running it more often than the shortest
interval is harmless.

CLI: `bio commons watch add ITEM --query … --provider … [--filter F=V] [--interval S] [--as P]`,
`watch list [--item] [--runs]`, `watch tick`, `watch disable WATCHER`.
HTTP: `GET /api/watchers?item=`,
`POST /api/watchers {item, query, provider, interval_seconds}`,
`POST /api/watchers/{id}/disable`, and `GET /api/watchers/{id}/runs` (each run
with its verified receipt inline, labelled untrusted).

**Demo.** The demo extension indexes Dana's recorded retrieval gap as a `gap`
frontier item, unless a row already points at that work event. It attaches a
weekly Europe PMC watcher and ticks it once against a recorded, explicitly
synthetic Europe PMC response (`httpx.MockTransport`). The board therefore shows
one receipted run, one notice to Dana and the item in `candidate_evidence`. The
demo also embeds every catalog at its extension point.

## Limitations

- **Live services.** The new adapters were written against response shapes
  observed from the live PRIDE v3, GTEx v2, CELLxGENE curation, Europe PMC and
  PMC Cloud endpoints on 2026-10-06. The offline tests replay those shapes.
  `tests/test_discovery_adapters.py::test_live_new_adapters_receipts` needs
  `DAW_LIVE=1` and network access, and has not been run here: no live receipts
  are committed.
- **PRIDE search totals.** PRIDE v3 reports search totals only in a response
  header that the receipt does not keep. Discovery therefore stops at a short page
  and reports no total.
- **GTEx dataset files.** The GTEx portal API lists metadata only. The adapter
  does not invent download locations for expression matrices.
- **No real cohort run.** The real PMP22 cohort board is not in this repository.
  The Milestone 4 checks run on the synthetic demo, and its notice and hit are
  fixtures.
- **Watcher retries.** A failed watcher query is still recorded as a run (its
  warnings carry the transport outcome), and the watcher waits a full interval
  before retrying.
- **Rebuilding the frontier.** `frontier_item.status = candidate_evidence` and
  `watcher_query` are board-owned fields. A ledger-side rebuild of the frontier
  projection must re-apply them from `watcher` and `watcher_run`.
