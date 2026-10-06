"""Render saved community search results without new analysis or external retrieval."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "sources" / "community"
seen = set()
lines = []
for query in ("polyasite", "longread", "gse139321"):
    path = root / f"rna-ends-{query}-search.json"
    response = json.loads(path.read_text())
    lines.append(f"SEARCH {query}")
    for item in response.get("items", []):
        ident = item["record_id"]
        if ident in seen:
            continue
        seen.add(ident)
        lines.extend([ident, item.get("title", ""),
                      "superseded_by=" + json.dumps(item.get("superseded_by", [])),
                      item.get("summary", ""), ""])
(root / "rna-ends-search-review.txt").write_text("\n".join(lines))
print(f"Rendered {len(seen)} distinct saved search records.")
