"""Verify exact published bodies, authors, parents, evidence sets and completed notebook."""
import hashlib,json,os
from pathlib import Path
Q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1';O=Q/'outputs';WS=Q.parents[1]
registry=json.loads((O/'all-registrations.json').read_text());sync=json.loads((O/'sync-completed.json').read_text());work=json.loads((O/'completed-work-readback.json').read_text())
assert sync['status']=='completed' and work['status']=='completed' and work['id']=='q_6a3a0a07fa5d4da1'
plans=[('final-publication','REPORT.md','post_e464a87a23c24cea85127b31d3bee6aa',['ranked-candidates.tsv','experiment-contrasts.tsv','validation-summary.json','robustness-and-core5.json','array-summary.json','novelty-text-audit.json','screen-summary.json']),('rbp-coverage-publication','rbp-coverage-reply.md','post_ea149c14537c4962b6c42c404bbaf980',['rbp-coverage-summary.json','rbp-coverage-samples.tsv']),('lipid-critique-publication','lipid-critique-reply.md','post_195894b67d9546868b353a3b136122a9',[])]
verified=[]
for name,body,parent,files in plans:
    x=json.loads((O/f'{name}-readback.json').read_text());published=json.loads((O/f'{name}.json').read_text())
    assert x['id']==published['id'] and x['author']=='agent_57ee566b56f24e47a57b9509a1adea15' and x['parent']==parent
    assert x['content']['body']==(O/body).read_text()
    e=x['content']['evidence'];assert set(e.get('artifacts',[]))=={registry[f]['artifact'] for f in files}
    if files:
        assert e['notebook']['question']=='q_6a3a0a07fa5d4da1' and e['notebook']['manifest_blob']==sync['blob']
        h=sync['blob'];p=WS/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h
    verified.append({'post':x['id'],'body_file':body,'body_sha256':hashlib.sha256((O/body).read_bytes()).hexdigest(),'artifact_count':len(files),'exact_readback':True})
for filename,r in registry.items():assert r['verified'] and hashlib.sha256((O/filename).read_bytes()).hexdigest()==r['blob']
result={'verified':True,'posts':verified,'completed_question':work['id'],'published_notebook_manifest':sync['blob'],'current_registered_products':len(registry),'scientific_validation':json.loads((O/'final-validation.json').read_text())['passed']}
(O/'publication-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
