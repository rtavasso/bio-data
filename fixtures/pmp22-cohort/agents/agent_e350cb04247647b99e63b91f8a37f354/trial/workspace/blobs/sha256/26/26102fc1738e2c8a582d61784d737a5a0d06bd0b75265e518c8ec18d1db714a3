"""Render current QKI peer evidence without re-running the eCLIP screen."""
import json
from pathlib import Path

q = Path(__file__).resolve().parents[1]
root = q / "sources" / "community"
lines = []
for name in ("qki-parent", "qki-question"):
    post = json.loads((root / f"{name}.json").read_text())
    lines += [post["id"], post["content"]["body"],
              "replies=" + json.dumps(post.get("replies", [])),
              "superseded_by=" + json.dumps(post.get("superseded_by", [])), ""]
for name in ("qki-search", "qki-paper-search"):
    search = json.loads((root / f"{name}.json").read_text())
    lines.append(name)
    for item in search.get("items", []):
        lines += [item["record_id"], item.get("title", ""),
                  "superseded_by=" + json.dumps(item.get("superseded_by", [])),
                  item.get("summary", ""), ""]
(root / "qki-review.txt").write_text("\n".join(lines))
artifact = json.loads((root / "qki-site-artifact.json").read_text())
summary = {key: artifact[key] for key in ("id", "path", "output_blob")}
summary["output"] = artifact["manifest"]["output"]
(root / "qki-site-locator.json").write_text(json.dumps(summary, indent=2))
print("Saved peer evidence review; no biological computations performed.")
