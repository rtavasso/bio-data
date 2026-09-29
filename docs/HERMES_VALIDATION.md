# Hermes integration validation — 2026-09-29

The stock Hermes adapter passed source analysis, explicit memory consolidation, and fresh-session reuse. The matched control also answered correctly: **persistence works; a scientific answer-quality advantage from native memory is not established.** Exact run IDs, transcript/checkpoint hashes and check results are in the [validation receipt](v3/receipts/hermes-learning.json). [HERMES.md](HERMES.md) explains reproduction and checkpoint semantics.

The unmodified upstream revision was `99721dca80a58830a7b04b954fa5cb58ccb51a4a`, installed separately with stable Python 3.14.7. All subjects used the `openai-codex` provider with `gpt-6-astra` and requested `xhigh` reasoning. Background review and curator were disabled; native memory writes happened in the foreground.

| Case | Observed result |
| --- | --- |
| Source preparation | Correct PMP22 values 0/5; preserved the entire synthetic table, including SOX10 7/11 and source context; three registered outputs with execution evidence. No native memory note was written spontaneously. |
| Explicit consolidation | Reused and checked the artifact, then successfully wrote a 467-character native memory pointer with applicability limits (`events.jsonl:62–63`). No source-table reprocessing was needed. |
| Fresh session with retained state | Inherited the note/history, documented the note's role in candidate lookup (`questions/q_e11f6401fc194f8d/LABBOOK.md:13`), verified provenance, reused the artifact and correctly answered 7/11. |
| Prior-work control | Received the identical scientific archive and prompt with empty Hermes memory/history. Found and reused the artifact through catalog search and also correctly answered 7/11. |

Both final answers agree with their executed scripts and saved outputs. They describe the numerical difference of 4 without claiming promoter activity, donor independence, statistical significance or real biological change. Every mechanical check passed in all four completed cases. Scientific judgments here are an authored audit of the evidence; the evaluator's separate model-review field remains unreviewed.

Restored agent/workspace checkpoints still match every recorded hash. The export contains a self-contained SQLite database and excludes auth stores. A real WAL-related snapshot defect was fixed and regression tested. Earlier credential/runtime failures and a host-sleep/inactivity interruption remain recorded. Preparation must serialize backups of a shared seed because the workspace enforces a writer lock. Native one-shot approval checks rejected some inline Python commands; the subjects recovered using ordinary saved scripts or shell commands without changing approvals.

The full offline suite passed **197 tests**, with 3 live tests skipped. After allowing the new consolidation skill in suite definitions, the 24 focused evaluator tests passed again. Ruff and skill validation passed. Live stock-agent rehearsals were separate from these offline tests.

This is a small synthetic rehearsal, with substantial checking overhead. It does not establish biological novelty, spontaneous procedural learning, a speed/cost benefit, or reliable automatic background consolidation. The native aggregate token counters reported zero despite actual inference, so no token-cost comparison is made. Future evaluation should use unseen biological questions, repeated matched controls and analysis decisions that can change when relevant prior work is retrieved.

An unlimited PMP22 continuation was prepared from the existing real research workspace for `q_277f20df4b6b47cc`, with no time/request/file/new-download/iteration cap and a workspace-specific 5 GiB disk reserve. Synthetic rehearsal state was excluded. The local launch script and readiness receipt are under `workspaces/hermes-ready/`; the research run was **not launched**. Roughly 5 GiB of disposable package caches were freed; original datasets and historical evaluations were retained. Physical disk capacity and upstream inactivity checks still apply.
