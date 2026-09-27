---
name: bio-artifact-reuse
description: "Find, assess, register, and reuse bio-data analysis artifacts with exact derivation provenance across research questions. Use when earlier processing or an intermediate representation may satisfy a new analysis."
---

# Bio Artifact Reuse

Search `bio artifact search --text "..."` and relevant prior work, then read `bio artifact show ARTIFACT_ID`. The manifest and `bio provenance ARTIFACT_ID` explain what produced the bytes. Similar titles are not a cache match.

Check source identity and immutable input hashes, selectors, code, parameters, references, output role and environment. A representation can be reused for a new question when its actual derivation fits; the question ID is provenance, not a derivation-key component. Check biological applicability separately: an intact artifact does not establish suitable tissue, donor independence, assembly or contrast semantics.

If requesting the exact same computation, use `bio artifact find --derivation DERIVATION.json`; a changed derivation requires different processing, and ambiguous output variants require inspection. To attach a fitting existing representation, use `bio artifact use ARTIFACT_ID --question QUESTION_ID --name FILE`. This records reuse and makes an editable copy. Do not modify its immutable source blob or falsely claim that a changed transformation was reused.

For a new output, save the actual script under the question, run it, then use `bio register OUTPUT --question QUESTION_ID --input ASSET_OR_ARTIFACT_ID --code SCRIPT --title "..." --parameters '{"actual_parameter":"value"}'`. Repeat input/code flags as needed. Use a full manifest for selectors, references, or an explicitly pinned environment (`bio register --help`, `contracts/artifactregistration.schema.json`). The registration API records provenance; it does not execute or validate arbitrary analysis code for you.

Both `--input` and `--code` are required when registering through flags. An input is an asset ID, artifact ID, or stored blob SHA256; for a local context/reference file, first run `bio object add PATH` and pass the returned blob hash. Include every file dependency in the derivation. Narrative interpretations can stay in `LABBOOK.md` and be preserved by `work sync`; do not invent a script provenance or call agent-authored prose human-authored. Record the chosen artifact or reason reuse failed, and sync useful partial findings before additional optional work. State source-cell semantics and unresolved assumptions in outputs. Use `bio` from the supplied environment, or `uv run bio` in a development checkout. See `examples/V2.md` for an end-to-end example when needed.
