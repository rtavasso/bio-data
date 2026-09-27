"""Acquire only bounded processed pilot representations, preserving remaining inventory."""
from daw.adapters import Sources
from daw.catalog import Workspace
from daw.inspectors import extract_members, inspect_asset
from daw.transport import Transport
from daw.util import write_json

ws = Workspace("workspaces/pilot")
receipts = []
with ws.writer():
    http = Transport(ws)
    selected = [a for a in ws.assets() if not a["body"]["raw"] and (
        a["body"]["name"].endswith((".xlsx", ".xml")) or
        a["body"]["name"] == "biomedicines-12-02594-s001.zip" or
        a["body"]["name"].startswith(("GSE139321_", "GSE201623_", "GSM6068778_")))]
    for asset in selected:
        result = http.acquire(asset["id"])
        receipts.append(result)
        print(asset["body"]["name"], result["outcome"], flush=True)
        if result["outcome"] == "available_full":
            inspection = inspect_asset(ws, result["asset_revision"])
            receipts.append(inspection)
            if inspection.get("kind") in {"archive", "gzip"}:
                members = [m["name"] for m in inspection["members"] if not m.get("directory") and
                           m["name"].lower().endswith((".xlsx", ".tsv", ".csv", ".txt", ".narrowpeak"))]
                if members:
                    for member in extract_members(ws, result["asset_revision"], members):
                        receipts.append(member)
                        receipt = inspect_asset(ws, member["asset_revision"])
                        receipts.append(receipt)
                        print("  member", member["member"], receipt["status"], flush=True)
            if asset["body"]["name"].endswith(".xml"):
                source = Sources(ws, http)
                receipts.append(source.jats_links(result["asset_revision"]))
        write_json("docs/receipts/pilot-acquisition.json", receipts)
    http.close()
ws.close()
