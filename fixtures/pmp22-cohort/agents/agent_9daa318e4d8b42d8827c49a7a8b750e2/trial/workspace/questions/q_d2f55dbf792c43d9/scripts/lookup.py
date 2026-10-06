import json, sys
import pyarrow.compute as pc
import pyarrow.parquet as pq
table = pq.read_table(sys.argv[1])
feature = sys.argv[3]
rows = table.filter(pc.equal(table["#Geneid"], feature)).to_pylist()
result = {"feature": feature, "rows": rows, "semantics": "literal source cell strings; no normalization",
          "absence_policy": "empty lookup is unresolved, never a null biological effect"}
with open(sys.argv[2], "w") as stream:
    json.dump(result, stream, sort_keys=True)
