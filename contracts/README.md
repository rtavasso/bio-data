# Runtime contracts

The v2 primary interface uses small provenance/storage models in `src/daw/substrate_models.py`: `Profile`, `Derivation`, `ArtifactRegistration`, `IndexPlan`, `GraphRecord`, and `Embedding`. Exported schemas are beside this file. Profiles are attributed descriptive notes, artifacts carry exact derivation inputs, and index plans bound acquisition work. There is no required scientific acceptance workflow. See [V2.md](../docs/V2.md) and [ordinary question workflows](../examples/V2.md).

The remaining sections describe the retained v1 `daw` interface and its scientific safety checks.

The original handoff referenced JSON contracts that were absent from the repository. These implementation contracts are derived from the [original specification](../docs/specs/BUILD_SPEC.md), not recovered copies of the missing originals. `ADAPTER_CONTRACTS.json` and the generated `ACCEPTANCE_TESTS.json` now live here; dependency/source reference indexes live in `docs/reference/` from the repository root.

`src/daw/models.py` defines strict public contracts. `scripts/export_contracts.py` exports JSON Schemas here. Unknown request fields are rejected; unknown **provider** fields survive in raw snapshots.

Runtime acceptance additionally verifies:

1. Original blobs exist and match their SHA-256.
2. Evidence locators resolve to the exact `raw_value`: JSON Pointer, `text:exact excerpt`, `lines:N-M`, or `sheet:NAME!A1`/rectangular range.
3. Selected assertions belong to the asset and match proposed values. Scientific settings require source assertions.
4. Conflicts remain blocked until a separate named operator review considers every current assertion. A proposal cannot approve itself with a Boolean. Review is an audit action; a single-user CLI cannot authenticate human authorship.
5. Table regions and columns are valid. Source row/column positions are one-based. Literal identifiers and uncached formulas are preserved.
6. References include assembly, species, contigs, annotation identity/hash, namespaces, aliases, and evidence. Aliasing is not liftover.
7. Each operator checks additional prerequisites: contrast direction/selection, native references, signal units/missingness, matrix layer/cell map/feature presence, count-generating semantics and biological grouping, or contact resolution/weights.

Run keys include byte identities, selectors, accepted interpretation digests, references, parameters, budgets, source-code identity, Python/platform, installed versions, and the lock hash when present. Attempt IDs and timestamps are excluded. Corrections change the key; retries retain separate receipts.

Every query freezes its candidate set before extraction. Unacquired assets, uncurated workbook sheets, and blocked numerical operations remain in the coverage ledger.
