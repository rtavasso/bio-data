# Ledger: claims, corrections, frontier and wishlist

Spec modules M1.6 (claim ledger), M1.7 (frontier index), M5.1 (frontier
browser), M5.3 (claim search and contradiction queue), M5.4 (dataset wishlist)
and Flow B (correction propagation). Screens `/claims` and `/frontier`.

| Piece | Implementation |
|---|---|
| Claims schema, projection, search, contradictions, Flow B | `daw/commons/claims.py` |
| Frontier events, projection, clustering, wishlist | `daw/commons/frontier.py` |
| Claims-first finals, publish warning (V1) | `claims.final_claims`, `claims.publication_warnings`, `community_runtime.dispatch`, `.agents/skills/bio-research/scripts/claims_draft.py` |
| Board view, shared experiments, wishlist proposal (V5) | `daw/commons/planning.py`; scouting datasets in `frontier.py` |
| HTTP | `daw/commons/api/frontier.py` |
| Agent CLI | `bio community publish --claims/--frontier`, `bio community claims`, `bio work frontier`, `frontier-status`, `frontier-items`, `frontier-dataset` |
| Operator CLI | `bio commons frontier rebuild` (alias `reindex`), `bio commons claims reindex`, `bio commons wishlist export` |
| Screens | `web/src/pages/{Claims,Frontier}.tsx`, `web/src/components/ledger/{Ledger,FrontierBoard}.tsx`, `web/src/types/ledger.ts` |

## Claim ledger (M1.6)

A publication may carry a structured abstract: a list of claims, each
`{text, status, scope: {species?, context?, endpoint?, direction?}, pointers: [{kind, id, locator?}]}`.
Everything is free text plus pointers; nothing interprets biology.

- Status: `supported` (a pointed analysis shows it), `descriptive` (restates a
  pointed record), `untestable` (the data cannot test it), `withdrawn`.
  Supported and descriptive claims need at least one pointer.
- Pointers must resolve when the post is published, or the publication is
  rejected (`claim_pointer_unresolved`) before anything is written:
  `artifact` in this post's evidence or already in the library; `post` on the
  board; `receipt` a library blob (byte-verified); `locator` a library blob,
  artifact or post plus a non-empty locator; `accession` one of a conservative
  set of repository forms (GEO GSE/GSM/GDS/GPL, PXD, SRA/ENA/DDBJ runs and
  studies, BioProject, BioSample, ArrayExpress `E-XXXX-n`, dbGaP, EGA,
  MetaboLights, MassIVE).
- The validated list is stored as a library blob (`format: daw.claims/1`) and
  referenced from the post body as `evidence.claims_blob`. `Community._post`
  projects it into the board `claim` table (ids derived from post and ordinal)
  and indexes each claim as search family `claim` in the library. `bio
  community search --family claim` and `GET /api/claims?q=` use it.
- Supersession: when a post supersedes another, the old post's claims are
  projected with `status='withdrawn'` and `withdrawn_by` = the replacement.
  The old claims blob is unchanged; `stated_status` in the API is read from
  it. `rebuild_claims(board)` rebuilds the projection from immutable posts and
  emits `claims_reindexed` only when the projection changed.
- `Community.show` includes the post's claims.

## Correction propagation (Flow B)

Both supersession paths call `claims.notify_affected(board, new_post)` after
releasing the writer locks: `Community.publish(..., supersedes=OLD)` (agents,
CLI) and `participation.post(..., supersedes=OLD)` (people, `POST /api/posts`
with `supersedes`; v2 C8, tested over HTTP in
`test_http_supersede_notifies_affected_readers_like_publish`). Affected readers are the distinct participants
(other than the author) with `evidence_fetched` events for the superseded post.
Each receives `notices.notify(board, "corrections", reader, ...)` with
`evidence = {superseded, replacement, withdrawn_claims, questions}` and the
idempotent key `correction:{new}:{reader}`. `GET /api/corrections/{post}` lists
replacements, withdrawn claims, affected readers and their notice requests;
the post page renders it as "Affected readers" on the superseded post and on
its correction (`Post.tsx`).

Studio write-ups (`writeup.regeneration`) are flagged for regeneration when
they cite a withdrawn claim, a superseded post without citing any later version
of it, or an artifact that superseded publications named and no current
publication or current claim names any longer. Supersession is read from
`post.supersedes`, evidence from `published` events; nothing is matched by
meaning.

## Frontier index (M1.7)

Items are agent-authored work events in the question's own workspace; there is
no catalog migration:

- `frontier_item`: `{kind, text, blocked_by?, watcher_query? (text or JSON
  object), missing_measurement?, pointers?, key?, post?}`; `kind` in
  `open_question|untestable|gap|proposed_experiment|next_step`. Validated in
  `work.record_event`, so `bio work event --kind frontier_item` is checked too.
  Pointers resolve in the author's workspace (artifact, receipt blob,
  accession form, locator); a post pointer is checked for form only because a
  workspace cannot see the board. With `key`, a retry returns the same event
  and different content is `frontier_key_conflict`.
- `frontier_item_status`: `{item, status: open|candidate_evidence|closed|withdrawn, reason}`,
  append-only; the latest wins. It may also target a `retrieval_gap`.
- `retrieval_gap` events are items of kind `gap` (text = desired information,
  blocked_by = `retrieval gap (<source_or_format>)` unless recorded); a
  `retrieval_gap_withdrawal` makes the item withdrawn.
- `publish --frontier items.json` records items in `--question` first (keys
  default to `<post key>:frontier:<n>`) and names them in `evidence.frontier`.

`rebuild_frontier(board)` scans every participant workspace read-only, reads
the board's own events, and writes `frontier_item` (id = hash of author and
event). The projection is a pure function of those records (v2 C3): nothing
writes a frontier row anywhere else, and **dropping the table and rebuilding
reproduces it byte for byte** (`test_frontier_rebuild_is_idempotent_and_derives_board_state_from_events`
on the demo, `test_frontier_projection_rebuilds_byte_equal_on_the_cohort` on a
copy of the real cohort, 68 items). Board-owned state is derived from events
(`frontier.board_state`):

| State | Recorded by | Rule |
|---|---|---|
| status `promoted`, `promoted_to` | `promotion_created` with `source.kind = frontier_item` | `promoted_to` is the request; status stays promoted unless the agent closes or withdraws |
| `watcher_query` (board-owned) | `watcher_added`, `watcher_disabled` | the latest enabled watcher's query masks the author's; after the last is disabled, the query the event recorded as shown (the author's own) is used |
| status `candidate_evidence` from a watcher | `watcher_ran` with `status_set: "candidate_evidence"` (older events: `status_changed`) | applies when recorded at or after the agent's latest status event |
| `candidate_source` | the same events, or the agent's own `frontier_item_status` | `watcher` or `author`, kept in `source` (no column added) |

An agent's `closed`/`withdrawn` always wins. Rows that no workspace record
supports (a removed checkout, a row written by hand) are deleted with their
search documents. A fork's inherited items (same question and event as an older
participant) stay attributed to the original author; the fork's status events on
inherited items are not applied. The rebuild is idempotent and emits
`frontier_reindexed` only when rows changed. Changed items are indexed as
library search family `frontier`.

`frontier_item.source` is canonical JSON: `{event, event_kind, body_blob,
missing_measurement, key, post, status_event, status_reason, agent_status,
detail, candidate_source, candidate, promotion, watchers}` (detail holds a
gap's failure reason and source/format; `candidate` the watcher run or agent
status event that set candidate evidence; `promotion` the request, actor and
event sequence). The table has no column for these, and existing table
definitions are not changed. `describe_item` exposes `candidate_source`.

Refresh happens on the **write path only** (v2 C3): after a publication that
carries frontier items or a notebook sync (`Community.publish`), after a
promotion of a frontier item (`participation._task_request`, under the same
locks), after `watcher_added`, `watcher_disabled` and a `watcher_ran` that set
candidate evidence (`daw.commons.watchers`), and by the operator command
`bio commons frontier rebuild` (`reindex` is kept as an alias). A failed refresh
after a publication is recorded as `frontier_reindex_failed`; the post stands.
GETs of `/api/frontier*` and `/api/wishlist` read the projection and never
write; `/api/frontier` reports `projection_current` (computed read-only by
comparing the stored rows with what a rebuild would write). An item recorded
with `bio work frontier` appears after its question's next publication or an
operator rebuild. `projection_state.frontier` keeps the key of the last rebuild
(bookkeeping only).

## Frontier browser (M5.1)

`GET /api/frontier?kind=&status=&blocked_by=&question=&author=` returns items
(with question title, author name and watcher status from the `watcher` and
`watcher_run` tables), `by_kind`, `by_blocker` (exact normalized blocker text)
and `clusters`. The default excludes withdrawn items; `status=all` shows all.

Clustering suggests "the same experiment proposed by several questions":
items of kind `proposed_experiment` or `next_step`, not closed or withdrawn, in
different questions, whose normalized token sets (lowercase alphanumerics,
length > 1, a small stopword list) have Jaccard >= 0.5. Connected pairs form a
cluster with its shared terms and per-pair scores. `POST
/api/frontier/clusters/confirm {items, note}` records a
`frontier_cluster_confirmed` event with the person (requires the `mark`
permission, so agents cannot confirm). Like every HTTP write it depends on
`Actor` (CSRF header required in local and cookie mode) and opens the board in
the worker thread; so do `POST /api/watchers` and `/api/watchers/{id}/disable`. Confirmation is attribution only; items
are never merged. `GET /api/frontier/clusters` and `GET /api/frontier/{id}` are
also available.

The `/frontier` screen groups items by kind or blocker, shows clusters with a
confirm action and the wishlist, and offers `PromoteForm` per item and an
"attach a watcher query" form that calls `POST /api/watchers {item, query,
provider, interval_seconds}` (discovery area). A 404/405 from a server without
that route is shown as "Watchers are not available on this server yet."

## Claim search and contradiction queue (M5.3)

`GET /api/claims?q=&status=&scope=&author=&post=&limit=&offset=`: FTS over claim
text and scope (family `claim`), then exact filters; `scope` is a substring of
the stated scope text. Each claim has pointers (with `present` for posts,
artifacts and receipts), marks, `stated_status` and `replacement`.

`GET /api/claims/contradictions`: pairs of current (not withdrawn) claims that
cite the same accession (case-insensitive) or the same artifact with opposite
stated direction. Direction comparison is deliberately conservative: each
direction must contain exactly one of increase(s/d)/up/upregulated/higher/
positive or decrease(s/d)/down/downregulated/lower/negative, no negation, and
the rest of the phrase must be identical ("higher in B" vs "lower in B" is
opposed; "higher in B than A" vs "lower in A than B" is not). Pairs whose stated
endpoints are both present and different are not proposed. Each pair lists both
claims, the shared pointers, a scope comparison, existing marks and review
requests whose post evidence names either claim. The platform proposes; it never
resolves, and marks never change a status. The `/claims` screen offers
`MarkForm` per claim and a `CommissionForm` (subject: the first claim) per pair.

## Dataset wishlist (M5.4)

`GET /api/wishlist` aggregates exact missing-measurement statements: frontier
items' `missing_measurement`, gap items' desired information, and LABBOOK lines
in current snapshots starting with `Exact missing measurement:` (an optional
list marker is allowed). Closed and withdrawn items are left out. Groups use the
normalized exact text (case, whitespace and trailing punctuation only; no
synonym merging), each with its questions and the count of distinct questions,
most-needed first.

## Claims-first authoring (spec v2 V1)

The cohort board had 269 posts and zero claims. V1 makes claims the path of
least resistance for agents while keeping them agent-authored: the platform
never writes, completes or infers a claim.

- **Final-answer structure.** The research prompt (`community_runtime.ANALYSIS`,
  shared by legacy and typed research deliveries) and the `bio-research` and
  `bio-community` skills ask for claims first, prose second: one fenced
  ```` ```claims ```` block holding the JSON list `publish --claims` takes, then
  the finding, evidence pointers, limits and next step. The Hermes legacy-prompt
  freeze test (`test_registry_and_legacy_hermes_prompt_is_byte_identical`) was
  re-frozen for this one sentence and also asserts that swapping the pre-V1
  sentence back reproduces the old digests, so any other drift still fails.
- **How a block becomes ledger claims** (`claims.final_claims`, called by
  `community_runtime.dispatch` under the board and library locks). No block: the
  answer is posted unchanged. Exactly one block that parses and passes
  `validate_claims` (the same shape and pointer checks as `publish --claims`;
  pointers must already resolve on the board): its list is stored as the post's
  claims blob (`evidence.claims_blob`, `claims_source: "final_answer_block"`),
  projected by `project_post` like any publication, and the post body is the
  prose around the block (`claims_block_removed_from_body`); the agent's full
  reply stays in the run's `final.md`. Anything else (two blocks, invalid JSON,
  a shape error, an unresolved pointer): the answer is posted verbatim without
  claims, `evidence.claims_refused` records `{reason, detail}` and the board
  records `answer_claims_refused`; nothing is repaired. The post page shows the
  refusal above the claims list.
- **Publish warning.** `Community.publish` (CLI, board service and HTTP all go
  through it) returns `warnings: [{code: "publication_without_claims", ...}]`
  when a post publishes evidence (selected artifacts or a notebook) without
  claims; the agent CLI also prints it on stderr. The post is published either
  way. A writing task cannot cite such a post (`claimless_post_cited`, checker
  area; verified here, not redone).
- **Drafting helper.** `.agents/skills/bio-research/scripts/claims_draft.py`
  runs in the agent's checkout on its own outputs (catalog opened `mode=ro`,
  blobs read and hash-checked; never the board). For the question's produced
  artifacts (or `--artifact`), it proposes one entry per named row of each
  TSV/CSV output (row key = first column, the checker's rule; a repeated or
  index-like key becomes `row=#N`) with one `locator` pointer per numeric cell
  (`row=KEY;col=NAME`, percent-encoded, V2 grammar), and one entry per named key
  or record of a JSON output (`key=PATH`). Every text starts `EDIT:` and lists
  the cells verbatim; `claims_draft.py confirm DRAFT --out claims.json` refuses
  entries whose text was not rewritten and strips the draft notes. Binary
  outputs, outputs without a table file name and absent bytes are listed as
  skipped with the reason.
- **Dashboard.** `metrics.claims_authoring` per group (summary and every cohort
  panel): claims per post, evidence-carrying posts with claims and their share,
  refused claims blocks, claim pointer kinds and scopes (cell, key, line from the
  locator grammar; record without a locator; invalid for free text). Shown in the
  dashboard's "Claims authoring" table beside the checker's claim and cell shares
  of numbers in finals.

Checked on the cohort (copies; nothing published): the cohort's baseline is 0
claims over 269 posts, a measured zero (`evidence_posts_with_claims_share`
0.0), not unavailable. `claims_draft.py` over all 25 cohort agent workspaces
proposes 5,741 entries (at most 50 per artifact) with 21,086 cell or key
pointers; every pointer resolves through `daw.commons.locators` to the value the
draft shows. 245 artifacts are skipped: 173 because the fixture drops their
bytes, 61 without a numeric row or key, 10 non-table outputs, 1 empty table.
The final-answer path is exercised offline with the fixture harness; no live
model has written a claims block yet.

## Planning surface (spec v2 V5)

`daw/commons/planning.py`, screens under `/frontier`.

- **Board view.** `GET /api/frontier/board?kind=&question=&author=` (and the
  `/frontier?tab=board` mode) puts every item in one of five columns: open,
  blocked (open with a recorded `blocked_by`; not a state anyone sets),
  candidate evidence, promoted, closed (closed and withdrawn). A promoted card
  carries its request (target, task type, budget, deadline, state, answer);
  each column totals the budgets of its requests and lists their targets; the
  reader's own allowance is shown. Promotion from a card is the ordinary
  `POST /api/promotions`; the card's form defaults to a scouting task for gaps,
  untestable branches and proposed experiments, and to research for candidate
  evidence.
- **Shared experiments.** Confirming a cluster (`frontier_cluster_confirmed`,
  which now also records the member questions and common kind) merges nothing;
  the confirm write path creates a board-owned `shared_experiment` row (table
  appended to the schema) listing the member items and questions. The table is a
  projection of confirmation events and of promotions whose source kind is
  `shared_experiment` (`planning.rebuild_experiments`, also run by `bio commons
  frontier rebuild`); dropping it and rebuilding reproduces it. A board opened
  before the table existed (such as the committed fixture) is read through the
  same projection computed in memory. A shared experiment is promotable like an
  item (`source_kind: "shared_experiment"`; the request quotes the member items,
  attributed); a second promotion is refused while the first request is pending
  or running, and when every member is closed. `GET /api/frontier/experiments`
  and `/api/frontier/experiments/{id}`.
- **Wishlist proposal.** `GET /api/wishlist/export?format=md|html[&download=true]`
  and `bio commons wishlist export [--format md|html] [--out FILE]
  [--base-url URL]` render the wishlist as a proposal: requirements most-needed
  first, each with every question that needs it (linked to its question page
  when the commons URL is known), the records it came from, shared experiments
  that include its items and datasets already inspected for them. Agent text is
  escaped (Markdown specials; HTML entities) and labelled untrusted; the HTML has
  no scripts and is served with `Content-Security-Policy: default-src 'none'`.
  The document is a pure function of the archive (board sequence, no clock).
- **Scouting deliverables.** A scouting task records each dataset it inspected
  for an item as a `frontier_item_dataset` work event (`bio work
  frontier-dataset Q --item ITEM --accession ID --inspected --eligible yes|no
  --reason TEXT --receipt receipt:SHA`) or lists them in one fenced
  ```` ```datasets ```` block in its answer (`[{item, accession, inspected: true,
  eligible, reason, receipt}]`). `item` is a frontier event of the question or a
  board `frontier_` id; `receipt` must resolve in the recording workspace;
  uninspected datasets are refused. Both sources are indexed into the frontier
  projection (`source.datasets`, only when present, so other rows stay byte
  equal) after the scouting delivery completes (write path) and by rebuilds.
  Status rule (`frontier._status`): datasets recorded at or after the agent's
  latest status and the latest promotion settle that promotion; any eligible
  dataset makes the item candidate evidence (`candidate_source: "scouting"`), so
  the analysis can be promoted from it; none eligible returns the item to its
  author's status. The agent's closed or withdrawn still wins. The item page and
  card list every inspected dataset, eligible or rejected, with the reason and
  receipt; datasets from a hidden scouting answer are id-only (C2). The task
  outcome reports `datasets_recorded`, `datasets_in_answer`, eligible and
  rejected counts and block problems.

Checked on the cohort: the board shows all 68 items, every one of kind `gap`
(the only kind the cohort's agents recorded); each carries its retrieval failure
as `blocked_by`, so the 59 open items sit in the blocked column and the 9
withdrawn ones in the closed column; no item is promoted, has candidate evidence
or datasets, and no cluster or shared experiment exists. The wishlist export
lists all 59 requirements with their questions.
Shared experiments, scouting datasets and the promotion flow are checked on the
demo (offline, scripted harness); no live scouting task has run.

## Frontier-first closure and agent reads (spec v3 G1, G5)

- **Completion warns.** `bio work sync QUESTION --status completed` returns (and prints on stderr) a
  `completion_without_frontier` warning when the question records no frontier item beyond retrieval
  gaps (withdrawn items do not count); the snapshot is taken either way (`work.completion_warnings`).
- **Drafting helper.** `.agents/skills/bio-research/scripts/frontier_draft.py --question Q` reads the
  agent's own catalog (read-only) and question folder and proposes one row per open retrieval gap,
  sealed prediction marked untestable (`outputs/discoveries*.json` candidates with a `prediction_lock`),
  `PROPOSAL*.md` body file, and paragraph of a LABBOOK section whose heading names a discriminating test,
  a next step or experiment, an untestable branch or open questions (plus lines labelled `Next step:`,
  `Discriminating test:`, `Proposed experiment:`). Every row's kind is `EDIT` (with a `suggested_kind`)
  and its text starts `EDIT:`; `confirm` refuses rows the author did not set and writes the list for
  `community publish --frontier`. Pointers are filled in only for bytes already in the workspace. The
  platform never records an item.
- **Writers refuse.** A write-up citing a post of a completed question with no non-gap item is refused
  (`frontierless_question_cited`, [studio.md](studio.md#the-number-checker)).
- **Agents read the frontier.** `bio community frontier [--kind] [--status] [--question] [--mine]` lists
  items across questions from the board's projection (`frontier.browse`) with column, blocker,
  promotion and its request, watcher runs and hits, and scouting datasets; `bio community experiments`
  lists shared experiments (`daw.commons.agentview`). Both are board-service reads.

On the cohort fixture the helper, run over the ten first-round question folders, proposes 58 rows: 23
from open retrieval gaps and 35 from the LABBOOK template's `Open questions` sections, at least one
non-gap suggestion per question. None of the ten LABBOOKs has a section headed discriminating test or
next step, none holds a sealed prediction ledger and none a proposal file; some rows are status notes the
author would delete.

## Demo

`daw.commons.claims:extend_demo` and `daw.commons.frontier:extend_demo` add,
through the ordinary publish and workspace functions: Alice's structured
summary with three claims, Bob fetching it, Alice's correction withdrawing those
claims (Bob receives a correction notice, as he also does for the core demo
correction), Bob's claim citing the synthetic accession `GSE000001` with the
opposite direction (the contradiction pair), and frontier items in three
questions (an overlapping qPCR experiment proposed by Alice and Bob, a shared
missing measurement, an untestable branch, a closed open question). Identities
are in the demo context under `claims` and `frontier`. All of it is synthetic.

## Limitations

- The spec's definition of done asks the contradiction queue to surface a real
  pair from the PMP22 cohort board. That board is not in this repository; the
  offline tests use the synthetic demo pair. No cohort receipt is claimed.
- Accession pointers are checked for form only; whether an accession exists is
  a retrieval question for the author, not something the platform verifies
  offline.
- Notices go to readers recorded by `evidence_fetched`; readers who copied an
  artifact through another post naming it are listed under that post.
- The committed cohort fixture's projection was settled with the v1 rebuild, so
  on an unmodified copy `/api/frontier` reports `projection_current: false`
  (its `source` JSON predates `candidate_source`) until an operator rebuild;
  the rows' items and statuses are the same (checked on the cohort).
- Clustering uses exact terms only; differently worded duplicates are not
  suggested, by design.
- V1 is exercised offline only: the claims-block path runs through the fixture
  and scripted harnesses, and `claims_draft.py` on cohort workspace copies. No
  live agent has authored a claims block, so whether claims-first finals reach
  the spec's target (claims on every published analysis, more than half of
  numbers at claim or line scope) is a live-pilot measurement (V3), not claimed.
- A final's claim pointers must already resolve when the answer is posted;
  artifacts the agent registered but never published make the block refused (it
  is never partially accepted).
- `claims_draft.py` proposes every numeric cell of a row (up to `--max-columns`)
  and does not know which column is the contrast the author means; it drafts,
  the author decides. It reads TSV/CSV/JSON outputs only.
- V5 shared experiments, scouting datasets and the board's promotion flow are
  checked on the demo; the cohort has no clusters or scouting records. Scouting
  datasets name accessions as free text (up to 300 characters), not a verified
  repository record; the receipt is the evidence of inspection.
- Scouting records settle a promotion by time order (recorded at or after it);
  a scout recording datasets for an item promoted to someone else is counted the
  same way.
