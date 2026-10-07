"""Demo extension for Studio (M6): commissioned write-ups, a review, a replication and a standing digest.

Everything goes through the ordinary functions: a synthetic person (`mira`, from the participation
demo) commissions tasks, the scripted harness delivers them through `community_runtime.dispatch`,
and the runtime's post-delivery hook records review marks, the replication confirmation and each
write-up's checker verdict (`writeup_check`). The replication really re-executes the synthetic contrast
script (`daw.commons.demo.CODE`) through the research skill's replicate.py and run_analysis.py, and its
answer is worded from that receipt. One write-up cites current ledger claims and artifact cells (renders,
every number verified), one cites a withdrawn claim (flagged for regeneration) and one has numbers
without claim or artifact pointers (refused, withheld on every surface). All synthetic.

It is not in `daw.commons.demo.EXTENSIONS`, because other areas' tests pin the core demo's exact runs
and task outcomes. `bio commons demo-studio DIR` (`apply`) adds these records to a built demo commons;
tests call `extend` on a private copy.
"""
import json
from pathlib import Path

from daw.commons import participation, studio
from daw.commons.demo import SYNTHETIC

# Scripted-harness hook for a replication (spec v2 C6): inside the agent's checkout, as the agent's own CLI
# calls would, it creates a question, fetches the original into it and runs the research skill's
# replicate.py with ./bin/python, which hash-checks the derivation's saved code and inputs, executes the code
# through run_analysis.py (a receipt is written) and registers the output with the same derivation. The
# answer is then worded from that receipt, so it claims an execution only when one is recorded.
REPLICATE_HOOK = r'''import json, os, pathlib, shlex, subprocess
trial = pathlib.Path(os.environ.get("HERMES_CWD") or os.getcwd())
CALLS = []  # the helper's terminal call, emitted into the captured stream by the scripted harness


def run(*argv, ok=(0,)):
    done = subprocess.run(list(argv), cwd=trial, capture_output=True, text=True)
    if "replicate.py" in " ".join(argv):
        CALLS.append({"command": shlex.join(argv), "exit_code": done.returncode, "output": done.stdout})
    if done.returncode not in ok:
        raise SystemExit(f"{argv[:4]} exited {done.returncode}: {done.stdout[-2000:]} {done.stderr[-2000:]}")
    return json.loads(done.stdout.strip().splitlines()[-1])


question = run("./bin/bio", "work", "new", __TITLE__)["question"]
run("./bin/bio", "community", "fetch", __POST__, "--question", question, "--artifact", __ORIGINAL__)
result = run("./bin/python", ".agents/skills/bio-research/scripts/replicate.py", __ORIGINAL__, "--question", question,
             ok=(0, 1))
(trial / "replication-result.json").write_text(json.dumps(result, indent=1))
if result.get("replica"):
    text = (f"Executed code blob {result['code_blob']} of derivation {result['derivation_key']} on its recorded inputs "
            f"through run_analysis.py (receipt blob {result['receipt_blob']}, exit code {result['exit_code']}) and "
            f"registered the output as {result['replica']}; its bytes "
            + ("are identical to" if result["byte_identical"] else "differ from") + f" the original {__ORIGINAL__}.")
else:
    text = (f"The saved code of {__ORIGINAL__} did not complete under run_analysis.py (receipt blob "
            f"{result.get('receipt_blob')}, exit code {result.get('exit_code')}); nothing was registered.")
answers = pathlib.Path(os.environ["COLLOQUY_DEMO_ANSWERS"])
post = pathlib.Path(__file__).name.removesuffix(".hook.py")
(answers / f"{post}.md").write_text(text + "\n\n" + __SYNTHETIC__)
'''


def replication_hook(post, original, title="Replicate the demo contrast"):
    """Hook text for `bio commons demo-deliver --hook` or a test: replicate `original`, fetched from `post`."""
    values = {"__TITLE__": title, "__POST__": post, "__ORIGINAL__": original, "__SYNTHETIC__": SYNTHETIC}
    text = REPLICATE_HOOK
    for key, value in values.items():
        text = text.replace(key, repr(value))
    return text


def extend(board, ctx):
    from daw.community_runtime import dispatch
    answers = board.root / "demo-harness" / "answers"
    person = ctx["participation"]["human"]
    agents, artifacts, claims = ctx["agents"], ctx["artifacts"], ctx["claims"]
    figure = ctx.get("observatory_map", {}).get("figure")
    budget = {"minutes": 30}

    def commission(task_type, target, note, **subject):
        return participation.commission(board, person, task_type, target, budget, note=note, **subject)

    def deliver(request, text, hook=None):
        post = board.one("SELECT post FROM request WHERE id=?", (request["id"],))["post"]
        (answers / f"{post}.md").write_text(text)
        if hook:
            (answers / f"{post}.hook.py").write_text(hook)
        return dispatch(board, request["id"], ctx["harness"])

    figure_line = f"\n\n![Synthetic marker figure]({figure})" if figure else ""
    measurement = artifacts["measurement"]
    current = commission("writing", agents["dana"], "Plain-language summary of the corrected marker contrast.",
                         subject_kind="post", subject_id=claims["correction"])
    current = deliver(current, (
        "# The demo marker contrast, corrected\n\nBy dana (synthetic demo writer)\n\n"
        f"The demo marker is higher in condition B than in A: log2(B/A) = [1.54]({claims['current']}). "
        f"The per-condition means are [11.0]({measurement}#row=A;col=mean) and "
        f"[32.0]({measurement}#row=B;col=mean), and the contrast table itself is "
        f"[the contrast artifact]({artifacts['contrast']}). Donor independence was not assessed; see "
        f"[the correction]({claims['correction']}) for context.{figure_line}\n\n{SYNTHETIC}"))
    stale = commission("writing", agents["bob"], "Short report on the original structured summary.",
                       subject_kind="post", subject_id=claims["summary"])
    stale = deliver(stale, (
        "# Marker contrast report\n\n"
        f"The structured summary reported log2(B/A) = [1.45]({claims['withdrawn']}) from the contrast table "
        f"[{artifacts['contrast']}].\n\n{SYNTHETIC}"))
    refused = commission("writing", agents["dana"], "Summarise the normalization check.",
                         subject_kind="post", subject_id=ctx["posts"]["reply"])
    refused = deliver(refused, (
        f"Context: [the normalization reply]({ctx['posts']['reply']}).\n\n"
        "After normalization the contrast is 1.31, about 15% below the corrected value.\n\n" + SYNTHETIC))
    review = commission("review", agents["bob"], "Check the correction against its evidence.",
                        subject_kind="post", subject_id=claims["correction"])
    block = {"review": {"target": claims["correction"], "verdicts": [
        {"criterion": "claims_traceable_to_pointers", "verdict": "supported", "pointers": [artifacts["contrast"]],
         "note": "The corrected value is the contrast table's B_vs_A row."},
        {"criterion": "methods_reproducible_from_receipts", "verdict": "partially_supported",
         "pointers": [artifacts["contrast"]], "note": "The saved analysis script is synthetic demo code."},
        {"criterion": "limitations_stated", "verdict": "supported", "pointers": [claims["correction"]],
         "note": "States that the records are synthetic."},
        {"criterion": "scope_matches_evidence", "verdict": "not_assessable", "pointers": [],
         "note": "Four synthetic samples; donor structure unknown."}]}}
    review = deliver(review, "Review of the correction.\n\n```review\n" + json.dumps(block, indent=1) + "\n```\n")
    replication = commission("replication", agents["bob"], "Re-execute the contrast derivation from its saved inputs.",
                             subject_kind="artifact", subject_id=artifacts["contrast"])
    # The hook re-executes the saved contrast script and words the answer from its run_analysis receipt.
    replication = deliver(replication, "No answer was recorded by the replication hook.",
                          hook=replication_hook(ctx["posts"]["finding"], artifacts["contrast"]))
    schedule = studio.schedule_digest(board, person, agents["dana"], {"questions": [ctx["questions"]["alice"]]},
                                      "weekly", budget)
    ticked = studio.digest_tick(board, "operator")["ticked"][0]
    digest = deliver(board.one("SELECT * FROM request WHERE id=?", (ticked["request"],)), (
        f"This week: Alice published the marker contrast [{ctx['posts']['finding']}] and corrected it "
        f"[{ctx['posts']['correction']}]; her structured summary [{claims['summary']}] was superseded by "
        f"[{claims['correction']}]. Open: donor structure.\n\n{SYNTHETIC}"))
    ctx["studio"] = {"writeup": current["answer"], "flagged": stale["answer"], "refused": refused["answer"],
                     "requests": {"writeup": current["id"], "flagged": stale["id"], "refused": refused["id"],
                                  "review": review["id"], "replication": replication["id"], "digest": digest["id"]},
                     "review": review["answer"], "replication_answer": replication["answer"],
                     "digest_schedule": schedule["id"], "digest": digest["answer"]}


def apply(root):
    """Add the Studio records to an existing synthetic demo commons (scripted harness; no model or network)."""
    from daw.commons.demo import scripted_runtime
    from daw.community import Community
    from daw.util import DawError, read_json, write_json
    root = Path(root).expanduser().resolve()
    context = root / "demo-harness" / "context.json"
    if not (root / "DEMO.json").is_file() or not context.is_file():
        raise DawError("not_a_demo_commons", str(root))
    ctx = read_json(context)
    if "studio" in ctx:
        return ctx["studio"]
    with Community(root) as board, scripted_runtime(root) as (harness, _):
        ctx["harness"] = harness
        extend(board, ctx)
    write_json(context, ctx)
    return ctx["studio"]
