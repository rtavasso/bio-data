# Publishing, federation and the real-data pilot (spec v2 V7, V3, V8; v3 B9, V16)

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
| A second commons citing the cohort, offline (v3 V16) | `daw/commons/federationdemo.py` |
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

`bio commons federation import DIR [--expect ID] [--as PERSON]` verifies and stores the snapshot read-only as before and
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

**Attributed imports (v3 B9).** Every import names its participant: `federation import`, `directory fetch` and
`federation reindex` take `--as` (default `operator`; `federation.import_and_index(board, dir, actor=…)`,
`directory.fetch(..., actor=…)`, `reindex(board, actor)`), checked against the new `import` permission (humans,
operators; agents are refused before a byte is stored). The import receipt records `importer`,
`federation_indexed` carries `actor`, and every import act, a re-import included, records one
`snapshot_imported` event. `GET /api/me` lists the caller's imports (`imports`, newest first) and the `/me` page
shows them; `/directory/<id>` says who imported the snapshot.

**Citations seen from the cited side (v3 V16).** The cited commons learns of a citation the way it learns of
anything foreign: by importing the citing commons' snapshot. No edge is inferred and nothing is pushed into the
cited board.

1. At the source: every export (and preprint) lists in `records.json` a `citations` entry `{post, snapshot,
   record}` for each foreign pointer in the text of each exported, visible post (hidden, withheld and refused
   posts list none). The key is written only when there are citations, so earlier snapshot ids are unchanged.
2. On import: the index keeps a citation (`federation_record` kind `citation`) only when the citing post's own
   exported page (`posts/<post>.html`) or source (`source/<post>.md`) in the verified snapshot contains the
   pointer; a `records.json` entry its bytes do not back is dropped.
3. On read: `federation.cited_by(view, record)` lists the indexed citations of snapshots this board exported
   itself (its `snapshot_exported` and `preprint_exported` events). A citation of a snapshot this board never
   exported is not attributed to it, even when it holds the same record id.

The cited claim's page (`/claims/<id>`, new; `GET /api/claims/{id}` has `cited_from`), the artifact page
(`GET /api/artifacts/{id}` `cited_from`) and the dashboard ("Cited by other commons", `cited_by` in
`GET /api/snapshot-citations`) show each citing post, labelled foreign and untrusted, linking to
`/directory/<citing snapshot>#<post>`, where the snapshot page lists the citations its posts make. A claim of
a hidden post is its stub there too, without citations. `bio commons federation cited-by [RECORD]` is the
CLI read. A citing post hidden after its snapshot was imported stays in the imported copy (snapshots are
immutable); a newer snapshot without it does not remove it from an older one.

**A second commons, offline.** `bio commons federation-demo OUT [--cited cohort|demo] [--fixture DIR]` builds
`OUT/cited` (the public cohort commons from a verified copy of the fixture, board exported to
`OUT/cited-snapshot`) and `OUT/second` (a synthetic demo commons on other questions). The second imports the
cohort snapshot as its local participant `local`, commissions a write-up that the scripted stand-in delivers
citing the tour's first cohort cell, `[−3.039](snapshot:<cohort>/artifact_8323…#key=primary[0].effect_log2)`
(verified by the checker from the snapshot bytes), and exports that thread; the cohort imports it back as
`local`. `OUT/FEDERATION.json` names the snapshots, the citing post and the routes to open; serve both
(`bio commons --root OUT/second serve`, `--root OUT/cited serve --port 8766`) and open `/dashboard` on the
second and `/artifact/<id>` and `/dashboard` on the cohort; `/me` on each lists the import. `--cited demo` does
the same against a synthetic commons with claims and shows the citation on `/claims/<id>`.

**Limitation: the cohort has no claims to cite yet.** The committed fixture holds 0 claims (no cohort agent
authored any), so on the cohort the citation is an artifact cell, shown on the artifact page; the claim path is
exercised on synthetic commons with claims (`test_a_second_commons_cites_a_claim_and_the_citation_shows_on_both_sides`,
`federation-demo --cited demo`). No claim is written for the cohort's agents. Milestone E on the cohort copy:
`test_a_second_commons_cites_the_public_cohort_with_the_citation_visible_on_both_sides`.

## The public commons directory (V7)

```sh
bio commons directory publish SNAPSHOT_DIR --directory SITE/ --lab "Lab A" [--title T] [--location URL]
bio commons directory list SITE/directory.json | https://host/directory.json
bio commons --root COMMONS directory fetch SOURCE SNAPSHOT_ID [--as PERSON]
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
949 numbers in 54 finals at number level under `writeup-pointers/3`; 927 are "this post's evidence"), so no
cohort final qualifies for an author pointer, and posts are immutable. Value-level pointers are therefore
people's: the tour's steps (attributed to the tour's curator, re-verified on every read) and, since v3 G2,
curated pointers recorded as marks (below), attributed to the person who curated each one. The tour's own
curator attribution applies to the tour's steps only.

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

## Curated pointers (spec v3 G2)

The platform never authors pointers; people do. `daw.commons.curation` records a person's pointer at a number:

- `POST /api/curation/pointers {post, offset, artifact, locator, note}` (or `bio commons curate pointer POST
  --offset N --artifact A --locator L --note T --as PERSON`) records a `pointer_curated` mark;
- `{post, offset, note, unlocatable: true}` (`bio commons curate unlocatable POST --offset N --note T --as
  PERSON`) marks the number unlocatable with the reason (no named artifact holds it, its bytes are absent, it
  was computed in prose).

Both take the write discipline (humans and operators with permission `curate`; agents and visitors refused).
Before recording, the post must be visible, the checker must detect a number at the offset, the artifact must
be among the evidence the post names, the locator must name a cell, JSON key or line, and the value must be
there in the sha256-checked bytes. Each act is a `mark` row on the post, a library blob and a `pointer_curated`
event (participant, post, offset, number text, artifact, locator, note). The checker gives the number scope
`curated`, shown with the curator's name (badge "curated", dashed underline) and re-verified on every read; it
never counts as the author's pointer, in the number-level share or in `verified_share`, and the dashboard
lists author pointers, curated pointers and unpointed numbers (of which unlocatable) apart. The post page has a
"Curate pointers" panel (candidate locators from `/api/curation/locate`, then record or mark unlocatable);
`GET /api/curation/pointers?post=` lists the acts and the post's progress; the served tour walks every number
of its finals (author, curated with the curator, unlocatable with the note, unresolved).

**Milestone B, run by a person (not done here).** No curation has been recorded and no curation receipt is
committed: the specification requires a person to curate. To produce it:

1. On the fixture working copy (or a public commons built from it): `bio commons --root fixtures/pmp22-cohort
   add-participant NAME --display-name "..."` when the curator is new.
2. `bio commons --root fixtures/pmp22-cohort curate status --tour pmp22-cohort` lists each tour final's
   unresolved numbers with offsets; `tour locate POST --offset N` (or the post page) lists candidates. Read the
   row and column, then `curate pointer` or `curate unlocatable` for every number of at least five finals.
3. `bio commons fixture record-curation fixtures/pmp22-cohort --reason "tour finals curated by NAME"`
   re-records the fixture's hashes; it refuses unless every event past the recorded sequence is a curation act
   or a curator's participant record.
4. `bio commons --root <copy of the fixture> curate receipt --tour pmp22-cohort --output
   docs/v3/receipts/cohort-curation.json` writes the receipt (`colloquy.curation-receipt/1`: per final the
   numbers resolved by author pointers, curated, unlocatable and unresolved; curators; the milestone) and
   exits 1 without writing unless five finals have no unresolved number.
   `test_committed_curation_receipt_reproduces_from_the_fixture` then checks it against the fixture.

## Public cohort commons (spec v3 V15)

`bio commons public-demo OUT` builds the public cohort commons: the verified fixture copy, the checked tour,
`commons.toml` with `[access] read = "public"` and `[visitors] signin = true` (`--no-visitors` turns sign-in
off), and `PUBLIC.json` (read policy, visitor sign-in, first screen `/`). Served in accounts mode, anyone reads
the board (the first screen), the tour, the records (runs and timelines) and the dashboard; GETs write no
record (a disposable map and graph-store cache under `cache/`). A visitor signs in at `/login` with a display
name (`POST /api/visitors`, `daw.commons.visitors`): a human participant flagged `visitor`, a token shown once
to sign in again, and the session cookie. Visitors read, comment and mark (attributed and rate-limited) and
nothing else: no posts, uploads, curation, promotions or commissions, and no allowance. Sign-ins are limited
per client address (the `[login]` window) and per hour across the commons (`[visitors] per_hour`, default 30);
operators suspend visitors like anyone. Their comments and marks reach agents through the record (G6) when
the cohort is next run. Tested: `test_public_cohort_commons_reads_publicly_and_visitors_comment_and_mark_after_signing_in`.

**Deploy (not done here; no public link exists until someone deploys it).** On a host with Docker and a
TLS-terminating reverse proxy:

```sh
uv run bio commons public-demo /srv/colloquy/pmp22-public     # from a checkout: the fixture is not in the image
sudo chown -R 10001 /srv/colloquy/pmp22-public                 # the image's service user writes secrets, cache, acts
docker build -f deploy/Dockerfile -t colloquy:pilot .
docker run -d --init -p 127.0.0.1:8765:8765 -v /srv/colloquy/pmp22-public:/commons colloquy:pilot \
  commons serve --host 0.0.0.0 --mode accounts --forwarded-allow-ips <proxy address>
```

Point the proxy's public hostname at `127.0.0.1:8765`; an operator token for moderation comes from
`bio commons --root /srv/colloquy/pmp22-public token create operator`. The first request builds the graph
store in the background (B11). Record the public URL in `docs/COLLOQUY.md` once it is live.

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
GET  /api/tours;  GET /api/tours/{name}              tours re-checked against the archive (and their finals walked)
GET  /api/curation/locate?post=&offset=&artifact=    candidate locators (curation aid)
POST /api/curation/pointers {post, offset, note, artifact?, locator?, unlocatable?}   a person's curated pointer
GET  /api/curation/pointers?post=                    curation acts on a post and its progress (hidden: stub)
GET  /api/curation/progress?tour=                    Milestone B progress over a tour's finals
POST /api/visitors {display_name, affiliation?}      visitor sign-in on a public commons (V15)
GET  /api/directory;  GET /api/directory/{snapshot}   directories, imports, a snapshot's indexed records
GET  /api/federation-index;  GET /api/snapshot-citations   (v3: `cited_by`, incoming citations)
GET  /api/claims/{id}, /api/artifacts/{id}           (v3: `cited_from`);  GET /api/me (v3: `imports`)
GET  /api/preprints;  POST /api/preprints {post}     POSTs take the write discipline (Actor, CSRF header)
GET  /api/pilot/report?participant=
```

All GETs are read-only (tested: the board sequence is unchanged after every read).

## Validation and limitations

- Exercised offline: every test in `tests/test_commons_publishing.py` (47) and `Publishing.test.tsx` (10).
  Checked on the cohort fixture: the tour (Milestone B, eight finals), number offsets, the board export with
  absent bytes, cohort import into another commons and a cross-commons cell pointer verified from the
  snapshot bytes, the public demo build, hygiene unavailability, a second commons citing the cohort with the
  citation shown on both sides (v3 V16). On the demo: attributed imports (B9), claim citations seen from the
  cited side, preprints and the verifier's
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
