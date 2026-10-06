"""Inspect source schemas and extract literal static documentation; no JS execution."""
import csv
import io
import json
from html import unescape
from pathlib import Path
import re
import tarfile
import pyarrow.parquet as pq
Q=Path(__file__).resolve().parents[1]
with tarfile.open(Q/'inputs/public/v11-eqtl-susie.tar','r:') as t:
    for m in t:
        if m.isfile() and 'fibro' in m.name:
            table=pq.read_table(io.BytesIO(t.extractfile(m).read()))
            print('SUSIE schema',table.schema)
            print(table.to_pylist()[:2])
            matches=[r for r in table.to_pylist() if any('ENSG00000109099' in str(v) or v=='PMP22' for v in r.values())]
            print('matches',matches)
with (Q/'inputs/public/catalogue-metadata-r7.tsv').open() as f:
    reader=csv.DictReader(f,delimiter='\t')
    print('CATALOGUE columns',reader.fieldnames)
    for r in reader:
        if any(x in str(r) for x in ['GENCORD','TwinsUK']): print(r)
text=(Q/'inputs/public/gtex-app.js').read_text()
segments=[]
for m in re.finditer('Covariates</h5>',text):
    begin=text.rfind('<h',max(0,m.start()-6000),m.start()-1000)
    segment=unescape(text[begin:m.end()+18000])
    segments.append({'source':'gtex-app.js','offset':begin,'text':segment})
(Q/'inputs/text').mkdir(exist_ok=True)
(Q/'inputs/text/gtex-documentation-snippets.json').write_text(json.dumps(segments,indent=2))
for x in segments[:1]:
    print(re.sub('<[^>]+>',' ',x['text']))
