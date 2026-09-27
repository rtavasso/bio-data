# Bio-Data Research Substrate: revised next-phase specification

## 1. Product definition

The platform is a **persistent scientific substrate for frontier coding agents** such as Claude Code or Codex.

The agent is responsible for scientific reasoning.

The platform is responsible for making the world's public scientific data, prior analysis, and provenance easy for the agent to discover, inspect, reuse, and process.

The intended architecture is:

```text
                         QUESTION
                            │
                            ▼
                   CLAUDE CODE / CODEX
                            │
                scientific reasoning layer
                            │
             ┌──────────────┼───────────────┐
             ▼              ▼               ▼
       model knowledge   runtime search   local substrate
                              │               │
                      papers / databases      │
                      structured resources   │
                                              ▼
                                   experiments / files
                                   prior analyses
                                   reusable artifacts
                                              │
                                              ▼
                                   question-specific work
```

The system should **not** attempt to encode biological reasoning into a universal graph, ontology, transfer engine, or scientific workflow.

The core principle is:

> **Precompute and preserve what data exists and what it physically contains. Let the frontier agent decide what it means for the current scientific question.**

---

# 2. What the existing `v2/research-substrate` branch already gets right

The current branch already implements most of the desired persistent substrate.

Keep:

- content-addressed immutable source storage;
- exact byte hashes;
- source/resource identity;
- source adapters;
- sample/file/resource relationships;
- progressive indexing;
- structural inspection;
- literal feature indexing inside files;
- dataset profiles;
- local FTS/vector search;
- question workspaces;
- `QUESTION.md`;
- `LABBOOK.md`;
- question event logs;
- reusable artifacts;
- derivation-keyed caching;
- prior-work search;
- provenance traversal;
- ordinary Python/R/shell analyses;
- offline reproducibility;
- explicit handling of unavailable/uninspected/unmeasured data.

The current v2 pilot already demonstrates two important properties:

1. Deep content indexing can expose entities such as `Pmp22` inside files whose titles and study metadata do not advertise them.
2. A derived representation prepared for one question can be safely reused by another when its derivation matches.

These should remain the foundation.

---

# 3. Do not build a local biological-mechanism graph yet

The previous proposed next step was to ingest OmniPath, SIGNOR, TRRUST, and similar databases into a local causal prior.

Do **not** make this a current requirement.

A frontier biological model already has a large amount of mechanistic biological knowledge in its parameters.

For example, given:

> What controls PMP22 transcription?

the agent can already propose likely relevant concepts such as:

```text
EGR2
SOX10
TEAD/YAP/TAZ
NRG1/ERBB
cAMP signaling
myelination state
chromatin regulation
promoter/enhancer mechanisms
```

It can also recursively reason about regulators of those regulators.

Therefore a local relationship graph only earns its complexity if it provides one of the following:

1. Important mechanistic relationships the model consistently fails to recall.
2. Strong provenance/completeness benefits that runtime retrieval cannot cheaply provide.
3. Repeated graph queries whose runtime cost becomes material.
4. Useful local joins between biological relationships and indexed experiments.

Until those are demonstrated, biological relationship databases should be **runtime tools**, not mirrored infrastructure.

---

# 4. Biological knowledge hierarchy

For mechanistic reasoning, use three layers.

```text
MODEL PARAMETRIC KNOWLEDGE
"What might matter?"
        │
        ▼
STRUCTURED EXTERNAL SOURCES
"What else is recorded, and where?"
        │
        ▼
PRIMARY PAPERS / EXPERIMENTAL DATA
"What was actually observed?"
```

## Layer 1 — model knowledge

Use the frontier model for:

- hypothesis generation;
- known pathway recall;
- regulators-of-regulators;
- likely cofactors;
- plausible mechanisms;
- competing biological explanations;
- deciding which mechanism branches deserve investigation.

This costs no platform engineering.

## Layer 2 — structured retrieval

When useful, query existing sources such as:

- OmniPath;
- SIGNOR;
- INDRA;
- TRRUST;
- Reactome;
- other biological databases.

Use them to:

- audit the model's candidate list;
- expand rare/long-tail relationships;
- obtain references;
- recover context and mechanism metadata.

These should initially be accessed live through ordinary APIs/web/tools.

## Layer 3 — primary evidence

Scientific conclusions ultimately depend on:

- primary literature;
- repository metadata;
- actual experimental files;
- direct reanalysis.

The local substrate is strongest at this layer.

---

# 5. The experimental-data substrate remains the unique core

The strongest justification for custom infrastructure is not biological relationship storage.

It is information that does **not exist in the model's weights or ordinary search results in a directly queryable form**.

Examples:

```text
Sheet 4 of supplement.xlsx contains PMP22.

An H5AD contains healthy myelinating Schwann cells.

A full gene matrix contains PMP22 although the paper never mentions it.

A genome-wide bigWig covers the human PMP22 regulatory domain.

A repository ZIP contains an auxiliary assay absent from the abstract.

A Hi-C matrix can answer a locus question the original study never asked.
```

This is where custom deep indexing has defensible value.

Continue prioritizing that.

---

# 6. Experimental indexing strategy

Maintain progressive indexing.

## Level 0 — resource metadata

Capture:

```text
publication
dataset
repository
accessions
identifiers
declared assay
declared species
relationships
```

## Level 1 — asset inventory

Capture:

```text
files
names
formats
sizes
checksums
raw vs processed
samples
repository relationships
```

## Level 2 — structural content

Inspect actual processed data where cheap enough.

Examples:

### Excel / CSV

```text
sheets
headers
dimensions
literal identifiers
table structure
```

### H5AD / HDF5

```text
shape
obs columns
var columns
layers
feature labels
```

### bigWig

```text
chromosomes
coordinate scope
reference metadata
```

### Cooler

```text
chromosomes
resolution
bins
weights
```

### archives

```text
member tree
nested formats
```

## Level 3 — optional descriptive enrichment

Agent-authored semantic descriptions remain useful but should be **opportunistic**, not required for indexing completion.

A background indexing job should not remain partial simply because no model-authored semantic profile exists.

Level 3 profiles can be created when:

- a dataset is investigated during a real research question;
- the semantics are unusually clear;
- a curated corpus is intentionally being enriched.

---

# 7. Experimental affordance profiles stay descriptive

Profiles should help an agent understand what a resource appears to contain.

Example:

```yaml
measurement:
  assay: RNA-seq
  scope: genome-wide

context:
  species: rat
  model: S16 Schwann cells

representations:
  - processed count table
  - raw sequencing

apparent_affordances:
  - gene-level expression lookup
  - differential-expression analysis with appropriate sample design

limitations:
  - immortalized model
  - replicate interpretation requires source metadata
```

Do not let this become:

```text
capability = scientifically approved
```

The agent decides applicability for its current question.

---

# 8. Do not build a universal transfer graph

Cross-species or cross-context transfer depends on the claim being made.

For example:

```text
mouse Egr2 involvement in Pmp22 regulation
```

may transfer reasonably well when asking:

> Is EGR2 probably involved in human PMP22 regulation?

The same evidence transfers far less strongly when asking:

> Does this exact mouse enhancer regulate human PMP22 promoter P1?

Therefore transfer should remain question-local.

Store reusable objective computations as ordinary artifacts:

```text
ortholog maps
synteny maps
liftOver results
sequence alignments
motif conservation
cell-state alignments
expression similarities
```

The agent decides whether those facts justify transfer for the current proposition.

Do not add:

```text
mouse_to_human_transfer_score
```

or a global transfer ontology.

---

# 9. The frontier agent should drive mechanism reconstruction

For a question such as:

> What is the full regulatory mechanism controlling PMP22 transcription in human myelinating Schwann cells?

the agent should roughly operate as follows.

```text
QUESTION
   │
   ▼
use model biological knowledge
   │
   ▼
generate candidate mechanism
   │
   ▼
audit/expand with runtime structured sources if useful
   │
   ▼
search local experimental substrate
   │
   ├── hidden relevant datasets
   ├── prior processed artifacts
   └── prior question work
   │
   ▼
runtime web/repository search for missing coverage
   │
   ▼
identify uncertain mechanism edges
   │
   ▼
ask what observations would discriminate alternatives
   │
   ▼
find datasets capable of making those observations
   │
   ▼
reuse compatible processing or perform new analysis
   │
   ▼
update mechanism
   │
   ▼
actively search for contradictions
   │
   ▼
repeat
```

This workflow belongs in the agent's reasoning, not in a platform state machine.

---

# 10. Use runtime biological databases as recall auditors

The agent should not query biological databases for every obvious relationship.

Instead use them selectively.

Example:

The model proposes:

```text
PMP22 <- EGR2
PMP22 <- SOX10
PMP22 <- TEAD/YAP
```

It then asks:

> What incoming regulators of EGR2, SOX10, or TEAD are recorded in structured resources that I did not consider?

That is a good use of OmniPath/SIGNOR/INDRA.

Structured databases become **recall expansion tools**.

The model remains the primary hypothesis generator.

---

# 11. Benchmark whether a local biological-prior cache is ever needed

Before building a local prior graph, run an empirical benchmark.

Choose biological entities across multiple mechanism types.

Examples:

```text
EGR2
SOX10
TEAD1
YAP1
PMP22
other TFs/signaling proteins
```

For each:

### Condition A

Ask the same frontier model to enumerate relevant direct and near-direct upstream regulators and mechanisms.

### Condition B

Query curated sources such as OmniPath/SIGNOR/TRRUST.

Compare:

```text
model-only relationships
database-only relationships
overlap
```

Then manually assess database-only edges.

The question is not:

> Does the database contain more edges?

It almost certainly will.

The question is:

> Does it repeatedly contain scientifically important mechanistic relationships the model missed?

If yes, local mirroring may be justified.

If no, keep runtime federation.

---

# 12. Apply the same test to the deep experimental index

Do not scale the experimental crawl simply because indexing machinery exists.

Compare:

### Runtime-only agent

```text
model
+ web
+ repository APIs
+ specialized indexes
```

against:

### Substrate-assisted agent

```text
same tools
+ local deep file/content index
```

Measure:

> Scientifically useful evidence opportunities found only because of the deep index.

The unit of success should be:

```text
dataset/file
+
specific analysis it enables
```

not:

```text
paper found
```

Example:

```text
GSE201627 ATAC
→ can test accessibility across the PMP22 domain
```

A unique result counts only if:

- it is relevant;
- it contains independent information;
- it can test an unresolved mechanism;
- a knowledgeable researcher would actually want to analyze it.

Use this benchmark to decide where global indexing should expand.

---

# 13. Retrieval-gap-driven indexing

Do not decide all future indexing formats in advance.

During real research, log cases such as:

```text
Relevant H5AD likely exists, but sample metadata is not globally searchable.

RDS object may contain Schwann cells, but its internal metadata cannot be queried.

Supplement contains full DE results, but web search only exposes the paper.

Public genomic tracks exist, but arbitrary-locus coverage isn't searchable.

Repository ZIP contains unknown nested assays.
```

Record them as question events:

```text
kind = retrieval_gap
```

Periodically aggregate these events.

The most frequent or high-value gaps determine what the custom index should support next.

This turns actual research failures into the indexing roadmap.

---

# 14. Prior question work remains first-class

Keep the current question workspace model:

```text
QUESTION.md
LABBOOK.md
scripts/
outputs/
events.jsonl
```

Future agents should retrieve:

```text
question summaries
LABBOOK entries
scripts
artifacts
provenance
```

not entire historical agent trajectories.

The full event log exists for:

- debugging;
- audit;
- recovery.

It should generally not be injected into future model context.

---

# 15. Keep derivation-based reuse exactly as implemented

This remains one of the strongest architectural decisions.

If Question A creates:

```text
donor-level pseudobulk matrix
```

Question B should reuse it when its derivation matches the new need.

If Question B instead needs promoter-level counts, it returns to the underlying data and reprocesses.

Question ID is provenance.

It is not artifact identity.

---

# 16. Simplify permanent agent instructions

The current `AGENTS.md` still asks agents to read large specification documents before modifying scientific behavior.

That should change.

Permanent instructions should be short.

Recommended content:

```text
# Bio-data research substrate

This repository supplies persistent scientific data and provenance
for Claude Code/Codex.

Scientific reasoning is question-local.

Use `bio --help` to discover platform operations.

For research questions:
- use your biological knowledge to form hypotheses,
- search local indexed data and prior work,
- use external structured databases/web search to audit and expand,
- analyze actual measurements when useful.

Original source bytes are immutable.

Reuse prior artifacts only when their derivation fits the current question.

Missing or unindexed data is not negative biological evidence.

Do not assume cross-species/context transfer.

Keep LABBOOK.md current.

Register reusable derived outputs with provenance.

Read detailed component docs only when modifying that component.
```

Do not require reading:

```text
BUILD_SPEC.md
v2_SPEC.md
AGENT_START.md
```

for ordinary research work.

Those remain engineering references.

---

# 17. Do not build a custom agent harness

Continue relying on Codex or Claude Code for:

- planning;
- long-horizon execution;
- context compaction;
- shell/code use;
- web/browser work;
- subagents;
- task decomposition.

Do not add:

```text
LangGraph
CrewAI
custom planner
custom scientific agent scheduler
```

unless a concrete harness limitation appears.

For complex questions, let the stock harness spawn focused subagents such as:

```text
direct mechanism literature
human datasets
rodent datasets
contradictory evidence
cross-species mapping
upstream pathways
```

Their results should return to the lead agent as compact summaries/artifacts.

---

# 18. What to build next

## Milestone 1 — simplify harness instructions

Update:

```text
AGENTS.md
AGENT_START.md
```

so a fresh coding-agent session can work from `bio --help` and targeted docs without preloading the large historical specs.

### Acceptance

A fresh session can:

1. enter the repo;
2. find the `bio` interface;
3. create a question;
4. search data/work/artifacts;
5. begin scientific work;

without reading the full build specifications.

---

## Milestone 2 — make semantic profile indexing optional

Modify background indexing so levels 0–2 determine job completeness.

Agent-authored level-3 profiles are enrichment only.

### Acceptance

A structural deep-index job can complete with:

```text
resources indexed
assets inventoried
supported files inspected
literal labels indexed
```

even when no semantic profile exists.

---

## Milestone 3 — add retrieval-gap workflow

Standardize a lightweight event format for:

```text
retrieval_gap
```

Fields may include:

```yaml
question:
desired_information:
source_or_format:
why_current_tools_failed:
likely_value:
possible_indexing_solution:
```

Do not over-schema it.

Add reporting/aggregation over these events.

### Acceptance

The system can answer:

> Which information-access failures have repeatedly blocked or slowed recent questions?

---

## Milestone 4 — build the experimental-index value benchmark

Create:

```text
benchmarks/retrieval/
```

Evaluate several difficult biological questions under:

```text
runtime-only
vs
runtime + local deep index
```

Score unique evidence opportunities for scientific usefulness.

### Acceptance

Produce:

```text
common discoveries
runtime-only discoveries
deep-index-only discoveries
scientifically valuable index-only discoveries
false-positive burden
agent/tool/time cost
```

Use this result before expanding global indexing.

---

## Milestone 5 — biological-prior recall benchmark

Do **not** build a local prior graph.

First compare model biological recall against curated structured resources.

### Acceptance

For a curated node set, report:

```text
model-only edges
database-only edges
shared edges

database-only edges judged:
- important
- useful but minor
- irrelevant/context-inappropriate
```

Only if the database contributes substantial important omissions should a local `bio prior` subsystem be considered.

---

## Milestone 6 — gap-driven format expansion

Use real question failures to decide whether to add richer indexing for:

```text
H5AD metadata
RDS/Seurat
supplement tables
genomic tracks
proteomic files
imaging objects
other scientific formats
```

No format is mandatory merely because it exists.

---

# 19. Explicitly do not build yet

Do not build:

```text
local biological relationship graph
global mechanistic truth graph
universal transfer graph
universal biology ontology
universal capability validator
scientific query DSL
global evidence scoring
automatic mechanism synthesis service
custom agent orchestrator
massive raw-data mirror
```

All remain possible future optimizations.

None has yet earned its implementation cost.

---

# 20. Final architecture

```text
┌─────────────────────────────────────────────────────────┐
│                 CLAUDE CODE / CODEX                     │
│                                                         │
│ biological knowledge                                    │
│ hypothesis generation                                   │
│ analysis design                                         │
│ transfer reasoning                                      │
│ scientific interpretation                               │
└───────────────┬───────────────────────┬─────────────────┘
                │                       │
                │                       │
                ▼                       ▼
       EXTERNAL KNOWLEDGE       LOCAL RESEARCH SUBSTRATE

       web / papers              experiments
       OmniPath                  files
       SIGNOR                    structural profiles
       INDRA                     hidden feature contents
       Reactome                  prior work
       etc.                      reusable artifacts
                │                       │
                └───────────┬───────────┘
                            ▼
                   ACTUAL DATA ANALYSIS
                            │
                            ▼
                      QUESTION RESULT
                            │
                            ▼
               REUSABLE RESEARCH MEMORY
```

The platform's strongest differentiated asset is:

> **persistent access to actual scientific measurements and previously completed processing that are not naturally accessible through model weights or ordinary paper search.**

The model's strongest differentiated asset is:

> **biological reasoning and hypothesis generation.**

Do not duplicate one with the other.

---

# 21. Governing design principles

1. **Use model knowledge before building knowledge infrastructure.**

2. **Use external biological databases to audit recall and provide provenance before mirroring them locally.**

3. **Invest custom indexing primarily where the underlying scientific contents are otherwise difficult to discover.**

4. **Benchmark every expensive indexing idea against a strong runtime agent.**

5. **Let retrieval failures determine future indexing scope.**

6. **Preserve source bytes and derivations so data can be reinterpreted for new questions.**

7. **Store prior work as searchable scientific artifacts and notebooks, not as giant model transcripts.**

8. **Keep question-specific scientific interpretation with the frontier agent.**

9. **Avoid formalizing abstractions until repeated real research demonstrates that they improve results.**

10. **The substrate should make the agent more capable, not tell the agent how to think.**
