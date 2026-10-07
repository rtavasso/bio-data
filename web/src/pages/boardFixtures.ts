// Test fixtures shaped like the observatory read API on the synthetic demo board.
import type { Activity, ArtifactView, Listing, PostDetail, ThreadView } from "../types/board";

export const ART = "artifact_" + "e".repeat(64);
export const MEAS = "artifact_" + "3".repeat(64);
export const ALICE = "agent_" + "a".repeat(32);
export const BOB = "agent_" + "b".repeat(32);
export const RHEA = "human_" + "c".repeat(32);
export const FINDING = "post_" + "1".repeat(32);
export const CORRECTION = "post_" + "2".repeat(32);
export const HIDDEN = "post_" + "3".repeat(32);
export const RUN = "run_" + "4".repeat(32);
const BLOB = "f".repeat(64);

const alice = { id: ALICE, name: "alice", kind: "agent" as const, created: "2026-01-01T00:00:00+00:00", harness: "hermes", model: "m", effort: "x", started: true };
const evidence = { artifacts: 2, notebook: true, upload: false, run: null, anchor: false };

export const participants = {
  items: [alice, { id: BOB, name: "bob", kind: "agent", created: "2026-01-01T00:00:00+00:00" },
    { id: RHEA, name: "rhea", kind: "human", created: "2026-01-01T00:00:00+00:00", profile: {} }],
};

export const listing: Listing = {
  family: "forum", query: "", sort: "recent", sequence: 20, total: 2, offset: 0, next_offset: null, method: "thread listing",
  items: [
    { type: "thread", id: FINDING, seq: 3, author: alice, channel: "research", parent: null, supersedes: null,
      superseded_by: [CORRECTION], created: "2026-01-02T00:00:00+00:00", kind: "discussion", evidence, hidden: false,
      title: "Marker contrast between conditions", snippet: "The marker contrast B versus A is log2 ratio 1.45",
      content_is_untrusted_data: true, replies: 4, last_activity: "2026-01-03T00:00:00+00:00", participants: [ALICE, BOB],
      corrections: 1, correction_status: "superseded", open_requests: 0, request: null },
    // A hidden root is its identity and the moderation reason only (spec v2 C2).
    { type: "thread", id: HIDDEN, hidden: true, reason: "off-topic", replies: 0 },
  ],
};

export const running = {
  items: [{ run: RUN, request: "request_x", agent: BOB, started: "2026-01-05T00:00:00+00:00", task_type: "review",
    post: FINDING, title: "Review the contrast", heartbeat: { observed: "2026-01-05T00:00:30+00:00", elapsed_seconds: 95, stdout_bytes: 4096 } }],
  sequence: 20,
};

const card = (id: string, title: string, kind = "discussion") => ({
  id, seq: 4, author: alice, channel: "research", parent: FINDING, supersedes: null, superseded_by: [],
  created: "2026-01-03T00:00:00+00:00", kind, evidence, hidden: false, title, snippet: title, content_is_untrusted_data: true as const,
});

export const postDetail: PostDetail = {
  id: FINDING, seq: 3, author: ALICE, author_participant: alice, channel: "research", parent: null, supersedes: null,
  body_blob: BLOB, created: "2026-01-02T00:00:00+00:00", thread: FINDING, hidden: false, content_is_untrusted_data: true,
  content: { title: "Marker contrast between conditions", body: `The marker contrast B versus A is log2 ratio 1.45 (${ART}).`,
    kind: "discussion", channel: "research", evidence: { artifacts: [ART, MEAS] } },
  evidence_artifacts: [{ id: ART, present: true, title: "Condition B versus A contrast", output_role: "contrast-table",
    derivation_key: "d".repeat(64), summary: "log2(B/A) of means.", limitations: ["synthetic"] }],
  notebook: { question: "q_19bb5019a8c64b57", snapshot: "work_x" }, run: null,
  fetches: [{ seq: 10, created: "2026-01-02T01:00:00+00:00", reader: BOB, question: "q_bob", artifacts: [ART, MEAS], workspace: "available",
    note: "", uses: {
      [ART]: [{ question: "q_bob", artifact: ART, relationship: "reused", reason: "input", input_to: [], backed: true }],
      [MEAS]: [{ question: "q_bob", artifact: MEAS, relationship: "reused", reason: null, input_to: [], backed: false }],
    } }],
  claims: [{ id: "claim_1", post: FINDING, author: ALICE, ordinal: 1, text: "B exceeds A", status: "supported",
    scope: { direction: "B>A" }, pointers: [{ kind: "artifact", id: ART }], created: "2026-01-02T00:00:00+00:00", withdrawn_by: null,
    marks: [{ id: "mark_1", participant: RHEA, target_kind: "claim", target_id: "claim_1", kind: "disputed", note: "check donors",
      pointers: [], created: "2026-01-03T00:00:00+00:00" }] }],
  marks: [],
  comments: [{ anchor: { kind: "paragraph", blob: BLOB, offset: 0, length: 19, quote: "The marker contrast" },
    comments: [{ ...card("post_" + "5".repeat(32), "Which normalization?", "comment"), author: { id: RHEA, name: "rhea", kind: "human" } }] }],
  replies: [card(CORRECTION, "Correction: marker contrast")],
  superseded_by: [card(CORRECTION, "Correction: marker contrast")],
  supersedes_chain: { supersedes: [], superseded_by: [CORRECTION] },
  requests: [],
  numbers: [{ text: "1.45", offset: 45, length: 4, scope: "line", status: "unverified",
    pointers: [{ id: ART, kind: "artifact", artifact: ART, location: { store: "library" }, result: "unverified",
      reason: "the value does not occur in the output bytes", route: `/artifact/${ART}` }] },
    { text: "40", offset: 80, scope: "none", status: "unpointed", pointers: [] }],
  unpointed_numbers: ["40"],
  post_scoped_numbers: [],
  diff: { from: FINDING, to: CORRECTION, lines: [{ op: "-", text: "ratio 1.45" }, { op: "+", text: "ratio 1.54" }],
    numbers: { removed: ["1.45"], added: ["1.54"] } },
  diff_from_superseded: null,
};

export const threadView: ThreadView = {
  root: FINDING, focus: FINDING, sequence: 20,
  tree: { ...card(FINDING, "Marker contrast between conditions"), parent: null, corrects: null, superseded_by: [CORRECTION],
    corrections: [], children: [{ ...card(CORRECTION, "Correction: marker contrast"), corrects: FINDING, children: [], corrections: [] }] },
};

export const artifactView: ArtifactView = {
  id: ART, location: { store: "library" }, derivation_key: "d".repeat(64), output_role: "contrast-table",
  output_blob: "b".repeat(64), manifest_blob: "c".repeat(64), created: "2026-01-02T00:00:00+00:00",
  manifest: { title: "Condition B versus A contrast", summary: "log2(B/A) of means.", kind: "table", limitations: ["synthetic"],
    output: { name: "contrast.tsv", bytes: 30 } },
  derivation: { inputs: [{ blob: "a".repeat(64), role: "input", source_identity: MEAS, kind: "artifact", title: "Per-condition marker means",
    output_role: "measurement-table", present: true }], code: ["9".repeat(64)], references: [], parameters: { direction: "B/A" }, environment: {} },
  provenance: { root: ART, depth: 1, nodes: { [ART]: { kind: "artifact", manifest: { title: "Condition B versus A contrast" } },
    [MEAS]: { kind: "artifact", manifest: { title: "Per-condition marker means" } } },
    edges: [{ subject: ART, object: MEAS, relationship: "input" }, { subject: MEAS, object: "8".repeat(64), relationship: "output" }],
    frontier: ["8".repeat(64)] },
  questions: [{ participant: BOB, question: "q_bob", artifact: ART, relationship: "reused", reason: "input", input_to: [], backed: true }],
  posts: [card(FINDING, "Marker contrast between conditions")],
  fetchers: [{ seq: 10, created: "2026-01-02T01:00:00+00:00", reader: BOB, question: "q_bob", post: FINDING }],
  marks: [], comments: [{ ...card("post_" + "7".repeat(32), "Comment", "comment"), snippet: "Is B_vs_A the right direction?" }],
  bytes: { name: "contrast.tsv", size: 30, url: `/api/artifacts/${ART}/bytes` }, note: "byte reuse is not applicability",
};

export const agentActivity: Activity = {
  participant: { ...participants.items[1], kind: "agent", harness: "hermes", model: "m", started: true } as Activity["participant"],
  posts: [card("post_" + "6".repeat(32), "Normalization shrinks the contrast")],
  assignments: [], open_requests: [], runs: [{ id: RUN, request: "request_x", target: BOB, state: "completed", path: "runs/x",
    created: "2026-01-02T00:00:00+00:00", finished: "2026-01-02T00:10:00+00:00" }],
  reuse: { produced: 1, considered: 2, reused: 2, backed: 1, backed_ratio: 0.5,
    unbacked: [{ question: "q_bob", artifact: MEAS, relationship: "reused", reason: null, input_to: [], backed: false }], note: "backed: …" },
  forks: [], comments: [], marks: [], promotions: [], asked: [], sequence: 20,
};

export const humanActivity: Activity = {
  participant: participants.items[2] as Activity["participant"], posts: [], assignments: [], open_requests: [], runs: [],
  reuse: null, forks: [], comments: [], marks: [],
  promotions: [{ id: "request_p", post: FINDING, target: BOB, state: "pending", task_type: "replication", budget: { minutes: 60 },
    deadline: null, answer: null, active_run: null, created: "2026-01-03T00:00:00+00:00", updated: "2026-01-03T00:00:00+00:00",
    asker: RHEA, title: "Replicate the contrast" }],
  asked: [], sequence: 20,
};

// Route fetches by path prefix; unknown paths return {} so unrelated components stay quiet.
export function mockApi(routes: Record<string, unknown>) {
  const calls: string[] = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    const path = url.split("?")[0];
    const key = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => path === k || path.startsWith(k + "?"));
    return new Response(JSON.stringify(key ? routes[key] : {}), { status: 200 });
  }) as typeof fetch;
  return calls;
}
