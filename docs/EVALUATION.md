# Agent workflow evaluation

Run the stock Codex CLI on a few questions, preserve what it did, inspect the resulting research work, and propose a small testable improvement. The evaluator lives under `benchmarks/agent/`; it does not change the `bio` catalog schema or implement an agent reasoning loop. Execution uses [Codex's non-interactive JSONL interface](https://learn.chatgpt.com/docs/non-interactive-mode).

See the [initial pilot](AGENT_EVALUATION_PILOT.md) for actual three-question results, reviewer findings and a tested registration improvement.

The [PMP22 mechanism audit](PMP22_MECHANISM_AUDIT.md) follows a broad regulatory-system question through upstream exploration, reused measurements, new acquisition, contradictions and an independent review.

The [sustained PMP22 audit](PMP22_DEEP_AUDIT.md) records a 48-minute continuation with deeper measurement analysis, independent numerical checks, remaining scientific gaps, and the structural failures that prompted handoff-checking improvements.

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

`mechanisms` asks exactly **“What is the full regulatory system for PMP22?”** without supplying a regulator list or preferred mechanism. It invokes recursive exploration and public retrieval, checks question-local network/coverage artifacts, and requires the reviewer to assess six dimensions: recursive exploration, breadth, discovery value, discrimination, revision, and calibration. Verdicts are `demonstrated`, `partial`, `not_demonstrated`, or `unresolved`, each with validated evidence locations. There is no combined scientific score. A valid graph, a longer path, or more citations cannot demonstrate investigation on their own.

```sh
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite mechanisms --timeout 900 --review
# To test new uses of existing data, add --seed-workspace PATH.
```

`mechanism-challenges` supplies fictional offline perturbations, an activity-versus-abundance distinction, an RNA-fate alternative, and a context decoy. The subject sees raw measurements and assay notes; specific expected observations remain outside the trial. Prepare it offline with `prepare --suite mechanism-challenges`. Executing its agent still requires `DAW_LIVE=1`. It is a bounded challenge for the exploration behavior, not evidence of real biological performance.

The mechanism skill describes the minimal `mechanisms.initial.json`, `mechanisms.json`, and `evidence-coverage.tsv` conventions. Structural inspection checks identifiers, evidence attribution, snapshots and table references; transcript/source review must establish actual exploration and revision. All-unavailable coverage can be structurally valid while discovery value remains unproven. Preserve an early snapshot when written rather than retrospectively reconstructing an initial hypothesis. Authored output files need explicit object preservation because notebook sync does not snapshot all question outputs.

Use `--seed-workspace PATH` to copy a preserved workspace into each trial. The original workspace is never passed to the subject as its writable catalog. Copying is capped at 2 GiB of stored blobs per workspace; allow disk/time for a separate copy per case. Existing questions/artifacts are recorded as a baseline so merely inheriting them cannot satisfy the new-work checks. Default workflow runs need no downloaded data or seed workspace.

For a skill comparison:

```sh
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite workflow --skills off --model MODEL
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite workflow --skills on --model MODEL
uv run python -m benchmarks.agent compare BEFORE_RUN AFTER_RUN --output workspaces/comparison.json
```

The disabled condition omits the project workflow skills and explicit skill invocation; normal project instructions remain. The manifest records current source/skill/prompt hashes, source revision, setup time, model request, CLI version and limits. Run several repetitions and alternate order before attributing a difference to a skill. Model defaults, system/user-level skills, provider behavior, environment state and caches can affect results; this is not a hermetic or blinded model benchmark. Comparison reports descriptive changes and missing cases, not statistical significance or global scientific scores.

For a custom suite, copy a JSON file from `benchmarks/agent/suites/`. Each case has a stable slug, question, `setup`, `data_access`, selected skills, observable `expect` checks and `review_focus`. Setup is one of the small built-in fixtures or `empty`; suite text cannot inject an arbitrary setup shell command. Select cases with repeated `--case`. `prepare` writes a concrete run; `run --prepared RUN` executes that recorded configuration once, rejecting altered prompts, subject sources or evaluation driver code. Prepare another run for a retry so transcripts survive.

## Sustained research and continuation

The `deep` profile allows one hour, 150 research requests, 512 MiB per file and 1 GiB of newly downloaded data. The default `pilot` profile retains five minutes, 20 requests, 64 MiB per file and 128 MiB total. Override these explicitly with `--timeout`, `--requests`, `--asset-mib` and `--total-mib`. The manifest, subject prompt and copied workspace configuration record the same allowances. Workspace transport limits apply per command; the agent must account for cumulative use across commands, browser tools and its own scripts. This is not a network-wide traffic limiter.

`mechanisms-deep` asks the PMP22 question with the requested follow-up priorities: resolve the Egr2-AS RNA discrepancy, seek quantitative accessibility measurements, and investigate an underexplored RNA/protein branch. It requires an investigation queue, new registered outputs, and execution evidence. A larger budget or more acquired bytes does not establish better science. Reviewer execution after `run --review` is separately capped at 15 minutes.

```sh
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite mechanisms-deep --profile deep --review

# Continue the existing question in an isolated copy; the original stays intact.
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite mechanisms-deep --profile deep \
  --seed-workspace PRIOR_WORKSPACE --continue-question QUESTION_ID --review
```

Continuation accepts one selected case and an existing question in the supplied seed. It prepares a fresh run with its own transcript and a new baseline; this also works after a timeout. It does not overwrite or replay the earlier execution. The agent continues the notebook and queue, preserving prior numbered checkpoints. Checks require a newly edited/synced notebook, new computations and changed network/coverage artifacts; inherited work does not satisfy new-work checks. A continuation with extra time and prior results is not a controlled before/after skills comparison.

The queue's `analyzed` state requires registered artifact IDs and a finding; `blocked` requires a limitation and preserved evidence files. Deferred high-priority work cannot be labeled `bounded_complete`. These checks validate the record, not whether a causal question is resolved. The reviewer checks actual source support, statistical appropriateness, and whether feasible consequential work remained at stopping.

The activity report separately shows newly acquired asset identities/unique bytes and new registered results, matching saved code and successful literal invocations. Script-name mentions are listed separately; quoted documentation and heredoc bodies do not earn execution credit. Dynamic execution, imports, shell variables and complex shell syntax may need manual review. Even a literal invocation is not proof of scientific validity. Acquisition bytes exclude inherited blobs, metadata-only browser traffic and duplicate bytes; historical runs without an acquisition baseline mark that limitation.

Acquisition metrics count catalog assets. Agent-written downloads preserved as object inputs are outside that metric and require separate receipt inspection; zero catalog acquisition bytes does not mean no downloading occurred. The mechanism skill includes a read-only status/coverage-header checker to catch map/queue label confusion and missing coverage columns before handoff. It does not replace complete structural, provenance or scientific review.

Use the supplied `./bin/python` and `./bin/bio` explicitly inside a trial. Login shells can reset PATH. The wrappers use the project interpreter and certifi trust bundle unless an explicit `SSL_CERT_FILE` is already set; they validate the selected bundle and retain hostname/certificate verification. An offline preflight records the interpreter, trust store and available scientific modules in `environment.json`. It verifies configuration, not live source availability. Invalid explicit CA configuration fails early.

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

Execution is sequential, with a default five-minute wall limit per case (configurable from 5–3600 seconds) and a 32 MiB raw log budget checked during execution. The runner bounds both monotonic and wall clocks, including host-sleep gaps; it records both durations. A timeout terminates the process group and retains partial evidence. There is no automatic retry or silent permission escalation. Public cases request bounded processed data; ordinary `bio` acquisition also applies its workspace budgets. Agent-written arbitrary network code remains the agent's responsibility and is visible in the transcript.

## Diagnose changes from evidence

Checks distinguish launch/completion, transcript parsing, preserved input bytes, code mutation, catalog integrity, new questions, edited/synced notebooks, scripts, registered outputs, reuse and gap events. They verify observable behavior, not the correctness of a scientific claim. A case can finish with failed workflow checks, and a well-written answer can still be scientifically unsupported. `scientific_review` remains unresolved in mechanical checks even after a separate reviewer supplies an opinion.

The reviewer sees the question, full recorded transcript and available outputs, with the same untrusted-content boundary as other source material. Its output separates strengths, findings, unresolved issues and next experiments. Findings identify the case, category, severity, an existing evidence file with a physical line or JSON pointer, a suggested change, and a validation test. Citation existence is checked; citation relevance and scientific judgments still need human assessment. Invalid or incomplete reviews retain their raw output and failure state.

Prefer a narrow fix supported by the trace: a broken command example, an unusable filter, an omitted provenance step, missing source context, or a fixture/environment defect. Rerun the affected case, compare the outputs and add a focused regression test where useful. Repeated actual access failures can motivate indexing work; one verbose review is not justification for a new format reader or biological graph.
