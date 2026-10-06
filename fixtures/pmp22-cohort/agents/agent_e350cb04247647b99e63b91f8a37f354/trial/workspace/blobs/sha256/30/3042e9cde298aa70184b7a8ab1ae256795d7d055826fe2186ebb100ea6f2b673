import json, os, subprocess
from pathlib import Path
P=Path(__file__).resolve().parents[1]
publication=json.loads((P/'outputs/publication.json').read_text())
post=publication['id']
r=subprocess.run(['./bin/bio','community','show',post],capture_output=True,text=True,check=True)
(P/'outputs/publication-readback.json').write_text(r.stdout)
d=json.loads(r.stdout)
assert d['content']['body']==(P/'REPORT.md').read_text()
print('PUBLICATION',post)
print('EVIDENCE',json.dumps(d['content'].get('evidence'),indent=2))
work=json.loads((P/'outputs/work-completed-readback.json').read_text())
print('WORK_METADATA',json.dumps({k:v for k,v in work.items() if k not in ['events','notes','artifacts','files','labbook','body','notebook']},indent=2)[:8000])
main=json.loads((P/'outputs/registration-main.json').read_text())
r=subprocess.run(['./bin/bio','--workspace',os.environ['BIO_COMMUNITY']+'/library','artifact','show',main['artifact']],capture_output=True,text=True,check=True)
(P/'outputs/shared-artifact-readback.json').write_text(r.stdout)
assert json.loads(r.stdout)['output_blob']==main['output_blob']
print('SHARED_ARTIFACT_VERIFIED',main['artifact'],main['output_blob'])
