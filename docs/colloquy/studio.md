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

## Replications (M6.3, spec v2 C6)

A replication is the one task allowed to execute fetched code. The carve-out,
stated in `AGENTS.md`, the replication task prompt (`tasks.INSTRUCTIONS`, which
replaces the general "no permission to execute downloaded code" line with
`tasks.REPLICATION_UNTRUSTED` so the prompt does not contradict itself) and the
research and community skills: **a replication may execute only the code blobs
named in the fetched derivation, after hash verification, through
`run_analysis.py`, inside a sandbox with egress off. Any other execution of
fetched code remains forbidden.**

Agent side. The replicating agent creates a question, fetches the original into
it (`community fetch POST --question Q --artifact ARTIFACT`) and runs
`./bin/python .agents/skills/bio-research/scripts/replicate.py ARTIFACT --question Q`.
The helper reads the manifest from the agent's own workspace, copies each code
and input blob out of the object store into
`questions/Q/{scripts,inputs}/replication-ID-rNNN/` and checks every copy's
sha256 (a tampered blob stops it before anything runs), then executes the entry
code blob through `run_analysis.py` as `INTERPRETER CODE INPUT... OUTPUT` (inputs
in derivation order) in a minimal environment with no proxy, board-token or
credential variables. It stores the receipt (`bio object add`), registers the
output with the original derivation unchanged (`bio register --manifest`, same
derivation key) when the receipt is complete, and records a
`replication_execution` work event naming the original, the replica, the
receipt blob and whether the bytes are identical. A failed run is recorded and
registers nothing. Several code blobs need `--entry SHA`; a recorded
`derivation.command` is reported, not executed.

Receipt gate (`daw.commons.replication`, used by `tasks._replication`). A
same-derivation registration made during the delivery counts only when one of
the delivery's `replication_execution` events names a receipt that verifies
against its content address and is a `run_analysis.py` receipt whose
`code_sha256` is one of the derivation's code blobs, with `code_unchanged`,
exit code 0, `complete`, and an output written with the replica's sha256.
Receipts are read from the agent's workspace through `Archive` (read-only).
Outcomes: `byte_identical` and `bytes_differ` (under a receipt),
`no_execution_receipt` (a matching registration without one, e.g. copied bytes;
the outcome lists each candidate's problems), `no_matching_derivation`,
`subject_unknown`, `subject_has_no_artifacts`. The originals are the subject
artifact, a post's published evidence, or a claim's or frontier item's artifact
pointers. The runtime's mismatch notice to the original author fires only for a
receipted `bytes_differ` and cites the receipt.

Same-producer refusal. `participation.commission`, `participation.promote`,
`assignments.assign` (task type `replication`) and `community_runtime.dispatch`
refuse a target that produced an original (`replication_target_produced_original`):
a participant whose own workspace links the artifact as `produced` (or holds it
with no question link). A fork's workspace is a copy of its parent's, so forks
created after the production are refused too; the dispatch-time check catches
requests queued before the check existed, before any state changes.

Platform records. `replication_check` re-verifies the outcome's receipts from
the agent's workspace (an outcome recorded before the gate, or a receipt that no
longer verifies, becomes `no_execution_receipt`) and then records, authored by
the `replication` system participant (`participants.ensure_system`):

- `byte_identical`: a `reproduced` mark on the original artifact (pointers: the
  run, the artifact, and each receipt blob with its workspace event) and a
  `replication_confirmed` reply to the original publication (the first post
  naming the artifact; else the request post) that quotes the receipt: producer
  code hash, exit code, start and finish.
- `bytes_differ` with no correction post of the agent's own (a post it published
  naming both artifacts; its final answer does not count): a
  `replication_mismatch` post replying to the original publication, listing both
  output hashes and each replica's receipt. The replica artifact is transferred
  to the library as the post's evidence so both outputs are verifiable byte for
  byte.
- `no_execution_receipt`: nothing is confirmed or posted; the check records the
  outcome once.

The agent signs only what it wrote (its answer and any post it published).
Idempotent (marks by id, posts by `request_key`); a `replication_checked` event
is appended when something was created or on the first check. The runtime calls
`studio.after_delivery` at the end of `_record_outcome` for every typed delivery
(reviews and replications; failures are written to
`runs/<run>/studio-followup.json`, never raised). Operators can re-run it:
`bio commons replication check REQUEST` or `POST /api/studio/replications/{request}/check`.

Sandbox. On a multi-tenant (accounts) commons a replication dispatch is refused
without `sandbox.toml` (`sandbox_required`; no override is accepted for executing
fetched code). With a sandbox its egress allowlist holds only the harness's model
hosts (`replication_egress`: `none` without a proxy network, else
`model_hosts_only`, in `runs/<run>/sandbox.json`). Local single-user mode runs it
unsandboxed and records the warning (`replication_unsandboxed` event and
`sandbox.json`).

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
contrast derivation by bob (the hook runs `replicate.py` in bob's checkout with
`./bin/python`, which re-executes the saved contrast script through
`run_analysis.py`; byte-identical under that receipt: `reproduced` mark and
confirmation reply by the `replication` participant, and bob's answer is worded
from the receipt) and a weekly standing digest with one delivered digest. It is not in
`demo.EXTENSIONS` because other areas' tests pin the core demo's exact runs and
task outcomes; tests call `studio_demo.apply` on a private copy. All synthetic.

`bio commons demo-deliver REQUEST --answer FILE --replicate` delivers a pending
replication request on a demo commons the same way: the hook fetches the subject
artifact into a new question in the target's checkout and runs `replicate.py`
with `./bin/python`; the answer is rewritten from the receipt. The demo
derivations' saved code (`daw.commons.demo.CODE`) is three tiny Python scripts
that recompute the measurement, contrast and normalized tables from their inputs
(`python SCRIPT INPUT OUTPUT`); a test checks that they reproduce the registered
bytes.

## Validation and limitations

- Offline tests (`tests/test_commons_studio.py`): token and sentence rules;
  refusal with locations (422); acceptance with the three-click chain verified
  against byte hashes and every embedded-map edge present in the full map; the
  regeneration flag after a supersede and its prefilled commission; agent review
  → idempotent marks; a person's review via HTTP; replication confirmation and
  mismatch through the real dispatch path, the scripted harness running
  `replicate.py` in the agent's checkout (the saved script really executes; a
  deliberately altered script gives a receipted mismatch), copied bytes and a
  receipt of another script giving `no_execution_receipt`, the same-producer
  refusal (producer, fork, promotion, assignment, dispatch, HTTP), a tampered
  code blob refused before execution, the prompt's carve-out, the sandbox rules
  for replication, plus an idempotent CLI re-check; on the PMP22 cohort (read
  only): all 281 library artifacts have a producer, all 11 forks inherit their
  parent's production and commissioning a fork or its parent is refused before
  any write;
  digest skeleton determinism and scoping, standing digest ticks attributed to
  the person; export determinism (two exports, same ID, identical bytes),
  escaping, hidden posts and public-only content; import verification and five
  tamper cases; federation endpoints; the demo overview.
- Not run live: the Milestone 3 definition of done asks for a **live** writing
  task whose page the renderer rejects for an unpointed number, and a replication
  of a **PMP22 cohort** derivation. No model session is available here; the same
  code paths ran with the scripted harness on the synthetic demo (re-execution of
  the demo's real saved scripts). Cohort derivations were not re-executed. A
  read-only survey of the cohort library's 281 manifests: 58 entry code blobs are
  absent from the redacted fixture, 193 of the 223 present read hard-coded paths
  inside the author's workspace, 8 take arguments, 32 derivations name two or
  three code blobs and 61 record a command. The helper's `CODE INPUT... OUTPUT`
  convention therefore fits few cohort derivations as saved; a live cohort
  replication will often end in a failed receipt (recorded, nothing registered)
  rather than a byte comparison. Mapping recorded commands and author paths onto
  the materialized inputs is not implemented.
- Sandboxed replication is exercised offline only (policy, allowlist and receipt
  fields); no container engine runs in the offline suite. The per-dispatch
  allowlist is enforced at the proxy only once the proxy takes per-dispatch
  policy (C7); until then a proxied sandbox enforces the proxy's start-time list,
  and only `network` unset (`--network none`) is egress off for the whole
  container. Inside one container the harness and the executed code share the
  model hosts; `replicate.py` strips proxy variables and credentials from the
  executed code's environment, which limits but does not isolate it.
- The receipt gate is structural: a run_analysis receipt is written inside the
  agent's own checkout, so an agent that forges one can pass it. It separates
  executed replications from copied bytes; it is not attestation.
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
- Review marks, replication checks, digest ticks and exports run host-side (the
  runtime's post-delivery hook or operator commands), never inside an agent's
  sandbox; the agent itself needs only the board service's existing operations
  (show, verify, fetch, publish, answer).
- Studio links to `/api/...` go through `withBase()`, so the screens work under a
  tenant prefix (`/c/<tenant>/`); `/studio` routes are lazy chunks.
- Standing digests need an operator cron for `digest tick`; nothing runs on a
  timer inside the server.
- Federated snapshots are served as text or attachments, not as browsable HTML
  inside the app; read the exported site from disk or a static host.
