# Agent workflow evaluation

Run the stock Codex CLI on a few questions, preserve what it did, inspect the resulting research work, and propose a small testable improvement. The evaluator lives under `benchmarks/agent/`; it does not change the `bio` catalog schema or implement an agent reasoning loop. Execution uses [Codex's non-interactive JSONL interface](https://learn.chatgpt.com/docs/non-interactive-mode).

See the [initial pilot](AGENT_EVALUATION_PILOT.md) for actual three-question results, reviewer findings and a tested registration improvement.

## Quick start

```sh
uv sync --all-extras
uv run python -m benchmarks.agent --help

# Prepare fixtures, snapshots and an inspectable report without a model or network.
uv run python -m benchmarks.agent prepare --suite workflow

# Run three short workflow questions using your installed/authenticated Codex CLI.
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite workflow --timeout 300 --review

# RUN is the exact run directory returned by the command.
uv run python -m benchmarks.agent report RUN
uv run python -m benchmarks.agent review RUN
```

Open the returned `report.html` in a browser. Case pages show checks, final answers, searchable notebook/output previews, failed commands, measured usage and transcript links. Raw JSONL is authoritative; readable transcripts retain raw line references. The review command without `--agent` creates a review prompt offline. `review RUN --agent` launches a separate reviewer; `review RUN --from-json review.json` imports an authored review with validated evidence locations. A recorded review is preserved rather than silently overwritten.

`--model MODEL` pins an explicit model; otherwise the stock CLI chooses its default, and the manifest says it is unpinned. `--codex PATH` selects the executable. The current runner uses `--ignore-user-config`, retains normal CLI authentication and execution rules, disables session persistence with `--ephemeral`, and never records credential files. It does not install Codex, choose a paid model, or invent unavailable cost telemetry. Prepare/report/compare and offline tests require no Codex login. Live subject or reviewer execution is explicitly gated by `DAW_LIVE=1`.

## Suites and repeatable experiments

`workflow` contains three small **synthetic** scenarios: zero versus omission, cross-question artifact reuse, and insufficient promoter/donor context. They exercise workflow behavior; they are not public biological discoveries. Source bytes and selected-table limitations are explicit. Reviewer expectations remain outside the subject prompt.

`research` contains three exploratory public-data questions about Egr2-AS expression, human Schwann-lineage chromatin, and human nerve cell composition. Those cases enable public web/data access; the workflow suite keeps scientific data access offline. The model service itself still requires connectivity. Use a single case first if you want a small live run:

```sh
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite research --case egr2-as-response --timeout 300
```

Use `--seed-workspace PATH` to copy a preserved workspace into each trial. The original workspace is never passed to the subject as its writable catalog. Copying is capped at 2 GiB of stored blobs per workspace; allow disk/time for a separate copy per case. Existing questions/artifacts are recorded as a baseline so merely inheriting them cannot satisfy the new-work checks. Default workflow runs need no downloaded data or seed workspace.

For a skill comparison:

```sh
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite workflow --skills off --model MODEL
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite workflow --skills on --model MODEL
uv run python -m benchmarks.agent compare BEFORE_RUN AFTER_RUN --output workspaces/comparison.json
```

The disabled condition omits the project workflow skills and explicit skill invocation; normal project instructions remain. The manifest records current source/skill/prompt hashes, source revision, setup time, model request, CLI version and limits. Run several repetitions and alternate order before attributing a difference to a skill. Model defaults, system/user-level skills, provider behavior, environment state and caches can affect results; this is not a hermetic or blinded model benchmark. Comparison reports descriptive changes and missing cases, not statistical significance or global scientific scores.

For a custom suite, copy a JSON file from `benchmarks/agent/suites/`. Each case has a stable slug, question, `setup`, `data_access`, selected skills, observable `expect` checks and `review_focus`. Setup is one of the small built-in fixtures or `empty`; suite text cannot inject an arbitrary setup shell command. Select cases with repeated `--case`. `prepare` writes a concrete run; `run --prepared RUN` executes that recorded configuration once, rejecting altered prompts, subject sources or evaluation driver code. Prepare another run for a retry so transcripts survive.

## What a run preserves

```text
RUN/
  manifest.json              actual configuration and source/prompt fingerprints
  evaluator-source/          exact Python driver sources at preparation
  report.json, report.html   batch comparison and diagnosis
  cases/CASE/
    prompt.txt               exact subject prompt
    baseline.json            pre-run catalog identities and immutable blob hashes
    project-files.json       hashes of the tested code/docs/skills
    execution.json           command, process state, elapsed time and limits
    events.jsonl, stderr.log raw CLI output, retained on failure or timeout
    final.md, transcript.md  final answer and readable trajectory
    artifacts.json          output/notebook paths, hashes and bounded previews
    report.json, report.html observable checks and source links
    trial/                  separate source snapshot, inputs and BIO_WORKSPACE
  review/                   frozen input report, reviewer prompt, transcript, JSON and provenance
```

Run folders are private and ignored under `workspaces/agent-evals/`. Snapshots copy current source bytes, including intentional uncommitted changes, and use the installed Python environment through `bio`/`python` wrappers. The subject's Git root and workspace-write sandbox are the trial directory. Original source files, historical workspaces, full historical specs, evaluation oracle and prior transcripts are not supplied as task material. This isolates ordinary writes; it is not a container or a claim that a hostile process cannot read any other host file. The installed environment and CLI authentication remain host dependencies.

Execution is sequential, with a default five-minute wall limit per case (configurable from 5–3600 seconds) and a 32 MiB raw log budget checked during execution. A timeout terminates the process group and retains partial evidence. There is no automatic retry or silent permission escalation. Public cases request bounded processed data; ordinary `bio` acquisition also applies its workspace budgets. Agent-written arbitrary network code remains the agent's responsibility and is visible in the transcript.

## Diagnose changes from evidence

Checks distinguish launch/completion, transcript parsing, preserved input bytes, code mutation, catalog integrity, new questions, edited/synced notebooks, scripts, registered outputs, reuse and gap events. They verify observable behavior, not the correctness of a scientific claim. A case can finish with failed workflow checks, and a well-written answer can still be scientifically unsupported. `scientific_review` remains unresolved in mechanical checks even after a separate reviewer supplies an opinion.

The reviewer sees the question, full recorded transcript and available outputs, with the same untrusted-content boundary as other source material. Its output separates strengths, findings, unresolved issues and next experiments. Findings identify the case, category, severity, an existing evidence file with a physical line or JSON pointer, a suggested change, and a validation test. Citation existence is checked; citation relevance and scientific judgments still need human assessment. Invalid or incomplete reviews retain their raw output and failure state.

Prefer a narrow fix supported by the trace: a broken command example, an unusable filter, an omitted provenance step, missing source context, or a fixture/environment defect. Rerun the affected case, compare the outputs and add a focused regression test where useful. Repeated actual access failures can motivate indexing work; one verbose review is not justification for a new format reader or biological graph.
