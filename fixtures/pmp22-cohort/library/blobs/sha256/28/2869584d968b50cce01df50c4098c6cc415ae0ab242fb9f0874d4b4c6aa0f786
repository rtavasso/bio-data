"""Calculate one ratio from a verified published synthetic mean table."""

import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--input-artifact", required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--source-post", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    data = args.input.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != args.input_sha256:
        raise ValueError("Input bytes do not match the inspected artifact")
    reader = csv.DictReader(io.StringIO(data.decode("utf-8")), delimiter="\t")
    if reader.fieldnames != ["gene", "mean_arbitrary_units"]:
        raise ValueError("Unexpected mean-table header")
    means = {}
    for row in reader:
        gene = row["gene"]
        if None in row or not gene or gene in means:
            raise ValueError("Malformed or duplicate gene row")
        mean = Decimal(row["mean_arbitrary_units"])
        if not mean.is_finite():
            raise ValueError("Non-finite mean")
        means[gene] = mean
    numerator = means["PMP22"]
    denominator = means["SOX10"]
    if denominator == 0:
        raise ValueError("SOX10 mean is zero; ratio undefined")
    ratio = numerator / denominator
    result = {
        "input_artifact": args.input_artifact,
        "input_sha256": digest,
        "source_post": args.source_post,
        "numerator_gene": "PMP22",
        "numerator_mean": float(numerator),
        "denominator_gene": "SOX10",
        "denominator_mean": float(denominator),
        "mean_units": "synthetic arbitrary units",
        "operation": "PMP22 mean / SOX10 mean",
        "ratio": float(ratio),
        "ratio_decimal": str(ratio),
        "ratio_units": "dimensionless",
        "limitation": "Synthetic infrastructure validation; no biological claim.",
    }
    serialized = json.dumps(result, indent=2, allow_nan=False) + "\n"
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(serialized)
    if json.loads(args.output.read_text(encoding="utf-8")) != result:
        raise ValueError("Output round-trip validation failed")
    print(f"PMP22 mean {numerator} / SOX10 mean {denominator} = {ratio}")
    print(f"Validated input SHA256: {digest}")
    print("Validated finite JSON and output round-trip equality.")


if __name__ == "__main__":
    main()
