# Minimal Hermes integration

The [local research community](COMMUNITY.md) additionally supports persistent
conversation continuation and isolated forks. Evaluation trials retain the
fresh-session semantics below. Both paths share the same launch/capture utilities.

The [live validation audit](HERMES_VALIDATION.md) records source preparation, native memory persistence, fresh-session reuse and the matched prior-work control.

Use an unmodified, pinned upstream [Hermes](https://github.com/NousResearch/hermes-agent) installation. The evaluator invokes its [one-shot JSONL interface](https://hermes-agent.nousresearch.com/docs/reference/cli-commands/#--format-stream-json--structured-jsonl-output), retaining the native stream and stderr. Install Hermes separately from this project's Python environment; the validated upstream revision uses stable Python 3.14, while `bio` uses Python 3.12–3.13. The run records the executable's version output and requested model/provider. No model credentials are needed for preparation, reports, checkpoint validation or offline tests.

```sh
uv run python -m benchmarks.agent prepare --runtime hermes \
  --suite learning --case learning-source --seed-workspace WORKSPACE

DAW_LIVE=1 uv run python -m benchmarks.agent run --prepared RUN \
  --hermes /absolute/path/to/hermes
```

Hermes uses a fresh trial-local home and generated configuration. It defaults to the `openai-codex` provider and `gpt-6-astra` / `xhigh`; `--hermes-provider`, `--model` and `--reasoning-effort` override these at preparation. Supply provider credentials through the stock provider's environment, or set `BIO_HERMES_AUTH_FILE` to an existing Hermes auth store **outside the run directory**. The adapter links that store at launch; auth stores, `.env`, config and arbitrary home files are excluded from checkpoint exports. Do not export whole live trial homes as learning checkpoints. A prepared checkpoint never carries authentication to another run.

The local terminal backend is not an OS sandbox. Project instructions prohibit parent-directory inspection, downloaded code, other agents and changes to fixed evaluation files. Offline cases omit web tools and prohibit scientific network retrieval in their prompt; shell networking is not technically blocked. Treat live results as local rehearsals, not hermetic/blinded benchmarks. The adapter does not pass `--yolo`; native approval behavior still applies. Only terminal, file, skills, memory and session-search tools are selected, plus web tools for public cases. Web-provider availability depends on the installed runtime's credentials; repository APIs and `bio` discovery remain available through the terminal.

## Learning and checkpoint semantics

The research-consolidation skill asks the subject to save a searchable evidence index for useful new or corrected knowledge and verify any appropriate native write. Stock Hermes restricts always-on memory to user/environment facts; task-specific research findings belong in the scientific archive and native session history. A useful topic-scoped retrieval skill may point to the revisable evidence. Learned procedures live in the trial profile; repository skills remain fixed. Automatic background review and skill curator are disabled in this adapter: upstream one-shot background threads are not a reliable completion barrier. This uses foreground consolidation with stock Hermes tools, not automatic background consolidation. No custom research agent loop is added.

`learning-before/` and `learning-baseline.json` preserve initial memory, skills and session database. After process termination, `checkpoint/` contains:

- `agent/`: allowlisted `memories/`, `skills/`, and a consistent SQLite backup of `state.db`.
- `workspace/`: a full `bio` backup with source bytes, catalog, notebooks, scripts and outputs.
- `checkpoint.json`: hashes, parent checkpoint identity, memory changes, completion state and restoration status.

An interrupted or failed run can leave a restorable checkpoint without being completed. A backup failure leaves no completed checkpoint receipt. Changed bytes and symlinks are rejected on restore. Snapshot generation occurs after the process ends; a 30-second heartbeat and streamed logs expose ongoing runs, but the adapter does not restart crashed agents automatically or provide mid-turn consistent checkpoints.

Hermes's stream caps individual tool outputs at 5000 characters. Full persisted messages are available in the captured session database; stream evidence never invents shell success from `is_error=false`. Only a terminal result with an explicit integer `exit_code` establishes an automatic command outcome. Known plain-text context-compaction messages retain their position as runtime status events; other malformed events still fail parsing. Truncated/ambiguous results require manual source/output inspection. Token fields are upstream reports and may use zero for unavailable measurements.

Automatic output-execution credit additionally requires the research skill's `run_analysis.py` receipt, linking the producing invocation, its execution-time code hash, exit status and newly written output hashes. Dependency invocations and stale output files alone cannot pass. Older transcripts without receipts remain manual-review evidence; this stricter check must not be described as proof that old analyses failed. Full discovery/queue schema and artifact/prediction reference validation is available to subjects through `./bin/python -m daw.research_records QUESTION_PATH` and uses the evaluator's shared implementation.

## Inspecting reuse on a real follow-up

The `pmp22-followup` suite provides an explicit `pmp22-consolidate` case and a `pmp22-state-composition` question. Restore the original checkpoint into consolidation with `--continue-question`, inspect its searchable evidence index and any verified native write, then seed a fresh follow-up from that completed checkpoint without `--continue-question`. Each case is selected and launched explicitly; no custom research loop or comparison arm is required. Inspect actual retrieval, applicability judgments, reused artifact identities and decisions made before new analysis. A single run demonstrates observed use of prior work, not a causal quality advantage from memory. Never supply future answers or fabricate historical execution receipts during record repair.

## Fresh-session transfer and control

Run the training case above first. `SOURCE_CHECKPOINT` is `RUN/cases/learning-source/checkpoint`. A subject may reasonably retain only catalog/notebook pointers and skip native memory. The separate `learning-consolidate` case explicitly tests the native write mechanism with an appropriate environment fact, without repeating analysis or storing scientific task logs in always-on memory:

```sh
uv run python -m benchmarks.agent prepare --runtime hermes \
  --suite learning --case learning-consolidate --seed-checkpoint SOURCE_CHECKPOINT
```

Launch that prepared case, then set `CHECKPOINT` to its `cases/learning-consolidate/checkpoint`. This explicitly prompted write is a persistence test, not evidence of spontaneous learning. To test spontaneous retention alone, use the original source checkpoint and report whether it contains any authored memory.

```sh
# Same prior research plus native learned memory/skills/session history.
uv run python -m benchmarks.agent prepare --runtime hermes \
  --suite learning --case learning-transfer --seed-checkpoint CHECKPOINT

# Prior-work control: identical scientific archive, fresh Hermes memory/history.
uv run python -m benchmarks.agent prepare --runtime hermes \
  --suite learning --case learning-transfer --seed-workspace CHECKPOINT/workspace
```

Prepare trials sequentially when they copy the same seed workspace: backup takes the workspace writer lock. Once preparation is complete, independent trials may run concurrently. Trials within a suite do not share state automatically. Fresh processes receive the same measurements but different inherited agent state. The source case investigates PMP22 and prepares the full synthetic table; transfer asks about SOX10 and inappropriate promoter/donor inference. Review actual retrieval, applicability, artifact reuse, numerical correctness and limitations. A successful round trip establishes persistence and workflow operation, not superiority over the control or new biological insight. This minimal comparison bundles native history, notes and learned skills; it does not isolate consolidation from raw transcript retrieval. Repeat on unseen questions and add finer ablations before making causal learning claims. Never seed the research lineage from holdout results or review answers.

## Preparing sustained research

```sh
uv run python -m benchmarks.agent prepare --runtime hermes \
  --suite discovery-iteration --profile deep --seed-workspace PRIOR_RESEARCH_WORKSPACE
```

Time, request count, per-file bytes and new download bytes default to zero (unlimited). Hermes's iteration setting is explicitly zero (unlimited). Transport inactivity timeouts and free-disk reserves remain separate operational constraints. Preparation preserves the source workspace's disk reserve configuration; verify the target volume has adequate capacity before launch. Prepared configurations reject later overrides. Keep the pinned Hermes installation, available provider credentials and the prepared evaluator/source bytes unchanged before running. `--review` continues to use a separate stock Codex reviewer.

On a laptop, prevent idle sleep while launching (for example, `caffeinate -i` on macOS). An unlimited research budget does not disable upstream API inactivity watchdogs or survive a sleeping host. Keep the machine powered and awake; an upstream interruption is recorded as a failed run, with completed scientific work retained in its checkpoint. Each finished Hermes case also makes a full workspace backup. APFS backups use independent copy-on-write files where available, with ordinary-copy fallback; account for new and changed data and for full copies on other filesystems.

If the inherited percentage reserve is unsuitable for the target volume, `prepare --disk-reserve-gib 5` explicitly sets a fixed 5 GiB reserve in the copied workspace. It records the override and seals the prepared configuration without changing the original workspace or repository defaults. This reserve governs `bio` transport; arbitrary analysis scripts and the final full backup can still consume disk space.
