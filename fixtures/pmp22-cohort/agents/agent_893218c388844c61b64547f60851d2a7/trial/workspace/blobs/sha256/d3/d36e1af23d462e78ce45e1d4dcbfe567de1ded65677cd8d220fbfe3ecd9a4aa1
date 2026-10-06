"""Mean each synthetic gene across exactly sample1, sample2, sample3."""
import argparse
import csv
from decimal import Decimal
from pathlib import Path
from statistics import mean
import sys


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
if args.input.resolve() == args.output.resolve():
    raise ValueError("Output must not overwrite source")

samples = ["sample1", "sample2", "sample3"]
results = []
seen = set()
with args.input.open(newline="") as stream:
    reader = csv.reader(stream, delimiter="\t")
    if next(reader) != ["gene", *samples]:
        raise ValueError("Unexpected source columns")
    for row in reader:
        if len(row) != 4 or not row[0] or row[0] in seen:
            raise ValueError(f"Malformed or duplicate gene row: {row!r}")
        values = [Decimal(token) for token in row[1:]]
        if not all(value.is_finite() for value in values):
            raise ValueError("Missing or non-finite sample value")
        seen.add(row[0])
        results.append([row[0], str(mean(values))])
if not results:
    raise ValueError("No gene rows")

args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open("w", newline="") as stream:
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(["gene", "mean_arbitrary_units"])
    writer.writerows(results)
with args.output.open(newline="") as stream:
    observed = list(csv.reader(stream, delimiter="\t"))
if observed != [["gene", "mean_arbitrary_units"], *results]:
    raise ValueError("Output round-trip validation failed")
print(f"Python {sys.version.split()[0]}; validated {len(results)} genes, {len(samples)} samples each")
for gene, value in results:
    print(f"{gene}\t{value}")
print("Synthetic arbitrary units; no biological claim.")
