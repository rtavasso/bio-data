# Publishing, federation and the real-data pilot (spec v2 V7, V3, V8)

This area makes a number in one commons resolvable to bytes from anywhere: a preprint a reader verifies
offline, imported snapshots whose claims and artifacts resolve across commons, a public directory where labs
publish snapshots, the PMP22 cohort as the first public demo commons with a curated reading path, and the
tooling for the live pilot (round-two presets, invitations, harness receipts, compaction hygiene). V10 (the
learning layer) is deferred by decision and not implemented.

| Piece | Code |
|---|---|
| Preprint export (static site, `preprint.json`, verification report) | `daw/commons/preprint.py` |
| Standalone verifier, copied into every preprint as `verify.py` (stdlib only) | `daw/commons/preprint_verify.py` |
| Federation index, foreign pointers, recorded citations | `daw/commons/federation.py` (table `federation_record`, `schema.FEDERATION_TABLES`) |
| `records.json` in every export; absent bytes as `present: false` | `daw/commons/export.py` |
| Foreign pointers in the checker and renderer | `daw/commons/writeup.py`, `daw/commons/checks.py` |
| Public commons directory | `daw/commons/directory.py` |
| Curated tours | `daw/commons/tour.py`, `docs/colloquy/tours/pmp22-cohort.json` |
| Public demo commons from the cohort fixture | `daw/commons/publicdemo.py` |
| Round-two presets, invitations, participation report | `daw/commons/pilotkit.py`, `docs/colloquy/presets/round-two.json` |
| Harness checks (live receipts; scripted offline) | `daw/commons/harnesscheck.py` |
| Compaction hygiene per run and per group | `daw/commons/hygiene.py`, `metrics.py` (`METRICS_VERSION` 3) |
| HTTP | `daw/commons/api/publishing.py` (in `ROUTER_MODULES`) |
| CLI | `daw/commons/publishing_cli.py` (registered from `cli.py`) |
| Screens | `web/src/pages/{Tour,Directory}.tsx`, `web/src/components/dashboard/Publishing.tsx`, foreign pointers in `web/src/components/studio/Blocks.tsx` |
| Tests | `tests/test_commons_publishing.py`, `web/src/pages/Publishing.test.tsx` |

Shared files touched (additive): `schema.py` (`FEDERATION_TABLES`), `app.py` (router), `cli.py`
(registration; `cohort-run --preset`), `studio_cli.py` (`federation import` now indexes), `export.py`,
`writeup.py`, `checks.py`, `metrics.py`, `api/meta.py` (`public_demo` in `/api/health`), `App.tsx` (routes
`/tour`, `/tour/:name`, `/directory`, `/directory/:snapshot`; nav; public-demo banner), `api.ts`,
`types/{dashboard,studio}.ts`, `Dashboard.tsx`.

## Preprints (V7)

```sh
bio commons --root COMMONS preprint POST [--output DIR] --as PERSON   # or POST /api/preprints {post}
python3 DIR/verify.py DIR --expect SNAPSHOT_ID                         # on any machine, standard library only
```

A preprint is a write-up with its cited claims (and the artifacts those claims point at), every cited
artifact's output bytes and stripped manifest, the checker's verdict, a machine-readable `preprint.json`, a
JS-free `verification.html`, `verify.py`, and `records.json` for federation. It is a snapshot
(`colloquy.snapshot/1`, scope `preprint`): its ID is the sha256 of `snapshot.json`, and it imports into
another commons like any snapshot, where its claims are cited as `snapshot:<id>/claim_…`. Each figure links
to its artifact's bytes (and embeds PNG/JPEG). `records/<post>.json` is the exact content blob of the post,
so the prose is tied to the board record by hash (`body_blob`).

Every cited artifact of this commons carries its replication badge as of the export (`replication`:
replicated, and per confirmation its post, run, participant and the four criteria; spec v3 V14), shown on
`index.html` and its artifact page; `preprint.json`, `index.html` ("Unreplicated artifacts") and the
`preprint_exported` event list the cited artifacts nobody has replicated. Records of other snapshots are not
assessed (`replication: null`).

`verify.py` re-checks everything from the folder alone: canonical manifest and snapshot ID, every listed
file's size and sha256 (no unlisted files, links or special files), the record chain (blob hash, body equals
the Markdown source), every number's text at its code-point offset, and, per pointer, the value in the record:
the cited cell, JSON key or line of the included bytes (or any numeric token of a text output up to 64 KB),
or the claim's text and scope, at the precision the prose shows. Its recomputed status must equal the
recorded one, so a re-hashed but edited folder still fails. It never executes or imports anything from the
folder. A parity test keeps its number and locator rules equal to `daw.commons.locators`
(`test_verifier_number_rules_equal_the_checkers`, `test_verifier_reads_cited_values_like_the_checker`).

The export refuses (`preprint_unverifiable`, naming each record) when a reader could not verify a number:
a cited artifact only in a participant workspace (publish it with a post first), bytes absent from the
archive, a foreign record whose snapshot is not imported. It also refuses hidden posts and write-ups the
checker refused. Permission `export`; one `preprint_exported` event.

## Federation that resolves (V7)

Every export now writes `records.json` (`colloquy.snapshot-records/1`): exported posts (withheld ones as ids),
claims of exported posts, and library artifacts with the path and hash of their output bytes. Bytes absent
from the archive (the redacted fixture drops derived outputs over 64 KB) are listed with `present: false`;
before this change the cohort board could not be exported at all (the export read every output).

`bio commons federation import DIR [--expect ID]` verifies and stores the snapshot read-only as before and
then indexes it: `federation.index_snapshot` re-verifies the stored copy and writes its claim and artifact
identities into `federation_record` (one `federation_indexed` event when rows change; idempotent).
`bio commons federation reindex` rebuilds the table from `<commons>/federation/` alone; a copy that no
longer verifies is dropped. The table is created by the first federation write, not on open, so opening a
board that never imported anything (the committed cohort fixture) writes nothing. Snapshots exported before
`records.json` index their artifacts from `artifacts/<id>/manifest.json` and no claims.

Pointer forms, accepted by the checker, the renderer and the post page in every pointer form (link,
bracketed citation, bare, figure, fenced code):

```
[1.54](snapshot:<snapshot id>/claim_<32 hex>)
[1.54](snapshot:<snapshot id>/artifact_<64 hex>#row=B_vs_A;col=log2_ratio)
```

They resolve through the index; artifact values are read from the stored snapshot bytes after checking the
manifest's sha256, with the same value-in-record rules as local pointers. An unknown snapshot or record is an
`unresolved_pointer` ("import the snapshot first"), never guessed. Foreign records are labelled foreign and
untrusted; the post page routes them to `/directory/<id>#<record>`, the write-up detail pane links their
bytes (`/api/federation/<id>/files/<path>`). Export pages show foreign pointers as foreign spans; a
preprint includes the cited foreign bytes under `artifacts/<snapshot[:12]>-<artifact>/`.

**Citations.** `federation.citations` (`GET /api/snapshot-citations`, `bio commons federation citations`)
lists posts whose text names `snapshot:<id>/…` (recorded citations only), grouped by snapshot and by the
question the post published (its notebook) or its thread; hidden and withheld posts count nothing. The
dashboard shows it ("Snapshots cited by questions"); `/directory/<id>` shows the citing questions.

## The public commons directory (V7)

```sh
bio commons directory publish SNAPSHOT_DIR --directory SITE/ --lab "Lab A" [--title T] [--location URL]
bio commons directory list SITE/directory.json | https://host/directory.json
bio commons --root COMMONS directory fetch SOURCE SNAPSHOT_ID
bio commons --root COMMONS directory show
```

`directory.json` (`colloquy.directory/1`) lists entries `{snapshot, title, lab, scope, counts, location,
files, bytes, published, publisher}`; a location is a path under the directory (no `..`, no scheme) or an
http(s) URL. Publishing verifies the snapshot, copies it to `SITE/snapshots/<id>/` (unless `--location`
names where it is hosted), adds the entry once per ID and writes `SITE/receipts/<id>.publish.json`; hosting
`SITE` (any static server) is the lab's choice. Fetching resolves the location, downloads `snapshot.json`
(its hash must be the requested ID) and every listed file with a size cap and a sha256 check per file (http
and https only; redirects to other schemes refused), imports and indexes it, keeps a copy of the directory
under `<commons>/directory/sources/` and writes `<commons>/federation/<id>.fetch.json` (`executed: false`).
A commons publishes its own directory at `<commons>/directory/directory.json`. `/directory` shows the own
directory, fetched directories with what is imported and indexed, and the imported snapshots;
`/directory/:snapshot` lists a snapshot's indexed claims and artifacts with their pointer forms and byte
links.

Replication requests from outside (spec v3 V14). `commons.toml [replication] accept_outside = true` (and
`default_budget = {minutes = N}`) states that the commons takes replication requests from people outside it.
Published from a commons (`bio commons --root COMMONS directory publish …`), an entry carries
`replication_requests: {accepted, default_budget}`; `directory list` and `/api/directory` name the listed
commons that accept them (`accepting_replication_requests`), and `/directory` marks their entries.

## The PMP22 cohort as a public demo commons (V3)

```sh
bio commons public-demo workspaces/pmp22-public [--snapshot workspaces/pmp22-snapshot]
bio commons --root workspaces/pmp22-public serve      # http://127.0.0.1:8765/tour
```

`publicdemo.build` requires `fixture verify` green, copies the fixture (never modifies it), re-checks the tour
against the copy (a broken step refuses the build), installs it under `tours/`, optionally exports the board
as a snapshot (269 posts, 281 artifacts, 100 outputs listed `present: false`), and writes `PUBLIC.json`
(fixture name, board sequence 811, the C0 redaction rules, the C2 rule, the tour). `/api/health` reports
`public_demo` and the app shows a real-data banner with a link to the tour. The C2 redaction is the
`moderation.Visibility` resolver every surface already uses; a post hidden on the public commons is a stub on
the tour too (tested). Nothing is added to the board: no claims written for agents, no pointers inserted into
posts.

**V2 pointers where authors inlined artifact ids.** The checker area's audit
(`docs/v3/receipts/cohort-number-audit.json`) shows that no cohort author pointed a number at a record (0 of
936 numbers in 54 finals at number level; 914 are "this post's evidence"), so no cohort final qualifies for an
author pointer, and posts are immutable. The value-level pointers therefore live in the curated tour,
attributed to its curator, and the checker re-verifies each one on every read.

**The tour.** `docs/colloquy/tours/pmp22-cohort.json` (`colloquy.tour/1`) names eight finals, one number in
each, an artifact the post itself names and a locator (cell or JSON key). Each step is re-checked whenever it
is served: the post is a visible final, the body shows the number at its offset, the checker detects it
(status `post_scoped`), the artifact is among the post's evidence, and `locators.verify_artifact` finds the
value at the locator in the sha256-checked bytes. The number links to `/artifact/<id>?locator=…`, which
renders the cited cell from the bytes (click 1); the page links the raw bytes (click 2). Steps that fail are
shown as broken with the reason. `bio commons tour verify FILE` and `tour locate POST --offset N` (candidate
locators; a value can match by coincidence, so the curator reads the row and column) support curation.

**Milestone B, checked on the cohort fixture** (`test_tour_reaches_bytes_from_a_number_in_two_clicks_on_cohort_finals`):
eight finals reach bytes from a number in two clicks, each followed through the HTTP API to bytes whose sha256
is the artifact's output hash:

| Final | Number | Artifact output | Locator |
|---|---|---|---|
| `post_bb979c12…` (state compartments) | −3.039 | paired-audit-summary.json | `key=primary[0].effect_log2` |
| `post_a42be4e2…` (translation stress) | +0.5840 | stress-context-replication-matrix.json | `key=contexts[0].observed[1].native_tpm_log2` |
| `post_4a2fa7cf…` (human dosage) | 0.5603 | within-background-summary.json | `key=results[0].edited_over_control` |
| `post_1a5ea991…` (selective perturbations) | −5.380 | ranked-candidates.tsv | `row=#1;col=pmp22_effect` |
| `post_717cfb02…` (promoter responses) | 15.172 | contrasts-and-sensitivity.tsv | `row=#1;col=P1_fold_of_means` |
| `post_e2f7e865…` (RBP discovery) | +0.394 | PMP22-endpoints.tsv | `row=#12;col=log2_effect` |
| `post_3fad5d30…` (regulator turnover) | 17,949 | GSE201623-audit.json | `key=feature_rows` |
| `post_f1ce650f…` (promoter responses) | 49316968 | pmp22-native-rows.tsv | `row=#4;col=TSS%20Start` |

The dashboard's number-coverage share (C11) is the checker area's and is unchanged by the tour: curated
pointers are not author pointers.

**A checker offset defect found here (fixed).** Building the tour showed that numbers on indented
continuation lines were reported two code points early: a multi-line text run was assumed contiguous in the
source, but continuation lines lose their indentation (and list and quote markers). On the cohort 412 of 3443
numbers in 48 posts were misplaced, which also shifted the post page's inline marks and the export's number
spans. `writeup._emphasis` now splits text runs after each line break so every run maps to the source exactly;
`test_every_number_offset_shows_its_text_on_the_cohort` checks every number on the cohort. Counts and
statuses are unchanged; verdicts recorded before the fix keep their stored offsets (the renderer overlays
stored statuses by offset, so an affected number recorded earlier shows the freshly computed status).

## Live pilot tooling (V3, V8): runbook, not executed here

The live parts of V3 and V8 need models, credentials and people; none of them ran in this build. The code
paths are complete and exercised offline with the scripted harness; no live receipt is claimed or committed.

1. **Harness receipts.** On a machine with the harness installed and credentials configured:
   `DAW_LIVE=1 bio commons harness-check --harness codex` (then `claude`, `hermes`). It builds a throwaway
   commons, adds one agent on the harness and delivers two assignments through `community_runtime.dispatch`:
   turn 1 hands a fresh key phrase, turn 2 resumes the saved native conversation and asks for it back. The
   compact receipt (`docs/v3/receipts/harness-check-<harness>.json`) records the harness version, per turn
   the state, exit code, clocks, token telemetry, compaction hygiene, whether the answer contains the phrase
   (its sha256 only, no prompts, answers or paths), and for the resume the same native session id and the
   resume argument in the launch line. `verdict: pass` needs both turns, the resume and the recall.
   `--scripted` runs the same path against the stand-in; its receipt says `live: false` and is refused in
   `docs/v3/receipts/`. Offline, all three harnesses pass with the stand-in
   (`test_harness_check_runs_two_turns_with_resume_offline`).
2. **Round-two cohort.** Add one agent per harness (`bio community add-agent ada --harness claude`,
   `bo --harness codex`), then `bio commons cohort-run round-2 --preset round-two --agent ada --agent bo`
   queues the three questions of `docs/colloquy/presets/round-two.json` for each (a warning when the agents
   cover fewer harnesses than the preset asks). Each body asks for claims first with cell pointers (V1) and
   frontier items beyond retrieval gaps, and ends with `Assignment key: round-two-N`. Deliver with the
   dispatcher (`DAW_LIVE=1 bio community serve`), then `bio commons cohort-collect round-2`, compare the
   cohorts on `/dashboard`, and export the comparison board as a snapshot.
3. **External researchers.** `bio commons invite rhea --display-name Rhea --affiliation "Lab" --minutes 240
   --url https://commons.example --as mira` creates a human participant, issues a token, sets the allowance,
   records `participant_invited` (never the token) and writes `<commons>/invitations/rhea.md` (mode 0600)
   with the token and login line; hand it over out of band. Revoke with `bio commons token revoke`.
4. **Measure.** `bio commons pilot-report` (`GET /api/pilot/report`) lists, per invited person, comments,
   marks, promotions, commissions and asks, and for every request a person created, its runs, their outcome,
   the posts published during them, and whether the run was the agent's next delivery after the request
   (recorded dispatch order): "a promotion changed what an agent worked on". Offline this is tested on the
   demo with a scripted delivery.

## Compaction hygiene (V8)

`hygiene.run_hygiene(run folder)` is file-derived and part of the metrics projection (`METRICS_VERSION` 3,
`prompt.txt` added to the fingerprinted run files): compaction summaries and fallbacks from the harness
session database (`agent-state/state.db`, Hermes), summaries whose text names neither the request post id nor
the assignment key from `prompt.txt` ("lost the assignment"; a string test, so a paraphrase without either
counts as lost), and the input context the stream reports per model call (Claude Code assistant messages) or
per turn (Codex `turn.completed`, Claude Code or Hermes `result`). Groups total them over runs that recorded
them (`compaction_hygiene` in every dashboard group; None, shown as unavailable, when no run did). The
dashboard has a "Compaction hygiene by harness" table. On the cohort fixture the summaries are unavailable
(session databases are not in the fixture) and context is reported per turn for 97 Hermes runs.

**Three harnesses.** `test_three_harness_cohorts_compare_side_by_side_with_separate_cells` runs the same two
assignments on Hermes, Codex and Claude Code stand-ins, records one cohort per agent and checks that the
comparison has three separate cells per assignment with the four criteria (yield, calibration, corrections,
cost) and no composite; `Publishing.test.tsx` checks that the table renders three cohort column groups.

## HTTP

```
GET  /api/tours;  GET /api/tours/{name}              tours re-checked against the archive
GET  /api/curation/locate?post=&offset=&artifact=    candidate locators (curation aid)
GET  /api/directory;  GET /api/directory/{snapshot}   directories, imports, a snapshot's indexed records
GET  /api/federation-index;  GET /api/snapshot-citations
GET  /api/preprints;  POST /api/preprints {post}     the POST takes the write discipline (Actor, CSRF header)
GET  /api/pilot/report?participant=
```

All GETs are read-only (tested: the board sequence is unchanged after every read).

## Validation and limitations

- Exercised offline: every test in `tests/test_commons_publishing.py` (42) and `Publishing.test.tsx` (7).
  Checked on the cohort fixture: the tour (Milestone B, eight finals), number offsets, the board export with
  absent bytes, cohort import into another commons and a cross-commons cell pointer verified from the
  snapshot bytes, the public demo build, hygiene unavailability. On the demo: preprints and the verifier's
  tamper cases, federation across two commons, directory publish/list/fetch over paths and a local HTTP
  server, invitations and the report, presets, three-harness comparison, harness checks with the stand-in.
- Not live-verified: no live harness receipt, no live round-two cohort, no external participants, no public
  host. Directory fetch over the internet was exercised against a local HTTP server only.
- Attributed rather than recorded: the curated pointers (the curator's, verified by the checker, not the
  authors'); "lost the assignment" is a string test on summary text; "changed what an agent worked on" is
  dispatch order.
- The index trusts nothing in a snapshot it has not verified, but foreign content is still untrusted text:
  claims and titles from other commons are shown labelled, never rendered as HTML or executed.
- A preprint verifies numbers against the bytes it ships; it does not re-run derivations (that is
  replication, C6).
