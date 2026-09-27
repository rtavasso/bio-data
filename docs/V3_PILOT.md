# V3 evaluation, 27 September 2026

V3 adds a research kickoff, optional semantic enrichment, recurring retrieval-gap reports, and separate retrieval/prior-recall evaluations. The preserved v2 workspace supplies a real local content index; newly collected public-source receipts supply a stronger runtime baseline. [Compact machine receipt](v3/receipts/evaluation.json) records run/report hashes, artifact IDs, question IDs, costs and limitations. Full datasets, run JSON, responses, and reports remain in ignored `workspaces/v3-evaluation/` and `workspaces/v2-pilot/`.

## Retrieval comparison

The same active agent used web search, native GEO metadata, Europe PMC, ChIP-Atlas, and ordinary Python file inspection, then added local deep-content queries. This is an **exploratory incremental comparison**, not independent blinded arms. The agent retained project/accession knowledge; the assisted arm starts with the runtime findings. Runtime-only discoveries are therefore zero by construction. It does not establish relative model performance, exhaustive recall, or a speedup.

| Question | Shared opportunities | Additional local candidates | Valuable unique local opportunities |
| --- | ---: | ---: | ---: |
| Egr2-AS expression response versus broad Schwann state change | 2 | 3 | 0 |
| Human Schwann-lineage PRC2/chromatin context at PMP22 | 2 | 0 | 0 |
| Human nerve PMP22 expression versus cell composition | 1 | 1 | 0 |
| Total | **5** | **4** | **0 established** |

The five shared **file-plus-analysis** opportunities are:

- [GSE201623](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE201623): `GSE201623_LentiAS.rnaseq.counts.txt.gz`, to examine Pmp22/Sox10 within the broader LentiAS/LentiGFP expression program. Runtime downloaded and directly inspected the 17,950-row table, confirming both labels. Source cells remain literal; replication and contrast eligibility require design review.
- [GSE201627](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE201627): the four processed LentiGFP/LentiAS narrowPeak files, to examine accessibility around source-native Pmp22 coordinates after assembly/reference review. These are not promoter-output measurements.
- [SRX24150189](https://chip-atlas.org/view?id=SRX24150189), also GSM8185872 in [GSE263109](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE263109): the hg38 H3K27ac BigWig from engineered NF1-proficient/SUZ12-deficient human Schwann cells. Candidate analysis is regional signal in that context, not healthy adult Schwann transfer. GEO and ChIP-Atlas representations are one information group; hg19/hg38 versions are not independent experiments.
- [GSE183305](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE183305): processed SUZ12-restoration ATAC tracks, starting with `GSM5555295_T265_tet_n_d5_rep1_R1.effectiveGenomeSize.bw`. Matched-condition comparison needs native assembly, induction, and normalization review. Malignant peripheral nerve sheath tumor context remains explicit.
- [GSE266026](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE266026): separate processed MTX/TSV files for seven human tibial-nerve samples, to investigate expression versus composition. Runtime fetched `GSM8239638_1-features.tsv.gz` and confirmed PMP22/SOX10 among 36,601 feature entries. The matrices and cell-state annotations were not analyzed, so usefulness remains unresolved. The source's trauma comparator must not become a healthy-control label.

Local Pmp22 lookup added the GSE139321 Tn5Prime table and a related PMC7430845 TSS/mark supplement. They give exact source locations for contextual investigation, but do not establish an additional analysis of Egr2-AS response. They share an information group and would not count as two independent opportunities. A `refGene.txt` annotation was a coordinate dependency rather than a measurement. A PMP22 match in `pbmc3k_raw.h5ad` was irrelevant tissue. Thus the assisted arm had **two false positives, two unresolved extra candidates, and no unreviewed candidates**. The runtime arm had no judged false positives among its five selected opportunities; one remained unresolved. These counts cover recorded candidates, not every web search hit.

The initial `Schwann` plus `bigwig` local filter returned zero; the actual stored format is `bw`, and an exact experiment lookup recovered tracks. This is a discoverability/context issue, not evidence that the experiment is absent. Raw local search results retain duplicate profile representations; the benchmark deduplicates opportunities before counting them.

Cost coverage is incomplete. Timed repository resolution and selected-file inspection comprised **9 operations / 36.23 seconds**; adding six local search operations brought the known subtotal to **15 / 36.49 seconds**. The assisted subtotal includes the runtime work it reused. Web search, agent review time, tokens, USD, indexing setup and storage costs were not metered; JSON marks these costs incomplete. These subtotals do not show end-to-end efficiency.

## Prior recall

The active agent sealed 32 model-only pairs before any database query; [the seal receipt](v3/receipts/prior-recall-seal.json) preserves the blob and timestamp. The node set was EGR2, SOX10, TEAD1, YAP1, PMP22 and STAT3. Two bounded SIGNOR/TRRUST-filtered OmniPath requests returned 134 rows, representing 132 source/target/human-namespace pairs. Full records, source identifiers, mixed signs, row locators and raw response receipts survive.

| Endpoint comparison | Pairs |
| --- | ---: |
| Model-only | 19 |
| Database-only | 119 |
| Shared | 13 |

Shared endpoints do not establish shared signs, directness, mechanisms or context. Database absence does not disprove a model hypothesis. Human identifiers do not establish that primary experiments were human. Resource-filtered OmniPath rows can retain annotations from additional resources; mixed effects were preserved rather than attributed uniformly to SIGNOR or TRRUST.

The citation audit covered all ten database-only pairs for EGR2/SOX10/PMP22 plus three selected YAP1/STAT3 pairs. **13/119 pairs were reviewed: 3 important, 4 useful but minor, 6 inappropriate or insufficiently supported for the proposed interpretation. The other 106 remain unreviewed.** Selection was explicit and not random; proportions must not be extrapolated. Judgments reflect this agent's bounded primary-abstract review, not expert consensus or exhaustive full-text curation.

| Pair | Assessment and source limitation |
| --- | --- |
| GSK3B → SOX10 | Important omitted protein-turnover candidate; [primary evidence](https://pubmed.ncbi.nlm.nih.gov/26461473/) is melanoma, with Schwann transfer unestablished. |
| ABL1 → YAP1 | Important alternative to a simple YAP/TEAD growth hypothesis: [DNA-damage/p73 context](https://pubmed.ncbi.nlm.nih.gov/18280240/). |
| PIAS3 → STAT3 | Important omitted inhibition of activated STAT3 DNA binding/transcription; [primary evidence](https://pubmed.ncbi.nlm.nih.gov/9388184/) does not establish target-tissue applicability. |
| WWP2 → EGR2 | Useful but minor candidate for protein turnover; [mouse T-cell context](https://pubmed.ncbi.nlm.nih.gov/19651900/). |
| GLI1 → EGR2 | Useful but minor repression candidate; [transformed-cell/medulloblastoma context](https://pubmed.ncbi.nlm.nih.gov/18924150/). |
| NMI → SOX10 | Useful but minor modulation candidate; [promoter-dependent reporter effects](https://pubmed.ncbi.nlm.nih.gov/16214168/) do not supply a universal sign. |
| PTPRD → STAT3 | Useful but minor [additional phosphatase route](https://pubmed.ncbi.nlm.nih.gov/19478061/); that mechanism class was already recalled through PTPN2. |
| SCD5 → EGR2 | Direction mismatch needing resolution: the [cited paper](https://pubmed.ncbi.nlm.nih.gov/22510410/) studies EGR2 regulation of bovine SCD5. |
| EWSR1 → EGR2 | [Fusion-associated Ewing sarcoma evidence](https://pubmed.ncbi.nlm.nih.gov/22327514/) cannot establish wild-type EWSR1 regulation in Schwann cells. |
| ITGA6 / ITGB4 → PMP22 | [Complex formation and PMP22-deficiency evidence](https://pubmed.ncbi.nlm.nih.gov/16436605/) do not establish directional integrin activation of PMP22 expression. |
| CNOT7 / CNOT8 → PMP22 | The supplied [miRNA/P-body citation abstract](https://pubmed.ncbi.nlm.nih.gov/15937477/) does not establish these specific edges. Support remains unresolved, not disproven. |

The two database requests took 3.72 seconds in total. Citation checking and agent review were not metered. The exact model identifier and token/cost telemetry were not exposed to this run. This demonstrates the value of runtime recall checks and citation inspection; it does not establish a benefit from a maintained local prior graph.

## Actual gaps and the format decision

Three question-local gap events form two groups: source/sample context slowed **two distinct questions**; linking human-nerve matrices to cell-state annotations blocked **one**. [Machine aggregation](v3/receipts/evaluation.json) records distinct questions separately from repeated observations. The reports identify failed routes and proposed follow-up rather than assigning scientific scores.

The immediate roadmap is to audit source-context propagation and format aliases, and locate/verify the cell annotations required by the nerve question. The successful separate MTX/TSV inventory means the large archive is not the only route. No evidence here justifies adding an RDS/Seurat execution path, a proteomic/imaging reader, an automatic raw-data pipeline, or expanded global crawling. Existing H5AD structural feature indexing stays available; richer metadata indexing needs a relevant measured object and a demonstrated question benefit first. This is the gap-driven decision required by v3, not a claim that all future format work is unnecessary.

## Reproduction and validation

With the preserved local run inputs:

```sh
uv run python -m scripts.v3_pilot --root workspaces/v3-evaluation
uv run python -m benchmarks.evaluate workspaces/v3-evaluation/retrieval/run.json \
  --output workspaces/v3-evaluation/retrieval/replayed-report.json
```

The first command recomputes comparisons, registers exact input/code/environment provenance, syncs question notebooks, and aggregates gaps. Replaying does not duplicate the same gap observations. It performs no network request, model invocation, or biological review. A fresh checkout includes protocols/evaluator/tests/compact receipts; it intentionally does not include downloaded datasets or the full local runs. Use the [retrieval protocol](../benchmarks/retrieval/README.md) and [bounded prior collector](../benchmarks/prior/README.md) for a new evaluation.

Offline tests cover fresh-session CLI discovery, missing optional semantics, retained v2 task receipts, real structural failures, gap grouping/coverage/history, candidate deduplication, incomplete comparisons, unknown costs, conflicting mechanism scopes, and immutable prior-response replay. Existing scientific tests remain acceptance criteria. Validation receipts are in `docs/v3/receipts/`; live response stores remain under ignored workspaces.

Validation passed **131 offline tests** (three live checks skipped by default), **3 opt-in live checks**, and Ruff. The base wheel also runs the offline content-search/artifact-reuse demo without scientific extras. Backup/restore checks cover both new receipt workspaces. A post-benchmark real-file check shows the extracted GSE201623 table completing with zero semantic profiles. The gzip wrapper retains its existing partial-inspection status because listing its member does not inspect the compressed stream; v3 does not erase that limitation. [The receipt](v3/receipts/optional-enrichment.json) preserves both scopes and the original overly broad completion expectation.
