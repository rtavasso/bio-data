"""Inspect all acquired sample-table schemas; preserve literal headers."""
import csv
import gzip
import json
import os
from pathlib import Path
q=Path(__file__).resolve().parents[1]
w=Path(os.environ['BIO_WORKSPACE'])
for m in json.loads((q/'inputs/independent/tcam-native-inputs.json').read_text()):
    sha=m['acquisition']['blob']
    with gzip.open(w/'blobs/sha256'/sha[:2]/sha,'rt') as f:
        rows=list(csv.reader(f,delimiter='\t'))
    print(m['name'], 'ROWS',len(rows),'HEADER',rows[0],'EXAMPLE',rows[1], 'PMP22 accession rows', [r for r in rows if r[0] in {'NM_000304','NM_153321'}])
