"""Inspect selected fetched native files using verified blob resolution."""
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
for receiptname in sys.argv[1:]:
    fetch=json.loads((ROOT/'outputs'/receiptname).read_text())
    blob=fetch['blob']
    meta=json.loads(subprocess.run(['./bin/bio','object','show',blob],capture_output=True,text=True,check=True).stdout)
    p=Path(meta['path'])
    assert hashlib.sha256(p.read_bytes()).hexdigest()==blob
    dest=ROOT/'inputs'/'sources'/(receiptname.removeprefix('fetch-').removesuffix('.json'))
    if not dest.exists():
        shutil.copyfile(p,dest)
    assert hashlib.sha256(dest.read_bytes()).hexdigest()==blob
    if p.read_bytes()[:2]==b'PK':
        wb=openpyxl.load_workbook(p,read_only=True,data_only=False) if p.suffix=='.xlsx' else openpyxl.load_workbook(p.open('rb'),read_only=True,data_only=False)
        view={}
        for ws in wb:
            rows=[]
            for i,row in enumerate(ws.iter_rows(values_only=True)):
                if i==5:
                    break
                rows.append(row)
            view[ws.title]={'rows':ws.max_row,'cols':ws.max_column,'first_rows':rows}
    else:
        with gzip.open(p,'rt') if p.read_bytes()[:2]==b'\x1f\x8b' else p.open() as f:
            rows=[next(f) for _ in range(4)]
        view={'first_rows':rows}
    out={'receipt':receiptname,'blob':blob,'path':str(dest),'inspection':view,'pandas':pd.__version__}
    (ROOT/'outputs'/(receiptname+'.inspection.json')).write_text(json.dumps(out,indent=2,default=str)+'\n')
    print(json.dumps(out,indent=2,default=str)[:15000])
