"""Bounded live provider handshakes. Run explicitly; no network during tests by default."""
from pathlib import Path

from daw.adapters import Sources
from daw.catalog import Workspace
from daw.models import Discovery
from daw.util import write_json

workspace = Workspace.create("workspaces/pilot")
receipts = []
with workspace.writer():
    for reference, provider in [("32770939", "europepmc"), ("GSE139321", "geo"),
                                ("GSE201627", "geo"), ("GSE201623", "geo"),
                                ("PRJNA579292", "ena"), ("ENCSR000AKO", "encode"),
                                ("E-MTAB-10553", "biostudies")]:
        source = Sources(workspace)
        try:
            receipt = source.add(reference, provider)
            receipts.append(receipt)
            print(reference, receipt["outcome"], len(receipt["assets"]), receipt.get("warnings", receipt.get("reason")), flush=True)
        finally:
            source.http.close()
        write_json(Path("docs/receipts/provider-probes.json"), receipts)
    for provider, term in [("zenodo", "Schwann"), ("chipatlas", "Schwann")]:
        source = Sources(workspace)
        try:
            result = source.discover(Discovery(provider=provider, query=term, page_size=5, max_pages=1))
            receipts.append(result)
            print(provider, len(result["resources"]), result["warnings"], flush=True)
        finally:
            source.http.close()
        write_json(Path("docs/receipts/provider-probes.json"), receipts)
workspace.close()
