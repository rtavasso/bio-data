# V2 real-data validation

The pilot migrates a copy of the verified v1 backup, indexes its existing source files, and answers two questions using normal Python scripts and a shared artifact. Original v1 data and receipts remain intact. The working directory is `workspaces/v2-pilot`; downloaded data, question outputs, and backups are deliberately ignored by Git.

## Content retrieval

The preserved inventory contains 177 current assets: 32 acquired, 138 listed, and seven with explicit acquisition limitations. There are 32 structural profiles and 461,318 literal-label postings in their latest revisions. These are source strings across files, not a count of measured genes. Deep indexing made zero network requests. [Summary receipt](v2/receipts/summary.json).

| Literal feature | Metadata-only text hits | Deep content hits | Content hits whose filenames omit the feature |
|---|---:|---:|---:|
| Pmp22 | 0 | 4 | 4 |
| Sox10 | 34 | 4 | 4 |
| PMP22 | 0 | 4 | 4 |
| SOX10 | 34 | 3 | 3 |
| MS4A1 | 0 | 3 | 3 |

The metadata baseline is ordinary full-text retrieval over file manifests and source context, recorded before structural indexing. The second column therefore includes source mentions that are not file-content matches. Deep results are exact, case-sensitive source labels with file/cell/axis locators. These columns are different retrieval modes, not directly comparable precision/recall scores. [Metadata baseline](v2/receipts/metadata-baseline.json), [deep-index results and frontier](v2/receipts/deep-index.json).

Pmp22 content hits include two rat expression tables, a published supplementary workbook, and a reference annotation. PMP22 hits include a human matrix feature axis, a selected-list workbook, a tumor expression table, and a reference annotation. An annotation is not an expression measurement, a selected list cannot establish a null result, and the PBMC matrix is not a Schwann experiment. The substrate exposes these distinctions for question-time review.

The practical hidden-reuse example is GSE201623, titled “Egr2 promoter antisense RNA as coordinator of chromatin remodeling and genome reorganization in Schwann cells [RNA-seq].” Neither the study title nor the counts filename advertises Pmp22 or Sox10. Both labels are present inside the table, and the agent-authored profile points to the original GEO SOFT title and table header without making a promoter or independence claim.

## Bounded public-search comparison

On September 27, 2026, the pilot requested one 20-result Europe PMC page each for `PMP22 AND Schwann` and `SOX10 AND Schwann`. Both succeeded and retained actual HTTP responses, hashes, timestamps, and pagination warnings. Neither returned metadata page mentioned GSE201623. Deep local retrieval exposed its relevant source rows immediately. [Public-search receipt](v2/receipts/public-search.json).

This is a small retrieval demonstration, not an exhaustive web search, blinded agent benchmark, or claim that runtime search could never discover the study. Additional queries or following repository links could find it. The demonstrated benefit is persistent content knowledge and reusable processing; broad recall, agent time/cost, and public-scale throughput still need a larger evaluation.

## Two ordinary questions, one preparation

1. `q_f0f0de465eb54cb6` asks which source values exist for Pmp22 in GSE201623. Its `scripts/prepare.py` reads the whole TSV into Parquet as literal strings with source row numbers. No normalization, imputation, or biological regrouping occurs.
2. `q_d2f55dbf792c43d9` asks about Sox10 in the same table. It discovers and reuses the exact prepared artifact, without running preparation again, then executes its own ordinary lookup script.

Every one of the 17,950 rows and 107,700 cells in the preparation was compared independently against Python's direct TSV reader. Both feature lookups also matched the original source rows. The second question's prepared file has the identical hash. Changing a processing parameter yields a missing derivation instead of silently reusing the output. Three artifacts and two completed notebooks are searchable globally. [Reuse, source-cell checks, and provenance](v2/receipts/question-reuse.json).

```sh
uv run bio -w workspaces/v2-pilot data search --feature Pmp22
uv run bio -w workspaces/v2-pilot work search Pmp22
uv run bio -w workspaces/v2-pilot work show q_f0f0de465eb54cb6 --notebook
uv run bio -w workspaces/v2-pilot artifact search Schwann
uv run bio -w workspaces/v2-pilot provenance artifact_ae47d75299e31396b253c089db31ef6a95911ffab74697818aa7dcda5135160a
```

The notebooks retain the questions, source identities, findings, failed retrieval routes, assumptions, and open scientific questions. Commands and artifact reuse are recorded as events. The retained v1 acceptance pipeline is not called by these scripts. No effect estimate, donor independence, promoter output, or causal interpretation is inferred from the four source columns.

## Honest incomplete coverage

The deep-index job finishes partial, with eight visible partial tasks: unsupported Python/SQL/chromosome-size files, two compressed annotation scans exceeding inspection bounds, and one annotation content scan that reaches its literal-label limit. Downloaded Python remains inert. These outcomes are retained rather than converted to successful inspection or biological absence.

During the pilot, an archive refresh exposed a missing-size edge case that could move previously extracted members back to a listed state. The implementation now preserves acquired members when immutable parent bytes and the exact member selector match; the regression test covers it. Both affected annotation members were re-extracted from the preserved originals and checked back into the current inventory. The catalog keeps the intermediate receipts. An invalid citation locator in the pilot script was corrected before the semantic profile was registered.

## Checks and reproduction

- `uv run ruff check src tests scripts recipes` passes.
- The complete scientific environment passes 106 offline tests; three network tests are separately gated. [Offline test receipt](v2/receipts/pytest-offline.xml).
- All three opt-in live tests pass: Europe PMC discovery, PMC Cloud supplementary inventory, and v2 GEO metadata indexing without downloading dataset files. [Live test receipt](v2/receipts/pytest-live.xml), [actual source receipts](v2/receipts/live-sources.json).
- Backup/restore copies the catalog, all immutable objects, and all 13 question working files into an independent workspace and verifies their hashes and database integrity. [Restore receipt](v2/receipts/backup-restore.json).
- The built wheel installs in a separate environment with only base dependencies. Its two-question demo passes with scientific extras absent and parent-process network connections disabled. [Base-install receipt](v2/receipts/base-install.json). Dependency installation uses the package registry; normal local operation is offline.

To replay against the preserved v1 backup, run `uv run python scripts/v2_pilot.py`. The script reuses recorded public-search receipts and never requires network for local indexing/reuse. To record the initial live baseline in a fresh receipt directory, set `DAW_LIVE=1`. A fresh metadata-only comparison requires an unindexed copy of the v1 backup; the script rejects a contaminated baseline. New machines must acquire the source files or restore a verified backup first. Tests and the synthetic `bio demo` remain self-contained.

The source-cell artifact records the exact environment at execution, independently of later code changes. Current code, model, reference, and parameter changes are not retroactively claimed to match that old derivation. Source files and complete actual response bodies stay in the workspace; Git holds compact receipts only.
