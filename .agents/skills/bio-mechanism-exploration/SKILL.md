---
name: bio-mechanism-exploration
description: "Explore broad biological mechanisms and regulatory systems by recursively investigating upstream controls, competing explanations, and overlooked data uses. Use with bio-research for mechanism discovery or blind-spot audits; simple value lookups do not need this workflow."
---

# Bio Mechanism Exploration

Success means finding consequential blind spots and measurements that distinguish explanations. More genes, graph nodes, citations or downloads do not demonstrate better exploration.

Define the endpoint and biological scope: RNA abundance, promoter output, protein abundance and activity can require different explanations. State provisional assumptions when species, cell state or context is unspecified; preserve alternatives. A request for the “full” system calls for an explicit frontier of unresolved questions, not a claim of completeness.

Before substantial collection, save an initial hypothesis network. Label recalled biological knowledge unverified. Follow important regulators upstream: what controls their abundance, activity, localization, partners or persistence? Look for feedback, shared causes and context-dependent effects. Explore across plausible branches before repeatedly deepening the familiar one. These questions are exploration prompts, not a fixed ontology or gene checklist.

Audit consequential connections using primary sources and appropriate structured resources. Expression associations, binding, perturbation results and indirect causal hypotheses are distinct. Each connection needs its own context and support; a path does not establish causation or authorize cross-species transfer. Retain contested and rejected hypotheses.

Record whether each claim comes from inspected source text/data or only a search excerpt. Reserve `supported` for claims whose relevant evidence you inspected; keep excerpt-only mechanisms provisional. Preserve the source passage or data with a precise locator when possible, and record retrieval failures separately from biological uncertainty.

For each important branch, identify an observation that would distinguish alternatives. Search by upstream mechanism, assay, perturbation and material as well as target name. Connect a located file to a specific analysis and its prerequisites; inspect suitable processed measurements within budget. Also ask what additional hypotheses an existing dataset could test. Revisit available files when a new mechanism suggests another use. Separate proposed analyses from work actually performed.

For sustained or continued investigations, read [the investigation queue conventions](references/investigations.md). Turn priority uncertainties into executable work with candidate files, prerequisites and stopping criteria. A citation, download, or saved plan leaves an available analysis unfinished. Continue through consequential feasible items until the scoped investigation is covered or the budget ends; preserve evidence for blockers and explicit reasons for deferrals. Do not quietly lower a difficult branch's priority to claim completion.

Explore measurements beyond the expected regulator panel when the assay and design permit: inspect sample quality and broad response patterns, identify unexpected changes, and compare suitable independent experiments. Let those observations add or reprioritize mechanisms. Establish units, feature universe, sample mapping and replication before statistical inference; deeper analysis may correctly expose a design limit instead of producing a p-value.

After the first collection pass, audit what current data cannot distinguish. Investigate a consequential neglected alternative or contradiction, then revise the network, coverage and priorities. Record what changed and why; if evidence does not justify a change, explain retention. Give uncertain but consequential branches attention even when their data are hard to find. Stop within budget or when further work has low expected value; retain prioritized unresolved branches and concrete next steps.

Save a revised map and its reason before starting the next collection or analysis it motivates. An intermediate revision written at the end is retrospective documentation, not evidence of a checkpoint during exploration; label it accordingly.

Read [the artifact conventions](references/artifacts.md) when saving outputs. Keep `mechanisms.initial.json`, current `mechanisms.json`, and `evidence-coverage.tsv`; preserve intermediate revisions without overwriting earlier ones. These are agent-authored question-local research artifacts, not platform biological truth. Preserve authored files with `bio object add` and record hashes in the notebook; `work sync` alone does not snapshot arbitrary output files. Register computed outputs with their actual input/code provenance. Sync useful partial work before spending remaining time on optional exploration.

Report supported mechanisms, a consequential upstream discovery and the data/analyses it opened, what evidence cannot distinguish, and the remaining frontier. Do not manufacture a discovery if the investigation did not establish one.

Before handoff, run the [status checker](scripts/check_statuses.py) on the question directory using the supplied Python. Map-frontier statuses differ from queue statuses; retain scientific nuance in the reason/limitation fields. The check covers syntax, vocabulary and coverage columns, not biological validity or provenance completeness.
