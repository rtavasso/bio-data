# Question-local mechanism artifacts

These interchange conventions describe research outputs, not an execution DSL or complete ontology. Add useful fields freely. Structural checks do not validate biology.

Save `outputs/mechanisms.initial.json` before substantial retrieval and `outputs/mechanisms.json` after investigation. Use distinct filenames such as `mechanisms.r002.json` for intermediate revisions. Preserve each snapshot with `bio object add PATH --classification interpretation` as written; record its hash and change in `LABBOOK.md`. Do not reconstruct a purported initial snapshot after research. Identical later snapshots are allowed when evidence did not justify a change; explain retention.

Each JSON document has:

- `revision`: positive integer, increasing for later snapshots.
- `scope`: object describing target, endpoint, species/context and assumptions; no invented metadata.
- `nodes`: objects with unique `id`, `label`, and `kind` (descriptive string). Distinguish abundance from activity where consequential.
- `edges`: objects with unique `id`, `source` and `target` node IDs, `mechanism`, `context`, `status`, and `evidence`. Status is `hypothesis`, `supported`, `contested`, or `rejected`, relative to the stated context. Evidence objects have `source` (URL, accession or preserved artifact), `locator` (figure, table, section, row or field), and `basis` (what was observed and what it does/does not establish). Unverified hypotheses may have empty evidence; other statuses require evidence. Citation existence does not establish relevance.
- `frontier`: objects with `node` ID, `question`, `priority`, `reason`, and `status` (`open`, `investigated`, or `deferred`). Priority is reasoned text, not a calibrated probability. Explain an empty frontier's scope/stopping boundary.
- `changes`: objects with `reason` and `evidence` in the same evidence format. Initial maps can have none; later entries explain retention, rejection, changed context or revised collection priorities.

The map frontier and investigation queue have different status vocabularies. A blocked frontier stays `open`, with the blocker in `reason`; work performed without resolving the question can be `investigated`, with that limitation in `reason`. Keep richer dispositions in an additional field. Do not put queue statuses such as `blocked` or invented labels such as `analyzed_but_unresolved` in `frontier.status`.

Before handoff, run `python .agents/skills/bio-mechanism-exploration/scripts/check_statuses.py QUESTION_DIRECTORY` (use `./bin/python` inside an evaluation trial). This read-only helper checks current-file JSON syntax, status vocabulary and coverage columns; it does not certify reference integrity, evidence support or scientific correctness. Correct the current record with a preserved revision and rationale; never rewrite historical snapshots to hide a failure.

Save UTF-8 `evidence-coverage.tsv`, one row per proposed or attempted discriminating analysis, with these columns:

| Column | Meaning |
| --- | --- |
| `edge_ids` | Semicolon-separated current edge IDs; an experiment may address several edges |
| `alternatives` | Explanations the observation could distinguish |
| `observation` | Measurement or perturbation/readout needed |
| `file_or_accession` | Actual file/URL/asset or accession; blank if not located |
| `analysis` | Concrete selectors/comparison and unverified prerequisites |
| `inspection_status` | `not_searched`, `searched`, `located`, `inspected`, `analyzed`, or `unavailable` |
| `source_locator` | Receipt, source section, row/field or native output path; distinguish metadata from measurement inspection |
| `result_or_limitation` | Observed result or unresolved limitation |
| `next_action` | Next action or reason for deferral |

`located` requires an actual source identity. `inspected` and `analyzed` also require a locator for evidence actually read/produced. A proposed filename is not a located file. Alternate encodings of an experiment are not independent evidence. An all-unavailable table is an honest limitation, not successful data reuse or analysis.

`inspection_status` describes work on a file, not support for its associated edges. In `result_or_limitation`, state which alternatives the measurement can actually distinguish. Label contextual or non-discriminating analyses explicitly; promoter peak overlap cannot establish recruitment or signaling, and a downstream expression change cannot establish feedback. Split rows when different edges have different evidential coverage.

Retain all required coverage columns and their names. A branch-level summary can be an additional file; it does not replace edge-linked coverage. Put nuanced labels such as “published summaries only” in `result_or_limitation`, keeping `inspection_status` within its documented vocabulary.
