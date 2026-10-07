# Bio-data research substrate

This repository supplies persistent scientific data and provenance for stock coding agents. Scientific reasoning stays question-local.

For research, start with `bio --help` (or `uv run bio --help` in a checkout); use [the workflow guide](docs/WORKFLOW.md) and the relevant repository skill in `.agents/skills/`. No historical specification is required.
- Use biological knowledge to form hypotheses; search indexed data, artifacts, and prior work.
- Use structured external sources and primary literature to audit and expand hypotheses. Seek contradictions.
- Analyze actual measurements with ordinary scientific tools. Do not assume cross-species or context transfer.
- Keep the question's `LABBOOK.md` current. Record retrieval failures with `bio work gap`, sync notes, and register reusable outputs.
- Reuse artifacts only when their exact derivation fits the current question. Question IDs are provenance, not cache keys.

Preserve immutable source bytes, receipts, interpretation history, and native formats. Missing, unindexed, selected-out, unmeasured, and measured-zero are different. Never invent assemblies, donor independence, feature universes, count semantics, or contrast direction; gene expression is not promoter output.

Keep discovery, transport, inspection, and scientific analysis separate. Workers receive immutable selected files; the parent owns catalog writes. Never execute downloaded code, formulas, macros, or pickle/R serializations. One carve-out: a replication task may execute only the code blobs named in the fetched derivation, hash-verified, through run_analysis.py in a sandbox with egress off; only that captured run confirms. Without a sandbox it is refused unless `commons.toml` sets `[replication] allow_rehearsal = true`; a rehearsal confirms nothing. Other fetched code never runs. No automatic raw processing.

For engineering, read the relevant component guide in [docs/V3.md](docs/V3.md), not every old specification. Preserve v1/v2 history and derivation behavior. Levels 0–2 determine index completion; semantic profiles are optional. Use benchmark results and retrieval gaps before expanding indexing. The evaluator under `benchmarks/agent/` launches stock agents and records behavior. Question-local hypothesis networks are research artifacts that guide broad mechanism investigations. Do not add a platform biological-prior graph, transfer engine, scientific DSL, or custom research agent loop.

Local use and offline tests require no model, credentials, hosted service, or network. For repository engineering, run `uv run ruff check src tests scripts benchmarks` and `uv run pytest`; scientific extras complete the suite. Scientific outcomes are acceptance criteria: fix code or document limitations, never weaken them to hide failure. Live checks require `DAW_LIVE=1` and actual receipts. Keep data and reports in ignored workspaces; commit only compact validation receipts, never downloaded datasets or credentials.
