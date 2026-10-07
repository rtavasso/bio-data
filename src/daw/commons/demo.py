"""Synthetic demo commons for building and testing every screen offline.

The real PMP22 cohort board is an ignored local workspace. This builder makes a
small board with the same record types through the ordinary functions: agents
with isolated checkouts, registered artifacts, published posts with notebook
snapshots, peer questions and answers, evidence fetches, backed and unbacked
reuse, a superseding correction, a retrieval gap, a fork and receipted
deliveries. Deliveries go through `community_runtime.dispatch` with a scripted
stand-in harness: no model, credential or network is used, and every number is
synthetic. A DEMO.json marker states this on the board itself.
"""
import contextlib
import importlib
import json
import os
import sqlite3
import uuid
from pathlib import Path
from unittest import mock

from daw import community_runtime
from daw.artifacts import attach_artifact, register_artifact
from daw.catalog import Workspace
from daw.community import Community
from daw.community_runtime import add_agent, dispatch, fork_agent
from daw.harness import scripted
from daw.substrate_models import ArtifactRegistration, Derivation, ObjectInput
from daw.util import DawError, now, write_json
from daw.work import create_question, record_event, sync_work

SYNTHETIC = "Synthetic demo record; numbers are fixtures, not biological measurements."

# The scripted stand-in harness lives with the adapters (daw.harness.scripted).
HARNESS = scripted.SCRIPT

# Saved code of the synthetic derivations: tiny real scripts that recompute each registered table from its
# input (`python SCRIPT INPUT OUTPUT`, the convention of the research skill's replicate.py), so a replication
# re-executes them (spec v2 C6). Their outputs are the registered bytes below; every number stays synthetic.
CODE = {
    "measurement.tsv": r'''"""Per-condition marker means of the synthetic sample table: measurement.py COUNTS OUTPUT."""
import sys

groups = {}
for line in open(sys.argv[1]).read().splitlines()[1:]:
    sample, condition, marker = line.split("\t")
    groups.setdefault(condition, []).append(float(marker))
with open(sys.argv[-1], "w") as out:
    out.write("condition\tmean\n")
    for condition in sorted(groups):
        out.write(f"{condition}\t{sum(groups[condition]) / len(groups[condition]):.1f}\n")
''',
    "contrast.tsv": r'''"""log2(B/A) of the synthetic per-condition means: contrast.py MEANS OUTPUT."""
import math
import sys

means = dict(line.split("\t") for line in open(sys.argv[1]).read().splitlines()[1:])
ratio = math.log2(float(means["B"]) / float(means["A"]))
with open(sys.argv[-1], "w") as out:
    out.write(f"contrast\tlog2_ratio\nB_vs_A\t{ratio:.2f}\n")
''',
    "normalized.tsv": r'''"""Synthetic library-size scaling of the contrast: normalized.py CONTRAST OUTPUT."""
import sys

SCALE = 0.85  # synthetic library-size factor
rows = dict(line.split("\t") for line in open(sys.argv[1]).read().splitlines()[1:])
with open(sys.argv[-1], "w") as out:
    out.write(f"contrast\tlog2_ratio_normalized\nB_vs_A\t{float(rows['B_vs_A']) * SCALE:.2f}\n")
''',
}


def _fake_native_session(executable, home, identity, cwd, *, fork=False):
    """Stand-in for the pinned Hermes session bridge, operating on the scripted harness's state.db."""
    with contextlib.closing(sqlite3.connect(home / "state.db")) as db, db:
        if not db.execute("SELECT id FROM sessions WHERE id=?", (identity,)).fetchone():
            raise DawError("unknown_saved_session", identity)
        child = "native_" + uuid.uuid4().hex if fork else identity
        if fork:
            db.execute("INSERT INTO sessions VALUES(?,?)", (child, str(cwd)))
            db.execute("INSERT INTO messages SELECT ?,content,timestamp FROM messages WHERE session=?", (child, identity))
    return {"session": child, "parent": identity if fork else None, "forked": fork, "cwd": str(cwd)}


@contextlib.contextmanager
def scripted_runtime(root):
    """Dispatch through the real runtime with the scripted harness; restores the environment afterwards."""
    harness = scripted.install(root / "demo-harness" / "hermes")
    answers = root / "demo-harness" / "answers"
    answers.mkdir(exist_ok=True)
    saved = {k: os.environ.get(k) for k in ("DAW_LIVE", "COLLOQUY_DEMO_ANSWERS", "BIO_AGENT")}
    os.environ.update(DAW_LIVE="1", COLLOQUY_DEMO_ANSWERS=str(answers))
    os.environ.pop("BIO_AGENT", None)
    try:
        with mock.patch.object(community_runtime, "native_session", _fake_native_session):
            yield harness, answers
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _no_reserve(root):
    (Path(root) / "config.toml").write_text("[budgets]\nasset_bytes=0\nbundle_bytes=0\nrequests=0\n"
                                            "reserve_bytes=0\nreserve_fraction=0\n")


class Researcher:
    """Helpers that act inside one agent's own workspace, as its CLI would."""

    def __init__(self, board, agent, tmp):
        self.board, self.agent, self.tmp = board, agent, tmp
        self.root = board.trial(agent) / "workspace"
        _no_reserve(self.root)

    def ws(self):
        return Workspace(self.root)

    def question(self, title, labbook):
        ws = self.ws()
        try:
            with ws.writer():
                q = create_question(ws, title)
                (Path(q["path"]) / "LABBOOK.md").write_text(labbook)
                (Path(q["path"]) / "scripts" / "contrast.py").write_text("# synthetic analysis script (never executed)\n")
                sync_work(ws, q["question"], summary=title)
            return q["question"]
        finally:
            ws.close()

    def source(self, name, text):
        path = self.tmp / f"{self.agent['name']}-{name}"
        path.write_text(text)
        ws = self.ws()
        try:
            with ws.writer():
                return ws.local_asset(path, "synthetic-demo")
        finally:
            ws.close()

    def register(self, question, name, text, *, title, summary, role, inputs, parameters, code=None):
        """Register `text` as the output of `code` (default: the saved demo script for `name`, `CODE`)."""
        path = self.tmp / f"{self.agent['name']}-{name}"
        path.write_text(text)
        ws = self.ws()
        try:
            with ws.writer():
                source = code if code is not None else CODE.get(name, f"# synthetic code for {name}\n")
                code = ws.put_bytes(source.encode(), "code")
                spec = ArtifactRegistration(title=title, summary=summary + " " + SYNTHETIC, output_role=role,
                                            derivation=Derivation(inputs=[ObjectInput(**i) for i in inputs], code=[code],
                                                                  parameters=parameters, references=[],
                                                                  environment={"demo": True}),
                                            limitations=[SYNTHETIC])
                return register_artifact(ws, path, spec, question=question)
        finally:
            ws.close()

    def gap(self, question, payload, evidence_text):
        ws = self.ws()
        try:
            with ws.writer():
                payload = {**payload, "evidence_blob": ws.put_bytes(evidence_text.encode(), "work")}
                return record_event(ws, question, "retrieval_gap", payload)
        finally:
            ws.close()

    def use(self, question, artifact, relationship, reason=None):
        ws = self.ws()
        try:
            with ws.writer():
                return attach_artifact(ws, question, artifact, relationship, reason=reason)
        finally:
            ws.close()

    def labbook(self, question, text):
        ws = self.ws()
        try:
            with ws.writer():
                (self.root / "questions" / question / "LABBOOK.md").write_text(text)
                return sync_work(ws, question)
        finally:
            ws.close()

    def publish(self, title, body, **options):
        return self.board.publish(self.agent["id"], title, body, workspace=self.root, **options)

    def fetch(self, post, question):
        return self.board.fetch(post, self.root, question, author=self.agent["id"])


def notebook(title, findings, open_questions):
    return (f"# Research notebook: {title}\n\n## Investigation\n\nSynthetic demo question.\n\n"
            f"## Data and prior work\n\nA synthetic local table imported for the demo.\n\n## Findings\n\n{findings}\n\n"
            "## Failed routes\n\n- A per-sample check failed once on a missing column (receipt in the run).\n\n"
            f"## Assumptions and limitations\n\n- {SYNTHETIC}\n\n## Open questions\n\n{open_questions}\n")


# Feature modules extend the demo by appending "module:function" here. Each function receives
# (board, context) after the core records exist, may add records through ordinary functions,
# and may add identities to `context` under its own key.
EXTENSIONS = [
    "daw.commons.claims:extend_demo",
    "daw.commons.frontier:extend_demo",
    "daw.commons.participation:demo_records",
    "daw.commons.questions:demo_extension",
    "daw.commons.discovery_demo:extend",
    "daw.commons.metrics:demo_cohort",
]


def build_demo(root, *, extensions=True):
    """Create a synthetic demo commons at `root` (must not exist) and return identities of its records.

    `extensions` is True (all of EXTENSIONS), False (core records only) or an explicit list of
    "module:function" entries, so a test can pin exactly which records exist."""
    root = Path(root).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise DawError("demo_root_not_empty", str(root))
    tmp = root / "demo-harness" / "inputs"
    tmp.mkdir(parents=True)
    board = Community.create(root)
    _no_reserve(board.library.root)
    board.library.close()
    board.library = Workspace(board.root / "library")
    write_json(root / "DEMO.json", {"synthetic": True, "created": now(), "note": SYNTHETIC})
    # A person's asks, promotions and commissions spend an allowance; without one they are refused (B13).
    (root / "commons.toml").write_text("[allowance]\nminutes = 600\n")
    ctx = {}
    try:
        with scripted_runtime(root) as (harness, answers):
            agents = {name: add_agent(board, name) for name in ("alice", "bob", "dana")}
            r = {name: Researcher(board, agent, tmp) for name, agent in agents.items()}
            # Alice: a measurement and a contrast derived from it.
            qa = r["alice"].question("Does the demo marker change between conditions?",
                                     notebook("Demo marker contrast", "- Pending.", "- Which samples share donors?"))
            src = r["alice"].source("counts.tsv", "sample\tcondition\tmarker\nS1\tA\t10\nS2\tA\t12\nS3\tB\t30\nS4\tB\t34\n")
            meas = r["alice"].register(qa, "measurement.tsv", "condition\tmean\nA\t11.0\nB\t32.0\n",
                                       title="Per-condition marker means", summary="Means per condition.",
                                       role="measurement-table", parameters={"aggregate": "mean"},
                                       inputs=[{"blob": src["blob"], "source_identity": src["asset_revision"]}])
            contrast = r["alice"].register(qa, "contrast.tsv", "contrast\tlog2_ratio\nB_vs_A\t1.54\n",
                                           title="Condition B versus A contrast", summary="log2(B/A) of means.",
                                           role="contrast-table", parameters={"contrast": "B_vs_A", "direction": "B/A"},
                                           inputs=[{"blob": meas["output_blob"], "source_identity": meas["artifact"]}])
            r["alice"].labbook(qa, notebook("Demo marker contrast",
                                            f"- log2(B/A) = 1.54 ({contrast['artifact']}).",
                                            "- Which samples share donors?\n- Does the contrast hold in a second dataset?"))
            brief = board.ask(agents["alice"]["id"], "operator", "Investigate whether the demo marker differs between "
                              "conditions A and B. " + SYNTHETIC, request_key="demo-brief-alice")
            (answers / f"{brief['post']}.md").write_text(
                f"Finding: the marker is higher in B; log2(B/A) = 1.54 (artifact {contrast['artifact']}), from means "
                f"11.0 and 32.0 (artifact {meas['artifact']}).\nLimits: four synthetic samples; donor sharing unknown.\n"
                "Next computable step: test donor structure.")
            dispatch(board, brief["id"], harness)
            p1 = r["alice"].publish("Marker contrast between conditions",
                                    f"The marker contrast B versus A is log2 ratio 1.45 ({contrast['artifact']}).\n\n{SYNTHETIC}",
                                    artifacts=[contrast["artifact"], meas["artifact"]], question=qa, request_key="demo-p1")
            # Bob discovers Alice's post, fetches it, and reuses the contrast as a registration input (backed).
            qb = r["bob"].question("Is the demo contrast robust to normalization?",
                                   notebook("Normalization check", "- Pending.", "- Is a spike-in available?"))
            r["bob"].fetch(p1["id"], qb)
            norm = r["bob"].register(qb, "normalized.tsv", "contrast\tlog2_ratio_normalized\nB_vs_A\t1.31\n",
                                     title="Normalized contrast", summary="Contrast after library-size scaling.",
                                     role="contrast-table-normalized", parameters={"normalization": "library_size"},
                                     inputs=[{"blob": contrast["output_blob"], "source_identity": contrast["artifact"]}])
            r["bob"].use(qb, contrast["artifact"], "reused", reason="its log2 ratio is the input to the normalization")
            r["bob"].use(qb, meas["artifact"], "reused")  # unbacked: no reason, never a registration input
            p2 = r["bob"].publish("Normalization shrinks the contrast",
                                  f"After normalization the contrast is 1.31 ({norm['artifact']}), below the reported 1.45.\n\n"
                                  f"{SYNTHETIC}", artifacts=[norm["artifact"]], question=qb, parent=p1["id"],
                                  request_key="demo-p2")
            # Bob asks Alice a question about her post; Alice answers in a resumed session.
            q_req = board.ask(p1["id"], agents["bob"]["id"], "Which samples share donors in your table?",
                              request_key="demo-donor-question", notify=True)
            (answers / f"{q_req['post']}.md").write_text("Donor identity is not recorded in the synthetic table; "
                                                         "independence cannot be assumed.")
            dispatch(board, q_req["id"], harness)
            # Alice corrects a transcription error: prose said 1.45, the table says 1.54.
            p3 = r["alice"].publish("Correction: marker contrast between conditions",
                                    f"Correction: the contrast is log2 ratio 1.54, not 1.45 ({contrast['artifact']}).\n\n"
                                    f"{SYNTHETIC}", artifacts=[contrast["artifact"]], question=qa,
                                    supersedes=p1["id"], parent=p1["id"], request_key="demo-p3")
            # Dana: a stalled question with a receipted retrieval gap.
            qd = r["dana"].question("Is there a perturbation dataset for the demo marker?",
                                    notebook("Perturbation search", "- No eligible dataset found.",
                                             "- Exact missing measurement: per-sample counts after marker knockdown."))
            gap = r["dana"].gap(qd, {"desired_information": "Per-sample counts after marker knockdown",
                                     "why_current_tools_failed": "Repository search returned no matching accession",
                                     "source_or_format": "GEO", "gap_key": "demo-knockdown-counts",
                                     "possible_indexing_solution": "Re-run the scoped search when new series appear"},
                                '{"query":"demo marker knockdown","hits":0}')
            p4 = r["dana"].publish("No perturbation data yet", f"Searches found no eligible knockdown data.\n\n{SYNTHETIC}",
                                   question=qd, request_key="demo-p4")
            fork = fork_agent(board, "alice", "alice-fork")
            ctx.update(agents={k: v["id"] for k, v in agents.items()}, fork=fork["id"],
                       questions={"alice": qa, "bob": qb, "dana": qd},
                       artifacts={"measurement": meas["artifact"], "contrast": contrast["artifact"],
                                  "normalized": norm["artifact"]},
                       posts={"finding": p1["id"], "reply": p2["id"], "correction": p3["id"], "gap": p4["id"],
                              "brief": brief["post"], "question": q_req["post"]},
                       requests={"brief": brief["id"], "question": q_req["id"]}, gap_event=gap["id"],
                       harness=harness)
            if extensions:
                for target in EXTENSIONS if extensions is True else extensions:
                    module, name = target.split(":")
                    getattr(importlib.import_module(module), name)(board, ctx)
    finally:
        board.close()
    write_json(root / "demo-harness" / "context.json", ctx)
    return ctx


def _demo_root(root):
    """The resolved root of a synthetic demo commons; anything else is refused (`not_a_demo_commons`)."""
    root = Path(root).expanduser().resolve()
    marker = root / "DEMO.json"
    try:
        synthetic = marker.is_file() and json.loads(marker.read_text()).get("synthetic") is True
    except ValueError:
        synthetic = False
    if not synthetic:
        raise DawError("not_a_demo_commons", str(root))
    return root


def watch_tick_recorded(root, response, *, actor="operator", max_watchers=10):
    """Run due watchers on a synthetic demo commons against a recorded Europe PMC search response.

    The same `watchers.tick` as the scheduled job, with an httpx MockTransport serving `response` (a
    Europe PMC search JSON object) for the search URL only, so Flow C can be exercised end to end
    without network. Refused unless the commons carries the synthetic DEMO.json marker."""
    from daw.commons.discovery_demo import recorded_transport
    from daw.commons.watchers import tick
    root = _demo_root(root)
    if not isinstance(response, dict) or not isinstance((response.get("resultList") or {}).get("result"), list):
        raise DawError("invalid_recorded_response", "a Europe PMC search JSON object with resultList.result")
    with Community(root) as board:
        return tick(board, transport=recorded_transport(response), max_watchers=max_watchers, actor=actor)


def _replication_hook(board, request):
    """The demo replication hook for a replication request's single original artifact (`studio_demo.replication_hook`)."""
    from daw.commons.replication import originals
    from daw.commons.studio import _original_post
    from daw.commons.studio_demo import replication_hook
    from daw.commons.tasks import subject_of
    if request["task_type"] != "replication":
        raise DawError("not_a_replication_request", request["task_type"] or "untyped")
    found = originals(board, subject_of(board.show(request["post"])["content"]))
    if len(found) != 1:
        raise DawError("replication_subject_ambiguous", f"{len(found)} original artifacts; the demo hook replicates one")
    post = _original_post(board, found[0])
    if not post:
        raise DawError("replication_original_unpublished", found[0])
    return replication_hook(post, found[0])


def deliver_scripted(root, request_id, answer, *, hook=None, replicate=False):
    """Deliver one pending request on a synthetic demo commons with the scripted stand-in harness.

    The operator's equivalent of `bio community run` for demos and end-to-end checks: the request goes
    through `community_runtime.dispatch` exactly as a live delivery would (prompt, stream, receipts, task
    outcome, post-delivery hooks), but the agent's answer is the given text. `hook` is optional fixture
    code that the scripted harness runs inside the agent's checkout before answering, as the agent's own
    CLI calls would (e.g. `./bin/bio register`, `./bin/bio community publish`). `replicate` (replication
    requests) uses the demo replication hook instead: fetch the subject and run the research skill's
    replicate.py with ./bin/python, so the saved code really executes under a receipt. Refused unless the commons
    carries the synthetic DEMO.json marker, so it can never stand in for a real agent on a real board."""
    root = _demo_root(root)
    if not isinstance(answer, str) or not answer.strip():
        raise DawError("answer_required")
    with Community(root) as board, scripted_runtime(root) as (harness, answers):
        request = board.one("SELECT * FROM request WHERE id=?", (request_id,))
        if not request:
            raise DawError("unknown_request", request_id)
        if request["state"] != "pending":
            raise DawError("request_not_pending", request["state"])
        if replicate:
            if hook:
                raise DawError("choose_hook_or_replicate")
            hook = _replication_hook(board, request)
        (answers / f"{request['post']}.md").write_text(answer)
        hook_path = answers / f"{request['post']}.hook.py"
        if hook:
            hook_path.write_text(hook)
        try:
            return dispatch(board, request_id, harness)
        finally:
            hook_path.unlink(missing_ok=True)
