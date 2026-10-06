"""Fetch only RNF40 processed counts and annotation workbook, with receipts."""
import gzip
import json
import subprocess
from pathlib import Path
import openpyxl
q=Path(__file__).resolve().parents[1]
ws=q.parents[1]
assets=json.loads((q/'outputs/rnf40-geo-assets.json').read_text())['items']
records=[]
for item in assets:
    if not item['name'].endswith(('.txt.gz','.xlsx')):
        continue
    r=subprocess.run(['./bin/bio','fetch',item['asset_revision'],'--question','q_5eaa65194750454d'],capture_output=True,text=True,check=True)
    (q/'outputs'/(item['name']+'-fetch.json')).write_text(r.stdout)
    d=json.loads(r.stdout)
    records.append({'name':item['name'],'receipt':d})
    if not d.get('blob'):
        print('UNAVAILABLE',item['name'],d)
        continue
    p=ws/'blobs/sha256'/d['blob'][:2]/d['blob']
    if item['name'].endswith('.gz'):
        with gzip.open(p,'rt') as f:
            print('NATIVE',item['name'], ''.join(next(f,'') for _ in range(4)))
    else:
        with p.open('rb') as f:
            w=openpyxl.load_workbook(f,read_only=True,data_only=False)
            for sheet in w:
                print('SHEET',sheet.title,sheet.max_row,sheet.max_column)
                for row in sheet.iter_rows(min_row=1,max_row=4,values_only=True):
                    print(repr(row))
(q/'outputs/rnf40-fetches.json').write_text(json.dumps(records,indent=2)+'\n')
