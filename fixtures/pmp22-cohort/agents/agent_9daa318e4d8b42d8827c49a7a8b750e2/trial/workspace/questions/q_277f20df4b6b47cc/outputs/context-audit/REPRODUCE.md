Question: q_277f20df4b6b47cc. Run from this isolated checkout, using supplied wrappers. No install, raw sequencing processing, author code, macros or R/pickle deserialization.

1. `./bin/python workspace/questions/q_277f20df4b6b47cc/scripts/analyze_footprint_context.py`
2. `./bin/python workspace/questions/q_277f20df4b6b47cc/scripts/analyze_footprint_followup.py`
3. `./bin/python workspace/questions/q_277f20df4b6b47cc/scripts/analyze_ridd_source.py`
4. `./bin/python workspace/questions/q_277f20df4b6b47cc/scripts/analyze_context_classes.py`
5. `./bin/python workspace/questions/q_277f20df4b6b47cc/scripts/analyze_footprint_counts.py`
6. `./bin/python workspace/questions/q_277f20df4b6b47cc/scripts/plot_context_summary.py`

The scripts resolve immutable source blobs inside this checkout by hash. Steps 3–6 depend on earlier outputs or preserved source objects. All six ran separately with exit status 0; logs and stderr are in this output directory. Arrow sysctl warnings are environment messages. Plotting can pause during font initialization.

`registrations.json` contains 26 registered computations with distinct output roles, source/input identities and exact code hashes. `input-objects.json` records source metadata objects. Downstream class/count/plot derivations reference their actual registered upstream artifacts. Scripts contain all numerical selectors; the five decision notes preserve the order of choices and exposure.

Primary data are the native deposited RSEM gene TPM and expected-count tables, not reprocessed sequencing. The original count/TPM matrices each have 22,406 exact gene labels. Primary scope is WT 2-hour versus own untreated control in each model. Late 8-vs-7-hour comparisons are secondary. Source Table S5's 25 date-like labels are excluded from exact cluster mapping, without gene renaming. No per-gene quantification-status flags are provided in these matrices; a TPM abundance cutoff is an analysis criterion, not a source quality flag.

The RIDD Table I analysis reads verified primary XML, preserving all 26 selected candidate rows and source stability categories. `ND` remains untested. The obsolete source localization text is retained rather than silently corrected. No qPCR bar heights are treated as replicate measurements.

The registration helper's first attempt registered the first 15 products successfully but expected the wrong JSON receipt key for downstream artifact IDs. Its failed log and initial helper text remain. The corrected helper reads `artifact`, skips previously registered products and finishes all 26; scientific outputs were unchanged.

Reports/maps/queue/novelty notes are agent-authored interpretations, preserved with `bio object add`; they are not falsely registered as computations. Current ledger repair preserves the old panel seal and every inherited rejected member. The old ledger and intake checker failure are under this directory.

Rerunning analyses rewrites only this continuation's computation outputs. To experiment with changed parameters, use new script/output revisions and register new derivations. Do not rewrite historical prediction files or numbered snapshots.
