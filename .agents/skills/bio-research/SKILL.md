---
name: bio-research
description: "Investigate a biological question using the bio-data workbench, public measurements, source-backed reasoning, question notebooks, and ordinary analysis scripts. Use for research questions, not general repository maintenance."
---

# Bio Research

When the goal is a finding beyond established results, use `bio-hypothesis-discovery` to distinguish known baselines, exploratory candidates, predictions and independent tests. Audit novelty separately from evidence strength; a useful analytical surprise does not itself establish new biology.

Start from the biological uncertainty: what competing explanations would different observations distinguish? Use existing biological knowledge as hypotheses and audit important missing mechanisms with structured resources and primary papers when network access is available. Respect an offline or bounded-data task; an unavailable source is a limitation to record.

Choose data by the inference they enable. Before a substantial analysis, compare plausible experiments and state which outcome would change the answer. Preserve the requested endpoint and scope when a convenient assay measures only one part. A result should update the explanation or narrow a meaningful uncertainty; more files or longer reports do not establish progress.

For broad mechanism or regulatory-system questions, use `bio-mechanism-exploration`. Save and revise a question-local hypothesis network, recursively investigate upstream controls, and connect competing explanations to data analyses. Audit blind spots during collection. A familiar first-order factor list alone does not complete a broad systems question. Simple extractions do not need a network.

Use `bio --help`; in a development checkout without `bio` on PATH, use `uv run bio`. Honor `BIO_WORKSPACE` or the workspace explicitly supplied by the user. For a new investigation, create a question with `bio work new "..."` and work in its returned directory. When continuing a supplied question, read its existing notebook and outputs and work in that question without replacing it. The CLI creates `QUESTION.md`, `LABBOOK.md`, `scripts/`, and `outputs/`.

Search data, artifacts, and previous work before new processing. `search` text is an option: `bio data search --text "Schwann RNA"`, `bio artifact search --text "prepared table"`, `bio work search --text "related question"`. Literal feature lookup uses `bio data search --feature PMP22`; case and source identifiers matter. Read `bio data show SUBJECT` using the result's `subject`, not its search-document `id`, before interpreting a match. Use the discovery or artifact-reuse skill when needed.

Analyze immutable source paths with ordinary Python/R/SQL and save the script alongside its outputs. Separate observed source values from biological conclusions: a gene-level zero is not a promoter measurement; omission, missing metadata, and unindexed content are unresolved. Establish sample identity, assay, units, contrast direction, assembly and feature universe only from evidence. Do not execute downloaded scripts, macros, formulas, or pickle/R serializations.

Use the explicitly supplied interpreter/wrappers when present; a login shell may reset PATH. Begin data analysis with design/quality checks and inspect broad patterns where appropriate, as well as the hypothesized features. Report unexpected observations and let them guide further acquisition. If prerequisites block an inference, preserve the evidence, perform still-valid analyses, and continue other feasible branches.

Run a saved analysis as a separate command, or use a success-dependent chain. Preserve its exit status and executed code version before displaying logs; a successful trailing `cat` does not mean the analysis succeeded. Keep failed runs and corrections visible.

Validate machine-readable outputs before registration. JSON must reject non-finite numbers (`allow_nan=False` in Python); represent missing values as `null` with their source token and meaning retained separately, never as zero or a silently discarded observation.

Keep the notebook useful to the next researcher: question, considered explanations, exact inputs/selectors, commands, findings, failed routes, limitations and next investigation. Register computed outputs with `bio register --help`; the flags require both `--input` and `--code`. Narrative conclusions can stay in `LABBOOK.md` and be preserved by `work sync`; do not fabricate code provenance just to register prose. Attribute agent-written interpretations accurately. Record a real information-access failure with `bio work gap QUESTION --need "..." --failed "..." --source-or-format "..."`. Scientific uncertainty alone is not necessarily an indexing failure.

Before a registration batch, inspect and validate the first successful JSON receipt. The artifact ID is in `artifact`; `output_blob` identifies the output bytes. Persist each receipt before continuing so a later error can resume from the completed registrations without guessing response fields.

Use distinct `--output-role` values for distinct products of one derivation, including separate PNG/PDF representations of a figure. Inspect conflicting-output warnings and retain the original receipts when correcting a role.

Finish with `bio work sync QUESTION --summary "..."`. Use `--status completed` only when the requested investigation is actually complete; an unresolved biological question can still have a useful bounded analysis. Report what the measurements support, what remains unresolved, and where the notebook and outputs are. Do not substitute a plan for an authorized analysis.

For detailed examples, read `docs/WORKFLOW.md` or `examples/V2.md` from the repository root as needed. Historical specs are not research kickoff material.
