# BIO research substrate

A local store of public scientific data and prior research for coding agents. Search what files contain, inspect the exact source, write ordinary Python/R/SQL, and reuse earlier processing when its derivation fits the new question. No server, credentials, model, or network is required for local use.

```sh
uv sync --locked
uv run bio init workspace
uv run bio demo
uv run bio data search --feature PMP22
uv run bio artifact search --text reusable
uv run bio work search --text PMP22
```

The offline demo indexes a synthetic table whose title does not mention PMP22, creates a question notebook and a normal script, then reuses the resulting artifact in a second question. Zero, missingness, and source labels stay distinct. Every command returns JSON.

For real scientific files and the complete test suite:

```sh
uv sync --locked --all-extras
uv run ruff check src tests scripts benchmarks
uv run pytest
uv run bio doctor
```

Use `bio -w /path/to/workspace …` or `BIO_WORKSPACE`. Data stays in ignored workspaces; the repository contains code, documentation, and compact validation receipts.

```sh
uv run bio resolve GSE201623
uv run bio data list --scope BUNDLE_ID
uv run bio fetch ASSET_ID
uv run bio inspect ACQUIRED_ASSET_ID
uv run bio data search --feature Pmp22
uv run bio work new "What does this experiment measure about Pmp22?"
```

The returned question folder contains `QUESTION.md`, `LABBOOK.md`, `scripts/`, `outputs/`, and `events.jsonl`. Read data through `bio data show`, run your own scientific code, register useful outputs with `bio register`, and index the notebook with `bio work sync`. No curation acceptance step is required.

The global indexer supports research-graph JSONL imports, repository manifests, bounded processed-file acquisition, structural inspection, literal feature lookup, and attributed semantic profiles. Levels 0–2 determine completion; semantic profiles are optional enrichment. It persists unfinished tasks and can run periodically under your existing scheduler. Full-text search is local SQLite FTS5; externally computed semantic vectors are optional.

Start with `bio --help` and [AGENT_START.md](AGENT_START.md). The [v3 guide](docs/V3.md) covers retrieval-gap reporting and evaluation before expansion. Read the [v3 pilot results](docs/V3_PILOT.md), [indexing guide](docs/V2.md), [question workflows](examples/V2.md), or [backup/restore](docs/BACKUP.md) as needed. [v3_SPEC.md](v3_SPEC.md) is the engineering specification, not required research-session context.

V3 keeps biological reasoning with the coding agent. Use structured external resources and primary papers to audit hypotheses at runtime. Record actual retrieval failures with `bio work gap`; inspect recurring failures with `bio work gaps`. The separate [retrieval](benchmarks/retrieval/README.md) and [prior-recall](benchmarks/prior/README.md) benchmarks measure useful omissions and review burden before proposing broader indexing. There is no local biological-prior graph or custom agent orchestrator.

This is an additive migration. Original objects, receipts, interpretations, and scientific tests remain intact. `daw` retains the v1 analytical interface and [historical pilot](docs/PILOT.md). Its fixed operators and approval pipeline are optional legacy functionality; `bio` uses source facts, searchable profiles, question-local reasoning, and reusable artifacts.
