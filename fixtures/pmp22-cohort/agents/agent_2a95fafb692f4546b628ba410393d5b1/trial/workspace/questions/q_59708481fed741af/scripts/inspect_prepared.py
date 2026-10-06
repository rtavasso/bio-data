import json
from pathlib import Path
import pyarrow.parquet as pq

q = Path(__file__).resolve().parents[1]
table = pq.read_table(q / 'outputs' / 'egr2as-original-strings')
print(table.schema)
print(json.dumps(table.slice(0, 3).to_pylist(), indent=2))
