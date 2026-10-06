import csv, sys
import pyarrow as pa
import pyarrow.parquet as pq
with open(sys.argv[1], newline="") as stream:
    reader = csv.reader(stream, delimiter="\t")
    names = next(reader)
    rows = list(reader)
assert len(set(names)) == len(names), "duplicate headers require explicit handling"
assert all(len(row) == len(names) for row in rows), "ragged source rows"
columns = {name: pa.array([row[i] for row in rows], type=pa.string()) for i, name in enumerate(names)}
columns["__source_row"] = pa.array(range(2, len(rows) + 2), type=pa.int64())
pq.write_table(pa.table(columns), sys.argv[2], compression="zstd")
