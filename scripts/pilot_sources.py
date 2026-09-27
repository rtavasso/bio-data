"""Complete bounded source handshakes and select native reference inputs."""
from daw.adapters import Sources
from daw.catalog import Workspace
from daw.inspectors import inspect_asset
from daw.transport import Transport
from daw.util import write_json

ws = Workspace("workspaces/pilot")
receipts = []
with ws.writer():
    for reference in ("zenodo:21324866", "zenodo:15581955", "zenodo:20101381", "chipatlas:SRX24150189"):
        source = Sources(ws)
        try:
            result = source.add(reference)
            receipts.append(result)
            print(reference, result["outcome"], flush=True)
            for aid in result["assets"]:
                a = ws.asset(aid)["body"]
                print("  ", a["name"], a["size"], a["url"], flush=True)
        finally:
            source.http.close()
        write_json("docs/receipts/extra-sources.json", receipts)
    urls = [
        "https://raw.githubusercontent.com/scverse/scanpy/main/src/scanpy/datasets/_datasets.py",
        "https://raw.githubusercontent.com/scverse/scanpy/main/src/scanpy/datasets/_utils.py",
        "https://exampledata.scverse.org/scanpy/pbmc3k_raw.h5ad",
        "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.chrom.sizes",
        "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/database/refGene.txt.gz",
        "https://hgdownload.soe.ucsc.edu/goldenPath/rn6/bigZips/rn6.chrom.sizes",
        "https://hgdownload.soe.ucsc.edu/goldenPath/rn6/database/refGene.txt.gz",
        "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/database/refGene.sql",
    ]
    for url in urls:
        source = Sources(ws)
        try:
            listed = source.add(url)
            receipt = source.http.acquire(listed["assets"][0])
            receipts.append({"listing": listed, "acquisition": receipt})
            if receipt["outcome"] == "available_full":
                receipts.append(inspect_asset(ws, receipt["asset_revision"]))
            print(url, receipt["outcome"], flush=True)
        finally:
            source.http.close()
        write_json("docs/receipts/extra-sources.json", receipts)
    http = Transport(ws)
    for asset in ws.assets():
        if asset["body"]["metadata"].get("genome") == "hg38" and asset["body"]["name"] in {
            "SRX24150189.bw", "SRX24150189.05.bed", "SRX24150189.20.bed"}:
            receipt = http.acquire(asset["id"])
            receipts.append(receipt)
            if receipt["outcome"] == "available_full":
                receipts.append(inspect_asset(ws, receipt["asset_revision"]))
            print(asset["body"]["name"], receipt["outcome"], flush=True)
            write_json("docs/receipts/extra-sources.json", receipts)
    http.close()
ws.close()
