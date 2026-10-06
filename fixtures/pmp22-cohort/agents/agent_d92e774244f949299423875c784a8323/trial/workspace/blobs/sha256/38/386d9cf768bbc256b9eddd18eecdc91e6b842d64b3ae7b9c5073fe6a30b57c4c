"""Inspect only first native fine-mapping schema; do not guess key names."""
import io
from pathlib import Path
import tarfile
import pyarrow.parquet as pq
Q=Path(__file__).resolve().parents[1]
for assay in ['eqtl','sqtl']:
    with tarfile.open(Q/f'inputs/public/v11-{assay}-susie.tar','r:') as tar:
        for m in tar:
            if m.isfile() and m.name.endswith('.parquet'):
                t=pq.read_table(io.BytesIO(tar.extractfile(m).read()))
                print(assay,m.name,t.column_names,t.slice(0,2).to_pylist())
                break
