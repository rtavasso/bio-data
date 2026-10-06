"""Verify science-preserving lint fixes; keep old bytes and real new receipts."""
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
runs=[('arsenite-execution-r002.json','arsenite-execution-r003.json'),('isrib-execution-r002.json','isrib-execution-r003.json'),('secondary-audit-execution-r002.json','secondary-audit-execution-r003.json'),('novelty-execution-r001.json','novelty-execution-r002.json'),('design-execution-r004.json','design-execution-r005.json')]
checks=[]
for previous,new in runs:
    old=json.loads((OUT/previous).read_text())
    assert old['complete'] and old['exit_code']==0
    before={}
    command=['./bin/python','.agents/skills/bio-research/scripts/run_analysis.py','--receipt',str(OUT/new)]
    for output in old['outputs']:
        path=Path(output['path'])
        data=path.read_bytes()
        assert hashlib.sha256(data).hexdigest()==output['sha256'],path
        saved=json.loads(subprocess.run(['./bin/bio','object','add',str(path)],text=True,capture_output=True,check=True).stdout)
        assert saved['blob']==output['sha256']
        before[str(path)]=gzip.decompress(data) if path.suffix=='.gz' else data
        command+=['--output',str(path)]
    command+=['--']+old['argv']
    subprocess.run(command,check=True)
    after=json.loads((OUT/new).read_text())
    assert after['complete'] and after['exit_code']==0
    assert hashlib.sha256(Path(after['producer']).read_bytes()).hexdigest()==after['code_sha256']
    for output in after['outputs']:
        path=Path(output['path'])
        data=path.read_bytes()
        assert hashlib.sha256(data).hexdigest()==output['sha256']
        semantic=gzip.decompress(data) if path.suffix=='.gz' else data
        assert semantic==before[str(path)],path
        checks.append({'output':str(path.relative_to(ROOT)),'previous_receipt':previous,'current_receipt':new,'decompressed_or_plain_bytes_identical':True,'sha256':output['sha256']})
report={'purpose':'Regression after output-variable naming, strict zip, and removal of redundant early write; not new biological replication or new-work credit','all_passed':True,'checks':checks}
(OUT/'regression-validation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
print('Verified',len(checks),'outputs unchanged in decompressed/plain content across',len(runs),'producer reruns.')
