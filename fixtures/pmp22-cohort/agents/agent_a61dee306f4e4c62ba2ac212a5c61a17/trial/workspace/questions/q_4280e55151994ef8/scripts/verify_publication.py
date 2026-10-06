"""Read back the exact publication, completed notebook and shared immutable bundle."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs'


def cli(*args):
    p = subprocess.run(['./bin/bio', *map(str,args)], capture_output=True,text=True,check=True)
    return json.loads(p.stdout)


def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')


published = json.loads((OUT/'publication-receipt.json').read_text())
readback = cli('community','show',published['id'])
save('publication-readback.json',readback)
assert readback['id'] == published['id']
assert readback['content']['body'] == (OUT/'publication.md').read_text()
assert readback['content']['evidence'] == published['content']['evidence']
regs = json.loads((OUT/'registrations.json').read_text())
bundle = json.loads((OUT/'bundle-registration.json').read_text())
expected_artifacts = {x['artifact'] for x in regs.values()} | {bundle['artifact']}
assert set(readback['content']['evidence']['artifacts']) == expected_artifacts
assert readback['author'] == 'agent_a61dee306f4e4c62ba2ac212a5c61a17'
assert readback['parent'] == 'post_85b763ee8b6b4ea6bad88cd7f71b48be'
library = Path(os.environ['BIO_COMMUNITY'])/'library'
shared = cli('--workspace',library,'object','show',bundle['output_blob'])
save('shared-bundle-readback.json',shared)
assert hashlib.sha256(Path(shared['path']).read_bytes()).hexdigest() == bundle['output_blob']
work = cli('work','show','q_4280e55151994ef8')
save('completed-work-readback.json',work)
assert work['status'] == 'completed'
assert work['snapshot']['files']['LABBOOK.md'] == hashlib.sha256((ROOT/'LABBOOK.md').read_bytes()).hexdigest()
validation = {'status':'passed','post':readback['id'],'exact_body':True,'artifact_set':sorted(expected_artifacts),
              'shared_bundle_bytes_verified':True,
              'completed_question':work['id'],'current_notebook_hash_verified':True,
              'publication_notebook':readback['content']['evidence']['notebook'],
              'note':'Published notebook is immutable; current notebook may add the publication link.'}
save('publication-validation.json',validation)
print(json.dumps(validation,indent=2))
