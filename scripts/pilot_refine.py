"""Recheck observed provider schemas and retain narrow follow-up discovery receipts."""
import json

from daw.adapters import Sources
from daw.catalog import Workspace
from daw.models import Discovery
from daw.util import write_json

ws = Workspace("workspaces/pilot")
receipts = []
with ws.writer():
    for reference in ("GSE139321", "GSE201627", "GSE201623", "PMC11592338", "PMC7430845", "chipatlas:SRX24150189"):
        source = Sources(ws)
        try:
            receipt = source.add(reference)
            receipts.append(receipt)
            print(reference, receipt["outcome"], len(receipt["assets"]), receipt.get("warnings", receipt.get("reason")), flush=True)
        finally:
            source.http.close()
        write_json("docs/receipts/provider-refinements.json", receipts)
    source = Sources(ws)
    try:
        for term in ('"Schwann cells" AND (RNA OR sequencing OR transcriptomic)', 'PMP22'):
            receipt = source.discover(Discovery(provider="zenodo", query=term, max_pages=1, page_size=5))
            receipts.append(receipt)
            for rid in receipt["resources"]:
                row = ws.one("SELECT native_id,body FROM resource WHERE id=?", (rid,))
                record = json.loads(row["body"])
                print("zenodo", row["native_id"], record.get("metadata", {}).get("title"), flush=True)
        write_json("docs/receipts/provider-refinements.json", receipts)
    finally:
        source.http.close()
ws.close()
