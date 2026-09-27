"""Small explicit-network smoke checks; receipts are persisted inside the test workspace."""
import pytest

from daw.adapters import Sources
from daw.models import Discovery
from daw.indexer import create_job, run_job
from daw.substrate_models import IndexPlan, Seed
from daw.util import write_json


@pytest.mark.live
def test_europe_pmc_live(ws):
    source = Sources(ws)
    try:
        result = source.discover(Discovery(provider="europepmc", query="EXT_ID:32770939", max_pages=2, page_size=10))
        assert result["resources"] and result["pages"]
        assert result["exhausted"]
    finally:
        source.http.close()


@pytest.mark.live
def test_pmc_cloud_live(ws):
    source = Sources(ws)
    try:
        result = source.add("PMC11592338")
        assert result["outcome"] == "inventoried" and result["assets"]
        assert any(ws.asset(a)["body"]["name"].endswith(".zip") for a in result["assets"])
    finally:
        source.http.close()


@pytest.mark.live
def test_geo_metadata_index_live(ws):
    job = create_job(ws, IndexPlan(level=1, include_existing=False,
        seeds=[Seed(reference="GSE201623")], max_tasks=30, max_requests=10))
    result = run_job(ws, job["id"])
    write_json(ws.root / "reports/live-index.json", result)
    assert result["state"] == "complete"
    assets = ws.assets()
    assert any(a["body"]["name"].endswith(".counts.txt.gz") for a in assets)
    assert all(a["blob"] is None for a in assets)
    assert ws.one("SELECT count(*) AS n FROM search_document")["n"] > 0
