"""Round three: verify --numbers sees the tables a post's claims point at, checks sentence-final numbers and runs on
an unposted draft; the full-text ladder distinguishes abstract-only routes and resolves PMIDs and DOIs; PMC, PMID
and DOI are accession pointers; CLI errors also reach stderr. Offline: every network call is an httpx.MockTransport."""
import json
import sys

import httpx
import pytest
from typer.testing import CliRunner

from daw.artifacts import register_artifact
from daw.bio_cli import app
from daw.catalog import Workspace
from daw.community import PROSE_NUMBER, Community
from daw.substrate_models import ArtifactRegistration, Derivation, ObjectInput
from daw.util import DawError
from daw.work import create_question


def no_reserve(root):
    (root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0\n")


@pytest.fixture
def board(tmp_path):
    board = Community.create(tmp_path / "community")
    no_reserve(board.library.root)
    board.library.close()
    board.library = Workspace(board.root / "library")
    yield board
    board.close()


def register(ws, tmp_path, question, name, text):
    src = tmp_path / f"{name}.in.tsv"
    src.write_text("x\n1\n")
    asset = ws.local_asset(src, "input " + name)
    spec = ArtifactRegistration(title=name, summary="fixture", derivation=Derivation(
        inputs=[ObjectInput(blob=asset["blob"], source_identity=asset["asset_revision"])],
        code=[ws.put_bytes(f"# {name}\n".encode())], parameters={}, references=[], environment={"fixture": True}))
    out = tmp_path / f"{name}.tsv"
    out.write_text(text)
    return register_artifact(ws, out, spec, question=question)["artifact"]


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    Workspace.create(root).close()
    no_reserve(root)
    ws = Workspace(root)
    question = create_question(ws, "Nedd4 counts")["question"]
    counts = register(ws, tmp_path, question, "counts",
                      "row\tdifference_cko_minus_control\nFig9b_E17.5\t-0.328428\nFig9b_P5\t12.75\n")
    cited = register(ws, tmp_path, question, "cited", "gene\teffect\nPmp22\t0.4217\n")
    yield ws, question, counts, cited
    ws.close()


# ---- 1. an answer's numbers come from the cells its own claim pointers name (post_f4838678… on the live board)

def test_verify_numbers_includes_claim_pointed_and_cited_post_tables(board, source):
    ws, question, counts, cited = source
    board.publish("operator", "Counts", "The counts table.", workspace=ws.root, artifacts=[counts], question=question)
    cited_post = board.publish("operator", "Effects", "The effects table.", workspace=ws.root, artifacts=[cited],
                               question=question)
    claims = [{"text": "Schwann-cell counts already differ at E17.5.", "status": "supported",
               "pointers": [{"kind": "locator", "id": counts, "locator": "row=Fig9b_E17.5;col=difference_cko_minus_control"}]}]
    body = (f"Counts differ by -0.328428 at E17.5 and by 12.75 at P5. As {cited_post['id']} showed, the effect "
            "is 0.42.")
    answer = board.publish("operator", "Answer", body, claims=claims)
    numbers = board.verify(answer["id"], numbers=True)["numbers"]
    assert numbers["unmatched"] == [] and numbers["checked"] == 3
    assert {t["source"] for t in numbers["tables"]} == {"claim", "cited_post"}
    assert numbers["unpointed"] == 3  # no pointer of their own: a warning field, not a failure


# ---- 2. a number before a sentence-final period is checked

def test_prose_number_includes_sentence_final_numbers_only():
    found = lambda text: [m.group(0) for m in PROSE_NUMBER.finditer(text)]  # noqa: E731
    assert found("The effect was 0.42.") == ["0.42"]
    assert found("Counts rose to 1234. Then fell.") == ["1234"]
    assert found("It was -1.5e-3.") == ["-1.5e-3"]
    assert found("Version 1.2.3 and ratio 1.5/2 and PMC1234567. GSE177037.") == []


# ---- 3. verify --draft: the claims-block check the runtime applies and the numbers check, before posting

def test_verify_draft_reports_refusals_numbers_and_writes_nothing(board, source, tmp_path):
    ws, question, counts, cited = source
    board.publish("operator", "Counts", "The counts table.", workspace=ws.root, artifacts=[counts], question=question)
    block = json.dumps([{"text": "Counts differ at E17.5.", "status": "supported",
                         "pointers": [{"kind": "locator", "id": counts,
                                       "locator": "row=Fig9b_E17.5;col=difference_cko_minus_control"}]}])
    good = f"Counts differ by -0.328428 at E17.5.\n\n```claims\n{block}\n```\n"
    posts = board.one("SELECT count(*) AS n FROM post")["n"]
    blobs = board.library.one("SELECT count(*) AS n FROM blob")["n"]
    checked = board.verify_draft(good)
    assert checked["verified"] and checked["would_refuse"] == [] and checked["claims"]["valid"]
    assert checked["numbers"]["unmatched"] == [] and checked["numbers"]["tables"][0]["source"] == "claim"
    assert [w["code"] for w in checked["warnings"]] == ["unpointed_numbers"] and checked["warnings"][0]["count"] == 1
    pointed = f"Counts differ by [-0.328428]({counts}#row=Fig9b_E17.5;col=difference_cko_minus_control)."
    assert board.verify_draft(pointed)["numbers"]["matched_by_pointer"] == 1
    wrong = f"Counts differ by [-0.5]({counts}#row=Fig9b_E17.5;col=difference_cko_minus_control)."
    assert [m["number"] for m in board.verify_draft(wrong)["numbers"]["pointer_mismatches"]] == ["-0.5"]
    bad = good.replace(counts, "artifact_" + "0" * 64) + "Also 9.99."
    refused = board.verify_draft(bad)
    assert refused["would_refuse"][0]["reason"] == "claim_pointer_unresolved" and not refused["verified"]
    assert "9.99" in refused["numbers"]["unmatched"]
    assert board.one("SELECT count(*) AS n FROM post")["n"] == posts
    assert board.library.one("SELECT count(*) AS n FROM blob")["n"] == blobs
    # --question: the question's registered (unpublished) tables are in the universe.
    local = board.verify_draft("The effect is 0.4217.", workspace=ws.root, question=question)
    assert local["numbers"]["unmatched"] == [] and "question" in {t["source"] for t in local["numbers"]["tables"]}
    with pytest.raises(DawError):
        board.verify_draft("x", question=question)
    draft = tmp_path / "ANSWER.md"
    draft.write_text(bad)
    out = CliRunner().invoke(app, ["community", "--root", str(board.root), "verify", "--draft", str(draft)])
    assert out.exit_code == 0, out.output
    assert json.loads(out.output)["would_refuse"][0]["code"] == "claims_refused"


def test_board_service_accepts_a_draft_verify():
    from daw.commons.boardservice import OPERATIONS
    assert {"draft", "question", "workspace"} <= OPERATIONS["verify"][1]


# ---- 4. full-text ladder: abstract-only routes, PMID and DOI resolution

def article(body_paragraphs, abstract=True):
    front = ("<front><article-meta><title-group><article-title>Dosage</article-title></title-group>"
             + ("<abstract><p>PMP22 dosage abstract.</p></abstract>" if abstract else "") + "</article-meta></front>")
    body = "".join(f"<p>Body paragraph {i}.</p>" for i in range(body_paragraphs))
    return f'<?xml version="1.0"?><article>{front}<body><sec><title>Results</title>{body}</sec></body></article>'.encode()


@pytest.fixture
def sources(tmp_path):
    from daw.adapters import Sources
    from daw.transport import Transport
    root = tmp_path / "ws"
    Workspace.create(root).close()
    no_reserve(root)
    ws = Workspace(root)

    def make(serve):
        return Sources(ws, Transport(ws, http_transport=httpx.MockTransport(serve), sleep=lambda _: None))
    yield ws, make
    ws.close()


def test_fulltext_abstract_only_route_falls_through_and_is_kept_only_as_a_last_resort(sources):
    ws, make = sources

    def serve(request):
        if "ebi.ac.uk" in request.url.host:
            return httpx.Response(200, content=article(0))
        if "eutils" in request.url.host:
            return httpx.Response(200, content=article(2))
        return httpx.Response(200, content=b"No result can be found")
    with ws.writer():
        fetched = make(serve).fulltext("PMC6607759")
    assert fetched["outcome"] == "available_full" and fetched["route"] == "ncbi_efetch" and fetched["paragraphs"] == 3
    assert [r["outcome"] for r in fetched["routes"]] == ["abstract_only", "available_full"]

    def abstracts(request):
        if "bionlp" in request.url.host:
            return httpx.Response(200, content=b"No result can be found")
        return httpx.Response(200, content=article(0))
    with ws.writer():
        kept = make(abstracts).fulltext("PMC4643454")
    assert kept["outcome"] == "abstract_only" and kept["paragraphs"] == 1 and kept["paragraphs_blob"]
    assert [r["outcome"] for r in kept["routes"]][:2] == ["abstract_only", "abstract_only"]
    assert "bio work gap" in kept["note"]


def test_bioc_abstract_passages_are_not_body():
    from daw.adapters import body_paragraph
    assert not body_paragraph({"locator": "passage[2]", "section": "ABSTRACT", "text": "a"})
    assert not body_paragraph({"locator": "abstract[1]/p[1]", "section": "", "text": "a"})
    assert body_paragraph({"locator": "passage[3]", "section": "RESULTS", "text": "a"})
    assert body_paragraph({"locator": "sec[1]/p[1]", "section": "Results", "text": "a"})


def test_fulltext_resolves_pmid_and_doi_and_reports_no_pmcid(sources):
    ws, make = sources
    asked = []

    def serve(request):
        asked.append(str(request.url))
        if "idconv" in request.url.path:
            ids = request.url.params["ids"]
            records = [{"pmid": "31000001", "pmcid": "PMC6607759"}] if ids in {"31000001", "10.1000/xyz.1"} else \
                [{"pmid": ids, "status": "error", "errmsg": "invalid article id"}]
            return httpx.Response(200, json={"status": "ok", "records": records})
        if "ebi.ac.uk" in request.url.host and "search" in request.url.path:
            return httpx.Response(200, json={"resultList": {"result": [{"id": "1", "source": "MED"}]}})
        if "ebi.ac.uk" in request.url.host:
            return httpx.Response(200, content=article(2))
        return httpx.Response(404)
    for reference in ("PMID:31000001", "PMID31000001", "31000001", "10.1000/xyz.1", "doi:10.1000/xyz.1"):
        with ws.writer():
            fetched = make(serve).fulltext(reference)
        assert fetched["outcome"] == "available_full" and fetched["pmcid"] == "PMC6607759", reference
        assert fetched["resolution"]["pmcid"] == "PMC6607759" and fetched["resolution"]["routes"][0]["route"] == "ncbi_idconv"
    assert any("www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/" in a for a in asked)
    with ws.writer():
        missing = make(serve).fulltext("PMID:99")
    assert missing["outcome"] == "no_pmcid" and missing["pmcid"] is None
    assert [r["route"] for r in missing["resolution"]["routes"]] == ["ncbi_idconv", "europepmc_search"]
    with ws.writer():
        supplement = make(serve).supplementary("PMID:99")
    assert supplement["outcome"] == "no_pmcid" and supplement["resolution"]["kind"] == "pmid"
    with pytest.raises(DawError) as error:
        make(serve).fulltext("not-an-id")
    assert error.value.reason == "unsupported_reference"


# ---- 5. PMC, PMID and DOI are accession pointers

def test_accessions_accept_pmc_pmid_and_doi():
    from daw.commons.claims import ACCESSIONS
    for value in ("PMC6607759", "PMID:31000001", "PMID31000001", "10.1038/s41586-020-2012-7", "GSE177037"):
        assert ACCESSIONS.fullmatch(value), value
    for value in ("PMC", "PMID:", "10.1/x", "doi:10.1038/x", "31000001"):
        assert not ACCESSIONS.fullmatch(value), value


# ---- 6. CLI errors reach stderr as well as stdout

def test_cli_errors_write_one_line_to_stderr(tmp_path, monkeypatch, capsys):
    from daw import bio_cli, cli
    monkeypatch.delenv("BIO_BOARD_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["bio", "community", "--root", str(tmp_path / "c"), "verify"])
    with pytest.raises(SystemExit) as code:
        bio_cli.main()
    captured = capsys.readouterr()
    assert code.value.code == 1 and json.loads(captured.out)["error"] == "invalid_verify"
    assert captured.err.startswith("error: invalid_verify: name a post") and captured.err.count("\n") == 1
    monkeypatch.setattr(sys, "argv", ["daw", "--workspace", str(tmp_path / "missing"), "bundle", "inventory", "b"])
    with pytest.raises(SystemExit):
        cli.main()
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"] == "workspace_not_initialized"
    assert captured.err.startswith("error: workspace_not_initialized: ")
