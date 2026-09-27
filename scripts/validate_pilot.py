"""Independently check pilot source cells, exact signal and native interval overlaps."""
import csv
import json
import math
import re

import openpyxl
import pyarrow.parquet as pq
import pyBigWig

from daw.catalog import Workspace
from daw.util import read_json, write_json

ws = Workspace("workspaces/pilot")
books, tables = {}, {}
cell_checks = []
try:
    for query in read_json("docs/receipts/pilot-table-results.json")["queries"][:3]:
        records = pq.read_table(ws.blob_path(query["artifacts"]["measurements.parquet"])).to_pylist()
        missing = 0
        for row in records:
            asset = ws.asset(row["asset_revision"])
            path = ws.blob_path(asset["blob"])
            if asset["body"]["name"].endswith(".xlsx"):
                if asset["blob"] not in books:
                    books[asset["blob"]] = openpyxl.load_workbook(path.open("rb"), read_only=False, data_only=True)
                match = re.fullmatch(r"sheet:(.*)!row:(\d+):column:(\d+)", row["locator"])
                value = books[asset["blob"]][match[1]].cell(int(match[2]), int(match[3])).value
            else:
                if asset["blob"] not in tables:
                    with path.open() as stream:
                        tables[asset["blob"]] = list(csv.reader(stream, delimiter="\t"))
                match = re.fullmatch(r"row:(\d+):column:(\d+)", row["locator"])
                value = tables[asset["blob"]][int(match[1]) - 1][int(match[2]) - 1]
            if value is None or value == "":
                assert row["value"] is None and row["text"] == (None if value is None else ""), row["locator"]
                missing += 1
            else:
                assert row["value"] == float(value), (row["locator"], value, row["value"])
                assert row["text"] == str(value), (row["locator"], "literal value changed")
        cell_checks.append({"run": query["run"], "exact_source_cells": len(records),
                            "numeric_values": len(records) - missing, "source_blank_values": missing, "match": True})
    genomic_checks = []
    for query in read_json("docs/receipts/pilot-genomic-results.json")["queries"]:
        request = read_json(ws.blob_path(query["artifacts"]["request.json"]))
        region = request["region"]
        records = pq.read_table(ws.blob_path(query["artifacts"]["measurements.parquet"])).to_pylist()
        if request["operator"] == "signal.interval_summary":
            assert len(records) == 1
            asset = ws.asset(records[0]["asset_revision"])
            with pyBigWig.open(str(ws.blob_path(asset["blob"]))) as bw:
                expected = bw.stats(region["chrom"], region["start"], region["end"], exact=True)[0]
            assert math.isclose(records[0]["value"], expected, rel_tol=1e-12)
            genomic_checks.append({"run": query["run"], "exact_native_mean": expected, "match": True})
        else:
            asset = ws.asset(records[0]["asset_revision"])
            with ws.blob_path(asset["blob"]).open() as stream:
                expected = [(i, int(r[1]), int(r[2])) for i, r in enumerate(csv.reader(stream, delimiter="\t"), 1)
                            if r[0] == region["chrom"] and int(r[1]) < region["end"] and int(r[2]) > region["start"]]
            actual = [json.loads(r["details_json"]) for r in records]
            assert expected == [(r["source_row"], r["start"], r["end"]) for r in actual]
            genomic_checks.append({"run": query["run"], "native_overlapping_rows": len(expected), "match": True})
    write_json("docs/receipts/numerical-crosschecks.json", {"table_cells": cell_checks, "genomic": genomic_checks,
        "limits": "Source-cell/vector agreement checks extraction, not author preprocessing or biological causality"})
    print("Validated", sum(c["exact_source_cells"] for c in cell_checks), "source cells and", len(genomic_checks), "genomic queries")
finally:
    for book in books.values():
        book.close()
    ws.close()
