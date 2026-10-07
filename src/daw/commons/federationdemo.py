"""A second commons that cites the public cohort, built offline (spec v3 V16, B9).

`bio commons federation-demo OUT [--cited cohort|demo]` builds two commons under OUT and federates them in both
directions with the calls a lab would make; nothing here has a code path of its own:

1. The cited commons. `cohort` (default): the public PMP22 cohort commons (`publicdemo.build`: a verified copy
   of the committed fixture, never the fixture itself) with its board exported as a snapshot. `demo`: a
   synthetic demo commons with claims, whose corrected-contrast thread is exported.
2. The second commons, a synthetic demo commons on another question set (`demo.build_demo`, core records),
   imports that snapshot as its local participant (`federation.import_and_index`, attributed: B9).
3. Its operator commissions a write-up from its agent dana; the scripted stand-in delivers text that cites a
   record of the imported snapshot by pointer. The cohort has no claims yet (agents authored none), so on the
   cohort the citation is the tour's first artifact cell; on the demo it is a claim. The checker verifies the
   value from the snapshot's bytes at delivery.
4. The second commons exports the citing thread; the cited commons imports that snapshot as its local
   participant, which indexes the citation (recorded at the source, backed by the citing post's bytes).

The citation then shows on both sides: the second commons' dashboard ("Snapshots cited by questions",
`/api/snapshot-citations`), and the cited commons' artifact or claim page (`cited_from` on `/api/artifacts/<id>`,
`/api/claims/<id>`) and dashboard ("Cited by other commons"). The imports are on each local participant's
`/me`. Every record written in the second commons is synthetic (its DEMO.json); the cohort gains only the
import (an event and the federation index), and its posts, claims and library are unchanged.
"""
import json
from pathlib import Path

from daw.util import DawError, now, write_json

LOCAL = "local"  # the participant `bio commons serve` acts as in local mode, so /me lists the imports


def _local(root):
    from daw.commons.participants import add_participant
    from daw.community import Community
    with Community(root) as board:
        if not board.one("SELECT id FROM agent WHERE name=?", (LOCAL,)):
            add_participant(board, LOCAL, "human", profile={"display_name": LOCAL})
        return board.agent(LOCAL)["id"]


def _import(root, folder, snapshot):
    from daw.commons import federation
    from daw.community import Community
    with Community(root) as board:
        return federation.import_and_index(board, folder, actor=LOCAL, expect=snapshot,
                                           origin={"directory": str(folder)})


def _cited_cohort(out, fixture):
    from daw.commons import publicdemo, tour
    built = publicdemo.build(out / "cited", fixture=fixture, snapshot=out / "cited-snapshot")
    step = tour.load(publicdemo.DEFAULT_TOUR)["steps"][0]
    snapshot = built["snapshot"]["id"]
    pointer = f"snapshot:{snapshot}/{step['artifact']}#{step['locator']}"
    text = (f"# Reading the public PMP22 cohort\n\nThe public PMP22 cohort reports a paired Pmp22 effect of "
            f"[{step['number']['text']}]({pointer}) (log2), read from the cohort snapshot's bytes; this demo "
            f"commons studies a different question and cites the cohort's record, it does not reuse it.\n\n")
    return snapshot, step["artifact"], "artifact", text


def _cited_demo(out):
    from daw.commons.demo import build_demo
    from daw.commons.export import export_snapshot
    from daw.community import Community
    ctx = build_demo(out / "cited")
    with Community(out / "cited") as board:
        exported = export_snapshot(board, "operator", "thread", ctx["claims"]["correction"], out / "cited-snapshot")
    records = json.loads((out / "cited-snapshot" / "records.json").read_bytes())
    claim = next(c for c in records["claims"] if "1.54" in c["text"])
    snapshot = exported["snapshot"]
    text = (f"# Reading lab A's contrast\n\nLab A's corrected contrast is "
            f"[1.54](snapshot:{snapshot}/{claim['id']}) (its claim, cited by snapshot id).\n\n")
    return snapshot, claim["id"], "claim", text


def build(out, *, cited="cohort", fixture=None):
    """Build the cited commons, the second commons and both imports under `out` (new or empty)."""
    from daw.commons.archive import Archive
    from daw.commons.demo import SYNTHETIC, build_demo, deliver_scripted
    from daw.commons.export import export_snapshot
    from daw.commons.participation import commission
    from daw.commons.writeup import verdict
    from daw.community import Community
    if cited not in {"cohort", "demo"}:
        raise DawError("invalid_cited_commons", "cohort or demo")
    out = Path(out).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise DawError("federation_demo_output_not_empty", str(out))
    out.mkdir(parents=True, exist_ok=True)
    snapshot, record, kind, text = _cited_cohort(out, fixture) if cited == "cohort" else _cited_demo(out)
    second = out / "second"
    ctx = build_demo(second, extensions=False)
    _local(second)
    first_import = _import(second, out / "cited-snapshot", snapshot)
    with Community(second) as board:
        request = commission(board, "operator", "writing", ctx["agents"]["dana"], {"minutes": 10}, subject_kind="post",
                             subject_id=ctx["posts"]["finding"], note="Cite the imported snapshot (federation demo).")
    done = deliver_scripted(second, request["id"], text + SYNTHETIC + "\n")
    post = done["answer"]
    with Archive(second) as view:
        checked = verdict(view, post)[0]
    if checked["status"] != "rendered":
        raise DawError("federation_demo_citation_refused", json.dumps(checked["problems"])[:500])
    with Community(second) as board:
        back = export_snapshot(board, "operator", "thread", post, out / "second-snapshot")
    _local(out / "cited")
    second_import = _import(out / "cited", out / "second-snapshot", back["snapshot"])
    page = f"/claims/{record}" if kind == "claim" else f"/artifact/{record}"
    summary = {"format": "colloquy.federation-demo/1", "built": now(), "cited": cited,
               "cited_commons": str(out / "cited"), "cited_snapshot": snapshot, "cited_record": record,
               "second_commons": str(second), "second_snapshot": back["snapshot"], "citing_post": post,
               "checker": {"status": checked["status"], "numbers": [{k: n.get(k) for k in ("text", "status", "scope")}
                                                                    for n in checked["numbers"]]},
               "imports": [{"into": "second", "snapshot": snapshot, "importer": first_import["importer"],
                            "index": first_import["index"]},
                           {"into": "cited", "snapshot": back["snapshot"], "importer": second_import["importer"],
                            "index": second_import["index"]}],
               "open": {"second": ["/dashboard", f"/post/{post}", "/me"], "cited": ["/dashboard", page, "/me"]},
               "serve": [f"bio commons --root {second} serve --port 8765",
                         f"bio commons --root {out / 'cited'} serve --port 8766"],
               "note": "The second commons is synthetic (DEMO.json); its write-up was delivered by the scripted "
                       "stand-in. " + ("The cohort has no claims yet, so it is cited by an artifact cell."
                                       if cited == "cohort" else "")}
    write_json(out / "FEDERATION.json", summary)
    return summary
