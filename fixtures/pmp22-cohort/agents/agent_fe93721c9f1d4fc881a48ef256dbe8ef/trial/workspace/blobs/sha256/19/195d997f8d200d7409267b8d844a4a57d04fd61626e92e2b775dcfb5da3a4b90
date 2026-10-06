import csv
import json
from pathlib import Path

q = Path(__file__).resolve().parents[1]
w = q.parents[1]
source = w / 'blobs/sha256/b3/b3d15fe88a6a680290cb57a382ac93c9f5451966d5d20b58bfa2994b0ddcb580'
found = []
with source.open() as f:
    for source_row, row in enumerate(csv.DictReader(f, delimiter='\t'), 2):
        for col in ['LentiAS-1', 'LentiAS-2', 'LentiGFP-1', 'LentiGFP-2']:
            if not row[col].isdecimal():
                found.append({'source_row': source_row, 'gene': row['#Geneid'], 'column': col, 'token': row[col]})
print(json.dumps(found, indent=2))
(q / 'outputs/nondecimal-count-tokens.json').write_text(json.dumps(found, indent=2, allow_nan=False) + '\n')
