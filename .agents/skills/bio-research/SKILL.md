---
name: bio-research
description: "Investigate a biological question using the bio-data workbench, public measurements, source-backed reasoning, question notebooks, and ordinary analysis scripts. Use for research questions, not general repository maintenance."
---

# Bio Research

Start from the biological uncertainty: what competing explanations would different observations distinguish? Use existing biological knowledge as hypotheses and audit important missing mechanisms with structured resources and primary papers when network access is available. Respect an offline or bounded-data task; an unavailable source is a limitation to record.

For broad mechanism or regulatory-system questions, use `bio-mechanism-exploration`. Save and revise a question-local hypothesis network, recursively investigate upstream controls, and connect competing explanations to data analyses. Audit blind spots during collection. A familiar first-order factor list alone does not complete a broad systems question. Simple extractions do not need a network.

Use `bio --help`; in a development checkout without `bio` on PATH, use `uv run bio`. Honor `BIO_WORKSPACE` or the workspace explicitly supplied by the user. Create a question with `bio work new "..."` and work in its returned directory. The CLI creates `QUESTION.md`, `LABBOOK.md`, `scripts/`, and `outputs/`.

Search data, artifacts, and previous work before new processing. `search` text is an option: `bio data search --text "Schwann RNA"`, `bio artifact search --text "prepared table"`, `bio work search --text "related question"`. Literal feature lookup uses `bio data search --feature PMP22`; case and source identifiers matter. Read `bio data show SUBJECT` using the result's `subject`, not its search-document `id`, before interpreting a match. Use the discovery or artifact-reuse skill when needed.

Analyze immutable source paths with ordinary Python/R/SQL and save the script alongside its outputs. Separate observed source values from biological conclusions: a gene-level zero is not a promoter measurement; omission, missing metadata, and unindexed content are unresolved. Establish sample identity, assay, units, contrast direction, assembly and feature universe only from evidence. Do not execute downloaded scripts, macros, formulas, or pickle/R serializations.

Validate machine-readable outputs before registration. JSON must reject non-finite numbers (`allow_nan=False` in Python); represent missing values as `null` with their source token and meaning retained separately, never as zero or a silently discarded observation.

Keep the notebook useful to the next researcher: question, considered explanations, exact inputs/selectors, commands, findings, failed routes, limitations and next investigation. Register computed outputs with `bio register --help`; the flags require both `--input` and `--code`. Narrative conclusions can stay in `LABBOOK.md` and be preserved by `work sync`; do not fabricate code provenance just to register prose. Attribute agent-written interpretations accurately. Record a real information-access failure with `bio work gap QUESTION --need "..." --failed "..." --source-or-format "..."`. Scientific uncertainty alone is not necessarily an indexing failure.

Finish with `bio work sync QUESTION --summary "..."`. Use `--status completed` only when the requested investigation is actually complete; an unresolved biological question can still have a useful bounded analysis. Report what the measurements support, what remains unresolved, and where the notebook and outputs are. Do not substitute a plan for an authorized analysis.

For detailed examples, read `docs/WORKFLOW.md` or `examples/V2.md` from the repository root as needed. Historical specs are not research kickoff material.
