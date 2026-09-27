"""Read-only bounded previews for reviewing the pilot's exact acquired representations."""
import json

from daw.catalog import Workspace
from daw.util import read_json

ws = Workspace("workspaces/pilot")
for a in ws.assets():
    if a["access"] != "available_full":
        continue
    row = ws.one("SELECT blob FROM inspection WHERE asset_revision=? ORDER BY created DESC LIMIT 1", (a["id"],))
    if not row:
        continue
    data = read_json(ws.blob_path(row["blob"]))
    if data.get("kind") == "workbook":
        print(json.dumps({"name": a["body"]["name"], "id": a["id"], "blob": a["blob"], "sheets": data["sheets"]}, ensure_ascii=False)[:14000])
    elif data.get("kind") == "delimited":
        print(json.dumps({"name": a["body"]["name"], "id": a["id"], "blob": a["blob"], "preview": data["preview"][:3]}, ensure_ascii=False)[:10000])
ws.close()
