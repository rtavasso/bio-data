"""Bounded primary-text retrieval with native bytes and actual transport receipts."""
import hashlib
import json
import shutil
import sys
import tomllib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

q = Path(__file__).resolve().parents[1]
workspace = q.parents[1]
config = tomllib.loads((workspace / "config.toml").read_text())
budget = config["budgets"]
usage = shutil.disk_usage(workspace)
cap = 2_000_000
reserve = max(budget["reserve_bytes"], usage.total * budget["reserve_fraction"])
assert usage.free - 2 * cap > reserve, "Configured disk reserve would be crossed"
assert budget["asset_bytes"] == 0 or cap <= budget["asset_bytes"]
root = q / "sources" / "qki-live"
root.mkdir(exist_ok=True)
targets = {
    "PMC13234107-bioc.xml": "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_xml/PMC13234107/unicode",
    "NCBI-Gene5376.html": "https://www.ncbi.nlm.nih.gov/gene/5376/",
    "human-PMP22-two-refseq.gb": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id=NM_000304.4,NM_153321.3&rettype=gb&retmode=text",
}
if len(sys.argv) > 1:
    targets = {name: targets[name] for name in sys.argv[1:]}


def retrieve(item):
    name, url = item
    path = root / name
    assert not path.exists(), "Do not overwrite immutable source bytes"
    receipt = {"url": url, "requested_utc": datetime.now(timezone.utc).isoformat(),
               "byte_cap": cap, "configured_reserve_bytes": reserve}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "bio-data-bounded-source-audit/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read(cap + 1)
            if len(payload) > cap:
                raise ValueError("Response exceeds byte cap")
            receipt.update(status=response.status, final_url=response.url,
                           content_type=response.headers.get("Content-Type", ""))
        path.write_bytes(payload)
        receipt.update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
                       source_path=str(path), received=True)
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        receipt.update(received=False, error=repr(error))
    (root / (name + ".receipt.json")).write_text(json.dumps(receipt, indent=2))
    return receipt


with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(retrieve, targets.items()))
print(json.dumps(results, indent=2))
if not all(result["received"] for result in results):
    raise SystemExit(1)
