"""Final relationship refresh and two distinct BioStudies metadata shapes."""
from daw.adapters import Sources
from daw.catalog import Workspace
from daw.models import Discovery
from daw.util import write_json

ws = Workspace("workspaces/pilot")
receipts = []
with ws.writer():
    for reference, provider in [("GSE139321", "geo"), ("GSE201627", "geo"), ("GSE201623", "geo"),
                                ("S-EPMC9722693", "biostudies")]:
        sources = Sources(ws)
        try:
            result = sources.add(reference, provider)
            receipts.append(result)
            print(reference, result["outcome"], len(result["assets"]), flush=True)
        finally:
            sources.http.close()
    sources = Sources(ws)
    try:
        result = sources.discover(Discovery(provider="europepmc", query="EXT_ID:32770939", max_pages=2, page_size=10))
        receipts.append(result)
        print("Europe PMC", result["exhausted"], result["warnings"],
            [(len(p["items"]), p["reported_total"], p["next_cursor"]) for p in result["pages"]], flush=True)
    finally:
        sources.http.close()
    write_json("docs/receipts/final-handshakes.json", receipts)
ws.close()
