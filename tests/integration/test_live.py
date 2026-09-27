"""Small explicit-network smoke checks; receipts are persisted inside the test workspace."""
import pytest

from daw.adapters import Sources
from daw.models import Discovery


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
