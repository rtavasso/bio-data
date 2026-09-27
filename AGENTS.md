# Research substrate invariants

- Read `BUILD_SPEC.md`, `v2_SPEC.md`, and all of `AGENT_START.md` before changing scientific behavior. The v2 framing supersedes the v1 primary analysis workflow.
- Keep `bio` focused on source facts, search, provenance, reusable artifacts, and question notebooks. Scientific applicability and analysis belong in ordinary question-local code and reasoning; no universal acceptance gate.
- Preserve the working v1 `daw` interface and history during additive migrations. Do not extend its typed planner or capability registry without a concrete need.
- Keep discovery, transport, inspection, interpretation, eligibility, and numerical extraction separate.
- No model, credentials, hosted service, or network is required for offline use or tests.
- Preserve source bytes, receipt history, and interpretation revisions. Machine results are JSON.
- Never invent an assembly, independent donor, measured feature universe, count semantics, or contrast direction.
- Selected-table omission is unresolved. Absent features differ from measured zeros. Gene-level measurements are not promoter measurements.
- Workers receive selected immutable files, never writable catalog connections. The parent owns writes.
- Never execute downloaded code, formulas, macros, or pickle/R serializations. No automatic raw processing.
- Scientific test outcomes are acceptance criteria. Fix code or document limitations; never weaken an expected result to hide failure.
- Check with `uv run ruff check src tests scripts` and `uv run pytest`. Install scientific extras for the complete suite.
- Live tests are opt-in with `DAW_LIVE=1`; preserve actual receipts.
- Data and reports belong in ignored workspaces. Do not commit downloaded datasets or credentials.
