# Agent workflow evaluation

Run the stock Codex CLI on a few questions, preserve what it did, inspect the resulting research work, and propose a small testable improvement. The evaluator lives under `benchmarks/agent/`; it does not change the `bio` catalog schema or implement an agent reasoning loop. Execution uses [Codex's non-interactive JSONL interface](https://learn.chatgpt.com/docs/non-interactive-mode).

See the [initial pilot](AGENT_EVALUATION_PILOT.md) for actual three-question results, reviewer findings and a tested registration improvement.

The [PMP22 mechanism audit](PMP22_MECHANISM_AUDIT.md) follows a broad regulatory-system question through upstream exploration, reused measurements, new acquisition, contradictions and an independent review.

The [sustained PMP22 audit](PMP22_DEEP_AUDIT.md) records a 48-minute continuation with deeper measurement analysis, independent numerical checks, remaining scientific gaps, and the structural failures that prompted handoff-checking improvements.

The [PMP22 discovery audit](PMP22_DISCOVERY_AUDIT.md) records a 43-minute hypothesis-testing attempt: three data-derived predictors, a frozen independent test, three rejections, source-quality corrections and a separate novelty audit. No novel mechanism was established.

## Quick start

The optional Hermes runtime and its checkpoint/transfer rehearsal are documented in [HERMES.md](HERMES.md). Codex remains the default runtime and the independent reviewer. Both use the same source preservation and scientific checks. Hermes is an external installation, not a dependency of `bio` or the offline test suite.

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

Report previews are capped separately from file metadata: after 300 previews, hashes and native paths remain available for up to 10,000 files. This keeps later scripts visible to provenance checks in sustained work. Omitted files/previews are reported explicitly; any file-metadata limit still requires manual review of omitted evidence.

Research and review agents default to `gpt-6-astra` with `xhigh` reasoning. The runner explicitly passes `--model gpt-6-astra -c 'model_reasoning_effort="xhigh"'`; `--model MODEL` and `--reasoning-effort EFFORT` override these settings. The configuration key is documented in the [official OpenAI configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference), and the [Astra model reference](https://developers.openai.com/api/docs/models/gpt-6-astra) lists `xhigh` support. Run manifests, HTML reports, recorded commands and reviewer provenance retain the requested settings; they do not independently attest to service-side model resolution. Historical records with missing settings remain unpinned rather than inheriting today's defaults.

`--codex PATH` selects the executable. The runner uses `--ignore-user-config`, retains normal CLI authentication and execution rules, disables session persistence with `--ephemeral`, and never records credential files. `run --review` uses the subject's recorded model and effort; standalone `review --agent` uses the pinned defaults unless overridden. Prepared runs reject model or effort overrides; prepare a fresh run to change them. Prepare/report/compare and offline tests require no Codex login. Live subject or reviewer execution is explicitly gated by `DAW_LIVE=1`. The runner does not install Codex or invent unavailable cost telemetry.

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

Use `--seed-workspace PATH` to copy a preserved workspace into each trial. The original workspace is never passed to the subject as its writable catalog. There is no fixed seed-copy size cap; allow disk/time for a separate copy per case. Existing questions/artifacts are recorded as a baseline so merely inheriting them cannot satisfy the new-work checks. Default workflow runs need no downloaded data or seed workspace.

For a skill comparison:

```sh
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite workflow --skills off --model MODEL
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite workflow --skills on --model MODEL
uv run python -m benchmarks.agent compare BEFORE_RUN AFTER_RUN --output workspaces/comparison.json
```

The disabled condition omits the project workflow skills and explicit skill invocation; normal project instructions remain. The manifest records current source/skill/prompt hashes, source revision, setup time, model request, CLI version and limits. Run several repetitions and alternate order before attributing a difference to a skill. Model defaults, system/user-level skills, provider behavior, environment state and caches can affect results; this is not a hermetic or blinded model benchmark. Comparison reports descriptive changes and missing cases, not statistical significance or global scientific scores.

For a custom suite, copy a JSON file from `benchmarks/agent/suites/`. Each case has a stable slug, question, `setup`, `data_access`, selected skills, observable `expect` checks and `review_focus`. Setup is one of the small built-in fixtures or `empty`; suite text cannot inject an arbitrary setup shell command. Select cases with repeated `--case`. `prepare` writes a concrete run; `run --prepared RUN` executes that recorded configuration once, rejecting altered prompts, subject sources or evaluation driver code. Prepare another run for a retry so transcripts survive.

## Sustained research and continuation

Both `pilot` and `deep` default to unlimited research time, requests, file size and newly downloaded bytes. The profiles select research instructions, not resource caps. Set optional limits with `--timeout SECONDS`, `--requests COUNT`, `--asset-mib MIB` and `--total-mib MIB`; zero means unlimited for each, and positive values have no imposed upper ceiling. For example, `--timeout 7200 --requests 300 --asset-mib 1024 --total-mib 4096` allows two hours, 300 requests, 1 GiB per file and 4 GiB of new downloads. Each limit can be set independently.

The manifest, subject prompt and copied workspace configuration record the same allowances. Finite workspace transport limits apply per command; the agent must account for cumulative use across commands, browser tools and its own scripts. This is not a network-wide traffic limiter. Usage is recorded even when unlimited; no model-token or dollar cap is imposed. Unlimited time permits sustained research, not an instruction to run forever: the agent should stop when the question is adequately addressed or further feasible work is unlikely to change the conclusion, preserving unresolved work.

New `bio` workspaces also default to `asset_bytes = 0`, `bundle_bytes = 0` and `requests = 0` in `config.toml`. Existing workspace settings and historical evaluation records are preserved. A newly prepared evaluation applies its requested allowances to the copied workspace, including continuations. To use unlimited acquisition in an existing standalone workspace, set those three fields to zero. Disk reserves, HTTP inactivity timeouts, retries, inspection-worker limits, parser limits and resumable indexing-plan bounds remain operational safeguards; they are separate from the research budget.

`mechanisms-deep` asks the PMP22 question with the requested follow-up priorities: resolve the Egr2-AS RNA discrepancy, seek quantitative accessibility measurements, and investigate an underexplored RNA/protein branch. It requires an investigation queue, new registered outputs, and execution evidence. A larger budget or more acquired bytes does not establish better science. Reviewer execution after `run --review` gets the same time allowance as each subject; its default is also unlimited. Use `review RUN --agent --timeout SECONDS` to specify a separate review limit.

```sh
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite mechanisms-deep --profile deep --review

# Continue the existing question in an isolated copy; the original stays intact.
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite mechanisms-deep --profile deep \
  --seed-workspace PRIOR_WORKSPACE --continue-question QUESTION_ID --review
```

Continuation accepts one selected case and an existing question in the supplied seed. It prepares a fresh run with its own transcript and a new baseline; this also works after a timeout. It does not overwrite or replay the earlier execution. The agent continues the notebook and queue, preserving prior numbered checkpoints. Checks require a newly edited/synced notebook, new computations and changed network/coverage artifacts; inherited work does not satisfy new-work checks. A continuation with extra time and prior results is not a controlled before/after skills comparison.

The queue's `analyzed` state requires registered artifact IDs and a finding; `blocked` requires a limitation and preserved evidence files. Deferred high-priority work cannot be labeled `bounded_complete`. These checks validate the record, not whether a causal question is resolved. The reviewer checks actual source support, statistical appropriateness, and whether feasible consequential work remained at stopping.

The activity report separately shows newly acquired asset identities/unique bytes and new registered results. Automatic execution credit requires the research skill's `run_analysis.py` receipt linking a successful producing invocation, execution-time code hash and newly written output hash to the registered artifact. Matching dependency invocations and script-name mentions remain review leads; quoted documentation, stale outputs and masked failures cannot earn credit. Older runs without producer receipts and complex/dynamic execution require manual review. Execution evidence is not proof of scientific validity. Acquisition bytes exclude inherited blobs, metadata-only browser traffic and duplicate bytes; historical runs without an acquisition baseline mark that limitation.

Acquisition metrics count catalog assets. Agent-written downloads preserved as object inputs are outside that metric and require separate receipt inspection; zero catalog acquisition bytes does not mean no downloading occurred. Completed retrieval claims must reference actual tool/HTTP receipts; planned queries do not count. The mechanism skill includes a read-only status/coverage-header checker. Subjects additionally use `./bin/python -m daw.research_records QUESTION_PATH` for the same full discovery/queue schemas and registered prediction/artifact reference checks used by the evaluator. Neither checker establishes biological validity or actual retrieval execution.

Use the supplied `./bin/python` and `./bin/bio` explicitly inside a trial. Login shells can reset PATH. The wrappers use the project interpreter and certifi trust bundle unless an explicit `SSL_CERT_FILE` is already set; they validate the selected bundle and retain hostname/certificate verification. An offline preflight records the interpreter, trust store and available scientific modules in `environment.json`. It verifies configuration, not live source availability. Invalid explicit CA configuration fails early.

## Discovery attempts

The `discovery` suite asks which candidate regulators predict PMP22 changes beyond a general Schwann-cell myelination response and whether predictions hold in an independent perturbation dataset. Use the deep profile and, when useful, continue a preserved question:

```sh
DAW_LIVE=1 uv run python -m benchmarks.agent run --suite discovery --profile deep \
  --seed-workspace PRIOR_WORKSPACE --continue-question QUESTION_ID --review
```

The [discovery skill](../.agents/skills/bio-hypothesis-discovery/SKILL.md) separates known baselines, exploratory candidates, locked predictions, validation results and novelty claims. Its helper preserves prediction bytes without overwriting prior files. The question-local `outputs/discoveries.json` links source-derived artifacts, validation outputs, exact prediction hashes and dated literature searches. Mechanical checks validate record integrity and expose sealing-receipt lines for review; they do not certify when outcomes were first inspected, biological independence or novelty. The agent can report no eligible candidate with an explanation instead of manufacturing a finding.

A single claim's ledger ID must match the sealed `candidate_id`. Individual claims sharing a panel use an explicit `prediction_id` and must appear in that panel's sealed `candidate_ids`; an existing lock cannot gain members after outcome inspection. See the skill's [record conventions](../.agents/skills/bio-hypothesis-discovery/references/records.md) for the complete contract.

The reviewer assesses six dimensions independently: `baseline_and_selection`, `prediction_timing`, `independent_validation`, `confounder_discrimination`, `novelty_audit`, and `claim_calibration`. It checks exposure in inherited outputs and source papers, sample overlap, actual executed analysis, generic-state and technical alternatives, and comparison with closest prior work. An informative rejection earns scientific credit; a positive result is not required. An observational association is not automatically a causal mechanism. A literature search with no match is bounded evidence, never proof that no one has reported the finding.

The existing mechanism rubric's `discovery_value` includes analytical insights and design problems. It does not establish new-to-field biology. A discovery continuation is guided public-data research, not a blinded benchmark or a controlled estimate of skill improvement. No automated field-novelty score is produced.

## Iterating from an audit

`discovery-iteration` keeps the broader PMP22 regulatory-system question visible while asking the agent to choose informative experiments, pursue consequential anomalies and distinguish new computation from new inference and biological novelty. The [investigation-design guide](../.agents/skills/bio-hypothesis-discovery/references/investigation-design.md) addresses control compatibility, endpoint selection, measured backgrounds and cross-context comparisons.

Source selection also includes [finding useful data beyond target-name searches](../.agents/skills/bio-data-discovery/references/indirect-discovery.md). Review the actual route from search or citation to file inspection, a defensible connection to the question, executed analysis and changed conclusions. Separate recovery of known target literature from new use of broadly collected measurements. Report which studies were screened, inspected, analyzed, rejected or left open, accounting for shared samples and inherited work. Searches without the target name can expose hidden opportunities but are not a success metric by themselves. A paper that omits the target from its title may already report the result in a table. These judgments belong in the existing scientific criteria, not a dataset-count or field-novelty score.

```sh
uv run python -m benchmarks.agent prepare --suite discovery-iteration --profile deep \
  --seed-workspace PRIOR_WORKSPACE --continue-question QUESTION_ID
DAW_LIVE=1 uv run python -m benchmarks.agent run --prepared RETURNED_RUN --review
```

Inspect the transcript, native outputs, failed checks and independent review. Choose a small change supported by the observed behavior, then prepare a fresh continuation with revised skills and a focused investigation brief. Keep previous runs and rejected hypotheses intact. Use ordinary stock-agent runs for this loop; no platform research orchestrator or automatic novelty score is involved. More time, inherited measurements and changed prompts make these guided continuations, not controlled estimates of a skill's effect.

The prediction-link helper checks inherited and new ledger entries without changing sealed bytes. Reports retain candidate reference errors and still expose valid candidates; any such error keeps the ledger check failed. Baseline comparison identifies unchanged prediction references, not scientific validity. Whole-ledger schema failures remain fatal to inspection.

Execution leads require a literal invocation covered by the successful shell status; automatic output credit additionally needs the producer receipt described above. A failed analysis followed by a successful dependency or display command receives no automatic credit. Separate analysis commands and preserved execution-time code/output hashes make manual review possible when automatic attribution is unavailable.

The [two-iteration validation receipt](v3/receipts/pmp22-discovery-iteration.json) pins the research and review records. It distinguishes a new retrospective analytical finding from independently confirmed biological novelty. Full reports, data and the parent audit remain in the ignored run directories identified by that receipt. Final guidance refinements made after review are identified separately from the live-tested snapshots.

The subsequent [source-discovery audit receipt](v3/receipts/pmp22-source-discovery-audit.json) traces literature queries and broader-purpose datasets in those same runs. It records target-name concentration, useful indirect analyses, and recovery of an already published RNA-decay mechanism. The resulting discovery guidance and review prompts have offline validation; they have not yet been tested in a new live run.

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

Execution is sequential, with no default time or raw-transcript size cap. When a finite timeout is supplied, the runner bounds both monotonic and wall clocks, including host-sleep gaps; it records both durations in either mode. A timeout or user interruption terminates the process group and retains partial evidence. The capture API also supports an optional positive `max_log_bytes` cap. There is no automatic retry or silent permission escalation. Public cases prefer processed data; ordinary `bio` acquisition applies any finite workspace budgets. Agent-written arbitrary network code remains the agent's responsibility and is visible in the transcript.

## Diagnose changes from evidence

Checks distinguish launch/completion, transcript parsing, preserved input bytes, code mutation, catalog integrity, new questions, edited/synced notebooks, scripts, registered outputs, reuse and gap events. They verify observable behavior, not the correctness of a scientific claim. A case can finish with failed workflow checks, and a well-written answer can still be scientifically unsupported. `scientific_review` remains unresolved in mechanical checks even after a separate reviewer supplies an opinion.

The reviewer sees the question, full recorded transcript and available outputs, with the same untrusted-content boundary as other source material. Its output separates strengths, findings, unresolved issues and next experiments. Findings identify the case, category, severity, an existing evidence file with a physical line or JSON pointer, a suggested change, and a validation test. Citation existence is checked; citation relevance and scientific judgments still need human assessment. Invalid or incomplete reviews retain their raw output and failure state.

Prefer a narrow fix supported by the trace: a broken command example, an unusable filter, an omitted provenance step, missing source context, or a fixture/environment defect. Rerun the affected case, compare the outputs and add a focused regression test where useful. Repeated actual access failures can motivate indexing work; one verbose review is not justification for a new format reader or biological graph.
