"""Inspect identifiers without silently normalizing them, and before any join."""

import csv
import gzip
import json
from pathlib import Path

q = Path(__file__).resolve().parents[1]
s = q / "inputs/sources"
with gzip.open(s / "gtex-flair-counts.source", "rt") as f:
    r = csv.reader(f, delimiter="\t")
    next(r)
    for i, row in enumerate(r):
        if i < 3 or "ENSG00000109099" in row[0]:
            print(repr(row[0]), len(row), sum(map(float, row[1:])))
x = json.loads((s / "gtex-file-list.source").read_text())
for row in x:
    if "gencode" in row.get("fileName", "").lower() and "annotation" in row.get("fileName", "").lower():
        print(row)
