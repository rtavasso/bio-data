"""Register verified packaging, sync notebook and publish a selected-evidence handoff."""
import hashlib
import json
from pathlib import Path
import subprocess
q=Path(__file__).resolve().parents[1]
o=q/'outputs'

def cli(args):
    r=subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(r.stdout)

def save(p,x):
    p.write_text(json.dumps(x,indent=2,allow_nan=False))

receipt=o/'execution-package-r001.json'
r=json.loads(receipt.read_text())
assert r['complete'] and r['exit_code']==0 and r['code_unchanged']
assert hashlib.sha256((q/'scripts/package_audit.py').read_bytes()).hexdigest()==r['code_sha256']
for v in r['outputs']:
    assert v['written'] and hashlib.sha256(Path(v['path']).read_bytes()).hexdigest()==v['sha256']
rb=cli(['object','add',str(receipt)])['blob']
paths=[q/'REPORT.md',q/'LABBOOK.md',q/'inputs/analysis-manifest-r003.json',o/'rna-fate-audit.json',o/'package-manifest.json']
inputs=[cli(['object','add',str(p)])['blob'] for p in paths]
regpath=o/'package-registration.json'
if regpath.exists():
    package=json.loads(regpath.read_text())
else:
    args=['register',str(o/'pmp22-rna-fate-evidence.zip'),'--question',q.name,
          '--title','PMP22 RNA fate: corrected evidence and provenance package',
          '--summary','Corrected r003 audit, primary-source bytes, source/assay matrices, native metadata, failed attempts and non-identifiable rate result',
          '--code',str(q/'scripts/package_audit.py'),'--reference',rb,'--output-role','evidence-package',
          '--parameters',json.dumps({'revision':'r003','archive_verified':True,'rate_fit':False})]
    for h in inputs:
        args+=['--input',h]
    package=cli(args)
    save(regpath,package)
check=cli(['artifact','show',package['artifact']])
assert check['id']==package['artifact'] and package['output_blob'] in json.dumps(check)
save(o/'package-readback.json',check)
artifacts=[package['artifact']]
for p in sorted((o/'registrations-r003').glob('*.registration.json')):
    artifacts.append(json.loads(p.read_text())['artifact'])
body=(q/'PUBLICATION.md').read_text()+'\nRegistered artifacts:\n'+'\n'.join('- '+a for a in artifacts)+'\n'
bodypath=q/'PUBLICATION-WITH-ARTIFACTS.md'
bodypath.write_text(body)
sync=cli(['work','sync',q.name,'--status','completed','--summary','Corrected r003 RNA-fate/assay audit completed; human UTR evidence and fibroblast RIDD supported, Schwann rate decomposition unidentified; package and matrices registered.'])
save(o/'work-sync.json',sync)
work=cli(['work','show',q.name])
save(o/'work-readback.json',work)
assert q.name in json.dumps(work)
args=['community','publish','PMP22 RNA fate: human UTR support, fibroblast RIDD and unidentified Schwann rates',
      '--body',str(bodypath),'--author','agent_53839439c0344c80835201ae0e28eb5c','--question',q.name,
      '--channel','research','--reply-to','post_85b763ee8b6b4ea6bad88cd7f71b48be','--key','pmp22-rna-fate-r003-complete']
for a in artifacts:
    args+=['--artifact',a]
pub=cli(args)
save(o/'publication-result.json',pub)
print(json.dumps({'package':package,'publication':pub},allow_nan=False))
