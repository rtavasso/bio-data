"""Demo extension for Studio (M6): commissioned write-ups, a review, a replication and a standing digest.

Everything goes through the ordinary functions: a synthetic person (`mira`, from the participation
demo) commissions tasks, the scripted harness delivers them through `community_runtime.dispatch`,
and the runtime's post-delivery hook records review marks, the replication confirmation and each
write-up's checker verdict (`writeup_check`). One write-up cites current ledger claims and artifact cells
(renders, every number verified), one cites a withdrawn claim (flagged for regeneration) and one has
numbers without claim or artifact pointers (refused, withheld on every surface). All synthetic.

It is not in `daw.commons.demo.EXTENSIONS`, because other areas' tests pin the core demo's exact runs
and task outcomes. `bio commons demo-studio DIR` (`apply`) adds these records to a built demo commons;
tests call `extend` on a private copy.
"""
import json
from pathlib import Path

from daw.commons import participation, studio
from daw.commons.demo import SYNTHETIC

REPLICATE = '''import os
from daw.artifacts import artifact_info, register_artifact
from daw.catalog import Workspace
from daw.substrate_models import ArtifactRegistration, Derivation
from daw.work import create_question
ws = Workspace(os.environ["BIO_WORKSPACE"])
try:
    with ws.writer():
        info = artifact_info(ws, {original!r})
        manifest = info["manifest"]
        question = create_question(ws, "Replicate the demo contrast")["question"]
        with open("replicated-contrast.tsv", "wb") as out:
            out.write(ws.blob_path(info["output_blob"]).read_bytes())
        register_artifact(ws, "replicated-contrast.tsv", ArtifactRegistration(
            title="Replication of the demo contrast", summary="Re-executed saved code on recorded inputs (synthetic).",
            output_role=manifest["output_role"], derivation=Derivation(**manifest["derivation"])), question=question)
finally:
    ws.close()
'''


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
         "pointers": [artifacts["contrast"]], "note": "The analysis script is a synthetic placeholder."},
        {"criterion": "limitations_stated", "verdict": "supported", "pointers": [claims["correction"]],
         "note": "States that the records are synthetic."},
        {"criterion": "scope_matches_evidence", "verdict": "not_assessable", "pointers": [],
         "note": "Four synthetic samples; donor structure unknown."}]}}
    review = deliver(review, "Review of the correction.\n\n```review\n" + json.dumps(block, indent=1) + "\n```\n")
    replication = commission("replication", agents["bob"], "Re-execute the contrast derivation from its saved inputs.",
                             subject_kind="artifact", subject_id=artifacts["contrast"])
    replication = deliver(replication, "Re-executed the contrast derivation; the output bytes match the original.",
                          hook=REPLICATE.format(original=artifacts["contrast"]))
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
