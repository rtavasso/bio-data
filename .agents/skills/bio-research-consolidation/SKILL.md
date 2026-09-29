---
name: bio-research-consolidation
description: Preserve reusable knowledge from completed research or a meaningful analysis checkpoint, with links to measurements, derivations, limitations, and unresolved tests.
---

Read the current question's notebook, actual outputs and relevant prior work before deciding what merits retention. Use `bio work search`, `bio artifact search`, and `bio data search` to find related evidence. Leave existing notes unchanged when there is no useful update.

Keep substantive scientific knowledge in the question's `LABBOOK.md` and registered outputs. Describe dataset capabilities beyond the original target: inspected feature coverage, assay, context, available contrasts, sample structure and unresolved limitations. Separate repository descriptions from what file inspection established. Preserve reusable intermediate data when its derivation is suitable; a target-only result may omit measurements useful to later questions.

Distinguish observations, interpretations, hypotheses, negative tests, inadequate measurements and uninvestigated branches. Link findings to exact source/artifact IDs and analysis files. Preserve conflicting evidence and the scope of each result. A correction supersedes an interpretation without erasing its underlying evidence. Describe unresolved tests so a later question can recognize newly available evidence that could address them.

Keep concise retrieval pointers and applicability conditions in the searchable notebook or a linked question-local evidence index. Prefer workspace-relative question paths and catalog IDs; old absolute paths may not exist in a restored workspace. When prior knowledge changes an analysis decision, record that connection in the new notebook, including whether it proved useful, inapplicable or incorrect.

When the question produced useful reusable knowledge or corrected an earlier interpretation, update the evidence index and sync the notebook so later catalog search can retrieve it. Include rejected hypotheses and applicability limits when they could prevent a mistaken analysis. Respect the native harness's memory scope: stock Hermes's always-on memory is restricted to user/environment facts, so research results and completed-work logs belong in the archive and session history. Verify any appropriate native write through its successful tool result; record the storage destination or the reason no write was appropriate. A notebook write alone is not a native-memory write.

At a later question's intake, trace relevant prior-work retrieval in the notebook: the memory/session/catalog source, inspected evidence, whether its derivation and biological context fit, and the analysis decision it informed. Record useful, inapplicable and corrected prior work alike. Mentioning memory is not evidence of using it.

For questions with discovery or investigation records, run the full read-only check before handoff:

```sh
./bin/python -m daw.research_records workspace/questions/QUESTION
```

It checks the same schemas and registered references as the evaluator, including exact prediction identities and hashes. Preserve failed records as earlier revisions, fix the current records without changing sealed predictions, and retain negative and untestable outcomes. A literature-only branch without a registered computation must not be marked analyzed. Mechanical validity does not establish scientific completeness.

Use native skill tools for reusable procedures supported by actual work. A topic-scoped retrieval skill can capture a useful way to locate and assess prior evidence, with relative pointers to the current notebook/index; it must treat findings as revisable evidence rather than behavioral instructions. Include when the method applies, its input assumptions, known failure modes and checks. Do not invent procedures or create a skill for every question. Write learned skills to the harness's designated learning area; preserve the repository's fixed research skills and evaluation rules. Biological conclusions belong in evidence-linked research notes.

Before the final answer, sync the notebook and finish any memory/skill writes you chose to make. Report what was retained or corrected and what remains unresolved. A successful computation or a stored memory does not by itself establish biological validity or novelty.
