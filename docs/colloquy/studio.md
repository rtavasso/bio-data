# Studio: write-ups, reviews, replications, digests, export and federation

Spec modules M6.1 (writing tasks and the renderer), M6.2 (reviews), M6.3
(replications), M6.4 (digests), M6.5 (publishing outward), M8.4 (export and
read-only import) and Flow B step 5 (regeneration flags). Screens `/studio` and
`/studio/:post`. Studio work starts only from a person's commission (or
promotion); nothing here chooses scientific work.

| Piece | Code |
|---|---|
| Pointer syntax, number check, renderer, regeneration flags | `daw/commons/writeup.py` |
| Reviews as marks, replication follow-up, digests, `/studio` overview, post-delivery hook | `daw/commons/studio.py` |
| Static export, snapshot manifest, federation import | `daw/commons/export.py` |
| HTTP | `daw/commons/api/studio.py` (in `ROUTER_MODULES`) |
| CLI | `daw/commons/studio_cli.py`: `bio commons export`, `federation`, `replication`, `review`, `digest`, `writeup`, `demo-studio` |
| Demo records | `daw/commons/studio_demo.py` (opt-in, below) |
| Screens | `web/src/pages/{Studio,Writeup}.tsx`, `web/src/components/studio/`, `web/src/types/studio.ts` |
| Tests | `tests/test_commons_studio.py`, `web/src/pages/{Studio,Writeup}.test.tsx` |

Shared files touched (additive): `schema.py` (table `digest_schedule`),
`permissions.py` (`review` for humans, operators and agents; `export` for
humans), `tasks.py` (writing and digest prompt text), `community_runtime.py`
(post-delivery hook), `app.py`, `cli.py`, `App.tsx`, `CommissionForm`
(`defaultTaskType`, `defaultNote` props) and the `bio-community` skill.

## Pointer syntax (M6.1)

A write-up is an ordinary post, usually the answer to a `writing` commission.
Writers cite records with

- a Markdown link whose target is a record identifier: `[1.54](claim_…)`,
  `[the contrast table](artifact_…)`, `[the correction](post_…)`;
- a bracketed citation in or right after the sentence it supports:
  `… = 1.54 [claim_…].` or `… = 1.54. [claim_…]` (several: `[claim_…; artifact_…]`);
- a figure: `![caption](artifact_…)`.

A bare identifier in prose is tolerated as a citation. Claims and artifacts
support results; posts are context only. The same text is in the writing task
prompt (`tasks.INSTRUCTIONS["writing"]`) and in `.agents/skills/bio-community/SKILL.md`.

## The renderer

`GET /api/studio/writeups/{post}` (`writeup.render_writeup`) parses the post's
Markdown and either serves HTML-safe blocks or refuses with **HTTP 422**
(`{"error": "writeup_refused", "problems": [...], "source": ...}`), every problem
carrying `kind`, `offset`/`length` (code points into the stored body), `line`,
the source `context` and a `reason`:

| Kind | When |
|---|---|
| `unpointed_number` | a number neither inside a claim/artifact pointer link nor in a unit that cites a claim or artifact (`reason` says when only post pointers were present) |
| `unresolved_pointer` | a claim not in the ledger, an artifact catalogued in neither the library nor any workspace, a missing post, or a malformed `claim_`/`artifact_`/`post_` identifier |
| `pointer_kind_not_allowed` | another identifier kind (question, run, request…) used as a pointer |
| `figure_not_artifact` | an image whose target is not an artifact |
| `post_hidden` | the post is hidden by moderation |

**Numeric tokens** (`writeup.NUMBER`): optionally signed integers and decimals
(thousands separators allowed), scientific notation (`1e-5`, `3.2×10^-4`),
percentages, ratios (`3:1`, `1/3`). **Not numbers:** digits inside identifiers
(a token preceded by a letter, digit, underscore or `.`, or by a hyphen that
follows a letter: `PMP22`, `log2`, `GSE1234`, `v1.2`, `IL-6`), record identifiers,
hashes and URLs; ordered-list ordinals; heading numbering (`## 2.1 Methods`);
dates and times in a byline (a paragraph among the first two blocks starting
with By / Written by / Prepared by / Author(s): / Date: / Updated:). A digit
followed by letters still counts (`5mg`, `2nd`); a date outside a byline counts;
code spans in prose count.

**Units checked:** sentences of paragraphs, list items and quotes; each heading;
each table row (a number in any cell needs a claim or artifact pointer in the
row); each fenced code block (needs a claim or artifact identifier in the
block); a figure's caption is covered by its artifact. Sentences end at `.`, `!`
or `?` followed by whitespace and a character that is not lowercase, except
after common abbreviations (e.g., i.e., et al., Fig., vs., approx.). Bracketed
citations that open the next sentence attach to the previous one.

**Markdown subset:** ATX headings, paragraphs, `-`/`*`/`+` and `1.`/`1)` lists
(continuation lines indented), `>` quotes, fenced code, GFM pipe tables,
thematic breaks, inline code, `**strong**`, `*em*` (underscore emphasis is left
literal so identifiers survive), links and images. Raw HTML is text. Only http(s)
and mailto links leave the commons; other link targets render as plain text.

**Served write-up:** `blocks` (sentences with tokens, pointers and every number
with what covers it), `pointers` (each cited record resolved: a claim with its
status, text, post, marks and its own pointers with routes and `bytes_url`; an
artifact with location, role, derivation key, sha256, `bytes_url`
(`/api/artifacts/{id}/bytes`) and, for PNG/JPEG outputs, an `image_url` served
through `/api/blobs` with magic-byte checks; a post with title), `stats` and
`evidence_map`: the observatory's map builder restricted to the write-up, its
cited records, cited claims' posts and pointers, and the recorded derivation
closure upstream of every artifact. Prose citations are listed as pointers, not
drawn as edges (no inferred edges). Sentence → pointer → artifact → bytes is at
most three clicks; the detail pane links the bytes directly.

## Regeneration flags (Flow B step 5)

If any cited claim has `withdrawn_by` set (or status `withdrawn`), the response
carries `regeneration_required`: each withdrawn claim, its replacement post and
title, that post's current claims and the claim at the same ordinal (labelled
"same position", never matched by meaning), plus a prefilled `commission`
(`writing`, subject the write-up, a note naming the withdrawn claims). The flag
is computed from the ledger at read time, so the renderer cannot serve a
write-up citing a withdrawn claim without it. `/studio` lists every flagged
output; `/studio/:post` shows a band with the replacements and a `CommissionForm`
prefilled from the flag.

## Reviews as marks (M6.2)

The runtime's review deliverable (`tasks.review_block`, or a JSON artifact with
output role `review`) or a person's review form is turned into `mark` rows on
the review's target (post, claim or artifact; else the request's subject),
authored by the reviewer (agent or person). Mapping: `supported`, `pass`,
`checked` → `checked_source`; `reproduced` → `reproduced`;
`partially_supported`, `not_supported`, `fail`, `concern` → `disputed`;
`not_assessable` and unpointed verdicts record no mark (listed in `skipped`).
The note is `Review criterion C: verdict. note`; pointers are kept (strings
become `{kind, id}` by prefix, `ID#locator` becomes a locator pointer, a sha256
a receipt, an accession form an accession; unparseable strings are dropped and
reported). Mark ids are `mark_` + sha256(review post, criterion), so
`studio.record_review_marks` is idempotent; each new mark records a
`mark_recorded` event with `source {review, criterion, verdict}`. Marks never
change a status.

People submit reviews with `POST /api/studio/reviews {target_kind, target_id,
verdicts: [{criterion, verdict, note, pointers: [{kind, id, locator?}]}],
summary}` (permission `review`, rate-limited like posts and marks): a reply post
of kind `review` carrying the structured verdicts and a fenced `review` block,
then the same mark recording. A verdict other than `not_assessable` needs a
pointer (`review_pointer_required`).

## Replications (M6.3)

Replications are commissioned by a person (or promoted); the replicating agent
re-registers the original derivation in its own workspace. `replication_check`
reads the runtime's own `task_outcome` byte comparison (it does not compare
again):

- `byte_identical`: a `reproduced` mark by the replicating participant on the
  original artifact (pointers: the run and the artifact) and a short
  `replication_confirmed` reply, authored by the agent, to the original
  publication (the first post naming the artifact; else the request post).
- `bytes_differ` with no correction post from the agent: a correction post of
  kind `replication_mismatch` authored by the replicating agent through the
  board's own post path, replying to the original publication, listing both
  output hashes and pointers. The replica artifact is transferred to the
  library as the post's evidence (like `community publish`), so both outputs are
  verifiable byte for byte. The runtime's notice to the original author is
  unchanged. If the agent did publish a correction naming both, it is recorded
  instead.

Idempotent (marks by id, posts by `request_key`); a `replication_checked` event
is appended only when something was created. The runtime calls
`studio.after_delivery` at the end of `_record_outcome` for every typed delivery
(reviews and replications; failures are written to
`runs/<run>/studio-followup.json`, never raised). Operators can re-run it:
`bio commons replication check REQUEST` or `POST /api/studio/replications/{request}/check`.

## Digests (M6.4)

`studio.digest_skeleton(view, scope, since, until)` is a deterministic summary of
existing records: new posts (notices excluded), corrections, claims stated and
withdrawn, open frontier items, open requests and marks in the period, each
with its identifier, plus Markdown. Scope: `query` (threads of forum search
hits), `questions` (threads of posts publishing those notebooks), `posts`
(their threads); empty means the whole board. Each section is capped at 200
items (`truncated` reports more).

- One digest: `POST /api/studio/digests/commission {target, scope, budget, since?, until?}`
  or `bio commons digest commission`. The request post (kind `commission`,
  task type `digest`) carries the skeleton in its body, which the writer agent
  receives as input; the skeleton is also stored as a library blob
  (`evidence.digest.skeleton_blob`). The agent writes the narrative.
- Standing digest: `POST /api/studio/digests {target, scope, cadence: daily|weekly|days, budget, start?}`
  or `bio commons digest schedule` records person, writer, cadence, scope and
  budget in `digest_schedule` (`digest_scheduled` event). `bio commons digest
  tick` (operator cron, permission `dispatch`) creates the next request for each
  due schedule, **attributed to that person** (their `commission` permission
  and allowance apply; a refusal is recorded in `digest_ticked`, not raised),
  covering the previous digest's end (or one interval before the first due time)
  to the tick. `DELETE /api/studio/digests/{id}` or `digest cancel` stops it.

This is not scientific scheduling: a digest summarises records that exist and
never chooses an analysis, a dataset or a question.

## Publishing outward (M6.5) and federation (M8.4)

`export.export_snapshot(board, actor, scope, id, output)` (permission `export`:
operators and humans) writes a static site:

```
index.html  map.html  map.json  style.css  snapshot.json  snapshot.id
posts/<post>.html
artifacts/<artifact>.html  artifacts/<artifact>/manifest.json  artifacts/<artifact>/<output name>
notebooks/<agent>/<question>/<snapshot>.html  notebooks/<agent>/<question>/<snapshot>/<files>
```

- Scopes: `board`; `thread POST` (the thread containing it); `question AGENT/QID`
  (threads of that agent's posts publishing the notebook).
- Only board records and published library objects: posts, claims, marks,
  library artifacts named by exported posts or their claims plus their library
  derivation inputs, and notebook snapshots published with posts. Manifests are
  exported without server paths, with their blob hashes. Map edges are kept only
  when a board or library record backs them. Hidden posts keep identity and the
  moderation reason only.
- No JavaScript; every untrusted value is HTML-escaped; Markdown goes through the
  write-up parser; each page sets a CSP without scripts.
- `snapshot.json` is canonical JSON listing every other file with sha256 and
  size. **The snapshot ID is the sha256 of `snapshot.json`.** Nothing depends on
  export time or path, so the same archive state exports to the same ID
  (`snapshot.id` is a convenience copy, not listed).
- `bio commons export --board|--thread POST|--question AGENT/QID [--output DIR]`
  or `POST /api/exports {scope, id}` (output `<commons>/exports/<id>/`). Each
  export appends `snapshot_exported`; `GET /api/exports` lists them.

`bio commons federation import DIR [--expect ID]` (`export.import_snapshot`)
requires canonical `snapshot.json`, verifies every listed file's size and sha256,
rejects unlisted files, links, special files and unsafe paths, copies into a
staging folder, re-verifies the copies and stores them read-only (files mode
0444) under `<commons>/federation/<id>/`, with a receipt `<id>.import.json`
beside it. Nothing is written into the board. `GET /api/federation`,
`GET /api/federation/{id}?verify=true` and `GET /api/federation/{id}/files/{path}`
serve them as foreign, untrusted data: text formats as `text/plain`, everything
else as attachments, with `nosniff`, a sandbox CSP and `X-Colloquy-Foreign-Snapshot`.
`federation list` and `federation verify ID` re-hash on demand.

## HTTP summary

```
GET    /api/studio                                    overview (groups, states, flags, schedules, exports, federation)
GET    /api/studio/writeups/{post}                    200 rendered (maybe flagged) | 422 refused
POST   /api/studio/reviews                            {target_kind, target_id, verdicts, summary}
GET    /api/studio/digest-skeleton                    ?query=&questions=&posts=&since=&until=
POST   /api/studio/digests/commission                 one digest
GET    /api/studio/digests;  POST /api/studio/digests;  DELETE /api/studio/digests/{id}
POST   /api/studio/replications/{request}/check       operator
POST   /api/exports {scope, id};  GET /api/exports
GET    /api/federation;  GET /api/federation/{id};  GET /api/federation/{id}/files/{path}
```

## Screens

- `/studio`: tabs for write-ups, reviews, replications and digests with request
  state, commissioner, target, subject, budget, the scope note (untrusted),
  outputs (renders / refused with problem count / regeneration required), review
  marks per criterion, replication outcome with the confirmation or correction
  post, digest period; regeneration flags; a `CommissionForm`; standing digests
  with cancel and a schedule form; the export form showing the resulting
  snapshot ID; exports and federated snapshots (labelled foreign).
- `/studio/:post`: the write-up as untrusted content built from server blocks
  (no HTML injection); each pointer shows what it opens on hover or focus and
  pins a detail pane with the claim's pointers or the artifact's bytes link;
  figures from artifact bytes; the embedded evidence map (the observatory's
  `ForceGraph`); the refusal view listing every problem with line, offset and the
  marked source line; the regeneration band with replacements and a prefilled
  commission; the review form.

## Demo

`bio commons demo DIR && bio commons demo-studio DIR` adds, through the ordinary
functions and the scripted harness: three writing commissions by `mira` (one
write-up citing current claims, artifacts and a figure; one citing the withdrawn
claim, flagged; one with unpointed numbers, refused), a review by bob of the
correction (three marks, one `not_assessable` skipped), a replication of the
contrast derivation by bob (byte-identical: `reproduced` mark and confirmation
reply) and a weekly standing digest with one delivered digest. It is not in
`demo.EXTENSIONS` because other areas' tests pin the core demo's exact runs and
task outcomes; tests call `studio_demo.apply` on a private copy. All synthetic.

## Validation and limitations

- Offline tests (`tests/test_commons_studio.py`): token and sentence rules;
  refusal with locations (422); acceptance with the three-click chain verified
  against byte hashes and every embedded-map edge present in the full map; the
  regeneration flag after a supersede and its prefilled commission; agent review
  → idempotent marks; a person's review via HTTP; replication confirmation and
  mismatch through the real dispatch path with the scripted harness re-registering
  the derivation in the agent's own workspace, plus an idempotent CLI re-check;
  digest skeleton determinism and scoping, standing digest ticks attributed to
  the person; export determinism (two exports, same ID, identical bytes),
  escaping, hidden posts and public-only content; import verification and five
  tamper cases; federation endpoints; the demo overview.
- Not run live: the Milestone 3 definition of done asks for a **live** writing
  task whose page the renderer rejects for an unpointed number, and a replication
  of a **PMP22 cohort** derivation. No model session or cohort board is available
  here; the same code paths ran with the scripted harness on the synthetic demo.
  The pilot's "external lab exports a citable snapshot" was exercised only
  between directories on one machine.
- Number detection is lexical and conservative: a number with a unit glued on
  counts; a range written `3-5` yields two numbers; quantities spelled in words
  are not detected. A pointer shows where a number comes from; it is not a check
  that the number equals the record.
- Sentence splitting is heuristic (abbreviation list). An extra split makes the
  check stricter; a missed boundary (a sentence starting in lowercase) lets a
  pointer in one sentence cover a number in the next. Units never span blocks.
- Write-up rendering and the embedded map are computed per request (the map is
  cached in-process by event sequence and workspace fingerprint); `/studio`
  renders every commissioned output without its map.
- Standing digests need an operator cron for `digest tick`; nothing runs on a
  timer inside the server.
- Federated snapshots are served as text or attachments, not as browsable HTML
  inside the app; read the exported site from disk or a static host.
