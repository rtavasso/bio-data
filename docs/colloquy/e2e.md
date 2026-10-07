# End-to-end verification and completion audit

This area checks that the merged Colloquy build works as one system. It covers
every screen in section 5 of the [specification](../vision/colloquy-build-spec.html),
Flows A–D from section 3, the section 8 metrics that the demo can show, and one
pass through a tenant prefix. The per-module status table is in
[COLLOQUY.md](../COLLOQUY.md#status-per-specification-module).

## Running the suite

```sh
uv sync --all-extras
npm --prefix web ci
npm --prefix web run e2e          # about 2 minutes; not part of `npm test`
```

`web/e2e/run.mjs` runs these steps:

1. Builds a fresh synthetic commons with `bio commons demo` and `bio commons
   demo-studio` in `web/e2e/.out/<run>/commons/`.
2. Builds the web app.
3. Starts `bio commons serve` on a free port.
4. Drives headless Chromium.

The run writes the following to `web/e2e/.out/<run>/`, which git ignores:

- a screenshot of every screen and flow step;
- `report.json`, with each step, its outcome, the measured metrics and every
  console or network problem;
- the server logs.

The exit status is non-zero if any step fails.

Playwright is a pinned devDependency of `web/` (`playwright` 1.56.1, exact), so
`npm --prefix web ci` installs it on a fresh machine. Its browser is installed
once with the same pinned version:

```sh
npx --prefix web playwright install chromium            # macOS, or Linux with system libraries present
npx --prefix web playwright install --with-deps chromium  # Linux CI: also installs system libraries
```

The runner never downloads anything itself. It resolves `playwright` from
`web/node_modules` first (then `NODE_PATH` and `/opt/node-tools/node_modules` as
fallbacks) and honours a pre-installed browser: `E2E_CHROMIUM` names a binary
explicitly; `PLAYWRIGHT_BROWSERS_PATH` (default `/opt/pw-browsers` when that folder
exists) is where Playwright looks for its pinned revision, and if that revision is
missing there the newest Chromium in that folder is used, with a note in the
log. Otherwise the launch fails with the install command above.

**The newest-Chromium fallback is not reproducible.** It runs whatever revision
happens to be installed in that folder, so a pass with it is a local
convenience, not a reproducible check; CI installs the pinned browser and never
takes it. `report.json` records which browser ran: `browser.source` is
`pinned`, `E2E_CHROMIUM` (as pinned as the binary you named) or
`newest-preinstalled-fallback` (`reproducible: false`), with the executable and
`browser.version`. Cite only a `pinned` run as the e2e check.

CI (`.github/workflows/ci.yml`) runs the suite on `ubuntu-latest` and
`macos-latest` after `npm run build` and `npm test`, with the browser installed
by `npx playwright install --with-deps chromium` (Linux) or
`npx playwright install chromium` (macOS), and keeps `report.json` and the
screenshots as a build artifact.

| Variable | Effect |
|---|---|
| `E2E_SKIP_BUILD=1` | Reuse `web/dist` |
| `E2E_OUT` | Output root |
| `E2E_CHROMIUM` | Browser binary |
| `E2E_HEADED=1` | Show the browser |

No model, credential or network is used. The scripted stand-in harness answers
for the agents. Every number on the board is a synthetic fixture.

### Operator commands for demos (new)

The flows need agent turns and a watcher run without a live model or network.
Two operator commands provide them. Both refuse any commons without the
synthetic `DEMO.json` marker (`not_a_demo_commons`), so they can never stand in
for a real agent or a real provider.

- **`bio commons demo-deliver REQUEST --answer FILE [--hook FILE]`**
  (`daw.commons.demo.deliver_scripted`) delivers one pending request with the
  scripted harness. It goes through `community_runtime.dispatch`, so it writes
  the prompt, stream, receipts and task outcome, and runs the post-delivery
  hooks. The agent's answer is the given text.
  - `--hook` is fixture Python that runs inside the agent's checkout before the
    answer, using only the agent's own CLI (`./bin/bio register`,
    `./bin/bio community fetch|ask|publish`), as a live agent's tool calls would.
  - The hook file is removed after the turn.
- **`bio commons demo-watch-tick --response FILE`**
  (`daw.commons.demo.watch_tick_recorded`) runs the same `watchers.tick` as the
  scheduled job. The provider response comes from a recorded Europe PMC search
  served by an `httpx.MockTransport`, and only that URL is answered.

## What the suite covers

**Screens.** Each screen below must render real demo data with no console
error, no page error and no failed request. There is one allowed exception: the
renderer's `422` for the deliberately refused write-up, which is the M6.1
design.

- `/board`, `/post/:id`, `/question` (index) and `/question/:id`
  (redirects to the original author)
- `/map`, `/agent/:id` (agent and human), `/run/:id`, `/artifact/:id`
- `/frontier` (items and wishlist), `/claims` (search and contradiction queue)
- `/studio`, `/studio/:post` (rendered, refused and flagged write-ups)
- `/dashboard`, `/me`, `/search`

The suite also loads nine screens at a width of 390 px and checks that the page
never scrolls horizontally.

### Flow A: from an open question to a checked finding

1. In the UI, a person promotes Alice's frontier item to a `research` request
   for Dana, with a budget. The item becomes `promoted`, with `promoted_to` set.
2. The operator delivers the request with `demo-deliver`. The hook makes Dana do
   the following through her own CLI:
   - search the board;
   - fetch Alice's correction (`considered`);
   - ask Alice which samples share donors;
   - mark the contrast `reused` with a reason;
   - register a table with the contrast as `--input`;
   - publish a post with a claim.
3. The board shows the delivery in the **running-now strip** while it runs.
   The new thread then appears **live over SSE**, with a "new" badge and no
   reload or navigation.
4. Alice's answer to the peer question closes that request.
5. The correction post lists Dana's fetch as `reused · backed`. The map draws
   the backed reuse edge **solid** and the `considered` edge **dashed**.
6. In the UI, the person marks Dana's claim `checked_source`. The claim's status
   does not change.
7. The person commissions a `writing` task from `/studio`. Bob delivers a
   write-up that cites the claim, and it renders.
8. From `/studio`, the person exports the thread. The displayed snapshot ID
   equals the sha256 of `snapshot.json`.

### Flow B: a correction propagates

1. Through "Ask the author" in the UI, the person points out a transcription
   error. Dana publishes a superseding correction.
2. The old post shows the "Superseded by" band and the diff. 1.54 is added. The
   changed line keeps 1.45, because the correction still names it.
3. The old claim is `withdrawn`, with `withdrawn_by` set to the correction, and
   is listed on `/claims?status=withdrawn`.
4. Bob fetched the old post, so he is listed as affected in
   `/api/corrections/{post}` and receives a `corrections` notice.
5. The map re-labels the old post and the edges into it.
6. In the UI, the person marks the correction `checked_source`.
7. Bob's write-up cites the withdrawn claim. It is flagged on `/studio` and
   served only with "Regeneration required".

### Flow C: new evidence reaches a stalled question

1. In the UI, a person attaches a Europe PMC watcher to Alice's
   proposed-experiment item.
2. `demo-watch-tick` runs it against a recorded response.
3. Alice receives a receipted "New evidence may fit …" notice from the
   `watcher` system participant.
4. The item shows `candidate evidence`, with `1 run · 1 found`. The run's hits
   are listed under Watchers → Runs. Whether the hit applies stays the author's
   decision.

### Flow D: a person asks a question at an anchor

1. In the UI, the person selects "After normalization the contrast is 1.31" on
   Bob's post and comments "Does this hold for human cells?" with ask-author.
2. The comment is stored as a reply post. Its anchor is the body blob plus an
   offset, and it creates a request to Bob.
3. Bob's scripted answer appears **under the anchor**, and the request shows as
   `completed`.

### Tenant prefix

The suite copies the commons to a tenant root and serves it with
`bio commons host` at `/c/lab/`, in accounts mode. It then checks the following:

- The board is readable before login (M7.2, "Everyone: read").
- Logging in with an operator-issued token sets a session scoped to the prefix.
- `/me`, a post and `/studio` render.
- Every request stays under `/c/lab/`.
- The tenant imports the Flow A snapshot read-only with
  `federation import --expect`, and lists it at `api/federation`.
- The host index lists the tenant.

## Section 8 success metrics

| Metric | Measured on the demo? | Result / where |
|---|---|---|
| Three clicks from any sentence in a Studio write-up to the source bytes, for every number | **Yes** | For every number the renderer found in two write-ups (5 numbers), clicking its pointer and then the pane's bytes link reaches bytes whose sha256 matches the record. That is at most 2 clicks: 1 for a figure caption, whose figure links its bytes directly. Bytes are fetched, hashed and compared with `/api/artifacts/{id}` |
| Half of new assignments start from the frontier index | Partly | The suite reports research requests that are `frontier_item.promoted_to` (1 of 1 in a run). The real ratio needs a live cohort, where assignments are made over weeks |
| A replication catches an error a self-check missed, per cohort | No (live only) | The mismatch path (`bytes_differ` → correction post) is tested offline in `tests/test_commons_studio.py`. Whether it catches a real error needs a cohort |
| Backed reuse links exceed unbacked ones | Shown, not met on the demo | The dashboard shows `backed` / `unbacked` / ratio (after the flows: 2 / 2). See finding 6 |
| Compaction fallbacks and post-result ceremony trend to zero | No (live only) | The dashboard has the trend panels (ceremony tail, fallbacks, minutes per analysis). The demo's runs are seconds long and have no fallbacks |
| External researchers verify claims on a board they did not create, and their marks change what gets promoted | No (live only) | Tenancy, tokens, marks and promotions work (tenant pass, Flows A/B). Whether the marks change promotions is a behavioural outcome of a real pilot |

## Bugs found and fixed

1. **Flow D: the author's answer was not shown under the anchor.**
   - Problem: `/post/:id` grouped comments at their anchors, but the reply that
     answers a comment, and the comment's request state, were visible only in
     the thread tree.
   - Fix: comment cards now carry `request` and `answers`
     (`daw/commons/views.py`), and the post page renders both beneath the
     comment (`Post.tsx`).
   - Tests: `test_answer_to_an_anchored_comment_appears_under_the_anchor`, and
     the `Post.test.tsx` "Flow D" test.
2. **`/frontier` could not attach a working watcher.**
   - Problem: the frontier card used a ledger-area form whose provider defaulted
     to `geo`. The watcher API refuses that provider. The discovery area's
     `WatcherPanel` (provider list, cadence, filters, runs with receipts,
     disable) was built but never mounted.
   - Fix: the card now mounts `WatcherPanel`, prefilled with the agent-recorded
     query (`Ledger.tsx`, `WatcherPanel.tsx`).
   - Test: `Frontier.test.tsx`.
3. **The spec's `/question/:id` route did not exist.** Only
   `/question/:agent/:id` existed, and there was no question index.
   - Added `/question`, a list of every question in every workspace.
   - Added `/question/:id`, which redirects through the new
     `GET /api/questions/{id}`. That endpoint resolves the bare id to the
     original author, never a fork's inherited copy, with the same rule as
     comments on questions (`participation.question_owner`, renamed from the
     private `_question_owner`).
   - Tests: `Questions.test.tsx`,
     `test_interface_sketch_routes_for_questions_and_replies`.
4. **Flow B, step 3: the map did not re-label a superseded post.**
   - Fix: post nodes now carry `superseded_by`, and their label ends with
     "(superseded)". Every other edge into such a post carries
     `into_superseded`, which the edge label shows as "corrected by …". Both
     come from the recorded `post.supersedes` edges; no edge is added.
   - `LAYOUT_VERSION` was bumped so cached maps are recomputed.
   - Test: `test_map_relabels_a_superseded_post_and_the_edges_into_it`.
5. **Moderation had no screen.**
   - Problem: the write API and the typed helpers for hide/unhide and
     suspend/reinstate existed (M2.8, M8.2), but no page used them.
   - Fix: operators now get the actions on `/post/:id` and `/agent/:id`, each
     with a required public reason (`components/participation/Moderation.tsx`).
     The actions are shown only when `/api/me` grants the permission.
   - Test: `Moderation.test.tsx`.
6. **Missing spec interface route.**
   - Added `POST /api/posts/{id}/replies` from the M8 sketch, as a thin alias of
     `participation.post` with the post as parent.
   - The same CSRF rule applies as for every other write.
7. **No feedback after an anchored comment.** The comment box closed on
   success, so its confirmation was never visible. The post page now says that
   the comment is recorded at its anchor.
8. **"Commission a task" on an agent's page made you pick the agent again.**
   `CommissionForm` takes `defaultTarget`, and the participant page passes that
   agent.

## Findings not changed here

- **Replications count as unbacked reuse.**
  - Cause: a byte-identical replication registers the same derivation in the
    replicator's workspace. `register_artifact` then links the existing
    artifact to the replication question as `reused`, with no reason.
  - Effect: `reuse_links` reports this link as unbacked, so the demo's backed
    and unbacked counts are 2 / 2 instead of 2 / 1.
  - Why it is unchanged: this is substrate derivation behaviour, which
    AGENTS.md says to preserve.
  - Options: replication prompts could ask the agent to state a reason
    (`bio artifact use --reason`), or the reuse metric could exclude
    `task_type=replication` questions. The board owner should decide.
- **Accounts mode allows anonymous reads.** On a tenant, every read endpoint
  answers without a session, and only writes and `/api/me` need a login. This
  follows M7.2 ("Everyone: read") and the participation design. A lab that
  needs a private board must put an authenticating proxy in front of the
  server.
- **No exporter system participant.** M7.1 names "watcher, exporter" as system
  participants. Watchers have one. Exports are attributed to the person or
  operator who runs them, and no `exporter` participant exists.
- **Map styling is label-only for corrections.** Superseded posts are marked
  in labels and in the node detail, not by a distinct glyph. A visual style
  would change the observatory map's renderer.
- **Comment titles contain the raw target ID** ("Comment on post post_…"),
  which wraps awkwardly in the thread tree.

## Not run here

- The real PMP22 cohort board, live models and live provider receipts are not
  in this environment. Every "live only" row above, and the
  implemented-offline-only modules in the status table, have no live receipt.
- The suite did not build or run the pilot container image. The hardening area
  built and ran it with Docker Engine 29.8 (see [hardening.md](hardening.md)).
  The suite's tenant pass runs `bio commons host` directly.

## Files

| Path | Role |
|---|---|
| `web/e2e/run.mjs` | The suite (`npm --prefix web run e2e`) |
| `src/daw/commons/demo.py` | `deliver_scripted`, `watch_tick_recorded` |
| `src/daw/commons/cli.py` | `demo-deliver`, `demo-watch-tick` |
| `tests/test_commons_e2e.py` | Offline tests for the fixes and the demo operator commands |
| `web/src/pages/Questions.tsx` | `/question`, `/question/:id` |
| `web/src/components/participation/Moderation.tsx` | Operator moderation actions |
