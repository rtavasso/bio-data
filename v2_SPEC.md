Yes. The revised version is **not a repudiation of the first spec**; it changes where intelligence lives.

The old spec tried to make the platform itself understand scientific usability through fairly explicit contracts. The new version says:

> **Build a rich, persistent research-data substrate and let Claude Code/Codex do most question-specific scientific reasoning at runtime.**

The platform should deeply index what exists and preserve/reuse prior work, but it should avoid prematurely encoding one canonical ontology, transfer model, or analysis workflow.

## Revised product definition

The new north star is:

> **A local research-data substrate for frontier coding agents that continuously discovers, inventories, acquires, inspects, processes, and indexes public scientific data, so an agent answering a new biological question can find data based on what it actually contains—not merely what the associated paper says—and can reuse prior downloads, processing, and research work when appropriate.**

There are two distinct operating modes.

```text
                  GLOBAL / CONTINUOUS
                DATA ARCHAEOLOGY INDEX
                          │
       discover → inventory → inspect → profile
                          │
                          ▼
                persistent research store
                          │
                          │
             ─────────────────────────
                          │
                   QUESTION TIME
                          │
                          ▼
                    Claude/Codex
                          │
              search existing substrate
                          │
           ┌──────────────┴───────────────┐
           ▼                              ▼
     reuse prior work              discover new data
           │                              │
           └──────────────┬───────────────┘
                          ▼
              question-specific processing
                          │
                          ▼
               connections / analysis
                          │
                          ▼
                    user result
                          │
                          ▼
              enrich persistent substrate
```

The important loop is that **every research question makes the data substrate better for future questions**.

---

# What survives from the old spec

Quite a lot.

These were good decisions and should remain.

### Immutable source data

Keep exact acquired bytes content-addressed:

```text
objects/
  sha256/
    ab/
      abc123...
```

This is essential because a later question may want to process the same source differently.

### Source/resource identity

Keep distinctions between:

- publication;
- repository record;
- biological experiment;
- sample;
- remote file;
- exact bytes.

The previous spec was correct that these cannot safely collapse into one concept.

### Provenance

Derived output must know:

```text
inputs
processing/code
parameters
reference data
environment
output
```

This is what makes old processing reusable.

### Native scientific formats

Keep:

```text
BAM as BAM
bigWig as bigWig
H5AD as H5AD
Cooler as Cooler
OME-TIFF as OME-TIFF
```

and use Parquet primarily for derived tabular data.

Do not force the world into one universal matrix.

### Source adapters + format inspection

The existing distinction remains valuable:

```text
source discovery/acquisition
            ≠
file inspection
            ≠
scientific analysis
```

A GEO adapter shouldn't decide whether an experiment is biologically comparable to another experiment.

### Scientific safety invariants

A lot of the old adversarial tests remain excellent:

- a significant-only table cannot establish a null result;
- `.raw` does not necessarily mean raw counts;
- sample rows are not necessarily biological replicates;
- a genome build cannot be guessed;
- missing and zero are different;
- reused datasets aren't independent confirmation;
- downloaded author code is untrusted.

Those are not unnecessary bureaucracy. They protect the substrate.

---

# The major change: remove scientific reasoning from the platform core

The old design says:

```text
source
→ acquisition
→ inspection
→ curation
→ capability validation
→ typed query
→ result package
```

The revised design is closer to:

```text
source
→ acquisition
→ inspection
→ searchable profile
→ persistent artifact

                    ↓

              frontier agent

                    ↓

question-specific interpretation
question-specific processing
question-specific comparability
question-specific analysis
```

The core application should know **facts about data and previous work**, not try to universally determine what scientific inference is valid.

---

# Diff against the previous spec

The most important changes are these.

| Previous spec | Revised view | Why |
|---|---|---|
| Bounded agent jobs such as discover/curate/query | Use stock Claude Code/Codex harness | Frontier harnesses already plan, use subagents, manage context and work over long horizons |
| Large curation packet passed to agent | Minimal initial context + searchable workspace | Strong models perform better with just-in-time context retrieval |
| Formal `capability` objects central to querying | Lightweight data-affordance profile | Don't encode all future scientific uses in advance |
| Accepted `curation_revision` as a major semantic object | Stable source facts + reusable derived artifacts + question-local interpretation | There may be multiple legitimate interpretations of one dataset |
| Typed scientific query compiled by the platform | Agent writes/executes appropriate SQL/Python/R/tools | Avoid rebuilding a scientific programming language |
| Typed operators as default analytical interface | Existing scientific tools + scripts first | Agent already knows how to code analyses |
| Large formal `request.json / plan.json / validation.json` pipeline | Question workspace + ordinary code + artifact provenance | Preserve reproducibility without overspecifying reasoning |
| Progressive discovery per question | Huge background discovery/indexing pass + runtime search | Reduce repeated work and expose hidden reusable datasets |
| Avoid embeddings initially | Semantic search over compact dataset/work summaries is probably worthwhile | Now the catalog may become genuinely large |
| Explicit capability-filtered retrieval | Search by assay/context/feature universe/affordance | Provides most of the same value with less rigid ontology |
| Question-specific capability status stored centrally | Agent determines scientific applicability using indexed facts | Applicability often depends on the question |
| Cross-species handling as explicit recipes/contracts | Cache objective mappings; make inference question-time | Transfer validity depends heavily on the proposition being tested |
| Static HTML report as initial UX | Agent conversation + files/results; report is optional output | The coding-agent harness is already the UI |

---

# The biggest philosophical difference

The old system asks:

> **Can I formally certify what this dataset can answer?**

The new system asks:

> **Can I tell an intelligent agent enough about what this dataset contains that it can determine whether and how to use it?**

That's much less work for the platform.

And probably more robust as models improve.

---

# Replace `capability` with `affordance`

I wouldn't completely discard the old idea.

I'd just weaken it.

Old:

```yaml
capability:
  expression.gene:
    status: ready
    prerequisites:
      ...
    validator:
      ...
```

New:

```yaml
profile:
  measurement:
    assay: RNA-seq
    scope: genome-wide

  features:
    kind: genes
    universe: approximately_all_detected

  contexts:
    species: rat
    model: S16

  available_representations:
    - count_matrix
    - raw_reads

  apparent_affordances:
    - gene expression
    - differential expression given appropriate design
```

The first tries to make the platform judge scientific fitness.

The second gives the **agent enough information to judge fitness**.

That's a major simplification.

---

# The large indexing run becomes a first-class product

This is one of the biggest changes from the old spec.

The old spec explicitly said:

> no attempt to mirror all GEO or publication supplements before delivering useful queries.

That was reasonable for an MVP.

But the larger product should intentionally perform **large-scale indexing**.

Not massive universal raw-data downloading.

Think of progressive depth.

## Index level 0: research graph

Bulk import things like:

```text
papers
DOIs
PMIDs
PMCIDs

dataset DOIs
GEO accessions
SRA/ENA/BioProject

publication ↔ dataset
dataset ↔ repository
paper ↔ supplement
paper ↔ software
```

Reuse bulk sources rather than crawl everything yourself.

---

## Level 1: repository manifests

For datasets:

```text
files
formats
sizes
checksums
samples
assays
raw vs processed
```

This can often happen without downloading large files.

---

## Level 2: structural profiling

Cheaply inspect useful processed assets.

For an H5AD:

```text
shape
obs fields
var IDs
layers
```

For XLSX:

```text
sheets
dimensions
headers
table regions
```

For bigWig:

```text
chromosomes
coordinate coverage
```

For Cooler:

```text
assembly
resolution
chromosomes
```

For ZIP:

```text
member tree
```

---

## Level 3: semantic profile

An agent can periodically create a small searchable summary:

> Genome-wide RNA-seq and ATAC-seq from rat S16 Schwann cells under EGR2-AS perturbation, with processed gene counts and accessibility tracks; useful for arbitrary gene-expression or locus-accessibility queries in this model.

This is where you expose **latent reuse potential**.

Crucially, that description isn't:

> “This study is about EGR2-AS.”

It's:

> “Here is what you could measure from the data.”

---

# This is what makes indexing better than runtime search

Normal runtime literature search might retrieve:

```text
Paper:
"Role of EGR2-AS in Schwann cell differentiation"
```

The deep index knows:

```text
associated data:

RNA-seq
  genome-wide
  12 samples

ATAC-seq
  genome-wide

Hi-C
  genome-wide
  10 kb resolution
```

Then a completely different question about PMP22 can retrieve that dataset because the system knows:

```text
PMP22 expression?
→ genome-wide RNA assay can measure it

PMP22 accessibility?
→ genome-wide ATAC assay can measure it

PMP22 contacts?
→ genome-wide Hi-C may measure it
```

That's the principal justification for the global index.

---

# What the global index should not do

Do not precompute:

```text
canonical differential expression
canonical normalization
canonical cell grouping
canonical cross-species transfer
canonical mechanism
canonical interpretation
```

unless there is a widely reusable standardized representation such as recount3.

Those depend too much on the eventual question.

Instead index:

```text
what exists
what is inside it
what was measured
what its experimental context is
what representations already exist
```

---

# Revised persistent storage

I would simplify the catalog substantially.

Something like:

```text
catalog.sqlite

resource
identifier
relationship
remote_asset
local_object
dataset_profile
artifact
question
question_artifact
```

Potentially:

```text
work_event
```

though JSONL may be enough.

The old spec's:

```text
assertion
curation_revision
capability
asset_revision
snapshot
```

can likely be collapsed.

You still need source snapshots and provenance, but they don't necessarily deserve elaborate first-class domain models.

---

# Data store

I'd use:

```text
workspace/

  catalog.sqlite

  objects/
    sha256/<hash>

  questions/
    q_00001/
      QUESTION.md
      LABBOOK.md
      scripts/
      outputs/
      events.jsonl

  profiles/
    ...

  cache/
```

Files remain immutable in `objects`.

Question outputs can link/reference them.

---

# Prior question work is now part of the indexed corpus

This is another meaningful change.

A completed question produces three categories of useful state.

## 1. Full trajectory

```text
events.jsonl
```

Useful for:

- auditing;
- debugging;
- recovering why something happened.

Usually **not loaded into model context**.

---

## 2. Research notebook

```text
LABBOOK.md
```

Contains:

```text
what was investigated
datasets that mattered
important findings
failed routes
assumptions
limitations
open questions
```

This is good model memory.

---

## 3. Reusable artifacts

Such as:

```text
processed count matrix
orthology mapping
promoter coordinates
sample mapping
lifted genomic regions
DE results
figures
```

These get globally indexed.

A future question can find them independently of the original conversation.

---

# Cache based on derivation, not question

Old and new specs agree here, but I'd emphasize it more.

An artifact should conceptually be:

```text
output =
f(
   source bytes,
   selected subset,
   code,
   parameters,
   references,
   environment
)
```

Question ID is provenance, **not cache identity**.

So:

```text
Question A
→ produces pseudobulk matrix X

Question B
→ needs same pseudobulk representation
→ reuses X
```

But:

```text
Question C
→ needs promoter-level data
→ starts again from underlying source
```

---

# The agent context becomes dramatically smaller

Instead of the previous `AGENT_START.md` telling the agent about dozens of specific scientific invariants and workflows, I'd make the permanent project instructions perhaps one page.

Something like:

```text
Mission:
Use public scientific data to answer open-ended biological
questions, including data generated for unrelated purposes.

Use `bio` tools to search, acquire, inspect and find prior work.

Original source bytes are immutable.

Reuse prior artifacts when their derivation is appropriate;
otherwise reprocess the source.

Don't equate missing/uninspected data with negative evidence.

Keep the current question's LABBOOK.md updated.

Use normal scientific software, Python/R and browser/computer
use when helpful.
```

Everything else should be discoverable through:

```text
bio --help
docs/
search
files
```

---

# Revised role of the `bio` CLI

The old CLI was roughly:

```text
discover
bundle inventory
bundle inspect
curate packet
curate validate
curate accept
run
query
report
```

I'd simplify toward:

```text
bio search
bio resolve
bio fetch
bio inspect

bio data search
bio artifact search

bio work search
bio work show

bio provenance

bio index run
bio index status
```

And perhaps:

```text
bio register
```

for things agents create.

The agent doesn't need:

```text
bio curate accept
```

before it is allowed to use data.

The filesystem + provenance system already gives us a safer mechanism.

---

# Source adapters stay

Adapters are still very valuable because they eliminate repetitive internet work.

Keep:

```text
Europe PMC
GEO
ENA
BioStudies
Zenodo
Figshare
ENCODE
ChIP-Atlas
CELLxGENE
...
```

But their job becomes narrower:

```text
discover
resolve
enumerate
download
```

They shouldn't attempt to make scientific judgments.

And use browser/computer use for the long tail:

```text
unknown site
     ↓
agent explores
     ↓
discovers data/download
     ↓
registers result
```

If the same site is encountered repeatedly, convert that successful workflow into an adapter.

---

# Transfer handling changes significantly

Previous direction:

```text
persistent TransferGraph
typed transfer edges
question-specific TransferAssessment
```

New direction:

Don't build that yet.

Instead expose/cachе the **objective computations** that help an agent reason about transfer:

```text
ortholog table
sequence alignment
synteny mapping
liftOver
cell-type alignment
motif conservation
expression similarity
```

These become artifacts.

The agent decides:

> Is this amount of correspondence sufficient for this question?

That reasoning lives in the `LABBOOK` and answer.

If later we find ourselves repeatedly encoding identical transfer concepts, then formalize them.

---

# What I'd explicitly delete/defer from v1

I would mark these parts of `BUILD_SPEC.md` as superseded for the new branch:

### Defer

- universal capability validator;
- capability status state machine;
- formal typed scientific query planner;
- canonical result package;
- agent proposal/acceptance curation workflow;
- global accepted interpretation/current-pointer model;
- extensive `request.json` and `plan.json` requirements;
- fixed operator registry as the primary way to do analysis;
- requirement that all analyses flow through predefined platform operators;
- formal transfer graph;
- global evidence/claim graph;
- static HTML as primary product UI.

They can re-emerge if real usage earns them.

---

# What I'd keep almost verbatim

From the previous spec:

### Keep

- content-addressed local storage;
- exact-byte hashing;
- input/output provenance;
- source adapters;
- recursive supplement and archive inspection;
- local SQLite catalog;
- native-format readers;
- question-independent structural inspections;
- separation of raw source from derived files;
- unsafe-file/code handling;
- reproducibility of derived artifacts;
- distinction among unavailable / unexamined / unmeasured / not detected;
- careful handling of sample independence and duplicate experiments;
- progressive downloads rather than downloading all raw sequencing;
- reuse of compendia such as recount3;
- adversarial format and metadata fixtures.

The demo you've already built is therefore probably **not wasted work** if it implemented these lower-level pieces.

---

# New branch architecture

I'd think of it as four layers.

```text
┌────────────────────────────────────────────────────────┐
│                  CLAUDE CODE / CODEX                   │
│ reasoning • coding • browser • computer use • agents  │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                     BIO TOOLING                        │
│ search • resolve • fetch • inspect • prior-work search│
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                 RESEARCH SUBSTRATE                     │
│                                                        │
│ broad research graph                                   │
│ repository/file manifests                              │
│ structural profiles                                    │
│ semantic data-affordance profiles                      │
│ reusable derived artifacts                             │
│ prior question summaries                               │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                    OBJECT STORE                        │
│ original bytes • native data • Parquet • scripts      │
└────────────────────────────────────────────────────────┘
```

---

# Suggested migration strategy for your new branch

I wouldn't rewrite the demo from scratch.

### Phase 1 — preserve substrate

Keep working pieces for:

```text
SQLite
object store
hashing
downloads
source registration
adapters
inspection
provenance
```

Delete nothing yet.

---

### Phase 2 — stop extending the old semantic layer

Don't spend further development time expanding:

```text
curation contracts
capability state machine
typed query planner
```

unless required for something concrete.

---

### Phase 3 — build the global indexer

Make the biggest new capability:

```text
bio index
```

with progressive depth:

```text
metadata
→ resource relationships
→ file manifests
→ structural inspection
→ semantic affordance profiles
```

This is likely the highest-leverage change.

---

### Phase 4 — introduce question workspaces

```text
questions/q_x/

QUESTION.md
LABBOOK.md
scripts/
outputs/
events.jsonl
```

Have Claude/Codex work normally inside them.

---

### Phase 5 — index internal work

Add:

```text
bio work search
bio artifact search
```

so question N can discover work done for question N−1.

---

### Phase 6 — test the core hypothesis

Take a set of biological questions and compare:

```text
web/runtime search alone
```

versus:

```text
deep local index + web fallback
```

The critical success metric:

> **Does the indexed version discover useful datasets whose original publication did not advertise relevance to the question?**

That's the reason this platform should exist.

---

## Revised one-sentence design principle

The previous spec was:

> **Build the smallest trustworthy bridge between public resources and queryable scientific measurements.**

I'd update it to:

> **Build a persistent, deeply indexed substrate of public scientific data and prior research work that gives frontier agents enough information to recognize, retrieve, reuse, and reprocess relevant data for arbitrary biological questions—including uses the original authors never considered.**

And one constraint underneath it:

> **Precompute what the data contains; defer what the data means for a particular scientific question.**

That is the core diff I'd use to guide the new branch.