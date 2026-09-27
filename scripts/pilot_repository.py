"""Bounded repository-first acquisition and independent Figshare handshake."""
from daw.adapters import Sources
from daw.catalog import Workspace
from daw.inspectors import inspect_asset
from daw.util import read_json, write_json


ws = Workspace("workspaces/pilot")
receipts = {}
with ws.writer():
    sources = Sources(ws)
    try:
        index = sources.http.fetch("https://api.figshare.com/v2/articles?page_size=1&order=published_date&order_direction=desc")
        receipts["figshare_index"] = index
        if index["outcome"] == "available_full":
            rows = read_json(ws.blob_path(index["blob"]))
            if rows:
                receipts["figshare_record"] = sources.add("figshare:" + str(rows[0]["id"]))
        for asset in ws.assets():
            if asset["body"].get("version") == "21324866" and asset["body"]["name"] in {"FPKM-NF2-VS-71.txt", "matrix.mtx.gz"}:
                result = sources.http.acquire(asset["id"])
                receipts[asset["body"]["name"]] = result
                if result["outcome"] == "available_full":
                    receipts[asset["body"]["name"] + ".inspection"] = inspect_asset(ws, result["asset_revision"])
                print(asset["body"]["name"], result["outcome"], flush=True)
        write_json("docs/receipts/repository-acquisition.json", receipts)
    finally:
        sources.http.close()
ws.close()
