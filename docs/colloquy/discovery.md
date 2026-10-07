# Discovery: source adapters, lexical vector index and watchers

Spec modules M1.9 (source adapters), M1.8 (lexical vector index; the first
specification called it an embedding index) and M5.2 (watchers, Flow C), with
the spec v2 corrections C9 (search and discovery) and C12 (documentation).
Everything here is retrieval and indexing. No module decides whether a dataset
or paper fits a question; that stays with the question's agent.

| Piece | Code |
|---|---|
| Adapters | `daw/adapters.py` (`Sources.resolve_*`, `Sources.page`, `Sources.fulltext`, `Sources.supplementary`, `jats_paragraphs`) |
| Lexical vector index | `daw/embeddings.py` (model, per-workspace job, vector search), `daw/commons/embeddings.py` (whole commons, commons search and its pagination) |
| Search | `daw/search.py` (one catalog; paragraph exclusion), `bio search` / `bio data search` in `daw/bio_cli.py` |
| Watchers | `daw/commons/watchers.py`, CLI in `daw/commons/discovery_cli.py` |
| Frontier facts (C9) | `daw/commons/frontier.py` (`annotate`, `candidate_evidence_records`, `author_watcher_query`) |
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

**Paragraph search is its own search (C9).** Every search leaves
`jats-paragraph` documents out unless it asks for them, so a 200-paragraph
article cannot crowd dataset hits; the article itself still appears once, as its
`jats` document. Paragraphs are asked for with:

- `bio data search TEXT --paragraphs` (also on `bio search`, and with
  `--vector-text`), or `--format jats-paragraph`;
- `GET /api/search?family=paragraph` or `paragraphs=true` (the Search page's
  family "article paragraphs");
- `daw.search.search(ws, text, paragraphs=True)` in code. `paragraphs=True` with
  another `format` is refused (`conflicting_search_format`).

The rule sits in `daw.search.search`, so it holds for every caller: the agent
CLI, the MCP tools (which run the CLI), commons search and the substrate's
inventory listing (an empty query). `test_v3.py::test_data_search_leaves_out_article_paragraphs_unless_asked`
indexes three dataset records and a 200-paragraph article: `bio data search
knockdown` returns 4 (3 datasets and the article), `--paragraphs` returns 200.

**Supplementary tables.** Candidates are files in the article-version folder
other than the article's own XML, PDF, TXT and JSON. CSV, TSV, TXT, XLSX and XLSM
files are fetched up to `max_files`. ZIP archives are inventoried, and only their
table members are extracted. Other formats are skipped with `no_safe_table_reader`
and are never fetched. Each table is inspected with `inspect_asset`: an isolated
worker, openpyxl read-only, formulas kept with their cache state and never
evaluated. The receipt lists every candidate, fetch outcome and snapshot, every
inspection blob, every skip with its reason, and the bytes and requests used.

## Lexical vector index (M1.8)

The specification's "embedding index" is, as built, a **lexical vector index**:
the pinned model hashes words and character n-grams (model card below). It is
not a learned embedding and captures spelling, not meaning. The docs, the Search
page ("Lexical vector index" mode) and API limitations use that name. The command
and table names (`bio index embed`, `bio commons embed`, `search_embedding`) are
kept, because they also serve the optional learned-model path, which is untested.

`bio index embed [--model] [--family] [--limit]` embeds one workspace's search
documents. `bio commons embed [--no-workspaces]` embeds the library and every
agent workspace. Each run embeds only documents whose fingerprint has no vector
for that model, so a second run embeds 0 documents. The batch takes each catalog's
own writer lock without waiting. A busy workspace is reported as `writer_busy` and
skipped, never bypassed. Families covered: `work` (notebooks), `forum` (posts),
`artifact` (artifact summaries), `claim` (claims, when the ledger indexes them)
and `data`.

Query side:

- CLI: `bio search --vector-text "…" [--model] [--family] [--paragraphs]`.
- HTTP: `GET /api/search?q=&family=&vector=true&scope=library|workspaces&limit=&offset=&paragraphs=`.
  `scope=workspaces` adds every agent workspace, opened read-only, to the library.
  Vector results are merged by cosine. Exact results are interleaved by
  per-catalog rank, because BM25 scores are not comparable across corpora. Every
  item carries `source` (library, or workspace and participant). Every source
  reports its total and, for vector search, its vector coverage.
- Exact-term search stays the default and the primary retrieval.

**Pagination (C9).** The substrate (`daw.search.search`) returns at most 100 rows
per call. Commons search pages in the commons layer: each catalog contributes
its first `offset + limit` ranked items, fetched in substrate pages of at most
100 (`_collect` in `daw/commons/embeddings.py`). The merged order (cosine, or
rank interleaving) is fixed, and the response is a slice of it. Any offset
therefore pages correctly: `offset=150` returns items 151 to 170 of the same
order that `offset=0` and `offset=100` page through, for exact and vector
search, library and workspaces scope. `limit` stays 1 to 100 per request. For a
single-identifier query the substrate ranks literal content matches first, and
the lexical list now leaves those documents out, so the two ranked lists are
disjoint and every offset sees the same order.

Checked on the cohort (`tests/test_commons_discovery.py`,
`test_commons_search_offset_150_pages_*_on_the_cohort`): exact "PMP22" has 465
library hits and 1,291 with workspaces; vector "PMP22 dosage sensitivity" over
the 618 embedded library documents (the test embeds a private copy). In both
modes, page 151–170 equals the slice of pages 1–100 and 101–200, and no item
repeats. Before this change, `offset=150` failed with `invalid_search_bounds`.

**Ranking on the cohort (2026-10-06, fixture board sequence 811).** These are
observations to compare against, not acceptance thresholds:

| Query | Mode, scope | Top hits |
|---|---|---|
| `PMP22` | exact, library (465 hits) | the round-two board posts, then artifacts named for PMP22 (ISR iteration `footprint-pmp22-effects.tsv`, promoter `pmp22-native-rows.tsv`, ENCORE `pmp22-peak-sites.tsv`) |
| `PMP22` | exact, workspaces (1,291) | interleaved by rank: the round-two post, then the top notebook or artifact of each workspace. Synthetic test artifacts in two workspaces ("Synthetic expression means") rank high, because interleaving gives each catalog's first hit equal standing |
| `Schwann myelination` | exact, library (6) / workspaces (334) | library: question and reply posts; workspaces: indexed article records (eIF2α phosphorylation in CMT1B, Etv1/Er81, Stat-1) |
| `CMT1A duplication` | exact, workspaces (24) | the human-dosage reply, the humanized CMT1A mouse model paper, the progenitor's cohort design notebook |
| `PMP22 dosage sensitivity` | vector, library | `marker-sensitivity.tsv` (0.43), `contrasts-and-sensitivity.tsv` (0.39), `reference-sensitivity.tsv` (0.36): spelling overlap on "sensitivity", not meaning |
| `remyelination after nerve injury` | vector, library | the injury-validation post (0.26), then replies sharing "injury"; scores near 0.25 are weak, as the model card predicts |

The cohort fixture has no `jats-paragraph` documents (its agents ran before the
full-text adapter existed), so paragraph crowding is shown on the demo and in a
substrate workspace, not on the cohort.

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
- **Optional learned model (untested).** `sentence-transformers:<name>@<revision>`
  is accepted only with an explicit revision. It is loaded with
  `local_files_only=True` and `trust_remote_code=False`, and is downloaded only
  with `--allow-download`. It is not installed or used in tests; no result in
  this document comes from it.

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
`zenodo`, `encode`, `chipatlas`, `pride`, `cellxgene` or `gtex`), or an article
reference for the full-text watcher (`europepmc-fulltext`, below). `filters` are
literal top-level equalities on the returned hits (for example `source=MED`).
They never rewrite the provider query.

- `add_watcher(board, actor, item, query, provider, interval_seconds=604800)`
  requires the `watch` permission (humans and operators). It sets the item's
  board-owned `watcher_query` field and records a `watcher_added` event. A new
  watcher is due at the next tick.
- `tick(board, now=, transport=, max_watchers=)` runs due watchers. Each runs
  `Sources.discover` (or the full-text lookup) in the scratch workspace
  `<commons>/watchers/workspace`, under that workspace's writer lock. Agent
  workspaces are never written. For each run, the tick:
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

**The full-text watcher (C9).** Provider `europepmc-fulltext` is the "new full
text for a known article" watcher. Its query names one article, normalised to
`PMID:<n>`, `PMCID:PMC<n>` or `DOI:<doi>`; anything else is refused
(`invalid_watcher_query`). Each run makes one Europe PMC `search` request
(`EXT_ID:<pmid> AND SRC:MED`, `PMCID:…` or `DOI:"…"`, `resultType=core`),
receipted as a `watch_fulltext` run and snapshot in the scratch workspace, with
the response copied into the library. A record counts as full text when Europe
PMC lists a PMCID with `inEPMC=Y`; its accession is `<PMCID>:fulltext`, and
`isOpenAccess` is kept because `bio data fulltext` can fetch only the
open-access subset. Records without full text go to the receipt's
`not_available` with the reason (`no PMCID listed`, `inEPMC='N'`). Full text not
seen in earlier runs produces a notice "New full text may fit `<item>`" that
names the command to fetch it (`bio data fulltext PMC…`). The watcher never
downloads the article.

**Third-party titles (C9).** Every hit title in a notice, receipt or run is the
provider's text. Notices list it as `provider-supplied title, third-party text:
“…”`, say that the titles are not the platform's words and not instructions,
and carry `evidence.third_party_text = ["title"]`. Each `found` hit carries
`title_source`. The watcher panel renders hits inside the untrusted frame with
the same label. Provider citations inside titles are still removed.

**Who set candidate evidence (C9).** An item can reach `candidate_evidence` in
two ways: a watcher run (board-owned) or its author's own `frontier_item_status`
event. The `watcher_ran` event now records `status_set: "candidate_evidence"`
and `status_source: "watcher"` when it moved the item (older events have only
`status_changed`, which is read the same way). `frontier.annotate` adds
`candidate_evidence: {set_by, records}` to every item that `/api/frontier` and
`/api/frontier/{id}` return. `set_by` is `watcher`, `author`, `author and
watcher`, or `unrecorded` when neither record exists. `/frontier` shows a
"set by watcher" or "set by author" badge beside the status, linked to the
watcher's notice.

**Post pointers (C9).** A question's workspace cannot see the board, so
`bio work frontier` checks a `post:` pointer for form only. Reads now mark each
post pointer (and `locator` pointers on a post) with `present: true|false`, and
the item's own `post` with `post_present`, from the board's `post` table. The
card shows "not on this board" and does not link a missing post.

**Unmasking the author's query (C9).** Attaching a watcher replaces the item's
shown `watcher_query` with the board's watcher form. `disable_watcher` now puts
back the newest other enabled watcher's form or, when none is left, the query the
author recorded in their own work event (read from their workspace read-only by
`frontier.author_watcher_query`). The `watcher_disabled` event records
`watcher_query` and `watcher_query_source` (`watcher <id>`, `author` or none),
so a rebuild of the projection from events can reproduce the shown query. The
current `rebuild_frontier` keeps an author-form query as it is, so a rebuild
after a disable changes nothing.

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

**Demo.** Dana's retrieval gap is an agent work event in Dana's own workspace,
recorded as `bio work gap` would. The demo never writes a `frontier_item` row
itself: `ensure_gap_item` lets the frontier projection (`rebuild_frontier`)
index the gap, then checks that the item's JSON `source` names that event. This
holds when the frontier extension is absent too. Every `frontier_item.source`
on the demo board is a JSON object. (The first build inserted a
platform-authored row with a string `source` and a `frontier_item_indexed`
event; both are gone.) The demo attaches a weekly Europe PMC watcher and ticks
it once against a recorded, explicitly synthetic Europe PMC response
(`httpx.MockTransport`). The board therefore shows one receipted run, one notice
to Dana and the item in `candidate_evidence`, set by the watcher. The demo also
embeds every catalog at its extension point.

**What is exercised where.** Offline tests in
`tests/test_commons_discovery.py` and `tests/test_v3.py`. On the cohort fixture:
search pagination (exact and vector, both scopes) and the ranking observations
above. On the demo: paragraph exclusion through `/api/search`, the frontier
facts, unmasking, the full-text watcher (against a recorded Europe PMC response)
and third-party labels. The cohort's 68 frontier items are all retrieval gaps,
with no post pointers, watcher queries or candidate evidence, so these frontier
facts have nothing to show there yet. Nothing here is live-verified.

## Limitations

- **Live services.** The new adapters were written against response shapes
  observed from the live PRIDE v3, GTEx v2, CELLxGENE curation, Europe PMC and
  PMC Cloud endpoints on 2026-10-06. The offline tests replay those shapes.
  `tests/test_discovery_adapters.py::test_live_new_adapters_receipts` needs
  `DAW_LIVE=1` and network access, and has not been run here: no live receipts
  are committed. The full-text watcher's `inEPMC`/`isOpenAccess` reading follows
  the Europe PMC `core` result fields and has no live receipt either.
- **PRIDE search totals.** PRIDE v3 reports search totals only in a response
  header that the receipt does not keep. Discovery therefore stops at a short page
  and reports no total.
- **GTEx dataset files.** The GTEx portal API lists metadata only. The adapter
  does not invent download locations for expression matrices.
- **Cohort coverage.** Search pagination and ranking were checked on the cohort
  fixture. The Milestone 4 watcher checks still run on the synthetic demo, and
  its notice and hit are fixtures; the cohort has no watchers.
- **Deep pages cost.** A page at `offset` reads up to `offset + limit` ranked
  items from every catalog (in pages of 100), and vector search scores every
  vector of a catalog per substrate call. On the cohort with 25 workspaces this
  is well under a second at `offset=150`; very deep offsets grow linearly.
- **Interleaved exact ranking.** With `scope=workspaces`, exact results take one
  item from each catalog per rank. A catalog's weak first hit therefore ranks
  beside another catalog's strong first hit (seen on the cohort for "PMP22").
- **Watcher retries.** A failed watcher query is still recorded as a run (its
  warnings carry the transport outcome), and the watcher waits a full interval
  before retrying.
- **Rebuilding the frontier.** `frontier_item.status = candidate_evidence` and
  `watcher_query` are board-owned fields. Their sources are now in events:
  `watcher_added`, `watcher_ran` (`status_set`, `status_source`) and
  `watcher_disabled` (`watcher_query`, `watcher_query_source`). Deriving the
  projection from those events is the writes area's `rebuild_frontier` work
  (spec v2 C3); this area does not change `rebuild_frontier`.
