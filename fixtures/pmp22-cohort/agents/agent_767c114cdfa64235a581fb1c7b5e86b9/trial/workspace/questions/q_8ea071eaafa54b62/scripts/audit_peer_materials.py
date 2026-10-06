"""Read exact peer artifacts and their derivations; never execute imported code."""
import json
import csv
import io
from pathlib import Path
import subprocess
import sys
q=Path(__file__).resolve().parents[1]
out=q/'inputs/community-reuse'
out.mkdir(exist_ok=True)
ids=sys.argv[1:] or ['artifact_0ad2e6fbf524635e89a43ac014998f9e8664b449e102c1b47eb5322fe5145fda','artifact_1dc56cde62ec0f2c595bb2ccdb71d1259b3c4dec85cda82a2ec057ab5761b9b7']
for aid in ids:
    p=subprocess.run(['./bin/bio','artifact','show',aid],capture_output=True,text=True)
    p.check_returncode()
    obj=json.loads(p.stdout)
    (out/(aid+'.manifest.json')).write_text(json.dumps(obj,indent=2))
    data=Path(obj['path']).read_text()
    (out/(aid+'.txt')).write_text(data)
    print('ARTIFACT',aid,'PATH',obj['path'],'PRODUCER',obj['manifest']['derivation']['code'],'INPUT_COUNT',len(obj['manifest']['derivation']['inputs']))
    if len(data)<20000:
        print(data)
    elif not data.lstrip().startswith(('{','[')):
        rows=list(csv.DictReader(io.StringIO(data),delimiter='\t'))
        print('TSV_ROWS',len(rows),'COLUMNS',list(rows[0]))
        if 'gene_requested' in rows[0]:
            for study in sorted({r['dataset'] for r in rows}):
                for gene in sorted({r['gene_requested'] for r in rows}):
                    group=[r for r in rows if r['dataset']==study and r['gene_requested']==gene]
                    measured=[r for r in group if r['status']=='measured']
                    vals=[float(r['cpm']) for r in measured]
                    print('COVERAGE',study,gene,'n_measured',len(measured),'n_rows',len(group),'cpm_range',(min(vals),max(vals)) if vals else None)
    else:
        x=json.loads(data)
        print('TOP KEYS',list(x))
        for k,v in x.items():
            if len(json.dumps(v))<8000:
                print(k,json.dumps(v))
