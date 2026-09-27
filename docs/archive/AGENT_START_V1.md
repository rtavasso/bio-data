# Start here: build the Data Archaeology Workbench

You are implementing a private, local, single-user research tool in a new repository. You have internet access and are expected to inspect current package documentation and source when needed. The user is technically capable; avoid teaching them basic coding or proposing infrastructure in place of working capabilities.

## Mission

Recover public experiments and their actual measurements, including supplementary tables and auxiliary assays that the publication did not emphasize. Make those measurements queryable with accurate context, provenance and an explicit ledger of unexamined resources. PMP22 regulation in Schwann cells is the first scientific use case, **not an inclusion filter requiring every paper or filename to mention PMP22**.

The supplied package is a researched specification, **not an implemented application**. Commands, adapter contracts and tests describe what you must build. Synthetic examples are not validated biological inputs. No real-data integration receipts are included.

## Read in this order

1. `BUILD_SPEC.md`, sections 1–7: product boundaries, architecture, identity and operating contract.
2. Sections 18–20: acceptance and vertical-slice delivery order.
3. `DEPENDENCIES.json`: activation decisions, not an install-all list.
4. `ADAPTER_CONTRACTS.json` plus section 8 for the sources used in the current slice.
5. The relevant format/capability/query contracts in sections 9–16, and matching cases in `ACCEPTANCE_TESTS.json`.

`SOURCES.json` contains primary documentation and explicit review status. Resolve uncertainties using those documents and the exact version you install; the review date is not a promise that a remote API still behaves identically.

## Binding architecture

One Python CLI/package (`daw`), one local SQLite metadata/identity/run catalog, immutable content-addressed files, versioned interpretation JSON, native scientific data formats, and Parquet for useful tables. DuckDB is an optional in-process analytical engine, **not another authoritative catalog**. One parent process owns catalog writes.

No required server, cloud store, agent SDK, graph database, vector database, distributed scheduler or custom LLM harness. Do not adopt LaminDB and a custom catalog simultaneously. Do not install all scientific readers into the base environment. Use isolated environments for optional tools and heavyweight R/workflow dependencies.

Keep these boundaries separate: **source enumeration → acquisition → structural inspection → scientific interpretation → capability validation → typed numerical query**. Do not combine all six in a publisher-specific script.

## Scientific invariants you must not “simplify”

**Five identities differ:** a paper, a biological experiment, a remote asset, its exact bytes, and an interpretation revision. Identical bytes can belong to distinct contexts; different representations can derive from one experiment. Neither hashes nor accessions alone solve experimental independence.

**Unknown is legitimate output.** Distinguish unavailable, uninspected, unsupported, filtered-out, not measured, and measured without detection. A significant-only table cannot establish a null effect for an absent gene. A sparse zero is not necessarily evidence that a feature was measured.

**Names do not establish semantics.** AnnData `.raw` is not a guarantee of counts. PEP CSV rows are not automatically biological samples. `chr` prefixes do not identify an assembly. A “human” sample label does not certify the reference used to generate its coordinates. A total gene count does not prove promoter-specific output.

**Preserve disagreement.** Store source assertions and evidence locators before accepting normalized interpretations. A later assertion cannot silently overwrite a contradiction. An agent's proposal cannot accept itself by setting a JSON boolean.

**A successful parse is not a scientific capability.** Each enabled operator needs a validated, question-specific capability. Do not auto-approve pooling across cell states, species, donors, assays or independently normalized tracks because the files share a format.

**Promoter/domain caution matters.** Keep PMP22 P1/P2 and species-specific reference definitions explicit. Do not substitute an arbitrary fixed-width window for an established regulatory domain or transfer rodent regulatory claims to humans by coordinate relabeling.

## First implementation sequence

Implement the minimal integrity layer in slice 0, then immediately complete the supplementary-table vertical slice. Do not spend the initial effort generalizing a plugin framework.

For slice 1, acquire a lawful public supplement through supported routes, enumerate its internal sheets/regions, preserve the original bytes, curate a precise region with source-backed semantics, query a feature, and produce a report with the coverage ledger. Recover something absent from the abstract. Demonstrate that a selected-only table cannot support a negative conclusion. Re-run without duplication.

Only then add GEO/PEP, processed genomic tracks, matrices and the other source adapters as required by a real query. Use the supplied public accessions as **unverified discovery seeds**, not canned outputs. Keep an independently chosen study or query withheld from recipe development.

## Agent jobs and escalation

Use bounded study-curation jobs with explicit resource budgets. Produce a manifest of assets, source-backed mappings, proposed recipes, capabilities and unresolved issues—not merely a narrative.

Prefer deterministic software for enumeration, checksums, parsing and numerical work. Use your reasoning for messy interpretation and exceptional recipes. Never execute downloaded author code automatically. Escalate an ambiguous design decision or an out-of-budget acquisition with the evidence and a proposed bounded action; do not repeatedly ask for information that the sources or current configuration already resolve.

Record failed acquisition routes, truncated enumeration, resource-limit outcomes and unsupported formats. A blocked asset must remain visible to queries that it might eventually answer.

## Acceptance and reporting

Implement the relevant offline adversarial tests before relying on an adapter. Live tests are separately gated. Do not alter expected scientific outcomes merely to make an import pass. JSON Schema validation is structural only; add the semantic runtime checks described in `contracts/README.md`.

Every supported adapter needs a live receipt: exact tool/version or endpoint, UTC retrieval time, source snapshot, enumeration coverage, fetched/blocked objects, hashes where applicable, and the actual validation outcome. Do not advertise an adapter as supported because its wrapper imports.

Deliver working commands, locked environments, reproducible pilot outputs, source/interpretation lineage, a coverage report, a backup/restore test and a truthful list of unsupported capabilities. Separate tests that passed, failed and were not run.

**Optimize for one new trustworthy cross-study answer, not the size of the platform.**