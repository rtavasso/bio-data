"""Preserve exact acquired and agent-curated inputs in this private object store."""
import hashlib
import json
import os
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'inputs'
paths=[OUT/'curation.json',OUT/'test-design.json',OUT/'prior/REPORT.md',OUT/'prior/mechanisms.r021.json']
paths += sorted((OUT/'public').glob('*.xml'))
paths += sorted((OUT/'public').glob('*.xlsx'))
paths += sorted((OUT/'public').glob('*.pdf'))
paths += [p for p in sorted((OUT/'public').glob('*.json')) if not p.name.endswith('.pretty.json')]
manifest={}
for p in paths:
    category='agent-curated' if p.parent==OUT else 'source'
    result=json.loads(subprocess.run(['./bin/bio','object','add',str(p),'--classification',category],check=True,capture_output=True,text=True).stdout)
    sha=hashlib.sha256(p.read_bytes()).hexdigest()
    assert result['blob']==sha
    manifest[str(p.relative_to(ROOT))]=result
    print(str(p.relative_to(ROOT)),sha)
# Already fetched peer source is immutable in this private workspace, not another agent's file.
peer='9e055a837fe13d3af27cf70b5d1d2cb630028cfcee938535ef019dd0065d6030'
meta=json.loads(subprocess.run(['./bin/bio','object','show',peer],check=True,capture_output=True,text=True).stdout)
assert Path(meta['path']).is_relative_to(Path(os.environ['BIO_WORKSPACE']))
manifest['peer/intervention-by-endpoint.tsv']=meta
(OUT/'immutable-manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False))
