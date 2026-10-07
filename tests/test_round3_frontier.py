"""Round three: agenda launches link their frontier item, completed requests show their outcome, duplicate items
are flagged, agents record evidence on each other's items, and identical question fan-out is refused."""
import json

import pytest
from typer.testing import CliRunner

from daw.catalog import Workspace
from daw.commons import agentview, boardservice, frontier, planning
from daw.commons.assignments import assign, cohort_run
from daw.commons.participants import add_participant
from daw.commons.participation import commission, set_allowance
from daw.community import Community
from daw.community_cli import app as community_app
from daw.util import DawError


def workspace(board, ctx, name):
    return Workspace(board.trial(board.agent(ctx["agents"][name])) / "workspace")


def row(board, item):
    return board.one("SELECT * FROM frontier_item WHERE id=?", (item,))


def card(view, item):
    return next((c["key"], i) for c in view["columns"] for i in c["items"] if i["id"] == item)


def test_assignment_from_an_agenda_schedules_the_item_and_completion_shows_the_answer(demo):
    from daw.commons.demo import deliver_scripted
    root, ctx = demo
    item = ctx["frontier"]["items"]["alice-qpcr"]
    with Community(root) as board:
        with pytest.raises(DawError, match="unknown_frontier_item"):
            assign(board, "operator", ctx["agents"]["bob"], "Agenda", "Do it.",
                   evidence={"source": {"kind": "frontier_item", "id": "frontier_" + "0" * 32}})
        request = assign(board, "operator", ctx["agents"]["bob"], "Agenda: qPCR", "Run the qPCR analysis.",
                         evidence={"source": {"kind": "frontier_item", "id": item}, "agenda": "round-three"})
        event = json.loads(board.one("SELECT body FROM event WHERE kind='task_assigned' ORDER BY seq DESC")["body"])
        assert event["source"] == {"kind": "frontier_item", "id": item}
        scheduled = row(board, item)
        assert scheduled["status"] == "promoted" and scheduled["promoted_to"] == request["id"]
        column, shown = card(planning.board_view(board), item)
        assert column == "promoted" and shown["request"]["id"] == request["id"]
        # The owner sees the assignment as an attributed act on its item.
        acts = agentview.acts(board, ctx["agents"]["alice"])["acts"]
        assert any(a["act"] == "assignment" and a["target_id"] == item and a["request"] == request["id"] for a in acts)
    done = deliver_scripted(root, request["id"], "Analysis done; see the attached table.")
    assert done["state"] == "completed"
    with Community(root) as board:
        settled = row(board, item)
        source = json.loads(settled["source"])
        assert settled["status"] == "candidate_evidence" and settled["promoted_to"] == request["id"]
        assert source["candidate_source"] == "request" and source["candidate"]["answer"] == done["answer"]
        assert source["agent_status"] == "open"  # the owner's own history is untouched
        listed = next(i for i in agentview.frontier_list(board)["items"] if i["id"] == item)
        assert listed["column"] == "candidate_evidence" and listed["candidate_evidence"] == "request"
        assert listed["outcome"] == {"request": request["id"], "answer": done["answer"]}
        before = board.rows("SELECT * FROM frontier_item ORDER BY id")
        with board.writer(), board.db:
            board.db.execute("DELETE FROM frontier_item")
        frontier.rebuild_frontier(board)
        assert board.rows("SELECT * FROM frontier_item ORDER BY id") == before
        # The owner reviews the answer and records its own status afterwards: that status stands.
        ws = workspace(board, ctx, "alice")
        try:
            with ws.writer():
                frontier.record_status(ws, ctx["questions"]["alice"], ctx["frontier"]["events"]["alice-qpcr"],
                                       "closed", "The answer settles it.")
        finally:
            ws.close()
        frontier.rebuild_frontier(board)
        assert row(board, item)["status"] == "closed"


def test_commission_and_cohort_run_with_an_item_schedule_it(demo):
    root, ctx = demo
    items = ctx["frontier"]["items"]
    with Community(root) as board:
        rhea = add_participant(board, "rhea", "human")["id"]
        set_allowance(board, "operator", rhea, {"minutes": 600})
        made = commission(board, rhea, "review", ctx["agents"]["bob"], {"minutes": 10}, subject_kind="frontier_item",
                          subject_id=items["dana-untestable"], note="Review this branch.")
        assert row(board, items["dana-untestable"])["promoted_to"] == made["id"]
        queued = cohort_run(board, "operator", "agenda", [("Spike-in", "Find a spike-in.")], ["alice"],
                            source=items["bob-qpcr"])
        request = next(iter(queued[ctx["agents"]["alice"]].values()))
        scheduled = row(board, items["bob-qpcr"])
        assert scheduled["status"] == "promoted" and scheduled["promoted_to"] == request


def test_recording_an_item_warns_about_live_items_by_others_naming_the_same_accession(demo, monkeypatch):
    root, ctx = demo
    monkeypatch.delenv("BIO_BOARD_URL", raising=False)
    monkeypatch.delenv("BIO_BOARD_TOKEN", raising=False)
    monkeypatch.setenv("BIO_COMMUNITY", str(root))
    monkeypatch.setenv("BIO_AGENT", "alice")
    items = ctx["frontier"]["items"]
    question = ctx["questions"]["alice"]
    with Community(root) as board:
        ws = workspace(board, ctx, "alice")
    try:
        with ws.writer():
            shared = frontier.record_item(ws, question, kind="gap", text="Need the knockdown counts from GSE000001.")
            [warning] = shared["warnings"]
            assert warning["code"] == "possible_duplicate_frontier_items"
            assert [(i["id"], i["shared_accessions"]) for i in warning["items"]] == [
                (items["dana-untestable"], ["GSE000001"])]
            near = frontier.record_item(ws, question, kind="proposed_experiment",
                                        text="Measure the marker by qPCR in conditions A and B using donor-matched "
                                             "samples and a spike-in.")
            assert [i["id"] for i in near["warnings"][0]["items"]] == [items["bob-qpcr"]]
            assert near["warnings"][0]["items"][0]["text_overlap"] >= frontier.DUPLICATE_TEXT
            # The author's own items and unrelated text raise nothing; the item is recorded either way.
            plain = frontier.record_item(ws, question, kind="next_step", text="Plot the residuals by batch.")
            assert "warnings" not in plain
            # Explicit board items (a caller that already read the board) take precedence over the lookup.
            quiet = frontier.record_item(ws, question, kind="gap", text="GSE000001 again.", existing=[])
            assert "warnings" not in quiet
    finally:
        ws.close()
    monkeypatch.delenv("BIO_AGENT")
    assert frontier.board_items() is None  # not an agent process: no board lookup


def test_evidence_on_another_participants_item_is_attributed_and_changes_no_status(demo):
    root, ctx = demo
    item = ctx["frontier"]["items"]["dana-untestable"]
    post = ctx["posts"]["finding"]
    bob, dana = ctx["agents"]["bob"], ctx["agents"]["dana"]
    with Community(root) as board:
        before = row(board, item)
        with pytest.raises(DawError, match="own_frontier_item"):
            frontier.record_peer_evidence(board, dana, item, "candidate_evidence", "mine", [f"post:{post}"])
        with pytest.raises(DawError, match="frontier_pointer_unresolved"):
            frontier.record_peer_evidence(board, bob, item, "candidate_evidence", "x", ["post:post_" + "0" * 32])
        with pytest.raises(DawError, match="invalid_frontier_evidence"):
            frontier.record_peer_evidence(board, bob, item, "candidate_evidence", "no pointer", [])
        with pytest.raises(DawError, match="invalid_frontier_status"):
            frontier.record_peer_evidence(board, bob, item, "promoted", "x", [f"post:{post}"])
        made = frontier.record_peer_evidence(board, bob, item, "candidate_evidence",
                                             "The full text is now fetchable; see the post.",
                                             [f"post:{post}", "accession:GSE000001"])
        assert made["participant"] == bob and made["owner"] == dana and not made["reused"]
        again = frontier.record_peer_evidence(board, bob, item, "candidate_evidence",
                                              "The full text is now fetchable; see the post.",
                                              [f"post:{post}", "accession:GSE000001"])
        assert again["reused"] and again["seq"] == made["seq"]
        assert row(board, item) == before  # the owner's status and the projection are untouched
        listed = next(i for i in agentview.frontier_list(board)["items"] if i["id"] == item)
        assert listed["status"] == before["status"]
        assert [(p["participant"], p["status"]) for p in listed["peer_evidence"]] == [(bob, "candidate_evidence")]
        _, shown = card(planning.board_view(board), item)
        assert shown["peer_evidence"][0]["reason"].startswith("The full text")
        view = agentview.overview(board, dana, after=0)
        assert any(r["record"] == "act" and r["act"] == "frontier_evidence" and r["target_id"] == item
                   and r["participant"] == bob for r in view["records"])
        mine = next(r for r in view["records"] if r["record"] == "frontier_item" and r["id"] == item)
        assert mine["peer_evidence"][0]["pointers"][0] == {"kind": "post", "id": post}
    # Through the board service socket handler, as the agent.
    through = boardservice.execute(root, ctx["agents"]["alice"], "frontier_evidence",
                                   {"item": item, "status": "closed", "reason": "Answered in the finding.",
                                    "pointers": [f"post:{post}"]})
    assert through["participant"] == ctx["agents"]["alice"] and through["status"] == "closed"
    with pytest.raises(DawError, match="invalid_board_request"):
        boardservice.execute(root, ctx["agents"]["alice"], "frontier_evidence", {"item": item, "extra": 1})
    # And from the CLI on a host.
    result = CliRunner().invoke(community_app, ["--root", str(root), "frontier-evidence", item, "--status",
                                                "candidate_evidence", "--reason", "CLI evidence.", "--pointer",
                                                f"post:{post}", "--author", "bob"], env={"BIO_AGENT": ""})
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["reason"] == "CLI evidence."
    with Community(root) as board:
        assert len(frontier.peer_evidence(board, [item])[item]) == 3


def test_the_same_question_to_many_owners_is_refused_after_three_targets(demo):
    root, ctx = demo
    with Community(root) as board:
        people = [ctx["agents"]["alice"], ctx["agents"]["dana"]] + [
            add_participant(board, name, "human")["id"] for name in ("rhea", "sol", "tau")]
        names = {p: board.agent(p)["name"] for p in people}

        def body(target, n):
            return (f"Hi {names[target]}, your full-text gap frontier_{n:032x} on PMC{1000 + n} is now resolvable: "
                    f"the article is cached as artifact_{n:064x}. Please update your gap's status.")
        for n, target in enumerate(people[:3]):
            board.ask(target, "bob", body(target, n), request_key=f"fan:{n}")
        with pytest.raises(DawError, match="identical_question_fanout") as refused:
            board.ask(people[3], "bob", body(people[3], 3))
        assert "community frontier-evidence" in refused.value.detail
        # Retries of an earlier ask, a follow-up to an earlier target and a different question all pass.
        assert board.ask(people[0], "bob", body(people[0], 0), request_key="fan:0")["target"] == people[0]
        assert board.ask(people[1], "bob", body(people[1], 9))["target"] == people[1]
        assert board.ask(people[4], "bob", "Which normalisation did you use for the qPCR table?")["target"] == people[4]
        # Another author is not limited by bob's asks.
        assert board.ask(people[3], "alice" if people[3] != ctx["agents"]["alice"] else "dana",
                         body(people[3], 3))["state"] == "pending"


def test_operators_may_brief_many_agents_with_one_text(demo):
    root, ctx = demo
    with Community(root) as board:
        people = [ctx["agents"][n] for n in ("alice", "bob", "dana")] + [
            add_participant(board, name, "human")["id"] for name in ("rhea",)]
        for target in people:
            assert board.ask(target, "operator", "Start the agenda item on donor structure.")["state"] == "pending"
