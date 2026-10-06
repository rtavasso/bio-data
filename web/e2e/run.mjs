// Whole-system end-to-end check of Colloquy against a freshly built synthetic demo commons.
//
//   npm --prefix web run e2e            (or: node web/e2e/run.mjs)
//
// Builds `bio commons demo` + `demo-studio` in a scratch folder, builds the web app, serves it with
// `bio commons serve`, and drives every screen of the spec's section 5 in headless Chromium (no console
// errors allowed), then Flows A–D through the UI, the operator CLI (`bio commons demo-deliver`,
// `demo-watch-tick`: the scripted harness and a recorded provider response; no model, credential or
// network) and the live event stream, measures the section 8 metrics that the demo can show, and makes
// one pass through a tenant prefix (`bio commons host`, accounts mode, /c/<tenant>/).
//
// Output (ignored by git): web/e2e/.out/<run>/{screenshots/*.png, report.json, commons/, server logs}.
// Environment: E2E_OUT (output root), E2E_SKIP_BUILD=1 (reuse web/dist), E2E_CHROMIUM (browser binary),
// E2E_HEADED=1, PLAYWRIGHT_BROWSERS_PATH (default /opt/pw-browsers when present).
// Every number on the demo board is a synthetic fixture; nothing here validates science.
import { execFile, spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import { createRequire } from "node:module";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const run = promisify(execFile);
const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.resolve(here, "..");
const repo = path.resolve(web, "..");
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const out = path.resolve(process.env.E2E_OUT ?? path.join(here, ".out"), stamp);
const shots = path.join(out, "screenshots");
fs.mkdirSync(shots, { recursive: true });

// ---- harness ------------------------------------------------------------------------------------

function loadPlaywright() {
  const require = createRequire(import.meta.url);
  const roots = [...(process.env.NODE_PATH ?? "").split(path.delimiter), "/opt/node-tools/node_modules", "/usr/local/lib/node_modules"];
  for (const id of ["playwright", ...roots.filter(Boolean).map((r) => path.join(r, "playwright"))]) {
    try {
      return require(id);
    } catch {
      // try the next location
    }
  }
  throw new Error("playwright is not resolvable: install it globally or set NODE_PATH (the browsers must already be installed)");
}

if (!process.env.PLAYWRIGHT_BROWSERS_PATH && fs.existsSync("/opt/pw-browsers")) process.env.PLAYWRIGHT_BROWSERS_PATH = "/opt/pw-browsers";
const { chromium } = loadPlaywright();

const results = [];
const metrics = {};
let current = "setup";

function check(condition, message) {
  if (!condition) throw new Error(message);
}

async function step(name, fn) {
  current = name;
  const started = Date.now();
  try {
    const detail = await fn();
    results.push({ step: name, ok: true, ms: Date.now() - started, ...(detail === undefined ? {} : { detail }) });
    console.log(`  ok   ${name}`);
    return detail;
  } catch (error) {
    results.push({ step: name, ok: false, ms: Date.now() - started, error: String(error?.message ?? error).slice(0, 2000) });
    console.log(`  FAIL ${name}: ${String(error?.message ?? error).split("\n")[0]}`);
    return undefined;
  }
}

const childEnv = () => {
  const env = { ...process.env };
  delete env.BIO_AGENT;
  delete env.BIO_COMMUNITY;
  return env;
};

async function bio(...args) {
  const { stdout } = await run("uv", ["run", "--quiet", "bio", ...args], { cwd: repo, env: childEnv(), maxBuffer: 64 << 20 });
  const text = stdout.trim();
  return text ? JSON.parse(text.split("\n").at(-1)) : null;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

const servers = [];
async function startServer(args, log, health) {
  const handle = fs.openSync(log, "a");
  const child = spawn("uv", ["run", "--quiet", "bio", ...args], { cwd: repo, env: childEnv(), detached: true, stdio: ["ignore", handle, handle] });
  servers.push(child);
  for (let i = 0; i < 240; i++) {
    try {
      const response = await fetch(health);
      if (response.ok) return child;
    } catch {
      // not listening yet
    }
    if (child.exitCode !== null) break;
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`server did not start (see ${log})`);
}

function stopServers() {
  for (const child of servers) {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch {
      // already gone
    }
  }
}

// ---- setup: demo commons, web build, server -----------------------------------------------------

const commons = path.join(out, "commons");
console.log(`e2e output: ${out}`);
let ctx;
await step("build the synthetic demo commons (bio commons demo + demo-studio)", async () => {
  await bio("commons", "demo", commons);
  await bio("commons", "demo-studio", commons);
  ctx = JSON.parse(fs.readFileSync(path.join(commons, "demo-harness", "context.json"), "utf8"));
  return { agents: Object.keys(ctx.agents), studio: Object.keys(ctx.studio) };
});
if (!ctx) {
  fs.writeFileSync(path.join(out, "report.json"), JSON.stringify({ results }, null, 2));
  process.exit(1);
}
if (!process.env.E2E_SKIP_BUILD) {
  await step("build the web app (npm run build)", async () => {
    await run("npm", ["--prefix", web, "run", "build"], { cwd: repo, maxBuffer: 64 << 20 });
  });
}
const port = await freePort();
const base = `http://127.0.0.1:${port}`;
await step("start bio commons serve", async () => {
  await startServer(["commons", "--root", commons, "serve", "--port", String(port)], path.join(out, "serve.log"), `${base}/api/health`);
});

const api = async (p) => {
  const response = await fetch(base + p);
  check(response.ok, `GET ${p}: ${response.status}`);
  return response.json();
};
const A = ctx.agents;
const files = path.join(out, "fixtures");
fs.mkdirSync(files, { recursive: true });
const fixture = (name, text) => {
  const file = path.join(files, name);
  fs.writeFileSync(file, text);
  return file;
};

// The scripted agent answers with `answer`; `hook` is fixture Python run in its checkout first, calling
// only the agent's own CLI (./bin/bio), as a live agent's tool calls would.
async function deliver(request, answer, hook) {
  const args = ["commons", "--root", commons, "demo-deliver", request, "--answer", fixture(`${request}.md`, answer)];
  if (hook) args.push("--hook", fixture(`${request}.hook.py`, hook));
  const row = await bio(...args);
  check(row.state === "completed", `delivery of ${request} ended ${row.state}`);
  return row;
}

const HOOK_HEADER = `import json, os, subprocess
from pathlib import Path
trial = Path(os.environ.get("HERMES_CWD") or os.getcwd())
work = trial / "e2e"
work.mkdir(exist_ok=True)

def bio(*args):
    done = subprocess.run(["./bin/bio", *args], cwd=trial, capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"bio {args} failed: {done.stdout} {done.stderr}")
    return json.loads(done.stdout) if done.stdout.strip() else None
`;

async function pendingRequest(target, taskType) {
  const rows = (await api(`/api/requests?target=${target}&state=pending&task_type=${taskType}`)).items;
  check(rows.length >= 1, `no pending ${taskType} request for ${target}`);
  return rows.at(-1);
}

// ---- browser -------------------------------------------------------------------------------------

const browser = await chromium.launch({ headless: !process.env.E2E_HEADED, ...(process.env.E2E_CHROMIUM ? { executablePath: process.env.E2E_CHROMIUM } : {}) });
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
const problems = [];
// Expected non-2xx responses: the renderer's refusal of an unpointed write-up is a 422 by design (M6.1),
// and the browser logs every non-2xx resource as a console error.
const expected = [/\/api\/studio\/writeups\/[^ ]+ 422/, /status of 422/];
page.on("console", (m) => m.type() === "error" && problems.push({ step: current, text: m.text(), url: m.location()?.url }));
page.on("pageerror", (e) => problems.push({ step: current, text: `pageerror: ${e.message}` }));
page.on("response", (r) => r.status() >= 400 && problems.push({ step: current, text: `${r.url()} ${r.status()}` }));
const unexpected = (name) => problems.filter((p) => p.step === name && !expected.some((re) => re.test(`${p.text} ${p.url ?? ""}`)));

let shot = 0;
async function snap(name) {
  shot += 1;
  await page.screenshot({ path: path.join(shots, `${String(shot).padStart(2, "0")}-${name}.png`), fullPage: true });
}

async function screen(name, route, expectations, extra) {
  await step(`screen ${route}`, async () => {
    await page.goto(base + route, { waitUntil: "load" });
    for (const text of expectations) await page.getByText(text, { exact: false }).first().waitFor({ timeout: 15000 });
    if (extra) await extra();
    await page.waitForTimeout(400);
    await snap(name);
    const bad = unexpected(`screen ${route}`);
    check(!bad.length, `console/network errors: ${bad.map((b) => b.text).join(" | ")}`);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    return { overflow_px: overflow };
  });
}

const runs = (await api("/api/runs?limit=50")).items;
const posts = ctx.posts;

console.log("Screens (spec section 5)");
await screen("board", "/board", ["Running now", "Marker contrast between conditions"]);
await screen("post", `/post/${posts.correction}`, ["Corrects", "Numbers and their pointers", "Comments at anchors"]);
await screen("questions", "/question", ["Questions", "Does the demo marker change between conditions?"]);
await screen("question", `/question/${ctx.questions.dana}`, ["Research notebook", "Hypothesis network", "Evidence coverage"], async () => {
  check(page.url().includes(`/question/${A.dana}/${ctx.questions.dana}`), `bare question id did not open dana's question: ${page.url()}`);
});
await screen("map", "/map", ["Only recorded relations are drawn"], async () => {
  await page.getByText(/\d+ nodes, \d+ edges/).first().waitFor();
  check(await page.locator(".map svg, .map canvas, svg, canvas").count() > 0, "no graph drawn");
});
await screen("agent", `/agent/${A.alice}`, ["Deliveries", "Assignments"]);
await screen("human", `/agent/${ctx.participation.human}`, ["Promotions and commissions", "Marks"]);
await screen("run", `/run/${runs.find((r) => r.task_type === "review")?.id ?? runs[0].id}`, ["Timeline", "Analysis receipts"]);
await screen("artifact", `/artifact/${ctx.artifacts.contrast}`, ["Output bytes", "Provenance"]);
await screen("frontier", "/frontier", [], async () => {
  await page.getByRole("heading", { name: /Proposed experiments/ }).waitFor();
  await page.getByRole("heading", { name: /Gaps/ }).waitFor();
});
await screen("frontier-wishlist", "/frontier?tab=wishlist", ["Donor identity per sample"]);
await screen("claims", "/claims", ["Contradiction queue", "Synthetic series GSE000001"]);
await screen("claims-queue", "/claims?tab=queue", ["GSE000001"]);
await screen("studio", "/studio", ["Regeneration flags", "Write-ups"]);
await screen("writeup", `/studio/${ctx.studio.writeup}`, ["all pointed", "Evidence map of the cited records"]);
await screen("writeup-refused", `/studio/${ctx.studio.refused}`, ["Not served"]);
await screen("writeup-flagged", `/studio/${ctx.studio.flagged}`, ["Regeneration required"]);
await screen("dashboard", "/dashboard", ["Evaluation dashboard", "backed"]);
await screen("me", "/me", ["local single-user mode", "Verification marks"]);
await screen("search", "/search?q=normalization", ["Normalization shrinks the contrast", "results"]);

// ---- Flow A ----------------------------------------------------------------------------------------

console.log("Flow A: open question to a published, checked finding");
const itemA = ctx.frontier.items["alice-donors"];
let requestA;
await step("A1 promote a frontier item with a budget (UI) -> typed request", async () => {
  await page.goto(`${base}/frontier`);
  const card = page.getByLabel(`Frontier item ${itemA}`);
  await card.getByRole("button", { name: "Promote" }).click();
  const form = card.locator("form");
  await form.getByLabel("Task type").selectOption("research");
  await form.getByLabel("Target participant").locator("option", { hasText: "dana" }).waitFor({ state: "attached" });
  await form.getByLabel("Target participant").selectOption({ label: "dana" });
  await form.getByLabel("Minutes").fill("30");
  await form.getByLabel("Note").fill("E2E: test donor structure on the corrected contrast.");
  await form.getByRole("button", { name: "Promote" }).click();
  await card.getByText("Promoted to an assignment.").waitFor();
  await snap("flowA-promoted");
  const item = await api(`/api/frontier/${itemA}`);
  check(item.status === "promoted" && item.promoted_to, `item status ${item.status}`);
  requestA = (await api(`/api/requests?target=${A.dana}&task_type=research`)).items.find((r) => r.id === item.promoted_to);
  check(requestA && requestA.state === "pending", "promoted request missing");
  check(JSON.stringify(requestA.budget).includes("30"), `budget ${JSON.stringify(requestA.budget)}`);
  return { request: requestA.id, task_type: requestA.task_type, budget: requestA.budget };
});

const hookA = `${HOOK_HEADER}
Q, PEER_POST, PEER, ARTIFACT = ${JSON.stringify(ctx.questions.dana)}, ${JSON.stringify(posts.correction)}, "alice", ${JSON.stringify(ctx.artifacts.contrast)}
bio("community", "search", "--text", "contrast")
bio("community", "fetch", PEER_POST, "--question", Q)                      # considered
(work / "ask.md").write_text("Which samples share donors in your contrast table?")
bio("community", "ask", PEER, "--body", str(work / "ask.md"), "--reply-to", PEER_POST)
bio("artifact", "use", ARTIFACT, "--question", Q, "--reason", "its B_vs_A row is the input to the donor check")
(work / "donor_check.py").write_text("# synthetic donor check (fixture; never executed)\\n")
(work / "donor-check.tsv").write_text("contrast\\tlog2_ratio\\tdonor_structure\\nB_vs_A\\t1.54\\tunknown\\n")
made = bio("register", str(work / "donor-check.tsv"), "--question", Q, "--input", ARTIFACT, "--code", str(work / "donor_check.py"),
           "--title", "Donor check of the demo contrast", "--summary", "Synthetic e2e fixture.", "--output-role", "donor-check-table")
(work / "claims.json").write_text(json.dumps([{"text": "The contrast log2(B/A) = 1.45 carries no recorded donor structure.",
    "status": "descriptive", "scope": {"species": "synthetic", "endpoint": "marker log2 ratio"},
    "pointers": [{"kind": "artifact", "id": made["artifact"]}, {"kind": "post", "id": PEER_POST}]}]))
(work / "post.md").write_text(f"Donor check: the contrast 1.45 ({made['artifact']}) has no recorded donor structure.\\n\\nSynthetic e2e fixture.")
bio("community", "publish", "E2E donor check of the demo contrast", "--body", str(work / "post.md"), "--artifact", made["artifact"],
    "--question", Q, "--claims", str(work / "claims.json"), "--key", "e2e-flow-a")
`;
let postA;
await step("A2 deliver with the scripted harness via the operator CLI; the new post arrives live over SSE", async () => {
  await page.goto(`${base}/board`);
  await page.getByText("Running now").waitFor();
  let navigations = 0;
  const count = (frame) => frame === page.mainFrame() && (navigations += 1);
  page.on("framenavigated", count);
  const delivery = deliver(requestA.id, "Published the donor check. Next computable step: record donor identity.", hookA);
  // M4.6: while the turn runs, the running-now strip lists the delivery (from delivery_started over SSE).
  const strip = page.getByLabel("Running now");
  const running = strip.getByText("research", { exact: true }).waitFor({ timeout: 60000 }).then(() => true, () => false);
  const card = page.getByLabel("E2E donor check of the demo contrast");
  await card.waitFor({ timeout: 90000 });
  await card.getByText("new", { exact: true }).waitFor();
  await delivery;
  metrics.running_strip_showed_delivery = await running;
  check(metrics.running_strip_showed_delivery, "the running-now strip never listed the active delivery");
  await strip.getByText("No deliveries running.").waitFor({ timeout: 30000 });
  page.off("framenavigated", count);
  check(navigations === 0, "the board navigated instead of updating live");
  await snap("flowA-live-post");
  const listing = (await api(`/api/posts?author=${A.dana}`)).items.find((t) => t.title === "E2E donor check of the demo contrast");
  postA = listing.id;
  const done = (await api(`/api/requests?target=${A.dana}&task_type=research`)).items.find((r) => r.id === requestA.id);
  check(done.state === "completed" && done.answer, "promoted request not completed");
  return { post: postA, answer: done.answer };
});

await step("A3 peer question: the agent asked its peer; the peer's answer closes the request", async () => {
  const asked = await pendingRequest(A.alice, "question");
  await deliver(asked.id, "Donor identity is not recorded in the synthetic table; independence cannot be assumed.");
  const closed = (await api(`/api/requests?target=${A.alice}&task_type=question`)).items.find((r) => r.id === asked.id);
  check(closed.state === "completed" && closed.answer, "peer question not answered");
  return { request: asked.id, answer: closed.answer };
});

let claimA;
await step("A4 post, claims, backed reuse and map edge are visible", async () => {
  await page.goto(`${base}/post/${postA}`);
  await page.getByText("carries no recorded donor structure").first().waitFor();
  const detail = await api(`/api/posts/${postA}`);
  check(detail.claims.length === 1, "claim missing");
  claimA = detail.claims[0].id;
  check(detail.numbers.some((n) => n.text === "1.45" && n.pointers.length), "number without pointer");
  await page.goto(`${base}/post/${posts.correction}`);
  await page.getByText("reused · backed").first().waitFor();
  const map = await api(`/api/map?participant=${A.dana}`);
  const edge = map.edges.find((e) => e.relation === "reused" && e.target === ctx.artifacts.contrast && e.source.includes(A.dana));
  check(edge && edge.backed && edge.style === "solid", "backed reuse is not a solid recorded edge");
  const considered = map.edges.find((e) => e.relation === "considered" && e.target === ctx.artifacts.contrast && e.source.includes(A.dana));
  check(considered && considered.style === "dashed", "considered edge is not dashed");
  await snap("flowA-backed-reuse");
  return { claim: claimA, edge: edge.id };
});

await step("A5 mark a claim checked_source (UI)", async () => {
  await page.goto(`${base}/post/${postA}`);
  await page.getByText("Mark this claim").click();
  const form = page.locator("details[open] form").first();
  await form.getByLabel("Mark kind").selectOption("checked_source");
  await form.getByLabel("Note").fill("Opened the donor-check table: the B_vs_A row is 1.54.");
  await form.getByLabel("Pointers").fill(`artifact:${(await api(`/api/posts/${postA}`)).content.evidence.artifacts[0]}`);
  await form.getByRole("button", { name: "Mark" }).click();
  await page.getByText("Mark recorded (attribution, not status).").waitFor();
  const marks = (await api(`/api/marks?target_kind=claim&target_id=${claimA}`)).items;
  check(marks.length === 1 && marks[0].kind === "checked_source", "mark not recorded");
  const claim = (await api(`/api/claims?post=${postA}`)).items[0];
  check(claim.status === "descriptive", "a mark changed the claim's status");
  await snap("flowA-marked");
});

let writeupA;
await step("A6 commission a writing task (UI) -> request(type=writing); delivered write-up renders", async () => {
  await page.goto(`${base}/studio`);
  const form = page.locator("form").filter({ has: page.getByLabel("Commission type") }).first();
  await form.getByLabel("Commission type").selectOption("writing");
  await form.getByLabel("Target participant").locator("option", { hasText: "bob" }).waitFor({ state: "attached" });
  await form.getByLabel("Target participant").selectOption({ label: "bob" });
  await form.getByLabel("Minutes").fill("20");
  await form.getByLabel("Scope").fill(`Plain-language note on the donor check ${postA}.`);
  await form.getByRole("button", { name: "Commission" }).click();
  await page.getByText("Commissioned.").waitFor();
  const request = await pendingRequest(A.bob, "writing");
  const fetchHook = `${HOOK_HEADER}
q = bio("work", "new", "Write up the donor check")["question"]
bio("community", "fetch", ${JSON.stringify(postA)}, "--question", q)
`;
  const artifact = (await api(`/api/posts/${postA}`)).content.evidence.artifacts[0];
  const done = await deliver(request.id, `# The donor check in brief\n\nThe donor check reports log2(B/A) = [1.45](${claimA}) with no recorded donor structure [${artifact}].\n\nSynthetic e2e fixture.`, fetchHook);
  writeupA = done.answer;
  await page.goto(`${base}/studio/${writeupA}`);
  await page.getByText(/all pointed/).waitFor();
  await snap("flowA-writeup");
  return { request: request.id, task_type: request.task_type, writeup: writeupA };
});

await step("metric: three clicks from any sentence in a Studio write-up to the source bytes", async () => {
  // For every number the renderer found in a write-up: click the pointer that covers it in its sentence
  // (click 1), then the bytes link in the detail pane (click 2); the bytes must hash to the recorded sha256.
  const checked = [];
  for (const writeup of [ctx.studio.writeup, writeupA]) {
    const rendered = await api(`/api/studio/writeups/${writeup}`);
    await page.goto(`${base}/studio/${writeup}`);
    await page.locator(".st-sentence").first().waitFor();
    for (const sentence of rendered.blocks.flatMap((b) => b.sentences ?? [])) {
      for (const number of sentence.numbers) {
        const target = number.covered_by[0];
        check(target, `number ${number.text} has no pointer`);
        let pointer = page.locator(`#sentence-${sentence.id} [data-pointer="${target}"]`).first();
        if (!(await pointer.count())) pointer = page.locator(`[data-pointer="${target}"]`).first();
        let bytes, clicks = 2;
        if (await pointer.count()) {
          await pointer.click();                                                    // click 1
          bytes = page.getByLabel("Pointer detail").getByRole("link", { name: /bytes/i }).first();
        } else {
          // A figure caption's number: the figure itself links its artifact's bytes (one click).
          bytes = page.locator("figure.st-figure", { hasText: number.text }).getByRole("link", { name: /bytes/i }).first();
          clicks = 1;
        }
        check(await bytes.count() || (await bytes.waitFor({ timeout: 5000 }).then(() => true, () => false)),
          `no bytes link for ${number.text} (${target})`);                          // the last click follows this link
        const href = await bytes.getAttribute("href");
        const response = await page.request.get(new URL(href, base).href);
        check(response.ok(), `bytes ${href}: ${response.status()}`);
        const sha = crypto.createHash("sha256").update(await response.body()).digest("hex");
        const artifactId = decodeURIComponent(href.match(/artifacts\/([^/]+)\/bytes/)?.[1] ?? "");
        if (artifactId) {
          const record = await api(`/api/artifacts/${artifactId}`);
          check(JSON.stringify(record).includes(sha), `bytes of ${artifactId} do not match its recorded sha256`);
        }
        checked.push({ writeup, number: number.text, pointer: target, clicks, bytes: href, sha256: sha });
      }
    }
  }
  check(checked.length >= 3, "too few numbers checked");
  metrics.three_clicks = { numbers_checked: checked.length, max_clicks: Math.max(...checked.map((c) => c.clicks)), checked };
  return { numbers: checked.length, max_clicks: metrics.three_clicks.max_clicks };
});

let snapshotId;
await step("M6.5 export the Flow A thread as a static, content-addressed snapshot (UI)", async () => {
  await page.goto(`${base}/studio`);
  const form = page.getByRole("form", { name: "Export" });
  await form.getByLabel("Export scope").selectOption("thread");
  await form.getByLabel("Export subject").fill(postA);
  await form.getByRole("button", { name: "Export static snapshot" }).click();
  const status = form.getByRole("status");
  await status.getByText(/Snapshot/).waitFor({ timeout: 60000 });
  snapshotId = (await status.locator(".mono").innerText()).trim();
  check(/^[0-9a-f]{64}$/.test(snapshotId), `not a sha256 snapshot id: ${snapshotId}`);
  const exported = await api("/api/exports");
  check(JSON.stringify(exported).includes(snapshotId), "export not listed");
  const folder = path.join(commons, "exports", snapshotId);
  const manifest = fs.readFileSync(path.join(folder, "snapshot.json"));
  check(crypto.createHash("sha256").update(manifest).digest("hex") === snapshotId, "snapshot id is not the sha256 of snapshot.json");
  check(fs.readFileSync(path.join(folder, "index.html"), "utf8").includes("E2E donor check"), "exported site lacks the thread");
  return { snapshot: snapshotId };
});

// ---- Flow B ----------------------------------------------------------------------------------------

console.log("Flow B: a correction propagates");
let correctionB;
await step("B1 ask the author (UI); the author publishes a superseding correction", async () => {
  await page.goto(`${base}/post/${postA}`);
  await page.getByText("Ask the author").click();
  await page.getByLabel("Question").fill("The prose says 1.45 but the donor-check table row is 1.54; which is right?");
  await page.getByRole("button", { name: "Ask" }).click();
  await page.getByText("Question queued.").waitFor();
  const asked = await pendingRequest(A.dana, "question");
  const artifact = (await api(`/api/posts/${postA}`)).content.evidence.artifacts[0];
  const hook = `${HOOK_HEADER}
OLD, ARTIFACT, Q = ${JSON.stringify(postA)}, ${JSON.stringify(artifact)}, ${JSON.stringify(ctx.questions.dana)}
(work / "claims-b.json").write_text(json.dumps([{"text": "The contrast log2(B/A) = 1.54 carries no recorded donor structure.",
    "status": "descriptive", "scope": {"species": "synthetic", "endpoint": "marker log2 ratio"},
    "pointers": [{"kind": "artifact", "id": ARTIFACT}]}]))
(work / "correction.md").write_text(f"Correction: the contrast is 1.54, not 1.45 ({ARTIFACT}).\\n\\nSynthetic e2e fixture.")
bio("community", "publish", "Correction: E2E donor check", "--body", str(work / "correction.md"), "--artifact", ARTIFACT,
    "--question", Q, "--claims", str(work / "claims-b.json"), "--supersedes", OLD, "--reply-to", OLD, "--key", "e2e-flow-b")
`;
  await deliver(asked.id, "A transcription error: the table says 1.54. Corrected in a superseding post.", hook);
  correctionB = (await api(`/api/posts/${postA}`)).superseded_by[0]?.id;
  check(correctionB, "no superseding post");
  return { correction: correctionB };
});

await step("B2 superseded band and the diff show which numbers changed", async () => {
  await page.goto(`${base}/post/${postA}`);
  await page.getByText(/Superseded by/).first().waitFor();
  await page.getByRole("button", { name: /Show (diff|changes)/ }).first().click();
  // 1.54 is added; 1.45 is still named by the correction, so it is not a removed number, but its line changed.
  await page.locator(".diff-numbers ins", { hasText: "1.54" }).first().waitFor();
  await page.locator(".diff-del", { hasText: "1.45" }).first().waitFor();
  await page.locator(".diff-add", { hasText: "1.54, not 1.45" }).first().waitFor();
  await snap("flowB-superseded-diff");
});

await step("B3 the ledger claim is withdrawn with a pointer to the replacement", async () => {
  const claim = (await api(`/api/claims?post=${postA}&status=withdrawn`)).items.find((c) => c.id === claimA);
  check(claim && claim.withdrawn_by === correctionB, "claim not withdrawn by the correction");
  await page.goto(`${base}/claims?status=withdrawn`);
  await page.getByLabel(`Claim ${claimA}`).waitFor();
  await snap("flowB-withdrawn-claim");
});

await step("B4 readers who fetched the old post are affected and receive a system notice", async () => {
  const report = await api(`/api/corrections/${postA}`);
  const text = JSON.stringify(report);
  check(text.includes(A.bob), "bob (who fetched the post) is not listed as affected");
  const notices = (await api(`/api/requests?target=${A.bob}&task_type=notice`)).items;
  check(notices.length >= 1, "no notice request to bob");
  await page.goto(`${base}/post/${correctionB}`);
  await page.getByText("A post you fetched was superseded").first().waitFor();
  return { affected: report.affected ?? report.readers ?? null };
});

await step("B5 the map re-labels the superseded post; a person marks the correction checked_source", async () => {
  const map = await api(`/api/map?participant=${A.dana}`);
  check(map.edges.some((e) => e.relation === "supersedes" && e.source === correctionB && e.target === postA), "no supersedes edge");
  check(map.nodes.find((n) => n.id === postA)?.superseded_by?.includes(correctionB), "old post not re-labelled superseded");
  const full = await api("/api/map?limit=10000");
  const fetched = full.edges.find((e) => e.relation === "fetched" && e.target === postA && e.source === A.bob);
  check(fetched?.into_superseded?.includes(correctionB), "the reader's fetch edge into the old post is not re-labelled");
  await page.goto(`${base}/post/${correctionB}`);
  await page.locator("summary", { hasText: /^Mark$/ }).click();
  const form = page.locator("details[open] form").first();
  await form.getByLabel("Note").fill("The table row reads 1.54, as the correction states.");
  await form.getByRole("button", { name: "Mark" }).click();
  await page.getByText("Mark recorded (attribution, not status).").waitFor();
  const marks = (await api(`/api/marks?target_kind=post&target_id=${correctionB}`)).items;
  check(marks.some((m) => m.kind === "checked_source"), "correction mark missing");
});

await step("B6 the write-up citing the withdrawn claim is flagged for regeneration in Studio", async () => {
  const response = await fetch(`${base}/api/studio/writeups/${writeupA}`);
  const rendered = await response.json();
  check(response.status === 200 && rendered.regeneration_required, "write-up not flagged");
  await page.goto(`${base}/studio`);
  await page.getByText("Regeneration flags").waitFor();
  const overview = await api("/api/studio");
  check(overview.regeneration_flags.some((f) => f.post === writeupA), "flag missing from /studio");
  await page.goto(`${base}/studio/${writeupA}`);
  await page.getByText("Regeneration required").first().waitFor();
  await snap("flowB-regeneration");
});

// ---- Flow C ----------------------------------------------------------------------------------------

console.log("Flow C: new evidence reaches a stalled question");
const itemC = ctx.frontier.items["alice-qpcr"];
await step("C1 attach a watcher query to a frontier item (UI)", async () => {
  await page.goto(`${base}/frontier`);
  const card = page.getByLabel(`Frontier item ${itemC}`);
  await card.getByRole("button", { name: "Watchers" }).click();
  const form = card.getByRole("form", { name: "Attach a watcher query" });
  await form.getByLabel("Provider").locator("option", { hasText: "europepmc" }).waitFor({ state: "attached" });
  await form.getByLabel("Watcher query").fill("demo marker qPCR donor-matched");
  await form.getByLabel("Provider").selectOption("europepmc");
  await form.getByRole("button", { name: "Attach watcher" }).click();
  await card.getByText(/Watcher attached/).waitFor();
  const watchers = (await api(`/api/watchers?item=${itemC}`)).items;
  check(watchers.length === 1 && watchers[0].provider === "europepmc", "watcher not recorded");
  return { watcher: watchers[0].id };
});

await step("C2 a watcher tick with a recorded provider response posts a receipted candidate to the author", async () => {
  const response = fixture("europepmc.json", JSON.stringify({ hitCount: 1, resultList: { result: [
    { id: "E2E0001", source: "SYNTHETIC", title: "Donor-matched qPCR of the demo marker (synthetic e2e fixture)", pubYear: "2026" }] } }));
  const tick = await bio("commons", "--root", commons, "demo-watch-tick", "--response", response);
  const ran = tick.ran.find((r) => r.new?.includes("E2E0001"));
  check(ran && ran.notice && ran.receipt_blob, "tick produced no receipted notice");
  check(ran.notice.target === A.alice && ran.notice.task_type === "notice", "notice not addressed to the author");
  return { run: ran.run, notice: ran.notice.post, receipt: ran.receipt_blob };
});

await step("C3 the frontier shows candidate evidence; applicability stays with the author", async () => {
  await page.goto(`${base}/frontier`);
  const card = page.getByLabel(`Frontier item ${itemC}`);
  await card.getByText("candidate evidence").first().waitFor();
  await card.getByText(/1 run · 1 found/).waitFor();
  await card.getByRole("button", { name: "Watchers" }).click();
  await card.getByRole("button", { name: "Runs" }).click();
  await card.getByText("E2E0001").waitFor();
  await snap("flowC-candidate");
  const item = await api(`/api/frontier/${itemC}`);
  check(item.status === "candidate_evidence", `status ${item.status}`);
  await page.goto(`${base}/board`);
  await page.getByText(`New evidence may fit ${itemC}`).first().waitFor();
});

// ---- Flow D ----------------------------------------------------------------------------------------

console.log("Flow D: a person asks a question at an anchor");
const postD = posts.reply;
const quote = "After normalization the contrast is 1.31";
let commentD;
await step("D1 highlight a sentence and comment with ask-author (UI)", async () => {
  await page.goto(`${base}/post/${postD}`);
  await page.getByText(quote).first().waitFor();
  await page.evaluate((text) => {
    const roots = [...document.querySelectorAll(".markdown")];
    for (const root of roots) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const at = node.data.indexOf(text);
        if (at >= 0) {
          const range = document.createRange();
          range.setStart(node, at);
          range.setEnd(node, at + text.length);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
          root.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
          return;
        }
      }
    }
    throw new Error("quote not found");
  }, quote);
  const box = page.getByLabel("Comment at anchor");
  await box.locator("blockquote", { hasText: quote }).waitFor();
  await box.getByLabel("Comment").fill("Does this hold for human cells?");
  check(await box.getByRole("checkbox").isChecked(), "ask-author is not the default");
  await box.getByRole("button", { name: "Comment" }).click();
  await page.getByText("Comment recorded at its anchor").waitFor();
  await page.locator(".comment-groups").getByText("Does this hold for human cells?").waitFor();
  const detail = await api(`/api/posts/${postD}`);
  const group = detail.comments.find((g) => g.anchor?.quote === quote);
  check(group, "comment not stored at the anchor");
  commentD = group.comments.at(-1);
  check(commentD.request?.state === "pending" && commentD.request.target === A.bob, "comment did not create a request to the author");
  check(group.anchor.blob === detail.body_blob && Number.isInteger(group.anchor.offset), "anchor is not a locator into the body blob");
  return { comment: commentD.id, request: commentD.request.id, anchor: group.anchor };
});

await step("D2 the author answers in its next turn; the answer appears under the anchor and closes the request", async () => {
  await deliver(commentD.request.id, "Not tested: the synthetic table has no human cells, so the normalized contrast says nothing about them.");
  await page.goto(`${base}/post/${postD}`);
  const answer = page.getByLabel("Answer to this comment").filter({ hasText: "no human cells" });
  await answer.waitFor();
  const detail = await api(`/api/posts/${postD}`);
  const card = detail.comments.flatMap((g) => g.comments).find((c) => c.id === commentD.id);
  check(card.request.state === "completed" && card.answers.length === 1, "request not closed by the answer");
  await snap("flowD-answer-under-anchor");
});

// ---- metrics and tenant smoke ---------------------------------------------------------------------

await step("metric: backed vs unbacked reuse links (dashboard)", async () => {
  const dashboard = await api("/api/dashboard");
  const reuse = dashboard.summary?.board?.reuse;
  check(reuse && Number.isInteger(reuse.backed) && Number.isInteger(reuse.unbacked), "dashboard reports no reuse counts");
  metrics.reuse = { ...reuse, backed_exceeds_unbacked: reuse.backed > reuse.unbacked };
  await page.goto(`${base}/dashboard`);
  await page.getByText(/backed/i).first().waitFor();
  await snap("dashboard-after-flows");
  return metrics.reuse;
});

await step("metric: assignments that started from the frontier index", async () => {
  const typed = [];
  for (const type of ["research", "review", "replication", "scouting", "writing", "digest"]) {
    typed.push(...(await api(`/api/requests?task_type=${type}`)).items);
  }
  const frontier = (await api("/api/frontier?status=all")).items.filter((i) => i.promoted_to).map((i) => i.promoted_to);
  const research = typed.filter((r) => r.task_type === "research");
  metrics.frontier_start = { research_assignments: research.length, from_frontier: research.filter((r) => frontier.includes(r.id)).length };
  return metrics.frontier_start;
});

await step("narrow width (390 px): screens render without horizontal page scroll", async () => {
  const narrow = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const report = {};
  for (const route of ["/board", `/post/${posts.correction}`, "/frontier", "/claims", "/studio", "/dashboard", "/me", "/map", "/question"]) {
    await narrow.goto(base + route, { waitUntil: "load" });
    await narrow.waitForTimeout(1200);
    report[route] = await narrow.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  }
  await narrow.screenshot({ path: path.join(shots, "narrow-last.png"), fullPage: true });
  await narrow.close();
  metrics.narrow_overflow_px = report;
  const over = Object.entries(report).filter(([, px]) => px > 1);
  check(!over.length, `horizontal overflow: ${over.map(([r, px]) => `${r} ${px}px`).join(", ")}`);
  return report;
});

console.log("Tenant prefix smoke pass (bio commons host, accounts mode)");
await step("tenant: /c/<tenant>/ login with a token, board, post and API under the prefix", async () => {
  const tenantRoot = path.join(out, "tenant", "lab");
  fs.cpSync(commons, tenantRoot, { recursive: true });
  const issued = await bio("commons", "--root", tenantRoot, "token", "create", "mira", "--label", "e2e");
  const config = fixture("tenants.toml", `[host]\nstatic_dir = ${JSON.stringify(path.join(web, "dist"))}\n\n[tenants.lab]\nroot = ${JSON.stringify(tenantRoot)}\ntitle = "E2E lab"\n`);
  const hostPort = await freePort();
  const host = `http://127.0.0.1:${hostPort}`;
  await startServer(["commons", "host", "--config", config, "--port", String(hostPort)], path.join(out, "host.log"), `${host}/api/health`);
  const tenantPage = await context.newPage();
  const seen = [];
  tenantPage.on("response", (r) => seen.push([r.url(), r.status()]));
  tenantPage.on("pageerror", (e) => seen.push([`pageerror ${e.message}`, 0]));
  // Reading is open to everyone (M7.2); acting needs a session from an operator-issued token.
  await tenantPage.goto(`${host}/c/lab/`, { waitUntil: "load" });
  await tenantPage.getByText("Marker contrast between conditions").first().waitFor({ timeout: 20000 });
  await tenantPage.goto(`${host}/c/lab/login`, { waitUntil: "load" });
  await tenantPage.getByLabel("Token").fill(issued.token);
  await tenantPage.getByRole("button", { name: /log in/i }).click();
  await tenantPage.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 20000 });
  check(tenantPage.url().startsWith(`${host}/c/lab/`), `left the prefix: ${tenantPage.url()}`);
  await tenantPage.goto(`${host}/c/lab/me`, { waitUntil: "load" });
  await tenantPage.getByText("mira", { exact: false }).first().waitFor();
  const me = await tenantPage.evaluate(async () => (await fetch("api/me")).status);
  check(me === 200, `session not established under the prefix (api/me ${me})`);
  await tenantPage.goto(`${host}/c/lab/post/${posts.correction}`, { waitUntil: "load" });
  await tenantPage.getByText("Numbers and their pointers").waitFor();
  await tenantPage.goto(`${host}/c/lab/studio`, { waitUntil: "load" });
  await tenantPage.getByText("Regeneration flags").waitFor();
  await tenantPage.screenshot({ path: path.join(shots, "tenant-studio.png"), fullPage: true });
  const outside = seen.filter(([url]) => url.startsWith(host) && !url.startsWith(`${host}/c/lab/`));
  check(!outside.length, `requests outside the tenant prefix: ${outside.map(([u]) => u).join(", ")}`);
  const failed = seen.filter(([url, status]) => status >= 400 && !/\/api\/me\b/.test(url) || status === 0);
  check(!failed.length, `failed responses: ${failed.map(([u, s]) => `${u} ${s}`).join(", ")}`);
  // Federation is read-only: the tenant imports the exported snapshot, verified by hash, as foreign data.
  if (snapshotId) {
    await bio("commons", "--root", tenantRoot, "federation", "import", path.join(commons, "exports", snapshotId), "--expect", snapshotId);
    const federated = await tenantPage.evaluate(async () => (await fetch("api/federation")).json());
    check(JSON.stringify(federated).includes(snapshotId), "imported snapshot not listed under the tenant");
  }
  const index = await (await fetch(`${host}/`)).text();
  check(index.includes("/c/lab/"), "tenant index does not list the tenant");
  await tenantPage.close();
  return { requests: seen.length };
});

await browser.close();
stopServers();

const failed = results.filter((r) => !r.ok);
const report = { started: stamp, base, commons, results, metrics, console_problems: problems,
  passed: results.length - failed.length, failed: failed.length,
  note: "Synthetic demo commons; the scripted harness stands in for agents. No model, credential or network was used." };
fs.writeFileSync(path.join(out, "report.json"), JSON.stringify(report, null, 2));
console.log(`\n${report.passed} passed, ${report.failed} failed · screenshots and report.json in ${out}`);
process.exit(failed.length ? 1 : 0);
