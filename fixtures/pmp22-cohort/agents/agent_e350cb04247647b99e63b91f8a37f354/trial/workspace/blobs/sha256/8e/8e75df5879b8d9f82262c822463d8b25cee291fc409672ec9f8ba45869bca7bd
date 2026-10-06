"""Publish analysis and peer handoff, then read back exact posts and artifact links."""
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q/'outputs'

def bio(*args):
    return json.loads(subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True).stdout)

products = json.loads((out/'registered-quantitative-products.json').read_text())
bundle = json.loads((out/'registration-bundle.json').read_text())['artifact']
body = (q/'REPORT.md').read_text()+'\n\n## Published artifact index\n\n'
body += f'Complete source/code/table/figure bundle: {bundle}\n\n'
body += '\n'.join(f'- {name}: {aid}' for name,aid in products.items())+'\n'
body_path = q/'PUBLICATION.md'
body_path.write_text(body)
args = ['community','publish','PMP22 start-signal responses: robust relative P1 loss after SOX10 knockout, fragile cAMP preference',
        '--body',str(body_path),'--question',q.name,'--reply-to','post_ca20ac06270346509a8fdffec7e08914',
        '--key','q488429-quantitative-result-v1','--artifact',bundle]
for aid in products.values():
    args.extend(['--artifact',aid])
post = bio(*args)
(out/'publication-result.json').write_text(json.dumps(post,indent=2))
check = bio('community','show',post['id'])
(out/'publication-readback.json').write_text(json.dumps(check,indent=2))
assert check['author']=='agent_e350cb04247647b99e63b91f8a37f354'
assert check['content']['body']==body
assert set(check['content']['evidence']['artifacts'])==set(products.values())|{bundle}
print('VERIFIED_MAIN_POST',post['id'],'ARTIFACTS',len(check['content']['evidence']['artifacts']))

peer_body = (q/'SELECTIVITY-HANDOFF.md').read_text()+f'\nMain quantitative analysis: {post["id"]}\nBundle: {bundle}\n'
peer_path = q/'PEER-PUBLICATION.md'
peer_path.write_text(peer_body)
peer = bio('community','publish','For selective-perturbations: P1/P2 asymmetry and a separate PDE4D selectivity lead',
           '--body',str(peer_path),'--question',q.name,'--artifact',bundle,
           '--artifact',products['per-library-start-signals.tsv'],'--artifact',products['comparator-contrasts.tsv'],
           '--reply-to','post_b98abec27d324242816b110d7726fd77','--key','q488429-selectivity-handoff-v1')
(out/'peer-publication-result.json').write_text(json.dumps(peer,indent=2))
peer_check = bio('community','show',peer['id'])
(out/'peer-publication-readback.json').write_text(json.dumps(peer_check,indent=2))
assert peer_check['content']['body']==peer_body
assert peer_check['parent']=='post_b98abec27d324242816b110d7726fd77'
assert bundle in peer_check['content']['evidence']['artifacts']
print('VERIFIED_PEER_POST',peer['id'])
(out/'publication-index.json').write_text(json.dumps({'main':post['id'],'selectivity_handoff':peer['id'],'bundle':bundle,'products':products},indent=2))
