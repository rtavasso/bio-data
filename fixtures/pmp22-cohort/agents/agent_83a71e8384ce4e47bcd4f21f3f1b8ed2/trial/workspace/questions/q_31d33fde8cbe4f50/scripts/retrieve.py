"""Explicit HTTPS acquisition, exact payload and per-attempt receipt; no source code execution."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib
from urllib.request import Request, urlopen
from urllib.error import HTTPError

p = argparse.ArgumentParser()
p.add_argument("label")
p.add_argument("url")
a = p.parse_args()
q = Path(__file__).resolve().parents[1]
o = q / "inputs/sources"
o.mkdir(parents=True, exist_ok=True)
rp = o / (a.label + ".receipt.json")
dest = o / (a.label + ".source")
assert not rp.exists() and not dest.exists(), "Fresh labels required"
config = tomllib.loads((Path(os.environ["BIO_WORKSPACE"]) / "config.toml").read_text())
reserve = 5368709120
for section in config.values():
    if isinstance(section, dict) and "reserve_bytes" in section:
        reserve = max(reserve, section["reserve_bytes"])
r = {"url": a.url, "started_utc": datetime.now(timezone.utc).isoformat(), "reserve_bytes": reserve}
assert shutil.disk_usage(o).free > reserve
try:
    try:
        response = urlopen(Request(a.url, headers={"User-Agent": "bio-data-research/1.0"}), timeout=180)
    except HTTPError as e:
        response = e
    with response as f, dest.open("wb") as d:
        r.update(status=f.status, final_url=f.url, headers=dict(f.headers))
        while block := f.read(1024 * 1024):
            assert shutil.disk_usage(o).free > reserve + len(block), "disk reserve"
            d.write(block)
    r.update(bytes=dest.stat().st_size, sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
    add = subprocess.run(
        ["./bin/bio", "object", "add", str(dest)], capture_output=True, text=True, check=True
    )
    r["object"] = json.loads(add.stdout)
except Exception as e:
    r["error"] = repr(e)
r["finished_utc"] = datetime.now(timezone.utc).isoformat()
rp.write_text(json.dumps(r, indent=2, allow_nan=False))
print(json.dumps(r, allow_nan=False))
