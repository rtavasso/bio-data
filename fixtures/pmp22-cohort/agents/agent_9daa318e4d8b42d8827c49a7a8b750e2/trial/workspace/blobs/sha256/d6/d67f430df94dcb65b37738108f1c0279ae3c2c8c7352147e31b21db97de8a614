from pathlib import Path
import json,hashlib
Q=Path(__file__).resolve().parents[1];U=Q/'outputs/upstream'
s=json.loads((U/'final-sync-r002.json').read_text());r=json.loads((U/'final-work-readback-r002.json').read_text())
assert r['id']==Q.name
assert r['current_work']=='work_'+s['blob']
assert s['files']['LABBOOK.md']==hashlib.sha256((Q/'LABBOOK.md').read_bytes()).hexdigest()
a=json.loads((U/'final-registration-r002.json').read_text());b=json.loads((U/'final-registration-r002-readback.json').read_text());assert a['artifact']==b['id']
v=json.loads((U/'validation.json').read_text());assert v['checks_passed']==len(v['checks']) and all(c['passed'] for c in v['checks'])
x=json.loads((Q/'outputs/investigations.json').read_text());unfinished=[i['id'] for i in x['items'] if 'high' in str(i.get('priority','')).lower() and i['status'] not in ['analyzed','rejected','blocked']];assert not unfinished,unfinished
print(json.dumps(dict(question=r['id'],current_work=r['current_work'],notebook_hash_verified=True,evidence_package=a['artifact'],checks=v['checks_passed'],high_priority_unexecuted_without_blocker=unfinished),indent=2))
